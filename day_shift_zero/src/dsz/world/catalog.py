"""Catalog types: what kinds of fixtures, items and processes exist. Pure data plus registries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from dsz.core.registry import Registry
from dsz.core.types import Condition, SimMinutes, TempZone


@dataclass(frozen=True, slots=True)
class FixtureKind:
    """A kind of fixture: its temperature zone, door, power, capacity and backend mapping."""

    name: str
    zone: TempZone = TempZone.AMBIENT  # zone when working (and powered, if powered)
    has_door: bool = False
    powered: bool = False  # zone applies only while switched on (oven, stove)
    container: bool = True  # items can be placed in or on it
    capacity: int | None = None
    sim_type: str | None = None  # backend mapping hint, e.g. RoboCasa FixtureType name


@dataclass(frozen=True, slots=True)
class ItemType:
    """A kind of item: backend asset, tags, allergens and shelf life per zone."""

    name: str
    asset: str  # backend asset group (RoboCasa obj_group) or proxy name
    tags: frozenset[str] = frozenset()  # e.g. {"perishable", "fragile", "ingredient", "container"}
    allergens: frozenset[str] = frozenset()
    shelf_life: Mapping[TempZone, SimMinutes | None] = field(default_factory=dict)
    # minutes until spoiled in each zone; missing or None means it does not spoil in that zone

    @property
    def fragile(self) -> bool:
        """Return True if a drop damages the item."""
        return "fragile" in self.tags

    @property
    def perishable(self) -> bool:
        """Return True if the item spoils in at least one zone."""
        return any(v is not None for v in self.shelf_life.values())


@dataclass(frozen=True, slots=True)
class ProcessSpec:
    """A semantic process. RoboCasa cooking is flag-based, so doneness lives here.

    The robot puts the inputs in an allowed fixture and calls `start_process`. The process
    completes after `duration` if the inputs stay put. Leaving them longer than
    `overrun_tolerance` past completion applies `overrun_effect`.
    """

    name: str
    fixture_kinds: frozenset[str]
    duration: SimMinutes
    adds_stage: str
    requires_stages: frozenset[str] = frozenset()
    requires_power: bool = False
    overrun_tolerance: SimMinutes | None = None
    overrun_effect: Condition | None = None
    combines: bool = False  # True: consumes all inputs into one product (e.g. assemble)
    product_type: str | None = None  # item type of the product when combines=True


FIXTURE_KINDS: Registry[FixtureKind] = Registry("fixture kind")
ITEM_TYPES: Registry[ItemType] = Registry("item type")
PROCESSES: Registry[ProcessSpec] = Registry("process")
