"""Scenario verifier: run the acceptance stages that exist (task spec section 7) on one folder.

| Stage | Done here |
|---|---|
| S1 Parse | `scenario.yaml` exists and parses |
| S2 Compile | Plugins, parameters, capabilities, references; ID and h_min rules; work due in the horizon |
| S3 Claims | Kind-A checks: the claims block (`claim_checks`) and the texts (`text_checks`: CR15; CR5 notes) |
| S4 Certify | On every seed and horizon: OC1, V1, H1, M1, R1 (recoverable half), C1 (a, c). OC2 on one pair |

The oracle is the scenario's own (`oracle.py`) if the definition names one, else the
generic oracle with its derived controls. The reviewer checks the rest of S3. The report
lists what S4 does not verify. S5 needs the embodied backend, which does not exist yet.
Deterministic, read-only, no LLM.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dsz.certify.claim_checks import check_claims
from dsz.certify.oracle import DERIVED_CONTROLS, GENERIC_ORACLE, STALE_PROBE
from dsz.certify.predicates import PILOT_THRESHOLDS, Thresholds, h1, memory_gap, unseen
from dsz.certify.runner import RunResult, run_policy
from dsz.certify.text_checks import announced_events, skill_sequences
from dsz.core.rng import RngStreams
from dsz.scenario import (
    ScenarioSpec,
    SpecError,
    SpecScenario,
    load_scenario,
    load_spec,
    validate_instance,
)
from dsz.world.manifest import MissingCapabilities

PASS, FAIL = "pass", "fail"
GENERIC_CONTROLS = ("noop",)
MIN_DAYS = 2
ID_PATTERN = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")
NOT_BUILT = ("S3 here runs the kind-A checks only; the reviewer checks the rest. S5 is not built (no embodied "
             "backend). Thresholds and numbers are pilot, not benchmark results.")
NOT_VERIFIED = (
    "Not verified: the irrecoverable half of R1 (no run can show that no policy saves the work item)",
    "Not verified: C1 (d) and CR4 cues; MR4 (look-again cost against slack); OC3 for a scenario's own oracle",
    "Not verified: CR10. The generic oracle reads ground truth, so it does not find failures by sensing",
)


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


def verify(folder: str | Path, seeds: int = 5, thresholds: Thresholds = PILOT_THRESHOLDS) -> Report:
    """Run S1 to S4 on the scenario in `folder`, stopping at the first failed stage."""
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
    report.stages.append(_certify(scenario, seeds, report.runs, thresholds))
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


def _certify(scenario: SpecScenario, seeds: int, runs: list[dict[str, Any]], th: Thresholds) -> StageResult:
    """Run OC1, V1 and the trace predicates H1, M1, R1 (recoverable half) and C1 on every pair; OC2 on one."""
    spec = scenario.spec
    stage = StageResult("S4 certify", PASS, notes=list(NOT_VERIFIED))
    oracle = spec.oracle.name if spec.oracle else GENERIC_ORACLE
    params = {c.name: c.params for c in spec.controls}
    derived = () if spec.oracle else DERIVED_CONTROLS
    controls = list(params) + [c for c in (*GENERIC_CONTROLS, *derived) if c not in params]
    params[oracle] = spec.oracle.params if spec.oracle else {}
    held = {"H1": 0, "M1": 0, "R1": 0, "C1": 0}
    pairs = [(days, seed) for days in range(spec.min_days, spec.default_days + 1) for seed in range(seeds)]
    for days, seed in pairs:
        where = f"seed {seed}, {days} days"
        results = {oracle: run_policy(scenario, oracle, params[oracle], seed, days, check_oc1=True)}
        results.update({c: run_policy(scenario, c, params.get(c, {}), seed, days) for c in controls})
        runs.extend({**r.row(), "role": "oracle" if n == oracle else "control"} for n, r in results.items())
        stage.problems += _v1(results, oracle, where)
        for name, problem in _predicates(scenario, results, oracle, seed, days, th).items():
            if problem:
                stage.problems.append(f"{name}: at {where}: {problem}")
            else:
                held[name] += 1
    stage.problems += _oc2(scenario, oracle, params[oracle], spec.default_days)
    if not spec.oracle and any(p.startswith(("V1: generic_oracle", "generic_oracle crashed")) for p in stage.problems):
        stage.problems.append("The generic oracle cannot do this scenario. By spec section 6 it needs scheduling "
                              "or search: change the scenario")
    stage.summary = (_tally(runs, [oracle, *controls]) + "; "
                     + ", ".join(f"{k} {v}/{len(pairs)} pairs" for k, v in held.items()))
    stage.status = FAIL if stage.problems else PASS
    return stage


def _v1(results: dict[str, RunResult], oracle: str, where: str) -> list[str]:
    """Return crashes, OC1 and V1 problems for one pair."""
    out = []
    for name, r in results.items():
        if r.error:
            out.append(f"{name} crashed at {where}: {r.error}")
        elif name == oracle and not r.passed:
            out.append(f"V1: {name} fails at {where} (score {r.score:.2f}): " + "; ".join(r.notes))
        elif name != oracle and r.passed:
            out.append(f"V1: control '{name}' passes at {where} (score {r.score:.2f}). "
                       "The difficulty it removes is missing")
    if results[oracle].oc1:
        out.append(f"{results[oracle].oc1} ({where})")
    return out


def _predicates(scenario: SpecScenario, results: dict[str, RunResult], oracle: str, seed: int, days: int,
                th: Thresholds) -> dict[str, str | None]:
    """Return predicate -> problem (None if it holds) for one pair. The checks need a passing oracle run."""
    o = results[oracle]
    if o.error or not o.passed:
        return {k: "not checked: the oracle did not pass" for k in ("H1", "M1", "R1", "C1")}
    claims = scenario.spec.claims
    found: dict[str, str | None] = {"H1": "; ".join(h1(o.calls, th)) or None}

    gaps = {c["id"]: memory_gap(o.calls, c, o.instance, o.item_types) for c in claims if c.get("property") == "P2"}
    best = max(gaps.values(), default=0)
    found["M1"] = None if best >= th.memory_gap else (
        f"largest memory gap {best} motor calls < k {th.memory_gap} ({_gap_list(gaps)})")

    never = results.get("never_recover") or run_policy(scenario, "never_recover", {}, seed, days)
    found["R1"] = (f"never_recover crashed: {never.error}" if never.error else
                   "never_recover passes, so no recoverable failure needed recovery" if never.passed else None)

    events = [c["event"] for c in claims if c.get("property") == "P3" and c.get("event")]
    why = [_c1(scenario, o, e, seed, days) for e in events]
    found["C1"] = None if any(w is None for w in why) else ("; ".join(why) or "no P3 claim names an event")
    return found


def _c1(scenario: SpecScenario, o: RunResult, event: str, seed: int, days: int) -> str | None:
    """Return why one claimed event fails C1 (a) or (c) on this pair, or None if it holds.

    (c) runs the generic oracle that misses this one event's moves until the robot looks.
    """
    if not unseen(o.calls, o.instance, event):
        return f"the robot can see event '{event}' happen (a)"
    stale = run_policy(scenario, STALE_PROBE, {"event": event}, seed, days)
    if stale.error:
        return f"{STALE_PROBE} crashed: {stale.error}"
    if stale.on_time >= o.on_time:
        return (f"a policy that misses event '{event}' still does {stale.on_time} work items on time, "
                f"like the oracle ({o.on_time}) (c)")
    return None


def _oc2(scenario: SpecScenario, oracle: str, params: dict, days: int) -> list[str]:
    """Return an OC2 problem if two oracle runs on seed 0 make different skill calls."""
    a, b = (run_policy(scenario, oracle, params, 0, days) for _ in range(2))
    same = [(c.t, c.name, c.args) for c in a.calls] == [(c.t, c.name, c.args) for c in b.calls]
    return [] if same else [f"OC2: two oracle runs at seed 0, {days} days differ"]


def _gap_list(gaps: dict[str, int]) -> str:
    """Return `claim=gap` pairs, or say that there is no P2 claim."""
    return ", ".join(f"{k}={v}" for k, v in gaps.items()) or "no P2 claim"


def _tally(runs: list[dict[str, Any]], policies: list[str]) -> str:
    """Return `name passed/total` for each policy."""
    out = []
    for name in policies:
        rows = [r for r in runs if r["policy"] == name]
        out.append(f"{name} {sum(bool(r.get('passed')) for r in rows)}/{len(rows)} passed")
    return "; ".join(out)
