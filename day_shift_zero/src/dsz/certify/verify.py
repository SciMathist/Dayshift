"""Scenario verifier: run the acceptance stages that exist (task spec section 7) on one folder.

| Stage | Done here |
|---|---|
| S1 Parse | `scenario.yaml` exists and parses |
| S2 Compile | Plugins, parameters, capabilities, references; ID and h_min rules; work due in the horizon |
| S3 Claims | Kind-A checks: the claims block (`claim_checks`) and the texts (`text_checks`: CR15; CR5 notes) |
| S4 Certify | V1: on every seed and horizon the oracle passes and every control fails. OC2 on one pair |

The oracle is the scenario's own (`oracle.py`) if the definition names one, else the
generic oracle with its derived controls. The reviewer checks the rest of S3. H1, M1,
R1, C1 and S5 are not built yet; the report says so. Deterministic, read-only, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dsz.certify.claim_checks import check_claims
from dsz.certify.oracle import DERIVED_CONTROLS, GENERIC_ORACLE
from dsz.certify.text_checks import announced_events, skill_sequences
from dsz.core.policy import Policy
from dsz.core.rng import RngStreams
from dsz.core.types import SkillCall, Verdict
from dsz.scenario import (
    POLICIES,
    ScenarioSpec,
    SpecError,
    SpecScenario,
    load_scenario,
    load_spec,
    materialize,
    validate_instance,
)
from dsz.world.manifest import MissingCapabilities

PASS, FAIL = "pass", "fail"
GENERIC_CONTROLS = ("noop",)
MAX_ACTIONS = 50_000
MIN_DAYS = 2
ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
NOT_BUILT = ("S3 here runs the kind-A checks only; the reviewer checks the rest. "
             "Not built yet: H1, M1, R1, C1 (S4) and S5. Numbers are pilot, not benchmark results.")


@dataclass
class StageResult:
    """The outcome of one stage. `problems` name a rule or predicate ID where one applies."""

    stage: str
    status: str
    problems: list[str] = field(default_factory=list)
    summary: str = ""
    notes: list[str] = field(default_factory=list)  # findings that do not fail the stage


@dataclass
class Report:
    """The verifier's report for one scenario folder."""

    folder: str
    scenario_id: str | None
    seeds: int
    stages: list[StageResult] = field(default_factory=list)
    runs: list[dict[str, Any]] = field(default_factory=list)  # one row per (policy, horizon, seed)
    note: str = NOT_BUILT

    @property
    def ok(self) -> bool:
        """Return True if no stage failed."""
        return all(s.status != FAIL for s in self.stages)

    def to_dict(self) -> dict[str, Any]:
        """Return the report as plain data, for `report.json`."""
        return {"ok": self.ok, **asdict(self)}

    def to_text(self) -> str:
        """Return the report for a person or an agent to read."""
        lines = [f"dsz verify {self.folder}  (scenario: {self.scenario_id or '?'}, seeds 0-{self.seeds - 1})"]
        for s in self.stages:
            lines.append(f"{s.stage:<11} {s.status.upper():<8} {s.summary}".rstrip())
            lines += [f"  - {p}" for p in s.problems]
            lines += [f"  note: {n}" for n in s.notes]
        lines += [self.note, f"RESULT: {'PASS' if self.ok else 'FAIL'}"]
        return "\n".join(lines)


def verify(folder: str | Path, seeds: int = 5) -> Report:
    """Run S1, S2 and S4 on the scenario in `folder`, stopping at the first failed stage."""
    folder = Path(folder)
    report = Report(str(folder), None, seeds)
    s1 = StageResult("S1 parse", PASS)
    report.stages.append(s1)
    try:
        report.scenario_id = load_spec(folder / "scenario.yaml").scenario_id
    except FileNotFoundError:
        s1.problems.append(f"scenario.yaml not found in {folder}")
    except yaml.YAMLError as e:
        s1.problems.append(f"YAML error: {e}")
    except SpecError as e:
        s1.problems.extend(e.problems)
    if s1.problems:
        s1.status = FAIL
        return report

    s2 = StageResult("S2 compile", PASS)
    report.stages.append(s2)
    try:
        scenario = load_scenario(folder)
    except SpecError as e:
        s2.problems.extend(e.problems)
    except MissingCapabilities as e:
        s2.problems.append(str(e))
    except Exception as e:  # noqa: BLE001  (an oracle module or plugin can raise anything)
        s2.problems.append(f"{type(e).__name__}: {e}")
    else:
        s2.problems.extend(_definition_rules(scenario.spec) + _instance_rules(scenario, seeds))
    if s2.problems:
        s2.status = FAIL
        return report

    s3 = _claims_stage(scenario, seeds)
    report.stages.append(s3)
    if s3.status == FAIL:
        return report
    report.stages.append(_certify(scenario, seeds, report.runs))
    return report


def _definition_rules(spec: ScenarioSpec) -> list[str]:
    """Return breaks of the ID rule and the horizon rule (task spec section 1)."""
    out = []
    if not ID_PATTERN.fullmatch(spec.scenario_id):
        out.append(f"ID: '{spec.scenario_id}' must be lowercase snake_case")
    if spec.min_days < MIN_DAYS:
        out.append(f"horizon.min_days is {spec.min_days}; the certified set starts at {MIN_DAYS} days or more")
    return out


