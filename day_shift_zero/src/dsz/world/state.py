"""Semantic world state: the evaluator's model of items, fixtures and running processes.

Backend-agnostic. In the symbolic backend it is the whole world. In the RoboCasa backend,
item locations are synced from physics after every skill. All changes go through methods,
so invariants hold (for example, a non-OK condition is irreversible).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from dsz.core.events import DomainEvent, EventBus
from dsz.core.types import Condition, Location, LocationKind, SimMinutes, TempZone
from dsz.world.catalog import FIXTURE_KINDS, ITEM_TYPES, FixtureKind, ItemType


@dataclass(slots=True)
class Item:
    """One physical item and its semantic state."""

    item_id: str
    item_type: str
    location: Location
    batch: str | None = None
    created_at: SimMinutes = 0
    stages: set[str] = field(default_factory=set)
    condition: Condition = Condition.OK
    spoilage: float = 0.0  # 0 fresh .. 1 spoiled, accumulated against the zone's shelf life
    extra_allergens: set[str] = field(default_factory=set)  # inherited when combined
    components: tuple[str, ...] = ()

    @property
    def type(self) -> ItemType:
        """Return the catalog entry for this item's type."""
        return ITEM_TYPES.get(self.item_type)

    @property
    def allergens(self) -> frozenset[str]:
        """Return the type's allergens plus any inherited from combined inputs."""
        return self.type.allergens | frozenset(self.extra_allergens)


@dataclass(slots=True)
class Fixture:
    """One fixture instance and its mutable state."""

    fixture_id: str
    kind: str
    is_open: bool = False
    powered_on: bool = False
    health: float = 1.0  # 1 healthy .. 0 failed; drift modules degrade it; only indirectly sensed

    @property
    def spec(self) -> FixtureKind:
        """Return the catalog entry for this fixture's kind."""
        return FIXTURE_KINDS.get(self.kind)

    def effective_zone(self) -> TempZone:
        """Return the zone the fixture really provides, given power and health."""
        spec = self.spec
        if spec.powered and not self.powered_on:
            return TempZone.AMBIENT
        if spec.zone in (TempZone.CHILLED, TempZone.FROZEN) and self.health < 0.5:
            return TempZone.AMBIENT  # failing cold storage
        return spec.zone


@dataclass(slots=True)
class ActiveProcess:
    """A process that the robot started and that has not yet been resolved."""

    process: str
    fixture_id: str
    item_ids: tuple[str, ...]
    started_at: SimMinutes
    done_at: SimMinutes
    completed: bool = False


