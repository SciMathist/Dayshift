"""Tests for dsz.events: engine ordering and deferral, built-in handlers, extensibility."""

import pytest

from dsz.actors import ChannelHub
from dsz.core.events import EventHandler
from dsz.core.registry import Registry
from dsz.core.rng import RngStreams
from dsz.core.scenario import ScheduledEvent
from dsz.core.types import Condition, Location, LocationKind
from dsz.events import EventEngine
from dsz.world.editor import SemanticWorldEditor


@pytest.fixture
def hub(bus):
    """Return a channel hub on the shared bus."""
    return ChannelHub(bus)


@pytest.fixture
def engine(world, bus, hub):
    """Return an engine over the test world."""
    return EventEngine(world, SemanticWorldEditor(world), hub, bus, RngStreams(0))


def _ev(t, kind, **payload):
    """Build a ScheduledEvent."""
    return ScheduledEvent(t, kind, payload)


def test_events_fire_in_time_then_insertion_order(world, engine, hub):
    """Events fire by time; ties keep insertion order; future events wait."""
    engine.load([_ev(10, "message", channel="c", sender="a", text="second"),
                 _ev(5, "message", channel="c", sender="a", text="first"),
                 _ev(10, "message", channel="c", sender="a", text="third"),
                 _ev(99, "message", channel="c", sender="a", text="later")])
    assert engine.run_until(10) == 3
    assert [m.text for m in hub.drain()] == ["first", "second", "third"]
    assert engine.next_time() == 99


def test_schedule_rejects_past_and_unknown(world, engine):
    """The engine fails fast on bad schedules."""
    world.now = 50
    with pytest.raises(ValueError, match="past"):
        engine.schedule(_ev(10, "message", channel="c", sender="a", text="x"))
    with pytest.raises(KeyError, match="unknown event type"):
        engine.schedule(_ev(60, "earthquake"))


def test_delivery_is_deferred_while_robot_is_at_the_shelf(world, engine, bus):
    """Never edit onto the robot: the delivery waits until the robot leaves."""
    world.add_item("egg_1", "egg", Location.parked())
    world.robot_at = "delivery_shelf"
    engine.schedule(_ev(10, "delivery", items=["egg_1"], fixture="delivery_shelf"))
    world.now = 10
    assert engine.run_until(10) == 0
    assert world.item("egg_1").location.kind is LocationKind.PARKED
    world.robot_at = "fridge"
    world.now = 15
    assert engine.run_until(15) == 1
    assert world.item("egg_1").location == Location.at("delivery_shelf")
    assert any(e.kind == "event.deferred" for e in bus.events)


def test_relocate_is_noop_when_item_is_held(world, engine, bus):
    """Effects apply to the state found: a held item is not relocated."""
    world.add_item("m", "milk", Location.at("fridge"))
    world.move("m", Location.held(), cause="test")
    engine.schedule(_ev(1, "relocate", item="m", to="cabinet_1"))
    world.now = 1
    engine.run_until(1)
    assert world.item("m").location.kind is LocationKind.HELD
    assert bus.events[-2].kind == "event.noop"


def test_consume_takes_oldest_ok_items_and_reports_shortfall(world, engine, bus):
    """Consumption is FIFO over OK items and reports what was missing."""
    world.add_item("old", "milk", Location.at("fridge"))
    world.now = 100
    world.add_item("new", "milk", Location.at("fridge"))
    world.add_item("bad", "milk", Location.at("fridge"))
    world.degrade("bad", Condition.SPOILED, cause="test")
    engine.schedule(_ev(100, "consume", item_type="milk", count=3))
    engine.run_until(100)
    report = next(e for e in bus.events if e.kind == "stock.consumed")
    assert report.data["taken"] == ["old", "new"] and report.data["short"] == 1
    assert world.item("bad").location.in_world


def test_message_with_fact_is_recorded_for_m1(world, engine, hub, bus):
    """A fact reveal reaches the robot and is logged evaluator-side."""
    engine.schedule(_ev(0, "message", channel="manager", sender="mgr", text="Sam is allergic to sesame",
                        fact_id="allergy_sam"))
    engine.run_until(0)
    assert hub.drain()[0].text == "Sam is allergic to sesame"
    assert any(e.kind == "fact.revealed" and e.data["fact"] == "allergy_sam" for e in bus.events)


def test_goal_change_and_faults(world, engine, hub, bus):
    """Goal changes reach the robot by message; faults lower health and stay evaluator-only."""
    engine.load([_ev(0, "goal_change", change={"tiers": 4}, channel="client", sender="c", text="Make it 4 tiers"),
                 _ev(0, "equipment_fault", fixture="fridge", health=0.3),
                 _ev(0, "door_left_open", fixture="freezer")])
    engine.run_until(0)
    assert hub.drain()[0].text == "Make it 4 tiers"
    assert world.fixture("fridge").health == 0.3 and world.fixture("freezer").is_open
    assert any(e.kind == "goal.changed" and e.data["change"] == {"tiers": 4} for e in bus.events)
    assert all(e.evaluator_only for e in bus.events if e.kind in ("fixture.fault", "goal.changed"))


def test_new_event_kind_plugs_in_without_platform_changes(world, bus, hub):
    """Open/closed: a new handler in its own registry runs through the same engine."""

    class PowerCut(EventHandler):
        """Test handler: switch every powered fixture off."""

        kind = "power_cut"

        def apply(self, ctx, event):
            """Turn all fixtures off."""
            for fx in ctx.world.fixtures.values():
                fx.powered_on = False

    reg: Registry = Registry("event type")
    reg.add(PowerCut.kind, PowerCut)
    world.fixture("oven").powered_on = True
    eng = EventEngine(world, SemanticWorldEditor(world), hub, bus, RngStreams(0), handlers=reg)
    eng.schedule(_ev(0, "power_cut"))
    eng.run_until(0)
    assert not world.fixture("oven").powered_on
