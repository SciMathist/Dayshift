"""Tests for dsz.core: RNG streams, registry, capability sets, instances and locations."""

import pytest

from dsz.core.registry import Registry
from dsz.core.rng import RngStreams
from dsz.core.scenario import Fact, Instance, ScheduledEvent, WorkItem
from dsz.core.types import MINUTES_PER_DAY, CapabilitySet, Horizon, HorizonType, Location


def test_rng_streams_are_reproducible_and_independent():
    """Same seed gives the same draws; heavy use of one stream does not shift another."""
    a, b = RngStreams(7), RngStreams(7)
    assert a.get("events").integers(0, 10**9) == b.get("events").integers(0, 10**9)
    c, d = RngStreams(7), RngStreams(7)
    c.get("work").random(1000)
    assert c.get("events").random() == d.get("events").random()
    assert RngStreams(7).get("events").random() != RngStreams(8).get("events").random()


def test_rng_checkpoint_restore():
    """Restoring a captured state replays the same draws."""
    r = RngStreams(3)
    r.get("noise").random(5)
    snap = r.state()
    x = r.get("noise").random()
    r.restore(snap)
    assert r.get("noise").random() == x


def test_registry_rejects_duplicates_and_names_unknowns():
    """Duplicate names raise; unknown names raise with a helpful message."""
    reg: Registry[int] = Registry("thing")
    reg.add("a", 1)
    with pytest.raises(KeyError, match="already registered"):
        reg.add("a", 2)
    with pytest.raises(KeyError, match="unknown thing 'b'"):
        reg.get("b")


def test_capability_gap_reports_by_category():
    """Only the missing capabilities are reported, grouped by category."""
    offered = CapabilitySet(fixtures=frozenset({"oven", "fridge"}), processes=frozenset({"bake"}))
    need = CapabilitySet(fixtures=frozenset({"oven", "blast_chiller"}), processes=frozenset({"bake"}))
    assert need.missing_from(offered) == {"fixtures": frozenset({"blast_chiller"})}


def test_instance_prefix_property():
    """A shorter prefix keeps exactly the facts, work and events before its end."""
    day = MINUTES_PER_DAY
    inst = Instance(
        scenario_id="s", seed=1, horizon=Horizon(HorizonType.CONTINUOUS, 3), objective="o",
        fixtures=("counter",), items=(),
        facts=(Fact("f1", 10, "manager", "x"), Fact("f2", 2 * day + 5, "manager", "y")),
        work=(WorkItem("w1", "order", 0, 100), WorkItem("w2", "order", day + 1, day + 100)),
        events=(ScheduledEvent(5, "delivery"), ScheduledEvent(2 * day, "relocate")),
    )
    p = inst.prefix(1)
    assert p.horizon.days == 1
    assert [f.fact_id for f in p.facts] == ["f1"]
    assert [w.work_id for w in p.work] == ["w1"]
    assert [e.t for e in p.events] == [5]
    with pytest.raises(ValueError):
        inst.prefix(4)


def test_location_helpers():
    """Fixture and held locations are in the world; parked and discarded are not."""
    assert Location.at("fridge", "shelf_1").in_world
    assert Location.held().in_world
    assert not Location.parked().in_world
    assert not Location.discarded().in_world
