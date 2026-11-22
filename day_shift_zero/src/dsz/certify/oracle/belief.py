"""Belief part of the generic oracle: where the oracle thinks each item is.

| Belief | Used by | Knows |
|---|---|---|
| `GroundTruthBelief` | Oracle | Every item's true place |
| `PlacedBelief` | `never_recover` | The true place, except that an item it put down stays where it put it |
| `ObservedBelief(remember=True)` | `hidden_state_blind` | The start layout, then only what the robot saw |
| `ObservedBelief(remember=False)` | `memoryless` | The start layout, plus the current view only |

Only the place is believed. Type, stages and condition come from the world, so a control
differs from the oracle in one thing.
"""

from __future__ import annotations

from typing import Protocol

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
