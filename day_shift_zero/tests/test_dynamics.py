"""Tests for dsz.dynamics: spoilage, wear, the runner and module extensibility."""

import pytest

from dsz.core.dynamics import DynamicsModule
from dsz.core.registry import Registry
from dsz.core.rng import RngStreams
from dsz.core.types import Condition, Location
from dsz.dynamics import MODULES, DynamicsRunner, build_modules
from dsz.events.bus import RecordingBus
from dsz.world.state import WorldState

H = 60


def _runner(world_bus, config, seed=0, tick=10):
    """Build a runner for `config` on the given bus."""
    return DynamicsRunner(build_modules(config), RngStreams(seed), world_bus, tick=tick)


def test_milk_spoils_on_counter_but_not_in_fridge(world, bus):
    """Milk lasts 6 h at ambient and 7 days chilled."""
    world.add_item("m_counter", "milk", Location.at("counter"))
    world.add_item("m_fridge", "milk", Location.at("fridge"))
    _runner(bus, {"spoilage": {}}).advance(world, 0, 6 * H)
    assert world.item("m_counter").condition is Condition.SPOILED
    assert world.item("m_fridge").condition is Condition.OK
    assert [e.data["item"] for e in bus.events if e.kind == "item.spoiled"] == ["m_counter"]


def test_failing_fridge_spoils_food(world, bus):
    """A fridge below half health behaves as ambient storage."""
    world.add_item("m", "milk", Location.at("fridge"))
    world.fixture("fridge").health = 0.4
    _runner(bus, {"spoilage": {}}).advance(world, 0, 6 * H)
    assert world.item("m").condition is Condition.SPOILED


def test_parked_items_do_not_age(world, bus):
    """Items still in the delivery pool are not in the world, so they do not spoil."""
    world.add_item("m", "milk", Location.parked())
    _runner(bus, {"spoilage": {}}).advance(world, 0, 48 * H)
    assert world.item("m").spoilage == 0.0


def test_wear_crosses_threshold_once(world, bus):
    """Wear publishes fixture.failing exactly once when health drops below 0.5."""
    _runner(bus, {"wear": {"fixtures": ["fridge"], "per_day": 0.2}}).advance(world, 0, 5 * 24 * H)
    assert world.fixture("fridge").health == pytest.approx(0.0)
    assert [e.kind for e in bus.events].count("fixture.failing") == 1


def _wear_after(splits, seed=3):
    """Return fridge health after advancing wear (with noise) over consecutive `splits`."""
    bus = RecordingBus()
    w = WorldState(bus)
    w.add_fixture("fridge", "fridge")
    r = _runner(bus, {"wear": {"fixtures": ["fridge"], "per_day": 0.1, "jitter": 0.5}}, seed=seed)
    for t0, t1 in zip(splits, splits[1:]):
        r.advance(w, t0, t1)
    return w.fixture("fridge").health


def test_dynamics_do_not_depend_on_how_the_agent_splits_time():
    """Different action timings (time splits) give the same exogenous wear."""
    one_call = _wear_after([0, 24 * H])
    many = _wear_after([0, 3, 7, 25, 26, 300, 301, 777, 1000, 24 * H])
    assert many == pytest.approx(one_call, abs=1e-12)
    assert _wear_after([0, 24 * H], seed=4) != one_call


def test_module_params_are_validated():
    """Invalid parameters fail when the module is built, not mid-run."""
    with pytest.raises(ValueError):
        build_modules({"spoilage": {"rate": 0}})
    with pytest.raises(ValueError):
        build_modules({"wear": {"per_day": 0.1}})
    with pytest.raises(KeyError, match="unknown dynamics module"):
        build_modules({"weather": {}})


def test_new_module_plugs_in_without_platform_changes(world, bus):
    """Open/closed: a new module in a separate registry runs through the same runner."""

    class Evaporation(DynamicsModule):
        """Test module: each tick, mark every in-world item as touched."""

        name = "evaporation"

        def advance(self, world, t0, t1, rng, bus):
            """Add a stage to every in-world item."""
            for item in world.in_world():
                world.add_stage(item.item_id, "evaporated")

    reg: Registry = Registry("dynamics module")
    reg.add(Evaporation.name, Evaporation)
    world.add_item("m", "milk", Location.at("fridge"))
    DynamicsRunner(build_modules({"evaporation": {}}, reg), RngStreams(0), bus).advance(world, 0, 30)
    assert "evaporated" in world.item("m").stages
    assert "evaporation" not in MODULES  # the global registry is untouched