class WorldState:
    """Items, fixtures and processes, with invariant-preserving changes that publish events."""

    def __init__(self, bus: EventBus) -> None:
        """Create an empty world that publishes changes on `bus`."""
        self._bus = bus
        self.items: dict[str, Item] = {}
        self.fixtures: dict[str, Fixture] = {}
        self.processes: list[ActiveProcess] = []
        self.now: SimMinutes = 0
        self.robot_at: str | None = None  # fixture whose approach pose the robot occupies

    # ---- construction -------------------------------------------------------------------
    def add_fixture(self, fixture_id: str, kind: str) -> Fixture:
        """Add a fixture of a registered `kind`. Raise KeyError on an unknown kind or duplicate id."""
        FIXTURE_KINDS.get(kind)
        if fixture_id in self.fixtures:
            raise KeyError(f"fixture '{fixture_id}' exists")
        fx = Fixture(fixture_id, kind)
        self.fixtures[fixture_id] = fx
        return fx

    def add_item(self, item_id: str, item_type: str, location: Location, batch: str | None = None) -> Item:
        """Add an item of a registered type. Raise KeyError on an unknown type, fixture or duplicate id."""
        ITEM_TYPES.get(item_type)
        if item_id in self.items:
            raise KeyError(f"item '{item_id}' exists")
        self._check_location(location)
        it = Item(item_id, item_type, location, batch=batch, created_at=self.now)
        self.items[item_id] = it
        return it

    # ---- queries ------------------------------------------------------------------------
    def item(self, item_id: str) -> Item:
        """Return the item with `item_id`."""
        return self.items[item_id]

    def fixture(self, fixture_id: str) -> Fixture:
        """Return the fixture with `fixture_id`."""
        return self.fixtures[fixture_id]

    def items_at(self, fixture_id: str) -> list[Item]:
        """Return the items in or on `fixture_id`."""
        return [i for i in self.items.values()
                if i.location.kind is LocationKind.FIXTURE and i.location.fixture == fixture_id]

    def in_world(self) -> Iterator[Item]:
        """Iterate over items physically present in the kitchen."""
        return (i for i in self.items.values() if i.location.in_world)

    def held(self) -> Item | None:
        """Return the item in the gripper, if any."""
        return next((i for i in self.items.values() if i.location.kind is LocationKind.HELD), None)

    def zone_of(self, item: Item) -> TempZone:
        """Return the temperature zone the item is in now."""
        if item.location.kind is LocationKind.FIXTURE and item.location.fixture:
            return self.fixtures[item.location.fixture].effective_zone()
        return TempZone.AMBIENT

    def fixtures_of_kind(self, kind: str) -> list[Fixture]:
        """Return all fixtures of `kind`."""
        return [f for f in self.fixtures.values() if f.kind == kind]

    def items_of_type(self, item_type: str, kind: LocationKind | None = None) -> list[Item]:
        """Return items of `item_type`, optionally only those with location kind `kind`, sorted by id."""
        out = [i for i in self.items.values()
               if i.item_type == item_type and (kind is None or i.location.kind is kind)]
        return sorted(out, key=lambda i: i.item_id)

    # ---- changes ------------------------------------------------------------------------
    def move(self, item_id: str, to: Location, cause: str) -> None:
        """Move an item and publish `item.moved`.

        Raises:
            KeyError: unknown fixture in `to`.
            ValueError: the gripper already holds another item, or the target fixture is full.
        """
        self._check_location(to)
        it = self.items[item_id]
        if to.kind is LocationKind.HELD:
            h = self.held()
            if h is not None and h.item_id != item_id:
                raise ValueError(f"gripper already holds '{h.item_id}'")
        if to.kind is LocationKind.FIXTURE and to.fixture:
            cap = self.fixtures[to.fixture].spec.capacity
            if cap is not None and it.location.fixture != to.fixture and len(self.items_at(to.fixture)) >= cap:
                raise ValueError(f"fixture '{to.fixture}' is full")
        src = it.location
        it.location = to
        self._bus.publish(DomainEvent(self.now, "item.moved",
                                      {"item": item_id, "from": _loc(src), "to": _loc(to), "cause": cause}))

    def degrade(self, item_id: str, condition: Condition, cause: str) -> None:
        """Set a non-OK condition once and publish it. Later calls on a non-OK item do nothing.

        Raises:
            ValueError: if `condition` is OK (conditions are irreversible).
        """
        if condition is Condition.OK:
            raise ValueError("cannot restore an item to OK")
        it = self.items[item_id]
        if it.condition is not Condition.OK:
            return
        it.condition = condition
        self._bus.publish(DomainEvent(self.now, f"item.{condition.value}", {"item": item_id, "cause": cause}))

    def add_stage(self, item_id: str, stage: str) -> None:
        """Mark that the item has completed a process stage."""
        self.items[item_id].stages.add(stage)

    def combine(self, product_id: str, product_type: str, inputs: Iterable[str], at: Location, stage: str) -> Item:
        """Consume `inputs` into a new product at `at`. The product inherits allergens and any bad condition."""
        inputs = tuple(inputs)
        allergens: set[str] = set()
        worst = Condition.OK
        for iid in inputs:
            src = self.items[iid]
            allergens |= set(src.allergens)
            if src.condition is not Condition.OK:
                worst = src.condition
            src.location = Location.discarded()
        prod = self.add_item(product_id, product_type, at)
        prod.extra_allergens = allergens
        prod.components = inputs
        prod.stages.add(stage)
        if worst is not Condition.OK:
            prod.condition = worst  # a bad input taints the product
        self._bus.publish(DomainEvent(self.now, "item.combined", {"product": product_id, "inputs": list(inputs)}))
        return prod

    def _check_location(self, loc: Location) -> None:
        """Raise KeyError if `loc` names an unknown fixture."""
        if loc.kind is LocationKind.FIXTURE and loc.fixture not in self.fixtures:
            raise KeyError(f"unknown fixture '{loc.fixture}'")


def _loc(loc: Location) -> str:
    """Format a location for event payloads, e.g. 'fridge/shelf_1' or 'held'."""
    if loc.kind is LocationKind.FIXTURE:
        return f"{loc.fixture}/{loc.slot}" if loc.slot else str(loc.fixture)
    return loc.kind.value
