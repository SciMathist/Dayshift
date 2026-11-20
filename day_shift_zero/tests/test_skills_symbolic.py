"""Tests for dsz.skills and dsz.sim.symbolic: skill flow, sensing, failures, grounding, checkpoints."""

from dataclasses import dataclass

from dsz.actors import ChannelHub, build_actors
from dsz.core.registry import Registry
from dsz.core.rng import RngStreams
from dsz.core.sim import Actuation, Checkpointable, GroundTruth, Perception, WorldEditor
from dsz.core.skills import Skill, SkillContext, SkillOutcome
from dsz.core.types import Condition, Location, LocationKind, SkillCall
from dsz.env.observation import ObservationBuilder
from dsz.events import EventEngine
from dsz.events.bus import RecordingBus
from dsz.sim.symbolic import SymbolicBackend
from dsz.skills import BusOrderDesk, BusSpeech, SkillExecutor
from dsz.world.processes import ProcessRunner
from dsz.world.snapshot import world_snapshot
from dsz.world.state import WorldState

FIXTURES = {"fridge": "fridge", "counter": "counter", "oven": "oven", "delivery_shelf": "delivery_shelf"}


@dataclass
class Kitchen:
    """Wired test kitchen: world, bus, backend, hub, processes and an executor."""

    world: WorldState
    bus: RecordingBus
    backend: SymbolicBackend
    hub: ChannelHub
    processes: ProcessRunner
    run: SkillExecutor

    def do(self, name, **args):
        """Execute one skill call and return its result."""
        return self.run.execute(SkillCall(name, args))


def make_kitchen(seed=0, pool=None, **noise) -> Kitchen:
    """Build a symbolic kitchen with optional parked pool and failure noise."""
    bus = RecordingBus()
    world = WorldState(bus)
    backend = SymbolicBackend(world, RngStreams(seed).get("noise"), **noise)
    backend.build(FIXTURES, pool or {})
    procs = ProcessRunner(world, bus)
    now = lambda: world.now  # noqa: E731
    ctx = SkillContext(backend, backend, procs, BusOrderDesk(bus, now), BusSpeech(bus, now))
    return Kitchen(world, bus, backend, ChannelHub(bus), procs, SkillExecutor(ctx))


def test_backend_implements_every_role():
    """The symbolic backend satisfies all role protocols."""
    b = make_kitchen().backend
    for role in (Actuation, Perception, WorldEditor, GroundTruth, Checkpointable):
        assert isinstance(b, role)


def test_closed_fridge_hides_its_contents():
    """Hidden state is real: a closed door means no detections."""
    k = make_kitchen()
    k.world.add_item("milk_1", "milk", Location.at("fridge"))
    k.do("navigate_to", fixture="fridge")
    assert k.backend.detections() == ()
    k.do("open", fixture="fridge")
    dets = k.backend.detections()
    assert [(d.index, d.label) for d in dets] == [(0, "milk")]


def test_fetch_and_place_flow_with_gripper_sensing():
    """Navigate, open, pick, carry and place; the gripper reading reflects the hand."""
    k = make_kitchen()
    k.world.add_item("milk_1", "milk", Location.at("fridge"))
    k.do("navigate_to", fixture="fridge")
    k.do("open", fixture="fridge")
    r = k.do("pick", index=0)
    assert r.accepted and r.elapsed == 1 and r.sensors.holding_something is True
    k.do("navigate_to", fixture="counter")
    r = k.do("place", fixture="counter")
    assert r.sensors.holding_something is False
    assert k.backend.locate("milk_1") == Location.at("counter")


def test_reach_door_and_capacity_failures_have_no_effect():
    """Out of reach, closed door and full fixture are reported by note and change nothing."""
    k = make_kitchen()
    k.world.add_item("m", "milk", Location.at("counter"))
    k.do("navigate_to", fixture="counter")
    k.do("pick", index=0)
    assert k.do("place", fixture="fridge").message == "out of reach"
    k.do("navigate_to", fixture="fridge")
    assert k.do("place", fixture="fridge").message == "door is closed"
    assert k.backend.held_item() == "m"
    k.do("open", fixture="fridge")
    for i in range(24):
        k.world.add_item(f"x{i}", "milk", Location.at("fridge"))
    assert k.do("place", fixture="fridge").message == "no space"
    assert k.backend.held_item() == "m"


def test_seeded_grasp_failure_and_break():
    """Injected failures: the hand stays empty, and a fragile item can break (irrecoverable)."""
    k = make_kitchen(grasp_fail_p=1.0, break_on_fail_p=1.0)
    k.world.add_item("egg_1", "egg", Location.at("counter"))
    k.do("navigate_to", fixture="counter")
    r = k.do("pick", index=0)
    assert r.sensors.holding_something is False and r.message == ""
    assert k.world.item("egg_1").condition is Condition.DAMAGED


