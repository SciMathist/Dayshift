"""Tests for dsz.world.processes: start checks, completion, abort, overrun and combining."""

from dsz.core.types import Condition, Location
from dsz.world.processes import ProcessRunner


def _kinds(bus):
    """Return the kinds of process events published so far."""
    return [e.kind for e in bus.events if e.kind.startswith("process.")]


def test_bake_needs_oven_power_and_items_inside(world, bus):
    """Start fails with a cook-visible reason when preconditions are not met."""
    world.add_item("tier", "cake_tier", Location.at("counter"))
    pr = ProcessRunner(world, bus)
    assert "needs one of" in pr.start("bake", "counter", ("tier",))
    assert "is off" in pr.start("bake", "oven", ("tier",))
    world.fixture("oven").powered_on = True
    assert "not in oven" in pr.start("bake", "oven", ("tier",))
    world.move("tier", Location.at("oven"), cause="test")
    assert pr.start("bake", "oven", ("tier",)) is None
    assert "already in a process" in pr.start("bake", "oven", ("tier",))


def test_bake_completes_then_burns_if_left(world, bus):
    """After 40 min the tier is baked; 15 min past that it is damaged."""
    world.fixture("oven").powered_on = True
    world.add_item("tier", "cake_tier", Location.at("oven"))
    pr = ProcessRunner(world, bus)
    pr.start("bake", "oven", ("tier",))
    world.now = 40
    pr.advance(40)
    assert "baked" in world.item("tier").stages
    world.now = 56
    pr.advance(56)
    assert world.item("tier").condition is Condition.DAMAGED
    assert _kinds(bus) == ["process.started", "process.completed", "process.overrun"]


def test_taking_out_in_time_avoids_overrun(world, bus):
    """Removing the output after completion and before the tolerance closes the process cleanly."""
    world.fixture("oven").powered_on = True
    world.add_item("tier", "cake_tier", Location.at("oven"))
    pr = ProcessRunner(world, bus)
    pr.start("bake", "oven", ("tier",))
    world.now = 41
    pr.advance(41)
    world.move("tier", Location.at("counter"), cause="test")
    world.now = 200
    pr.advance(200)
    assert world.item("tier").condition is Condition.OK and not world.processes


def test_removing_early_aborts_without_stage(world, bus):
    """Lead time is real: pulling the item early leaves it unprocessed."""
    world.add_item("chicken", "chicken_breast", Location.at("fridge"))
    pr = ProcessRunner(world, bus)
    pr.start("marinate", "fridge", ("chicken",))
    world.now = 60
    world.move("chicken", Location.at("counter"), cause="test")
    pr.advance(60)
    assert "marinated" not in world.item("chicken").stages
    assert _kinds(bus)[-1] == "process.aborted"


def test_switching_oven_off_aborts_bake(world, bus):
    """A powered process aborts if the fixture is off at completion time."""
    world.fixture("oven").powered_on = True
    world.add_item("tier", "cake_tier", Location.at("oven"))
    pr = ProcessRunner(world, bus)
    pr.start("bake", "oven", ("tier",))
    world.fixture("oven").powered_on = False
    world.now = 40
    pr.advance(40)
    assert "baked" not in world.item("tier").stages


def test_assemble_combines_inputs_into_one_product(world, bus):
    """Assemble consumes the inputs and yields a product that carries their allergens."""
    for iid in ("t1", "t2"):
        world.add_item(iid, "cake_tier", Location.at("counter"))
        world.add_stage(iid, "frosted")
    world.add_item("flower", "sugar_flower", Location.at("counter"))
    pr = ProcessRunner(world, bus)
    assert pr.start("assemble", "counter", ("t1", "t2", "flower")) is None
    world.now = 45
    pr.advance(45)
    product = world.item("assemble_1")
    assert product.location == Location.at("counter") and "assembled" in product.stages
    assert product.components == ("t1", "t2", "flower") and "egg" in product.allergens
    assert not world.item("t1").location.in_world
