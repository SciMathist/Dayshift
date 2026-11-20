"""Default kitchen vocabulary. Scenarios compose from these entries; plugins may register more.

Shelf lives and durations are world-model defaults chosen for plausibility. They are not
calibrated benchmark thresholds. Assets were checked against RoboCasa in spike run 2.
Items tagged `proxy` reuse a stand-in asset.
"""

from __future__ import annotations

from dsz.core.types import Condition, TempZone
from dsz.world.catalog import FIXTURE_KINDS, ITEM_TYPES, PROCESSES, FixtureKind, ItemType, ProcessSpec

H = 60
D = 24 * H
A, C, F = TempZone.AMBIENT, TempZone.CHILLED, TempZone.FROZEN


def _fixtures() -> list[FixtureKind]:
    """Return the default fixture kinds."""
    return [
        FixtureKind("fridge", zone=C, has_door=True, capacity=24, sim_type="FRIDGE"),
        FixtureKind("freezer", zone=F, has_door=True, capacity=16, sim_type="FRIDGE"),
        FixtureKind("cabinet", has_door=True, capacity=12, sim_type="CABINET"),
        FixtureKind("drawer", has_door=True, capacity=8, sim_type="DRAWER"),
        FixtureKind("counter", capacity=10, sim_type="COUNTER"),
        FixtureKind("oven", zone=TempZone.HOT, has_door=True, powered=True, capacity=4, sim_type="OVEN"),
        FixtureKind("stove", zone=TempZone.HOT, powered=True, capacity=4, sim_type="STOVE"),
        FixtureKind("microwave", zone=TempZone.HOT, has_door=True, powered=True, capacity=1, sim_type="MICROWAVE"),
        FixtureKind("stand_mixer", powered=True, capacity=1, sim_type="STAND_MIXER"),
        FixtureKind("sink", capacity=6, sim_type="SINK"),
        FixtureKind("dishwasher", has_door=True, capacity=12, sim_type="DISHWASHER"),
        FixtureKind("trash", capacity=None, sim_type=None),
        FixtureKind("delivery_shelf", capacity=10, sim_type="COUNTER"),  # inbound supplies land here
        FixtureKind("dispatch_shelf", capacity=10, sim_type="COUNTER"),  # couriers collect outbound orders here
    ]


def _item(name: str, asset: str, tags: set[str], allergens: set[str], life: dict) -> ItemType:
    """Build an ItemType from plain sets (keeps the table below short)."""
    return ItemType(name, asset, frozenset(tags), frozenset(allergens), life)


def _items() -> list[ItemType]:
    """Return the default item types."""
    egg_life = {A: 2 * D, C: 21 * D, F: None}
    dairy = {A: 6 * H, C: 7 * D, F: 60 * D}
    raw_meat = {A: 2 * H, C: 2 * D, F: 90 * D}
    baked = {A: 2 * D, C: 5 * D, F: 60 * D}
    ing, per, fra = "ingredient", "perishable", "fragile"
    return [
        _item("egg", "egg", {ing, per, fra}, {"egg"}, egg_life),
        _item("butter", "butter_stick", {ing, per}, {"dairy"}, dairy),
        _item("milk", "milk", {ing, per}, {"dairy"}, dairy),
        _item("cream_cheese", "cream_cheese_stick", {ing, per}, {"dairy"}, dairy),
        _item("chicken_breast", "chicken_breast", {ing, per}, set(), raw_meat),
        _item("steak", "steak", {ing, per}, set(), raw_meat),
        _item("bread", "bread", {ing, per}, {"gluten"}, {A: 4 * D, C: 7 * D, F: 90 * D}),
        _item("cheese", "cheese", {ing, per}, {"dairy"}, {A: 1 * D, C: 21 * D, F: None}),
        _item("nut_spread", "jar", {ing, "proxy"}, {"nuts"}, {}),
        _item("cake_tier", "cake", {"product", per, fra}, {"gluten", "egg", "dairy"}, baked),
        _item("cupcake", "cupcake", {"product", per, fra}, {"gluten", "egg", "dairy"}, baked),
        _item("sugar_flower", "cupcake", {"product", fra, "proxy"}, set(), {A: 30 * D, C: 3 * D, F: None}),
        _item("meal_box", "tupperware", {"container", "product"}, set(), {}),
        _item("plate", "plate", {"container"}, set(), {}),
        _item("tray", "tray", {"container"}, set(), {}),
        _item("oven_tray", "oven_tray", {"container"}, set(), {}),
    ]


def _processes() -> list[ProcessSpec]:
    """Return the default processes."""
    damaged = Condition.DAMAGED
    return [
        ProcessSpec("bake", frozenset({"oven"}), 40, "baked", requires_power=True,
                    overrun_tolerance=15, overrun_effect=damaged),
        ProcessSpec("cook", frozenset({"stove", "oven"}), 20, "cooked", requires_power=True,
                    overrun_tolerance=10, overrun_effect=damaged),
        ProcessSpec("reheat", frozenset({"microwave"}), 3, "hot", requires_stages=frozenset({"cooked"}),
                    requires_power=True, overrun_tolerance=5, overrun_effect=damaged),
        ProcessSpec("cool", frozenset({"counter"}), 60, "cooled", requires_stages=frozenset({"baked"})),
        ProcessSpec("chill", frozenset({"fridge"}), 4 * H, "chilled"),
        ProcessSpec("freeze", frozenset({"freezer"}), 6 * H, "frozen"),
        ProcessSpec("thaw", frozenset({"fridge"}), 12 * H, "thawed", requires_stages=frozenset({"frozen"})),
        ProcessSpec("marinate", frozenset({"fridge"}), 8 * H, "marinated"),
        ProcessSpec("mix", frozenset({"stand_mixer"}), 10, "mixed", requires_power=True),
        ProcessSpec("frost", frozenset({"counter"}), 30, "frosted", requires_stages=frozenset({"cooled", "chilled"})),
        ProcessSpec("dry", frozenset({"cabinet"}), 1 * D, "dried"),
        ProcessSpec("assemble", frozenset({"counter"}), 45, "assembled", combines=True, product_type="cake_tier"),
        ProcessSpec("pack", frozenset({"counter"}), 5, "packed", combines=True, product_type="meal_box"),
    ]


def register_default_vocabulary() -> None:
    """Register the default vocabulary. Idempotent, so any composition root or test may call it."""
    for fk in _fixtures():
        if fk.name not in FIXTURE_KINDS:
            FIXTURE_KINDS.add(fk.name, fk)
    for it in _items():
        if it.name not in ITEM_TYPES:
            ITEM_TYPES.add(it.name, it)
    for p in _processes():
        if p.name not in PROCESSES:
            PROCESSES.add(p.name, p)
