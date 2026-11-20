"""Tests for dsz.actors: channel hub and the supplier."""

import pytest

from dsz.actors import ChannelHub, build_actors
from dsz.core.events import DomainEvent
from dsz.core.rng import RngStreams
from dsz.core.types import MINUTES_PER_DAY, Location, LocationKind, Message
from dsz.events import EventEngine
from dsz.events.bus import RecordingBus
from dsz.world.editor import SemanticWorldEditor
from dsz.world.state import WorldState

SUPPLIER = {"role": "supplier", "name": "acme", "lead_time_days": [1, 2], "fixture": "delivery_shelf"}


def _setup(seed=0, pool=4, supplier=SUPPLIER):
    """Return (world, bus, hub, engine) with `pool` parked eggs and an attached supplier."""
    bus = RecordingBus()
    world = WorldState(bus)
    world.add_fixture("delivery_shelf", "delivery_shelf")
    for i in range(pool):
        world.add_item(f"egg_{i}", "egg", Location.parked())
    hub = ChannelHub(bus)
    eng = EventEngine(world, SemanticWorldEditor(world), hub, bus, RngStreams(seed))
    for actor in build_actors([supplier]):
        actor.attach(eng.context(f"actors.{actor.name}"))
    return world, bus, hub, eng


def _order(bus, world, qty, supplier="acme"):
    """Publish an order the way the `order` skill will."""
    bus.publish(DomainEvent(world.now, "order.placed", {"supplier": supplier, "item_type": "egg", "qty": qty}))


def test_hub_drain_returns_only_new_messages():
    """Drain is incremental; history keeps everything."""
    bus = RecordingBus()
    hub = ChannelHub(bus)
    hub.post(Message(0, "c", "a", "one"))
    assert [m.text for m in hub.drain()] == ["one"]
    hub.post(Message(1, "c", "a", "two"))
    assert [m.text for m in hub.drain()] == ["two"]
    assert len(hub.history) == 2 and not bus.events[0].evaluator_only


def test_order_is_confirmed_and_delivered_after_lead_time():
    """An order schedules a morning delivery 1-2 days later and confirms by message."""
    world, bus, hub, eng = _setup()
    _order(bus, world, 2)
    msg = hub.drain()[0]
    assert msg.channel == "supplier" and "2 x egg" in msg.text
    arrive = next(e for e in bus.events if e.kind == "order.accepted").data["arrive_t"]
    assert arrive in (MINUTES_PER_DAY + 480, 2 * MINUTES_PER_DAY + 480)
    world.now = arrive
    eng.run_until(arrive)
    assert len(world.items_of_type("egg", LocationKind.FIXTURE)) == 2


def test_reserved_stock_is_not_promised_twice():
    """Two orders before delivery draw on different pool items; the pool can run out."""
    world, bus, hub, eng = _setup(pool=3)
    _order(bus, world, 2)
    _order(bus, world, 2)
    texts = [m.text for m in hub.drain()]
    assert "2 x egg" in texts[0] and "1 x egg" in texts[1]
    _order(bus, world, 1)
    assert "out of stock" in hub.drain()[0].text


def test_orders_for_another_supplier_are_ignored():
    """Each supplier handles only its own orders."""
    world, bus, hub, eng = _setup()
    _order(bus, world, 1, supplier="other")
    assert hub.drain() == ()


def test_supplier_is_deterministic_per_seed():
    """Same seed and same orders give the same lead times."""
    def arrivals(seed):
        """Return arrival times for five single-egg orders."""
        world, bus, hub, eng = _setup(seed=seed, pool=5)
        for _ in range(5):
            _order(bus, world, 1)
        return [e.data["arrive_t"] for e in bus.events if e.kind == "order.accepted"]
    assert arrivals(1) == arrivals(1)


def test_supplier_requires_fixture():
    """Misconfigured actors fail at build time."""
    with pytest.raises(ValueError, match="fixture"):
        build_actors([{"role": "supplier"}])
