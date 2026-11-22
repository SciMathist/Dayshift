"""Belief part of the generic oracle: where the oracle thinks each item is.

| Belief | Used by | Knows |
|---|---|---|
| `GroundTruthBelief` | Oracle | Every item's true place |
| `PlacedBelief` | `never_recover` | The true place, except that an item it put down stays where it put it |
| `ObservedBelief(remember=True)` | `hidden_state_blind` | The start layout, then only what the robot saw |
| `ObservedBelief(remember=False)` | `memoryless` | The start layout, plus the current view only |
| `StaleAfterEventBelief` | `stale_after_event` (C1 probe) | Ground truth, except one event's moves until it looks |

Only the place is believed. Type, stages and condition come from the world, so a control
differs from the oracle in one thing.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from dsz.core.scenario import Instance
from dsz.core.types import LocationKind
from dsz.world.state import WorldState


class Belief(Protocol):
    """Where the oracle thinks items are."""

    def observe(self, world: WorldState) -> None:
        """Update from what the robot can perceive now. Called once per decision."""
        ...

    def where(self, item_id: str) -> str | None:
        """Return the fixture the item is believed to be at, or None if unknown or not at a fixture."""
        ...


class GroundTruthBelief:
    """Read every place from the world."""

    def __init__(self, world: WorldState) -> None:
        """Read from `world`."""
        self._world = world

    def observe(self, world: WorldState) -> None:
        """Nothing to update."""

    def where(self, item_id: str) -> str | None:
        """Return the item's true fixture."""
        loc = self._world.item(item_id).location
        return loc.fixture if loc.kind is LocationKind.FIXTURE else None


class PlacedBelief(GroundTruthBelief):
    """Ground truth, but an item the robot put down is believed to stay there (no monitor)."""

    def __init__(self, world: WorldState) -> None:
        """Start with no placements."""
        super().__init__(world)
        self._placed: dict[str, str] = {}
        self._held: str | None = None

    def observe(self, world: WorldState) -> None:
        """Record the item the robot put down since the last decision."""
        held = world.held()
        if self._held and held is None and world.robot_at:
            loc = world.item(self._held).location
            if loc.kind is LocationKind.FIXTURE and loc.fixture == world.robot_at:
                self._placed[self._held] = world.robot_at
        if held is not None:
            self._placed.pop(held.item_id, None)
        self._held = held.item_id if held else None

    def where(self, item_id: str) -> str | None:
        """Return where the robot put the item, else its true fixture."""
        return self._placed.get(item_id) or super().where(item_id)


class StaleAfterEventBelief(GroundTruthBelief):
    """Ground truth, except one event: an item it moves stays where it was until the robot looks.

    This is the C1 (c) probe, "a policy that uses the state before the event". If the robot
    looks at the old place and the item is gone, the item's place becomes unknown.
    """

    def __init__(self, world: WorldState, instance: Instance, event_id: str) -> None:
        """Watch the events in `instance` whose definition id is `event_id`."""
        super().__init__(world)
        self._pending = sorted((e for e in instance.events if e.source == event_id), key=lambda e: e.t)
        self._before = _places(world)
        self._stale: dict[str, str | None] = {}

    def observe(self, world: WorldState) -> None:
        """Mark items the event moved since the last decision; clear them once the robot looks."""
        now = _places(world)
        for event in [e for e in self._pending if e.t <= world.now]:
            moved = [i for i in _named(event.payload, world) if self._before.get(i) and now.get(i)
                     and now[i] != self._before[i]]
            if moved:
                self._stale.update({i: self._before[i] for i in moved})
                self._pending.remove(event)
        here = world.robot_at
        if here and (not world.fixture(here).spec.has_door or world.fixture(here).is_open):
            for iid, believed in list(self._stale.items()):
                if now.get(iid) == here:
                    del self._stale[iid]
                elif believed == here:
                    self._stale[iid] = None
        self._before = now

    def where(self, item_id: str) -> str | None:
        """Return the stale place of an item the event moved, else its true fixture."""
        return self._stale[item_id] if item_id in self._stale else super().where(item_id)


def _places(world: WorldState) -> dict[str, str]:
    """Return item id -> fixture for every item at a fixture."""
    return {i.item_id: i.location.fixture for i in world.in_world() if i.location.kind is LocationKind.FIXTURE}


def _named(payload: Mapping[str, Any], world: WorldState) -> list[str]:
    """Return the ids of the items an event payload names, by id or by type."""
    ids = list(payload.get("items", [])) + ([payload["item"]] if isinstance(payload.get("item"), str) else [])
    if isinstance(payload.get("item_type"), str):
        ids += [i.item_id for i in world.in_world() if i.item_type == payload["item_type"]]
    return ids


class ObservedBelief:
    """Start from the initial layout; then believe only what the robot saw at each fixture."""

    def __init__(self, instance: Instance, remember: bool) -> None:
        """Start from the instance's initial placements. `remember=False` keeps only the current view."""
        self._prior = {i.item_id: i.location.fixture for i in instance.items
                       if i.location.kind is LocationKind.FIXTURE}
        self._seen: dict[str, str] = dict(self._prior)
        self._remember = remember

    def observe(self, world: WorldState) -> None:
        """Record the items visible at the robot's fixture (doors must be open or absent)."""
        if not self._remember:
            self._seen = dict(self._prior)
        held = world.held()
        if held is not None:
            self._seen.pop(held.item_id, None)
        here = world.robot_at
        if not here or (world.fixture(here).spec.has_door and not world.fixture(here).is_open):
            return
        visible = {i.item_id for i in world.items_at(here)}
        for iid in [i for i, f in self._seen.items() if f == here and i not in visible]:
            del self._seen[iid]
        self._seen.update({iid: here for iid in visible})

    def where(self, item_id: str) -> str | None:
        """Return the fixture where the item was last seen, or None."""
        return self._seen.get(item_id)