def test_grasp_noise_is_deterministic_per_seed():
    """Same seed and actions give the same success pattern."""
    def pattern(seed):
        """Return grasp outcomes over ten tries."""
        k = make_kitchen(seed=seed, grasp_fail_p=0.5)
        k.world.add_item("m", "milk", Location.at("counter"))
        k.do("navigate_to", fixture="counter")
        out = []
        for _ in range(10):
            out.append(bool(k.do("pick", index=0).sensors.holding_something))
            if out[-1]:
                k.do("place", fixture="counter")
        return out
    assert pattern(5) == pattern(5)
    assert len(set(pattern(5))) == 2  # both outcomes occur


def test_start_process_through_skill():
    """Baking via skills: power on, load, start; reasons come back as messages."""
    k = make_kitchen()
    k.world.add_item("tier", "cake_tier", Location.at("oven"))
    assert k.do("start_process", process="bake", fixture="oven").message == "oven is off"
    k.do("navigate_to", fixture="oven")
    k.do("set_power", fixture="oven", on=True)
    assert k.do("start_process", process="bake", fixture="oven").message == "bake started"
    k.world.now = 40
    k.processes.advance(40)
    assert "baked" in k.world.item("tier").stages


def test_order_skill_reaches_supplier():
    """The order skill publishes order.placed; the supplier answers on its channel."""
    k = make_kitchen(pool={"egg_1": "egg", "egg_2": "egg"})
    eng = EventEngine(k.world, k.backend, k.hub, k.bus, RngStreams(0))
    for a in build_actors([{"role": "supplier", "name": "acme", "fixture": "delivery_shelf"}]):
        a.attach(eng.context("actors.acme"))
    k.do("order", supplier="acme", item_type="egg", qty=2)
    assert "2 x egg" in k.hub.drain()[0].text


def test_executor_rejects_bad_calls_without_side_effects():
    """Unknown skills and bad arguments are rejected and take no time."""
    k = make_kitchen()
    bad = [SkillCall("teleport", {}), SkillCall("pick", {}), SkillCall("pick", {"index": True}),
           SkillCall("pick", {"index": 0, "force": 3}), SkillCall("wait", {"minutes": 0}),
           SkillCall("order", {"supplier": "a", "item_type": "egg", "qty": 0})]
    for call in bad:
        r = k.run.execute(call)
        assert not r.accepted and r.elapsed == 0 and r.message
    assert k.world.robot_at is None and not k.bus.events


def test_checkpoint_restore_roundtrip():
    """Restoring a checkpoint brings back items, robot position and noise state."""
    k = make_kitchen(grasp_fail_p=0.5)
    k.world.add_item("m", "milk", Location.at("counter"))
    k.do("navigate_to", fixture="counter")
    blob = k.backend.checkpoint()
    first = [bool(k.do("pick", index=0).sensors.holding_something)]
    k.backend.restore(blob)
    assert k.world.robot_at == "counter" and k.world.item("m").location.kind is LocationKind.FIXTURE
    assert [bool(k.do("pick", index=0).sensors.holding_something)] == first


def test_observation_has_no_hidden_state_by_default():
    """Observations carry detections and new messages only, unless pi_sym mode is on."""
    k = make_kitchen()
    k.world.add_item("m", "milk", Location.at("fridge"))
    obs = ObservationBuilder(k.backend, k.hub, lambda: k.world.now).build()
    assert obs.state is None and obs.detections == () and obs.messages == ()
    sym = ObservationBuilder(k.backend, k.hub, lambda: k.world.now, full_state=lambda: world_snapshot(k.world))
    assert sym.build().state["items"]["m"]["at"] == "fridge"


def test_new_skill_plugs_in_without_platform_changes():
    """Open/closed: a new skill in its own registry runs through the same executor."""

    class Hum(Skill):
        """Test skill: hum a tune for two minutes."""

        name = "hum"
        doc = "Hum."
        args = {"tune": str}

        def run(self, ctx, args):
            """Return two minutes."""
            return SkillOutcome(2, message=f"humming {args['tune']}")

    reg: Registry = Registry("skill")
    reg.add(Hum.name, Hum)
    k = make_kitchen()
    ex = SkillExecutor(k.run._ctx, registry=reg)
    r = ex.execute(SkillCall("hum", {"tune": "la"}))
    assert r.accepted and r.elapsed == 2 and r.message == "humming la"
    assert "hum(tune: str): Hum." == ex.doc()
