"""Materializer: wire an Instance into a running world (the composition root for one run).

`materialize()` builds the backend, places items, loads events (exogenous, fact reveals,
work tickets), attaches actors, modules, the work tracker and the success check, and
returns a `Run`. `Run.act()` executes a skill and advances time; `Run.advance_to()` steps
time event by event.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from dsz.actors import ChannelHub, build_actors
from dsz.core.policy import Observation, TaskBrief
from dsz.core.rng import RngStreams
from dsz.core.scenario import Instance, Scenario, ScheduledEvent
from dsz.core.sim import SimBackend
from dsz.core.skills import SkillContext
from dsz.core.success import SuccessCheck
from dsz.core.types import SimMinutes, SkillCall, SkillResult, Verdict
from dsz.dynamics import DynamicsRunner, build_modules
from dsz.env.observation import ObservationBuilder
from dsz.events import EventEngine
from dsz.events.bus import RecordingBus
from dsz.scenario.work import WorkTracker
from dsz.sim.symbolic import SymbolicBackend
from dsz.skills import BusOrderDesk, BusSpeech, SkillExecutor
from dsz.world.processes import ProcessRunner
from dsz.world.snapshot import world_snapshot
from dsz.world.state import WorldState
from dsz.world.vocabulary import register_default_vocabulary

BackendFactory = Callable[[WorldState, RngStreams], SimBackend]


def symbolic_backend(world: WorldState, rng: RngStreams) -> SimBackend:
    """Default backend factory: deterministic symbolic kitchen (tau_sym)."""
    return SymbolicBackend(world, rng.get("noise"))


@dataclass
class Run:
    """One materialized run. Evaluator-side object: never hand it to a policy."""

    instance: Instance
    world: WorldState
    bus: RecordingBus
    backend: SimBackend
    processes: ProcessRunner
    dynamics: DynamicsRunner
    engine: EventEngine
    hub: ChannelHub
    tracker: WorkTracker
    success: SuccessCheck
    executor: SkillExecutor
    observer: ObservationBuilder

    @property
    def end(self) -> SimMinutes:
        """Return the end of the horizon."""
        return self.instance.horizon.end

    @property
    def done(self) -> bool:
        """Return True once the horizon has elapsed."""
        return self.world.now >= self.end

    def brief(self) -> TaskBrief:
        """Return what the policy is told at the start."""
        i = self.instance
        return TaskBrief(i.scenario_id, i.objective, self.executor.doc(), i.horizon.days)

    def observe(self, last: SkillResult | None = None) -> Observation:
        """Return the policy-visible observation."""
        return self.observer.build(last)

    def act(self, call: SkillCall) -> SkillResult:
        """Execute `call`, then let its duration pass."""
        result = self.executor.execute(call)
        self.advance_to(self.world.now + result.elapsed)
        return result

    def advance_to(self, t: SimMinutes) -> None:
        """Advance time to `t` (clamped to the horizon), stopping at every queued event."""
        t = min(t, self.end)
        self._settle()
        while self.world.now < t:
            nxt = t
            ev_t = self.engine.next_time()
            if ev_t is not None and self.world.now < ev_t < nxt:
                nxt = ev_t
            self.dynamics.advance(self.world, self.world.now, nxt)
            self.world.now = nxt
            self._settle()

    def verdict(self) -> Verdict:
        """Return the success verdict for the run so far."""
        return self.success.verdict(self.world, self.backend)

    def _settle(self) -> None:
        """Fire due events, resolve processes and update work at the current time."""
        self.engine.run_until(self.world.now)
        self.processes.advance(self.world.now)
        self.tracker.update()


def derived_events(instance: Instance) -> list[ScheduledEvent]:
    """Return message events for facts and work_release events for tickets."""
    out = [ScheduledEvent(f.revealed_at, "message",
                          {"channel": f.channel, "sender": f.sender, "text": f.text, "fact_id": f.fact_id}, True)
           for f in instance.facts]
    for w in instance.work:
        tk = w.spec.get("ticket")
        if tk:
            out.append(ScheduledEvent(w.released_at, "work_release",
                                      {"work_id": w.work_id, "channel": tk["channel"], "sender": tk["sender"],
                                       "text": tk["text"]}, True))
    return out


def materialize(scenario: Scenario, instance: Instance, backend_factory: BackendFactory = symbolic_backend,
                full_state: bool = False) -> Run:
    """Build a Run for `instance`. `full_state=True` is for the pi_sym (E1) ablation only."""
    register_default_vocabulary()
    bus = RecordingBus()
    world = WorldState(bus)
    rng = RngStreams(instance.seed)
    backend = backend_factory(world, rng)
    backend.build(instance.fixtures, {i.item_id: i.item_type for i in instance.items})
    for it in instance.items:
        world.item(it.item_id).batch = it.batch
        if it.location.in_world:
            backend.spawn(it.item_id, it.location)
    hub = ChannelHub(bus)
    engine = EventEngine(world, backend, hub, bus, rng)
    engine.load(list(instance.events) + derived_events(instance))
    for actor in build_actors(instance.actors):
        actor.attach(engine.context(f"actors.{actor.name}"))
    success = scenario.success_check(instance)
    success.attach(bus, instance)
    processes = ProcessRunner(world, bus)
    now = lambda: world.now  # noqa: E731
    ctx = SkillContext(backend, backend, processes, BusOrderDesk(bus, now), BusSpeech(bus, now))
    state = (lambda: world_snapshot(world)) if full_state else None
    run = Run(instance, world, bus, backend, processes, DynamicsRunner(build_modules(instance.modules), rng, bus),
              engine, hub, WorkTracker(instance.work, world, backend, bus), success, SkillExecutor(ctx),
              ObservationBuilder(backend, hub, now, full_state=state))
    run.advance_to(0)
    return run
