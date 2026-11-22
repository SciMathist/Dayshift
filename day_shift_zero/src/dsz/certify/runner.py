"""Run one policy on one (seed, horizon) pair and record what each skill call touched.

Evaluator-side. The record feeds V1, OC1, OC2 and the trace predicates (`predicates.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from dsz.certify.predicates import Call
from dsz.core.policy import Policy
from dsz.core.rng import RngStreams
from dsz.core.scenario import Instance
from dsz.core.types import SkillCall
from dsz.scenario import POLICIES, Run, SpecScenario, materialize
from dsz.world.snapshot import world_snapshot
from dsz.world.state import WorldState

MAX_ACTIONS = 50_000


@dataclass
class RunResult:
    """The outcome of one run."""

    policy: str
    seed: int
    days: int
    instance: Instance | None = None
    passed: bool = False
    score: float = 0.0
    on_time: int = 0  # work items done by their deadline
    notes: list[str] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    item_types: dict[str, str] = field(default_factory=dict)  # every item id the run saw, made ones too
    oc1: str | None = None  # the first world change made while the policy decided
    error: str | None = None

    def row(self) -> dict[str, Any]:
        """Return the run as one plain row for the report."""
        out = {"policy": self.policy, "seed": self.seed, "days": self.days}
        if self.error:
            return {**out, "error": self.error}
        return {**out, "passed": self.passed, "score": round(self.score, 4), "on_time": self.on_time,
                "actions": len(self.calls), "notes": list(self.notes)}


def run_policy(scenario: SpecScenario, name: str, params: Mapping[str, Any], seed: int, days: int,
               check_oc1: bool = False) -> RunResult:
    """Run policy `name` on (seed, days). `check_oc1` also checks that deciding never changes the world."""
    result = RunResult(name, seed, days)
    try:
        instance = scenario.generate(seed, scenario.horizon(days), RngStreams(seed))
        result.instance = instance
        run = materialize(scenario, instance)
        policy = POLICIES.get(name)(instance, run.world, params)
        _drive(run, policy, result, check_oc1)
    except Exception as e:  # noqa: BLE001  (report any policy or platform crash as a finding)
        result.error = f"{type(e).__name__}: {e}"
        return result
    verdict = run.verdict()
    result.passed, result.score, result.notes = verdict.passed, verdict.score, list(verdict.notes)
    result.on_time = sum(st.on_time for st in run.tracker.status.values())
    result.item_types = {iid: item.item_type for iid, item in run.world.items.items()}
    return result


def _drive(run: Run, policy: Policy, result: RunResult, check_oc1: bool) -> None:
    """Run `policy` until the horizon ends, recording each call in `result`."""
    world = run.world
    policy.reset(run.brief())
    obs = run.observe()
    while not run.done:
        before = world_snapshot(world) if check_oc1 and result.oc1 is None else None
        action = policy.act(obs)
        if before is not None and world_snapshot(world) != before:
            result.oc1 = f"OC1: the world changed while {result.policy} decided at minute {world.now}"
        if not isinstance(action, SkillCall):
            raise TypeError(f"expected a SkillCall, got {type(action).__name__}")
        if len(result.calls) >= MAX_ACTIONS:
            raise RuntimeError(f"more than {MAX_ACTIONS} skill calls before the horizon ended")
        t, at, held = world.now, world.robot_at, world.held()
        inputs = (tuple(i.item_id for i in world.items_at(action.args["fixture"]))
                  if action.name == "start_process" and action.args.get("fixture") in world.fixtures else ())
        obs = run.observe(run.act(action))
        view = _can_see(world)
        result.calls.append(Call(t, action.name, dict(action.args), at, world.robot_at,
                                 held.item_id if held else None,
                                 world.held().item_id if world.held() else None, inputs,
                                 tuple(i.item_id for i in world.items_at(world.robot_at)) if view else (), view))


def _can_see(world: WorldState) -> bool:
    """Return True if the robot stands at a fixture whose inside it can see."""
    here = world.robot_at
    return bool(here) and (not world.fixture(here).spec.has_door or world.fixture(here).is_open)
