"""Tests for dsz.world: clock, fixtures, world state changes, vocabulary and manifest."""

import pytest

from dsz.core.registry import Registry
from dsz.core.types import CapabilitySet, Condition, Location, TempZone
from dsz.world.catalog import FIXTURE_KINDS, ITEM_TYPES, PROCESSES
from dsz.world.clock import SimClock
from dsz.world.manifest import ManifestSources, MissingCapabilities, build_manifest, check_requirements


def test_clock_moves_forward_only():
    """The clock reports day and time of day, and refuses to go back."""
    c = SimClock()
    c.advance(25 * 60 + 30)
    assert (c.day, c.minute_of_day, c.stamp()) == (1, 90, "day 2 01:30")
    with pytest.raises(ValueError):
        c.advance_to(10)


def test_zones_follow_power_and_health(world):
    """Powered fixtures are ambient when off; failing cold storage becomes ambient."""
    assert world.fixture("fridge").effective_zone() is TempZone.CHILLED
    assert world.fixture("oven").effective_zone() is TempZone.AMBIENT  # off
    world.fixture("oven").powered_on = True
    assert world.fixture("oven").effective_zone() is TempZone.HOT
    world.fixture("fridge").health = 0.3
    assert world.fixture("fridge").effective_zone() is TempZone.AMBIENT


def test_move_publishes_and_enforces_single_grasp(world, bus):
    """Moves publish item.moved, and the gripper holds one item at a time."""
    world.add_item("egg_1", "egg", Location.at("counter"))
    world.add_item("milk_1", "milk", Location.at("counter"))
    world.move("egg_1", Location.held(), cause="skill.pick")
    assert world.held().item_id == "egg_1"
    with pytest.raises(ValueError, match="already holds"):
        world.move("milk_1", Location.held(), cause="skill.pick")
    assert bus.events[-1].kind == "item.moved" and bus.events[-1].data["to"] == "held"


def test_capacity_enforced(world):
    """A full fixture rejects another item."""
    cap = FIXTURE_KINDS.get("fridge").capacity
    for i in range(cap):
        world.add_item(f"m{i}", "milk", Location.at("fridge"))
    world.add_item("extra", "milk", Location.at("counter"))
    with pytest.raises(ValueError, match="full"):
        world.move("extra", Location.at("fridge"), cause="test")


def test_degrade_is_irreversible(world, bus):
    """The first non-OK condition sticks and is published once."""
    world.add_item("egg_1", "egg", Location.at("counter"))
    world.degrade("egg_1", Condition.DAMAGED, cause="dropped")
    world.degrade("egg_1", Condition.SPOILED, cause="time")  # no-op: already not OK
    assert world.item("egg_1").condition is Condition.DAMAGED
    assert [e.kind for e in bus.events] == ["item.damaged"]
    with pytest.raises(ValueError):
        world.degrade("egg_1", Condition.OK, cause="magic")


def test_combine_inherits_allergens_and_taint(world):
    """A combined product inherits allergens and a bad input condition."""
    world.add_item("tier", "cake_tier", Location.at("counter"))
    world.add_item("spread", "nut_spread", Location.at("counter"))
    world.degrade("spread", Condition.SPOILED, cause="test")
    prod = world.combine("cake", "cake_tier", ["tier", "spread"], Location.at("counter"), "assembled")
    assert "nuts" in prod.allergens and "egg" in prod.allergens
    assert prod.condition is Condition.SPOILED
    assert not world.item("tier").location.in_world


def test_unknown_fixture_or_type_rejected(world):
    """Unknown fixtures and item types raise KeyError."""
    with pytest.raises(KeyError):
        world.add_item("x", "egg", Location.at("blast_chiller"))
    with pytest.raises(KeyError):
        world.add_item("y", "unobtainium", Location.at("counter"))


def test_default_vocabulary_covers_both_reference_scenarios():
    """The default vocabulary has what cloud kitchen and wedding cake need."""
    for name in ["egg", "butter", "milk", "chicken_breast", "cake_tier", "sugar_flower", "meal_box", "nut_spread"]:
        assert name in ITEM_TYPES
    for name in ["bake", "cool", "chill", "freeze", "thaw", "frost", "assemble", "pack", "marinate"]:
        assert name in PROCESSES


def test_manifest_rejects_scenario_with_missing_capability():
    """A scenario that needs a missing capability is rejected by name."""
    empty = Registry("x")
    offered = build_manifest(ManifestSources(FIXTURE_KINDS, ITEM_TYPES, PROCESSES, empty, empty, empty, empty))
    check_requirements("ok", CapabilitySet(processes=frozenset({"bake"})), offered)
    with pytest.raises(MissingCapabilities, match="blast_chill"):
        check_requirements("bad", CapabilitySet(processes=frozenset({"blast_chill"})), offered)