def _instance_rules(scenario: SpecScenario, seeds: int) -> list[str]:
    """Return reference problems and work due after the horizon ends (CR14), on every certified pair.

    The compiler checks references on one probe instance only; a `one_of` choice can name a
    bad fixture that only another seed draws.
    """
    spec, out = scenario.spec, []
    for days in range(spec.min_days, spec.default_days + 1):
        for seed in range(seeds):
            instance = scenario.generate(seed, scenario.horizon(days), RngStreams(seed))
            out += [f"seed {seed}: {p}" for p in validate_instance(instance) if f"seed {seed}: {p}" not in out]
            late = [w.work_id for w in instance.work if w.deadline > instance.horizon.end]
            if late and not any(o.startswith(f"CR14: at {days} days") for o in out):
                out.append(f"CR14: at {days} days (seed {seed}) {', '.join(late)} are due after the horizon ends")
    return out


def _claims_stage(scenario: SpecScenario, seeds: int) -> StageResult:
    """Run the kind-A checks on the claims and on every seed's texts at the longest horizon."""
    stage = StageResult("S3 claims", PASS)
    instances = [scenario.generate(seed, scenario.horizon(), RngStreams(seed)) for seed in range(seeds)]
    stage.problems = check_claims(scenario.spec, instances)
    for instance in instances:
        stage.problems += [p for p in skill_sequences(instance) if p not in stage.problems]
        stage.notes += [n for n in announced_events(instance) if n not in stage.notes]
    stage.status = FAIL if stage.problems else PASS
    stage.summary = f"{len(scenario.spec.claims)} claim(s) checked; {len(stage.notes)} CR5 note(s)"
    return stage


def _certify(scenario: SpecScenario, seeds: int, runs: list[dict[str, Any]]) -> StageResult:
    """Run V1 (oracle passes, controls fail) on every pair and OC2 on one pair."""
    spec = scenario.spec
    stage = StageResult("S4 certify", PASS)
    oracle = spec.oracle.name if spec.oracle else GENERIC_ORACLE
    params = {c.name: c.params for c in spec.controls}
    derived = () if spec.oracle else DERIVED_CONTROLS
    controls = list(params) + [c for c in (*GENERIC_CONTROLS, *derived) if c not in params]
    policies = [oracle] + controls
    params[oracle] = spec.oracle.params if spec.oracle else {}
    for days in range(spec.min_days, spec.default_days + 1):
        for seed in range(seeds):
            for name in policies:
                row = _run(scenario, name, params.get(name, {}), seed, days)
                row["role"] = "oracle" if name == oracle else "control"
                runs.append(row)
                where = f"seed {seed}, {days} days"
                if "error" in row:
                    stage.problems.append(f"{name} crashed at {where}: {row['error']}")
                elif row["role"] == "oracle" and not row["passed"]:
                    stage.problems.append(f"V1: {name} fails at {where} (score {row['score']:.2f}): "
                                          + "; ".join(row["notes"]))
                elif row["role"] == "control" and row["passed"]:
                    stage.problems.append(f"V1: control '{name}' passes at {where} (score {row['score']:.2f}). "
                                          "The difficulty it removes is missing")
    if not stage.problems:
        a = _run(scenario, oracle, params[oracle], 0, spec.default_days, keep_trace=True)
        b = _run(scenario, oracle, params[oracle], 0, spec.default_days, keep_trace=True)
        if a.get("trace") != b.get("trace"):
            stage.problems.append(f"OC2: two oracle runs at seed 0, {spec.default_days} days differ")
    if not spec.oracle and any(p.startswith(("V1: generic_oracle", "generic_oracle crashed")) for p in stage.problems):
        stage.problems.append("The generic oracle cannot do this scenario. By spec section 6 it needs scheduling "
                              "or search: change the scenario")
    stage.summary = _tally(runs, policies)
    stage.status = FAIL if stage.problems else PASS
    return stage


def _run(scenario: SpecScenario, name: str, params: dict, seed: int, days: int,
         keep_trace: bool = False) -> dict[str, Any]:
    """Run one policy on one (seed, horizon) pair and return a report row."""
    row: dict[str, Any] = {"policy": name, "seed": seed, "days": days}
    try:
        instance = scenario.generate(seed, scenario.horizon(days), RngStreams(seed))
        run = materialize(scenario, instance)
        policy = POLICIES.get(name)(instance, run.world, params)
        verdict, trace = _drive(run, policy)
    except Exception as e:  # noqa: BLE001  (report any policy or platform crash as a finding)
        row["error"] = f"{type(e).__name__}: {e}"
        return row
    row.update(passed=verdict.passed, score=round(verdict.score, 4), actions=len(trace), notes=list(verdict.notes))
    if keep_trace:
        row["trace"] = trace
    return row


def _drive(run, policy: Policy) -> tuple[Verdict, list[str]]:
    """Run `policy` until the horizon ends. Return the verdict and the skill calls made."""
    policy.reset(run.brief())
    obs, trace = run.observe(), []
    while not run.done:
        action = policy.act(obs)
        if not isinstance(action, SkillCall):
            raise TypeError(f"expected a SkillCall, got {type(action).__name__}")
        trace.append(f"{run.world.now}:{action.name}{sorted(action.args.items())}")
        if len(trace) > MAX_ACTIONS:
            raise RuntimeError(f"more than {MAX_ACTIONS} skill calls before the horizon ended")
        obs = run.observe(run.act(action))
    return run.verdict(), trace


def _tally(runs: list[dict[str, Any]], policies: list[str]) -> str:
    """Return `name passed/total` for each policy."""
    out = []
    for name in policies:
        rows = [r for r in runs if r["policy"] == name]
        out.append(f"{name} {sum(bool(r.get('passed')) for r in rows)}/{len(rows)} passed")
    return "; ".join(out)
