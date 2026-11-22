"""Tests for scenario folders, the verifier (`dsz verify`) and the vocabulary reference (`dsz vocab`)."""

import copy
import json
import textwrap
from pathlib import Path

import pytest
import yaml

from dsz.certify.predicates import PILOT_THRESHOLDS
from dsz.certify.verify import FAIL, PASS, _certify, verify
from dsz.cli import main
from dsz.scenario import SpecError, load_scenario, parse_spec
from dsz.scenario.vocabulary_doc import vocabulary_data, vocabulary_markdown
from tests.test_scenario import DELI

CARE_HOME = Path(__file__).resolve().parents[1] / "scenarios" / "care_home_lunches"


def _claimed(raw: dict) -> dict:
    """Return a copy of a DELI-like definition with a claims block that passes the kind-A checks."""
    raw = copy.deepcopy(raw)
    raw["generator"]["params"]["events"][0]["id"] = "move_bread"
    place = {"object": "bread", "place": "cupboard", "action": "find"}
    raw["claims"] = [
        {"id": "L1", "property": "P1", "mechanism": "lead_time", "consequence": place},
        {"id": "M1", "property": "P2", "mechanism": "hidden_state", "memory": "S", "content": "where",
         "hidden": ["cupboard", "fridge"], "consequence": place},
        {"id": "C1", "property": "P3", "mechanism": "drift", "event": "move_bread", "consequence": place},
        {"id": "R1", "property": "P4", "mechanism": "drift", "recovery": "recoverable", "consequence": place},
        {"id": "R2", "property": "P4", "mechanism": "compounding", "recovery": "irrecoverable", "consequence": place},
    ]
    return raw


def _folder(tmp_path: Path, raw: dict, oracle: str | None = None) -> Path:
    """Write a scenario folder with `raw` as scenario.yaml and an optional oracle.py."""
    folder = tmp_path / raw.get("id", "scenario")
    folder.mkdir()
    (folder / "scenario.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    if oracle is not None:
        (folder / "oracle.py").write_text(textwrap.dedent(oracle), encoding="utf-8")
    return folder


def _statuses(report) -> dict[str, str]:
    """Return stage name -> status."""
    return {s.stage: s.status for s in report.stages}


def test_min_days_defaults_to_days_and_is_bounded():
    """horizon.min_days is optional and must lie in 1..days."""
    assert parse_spec(DELI).min_days == DELI["horizon"]["days"]
    with pytest.raises(SpecError, match="min_days"):
        parse_spec({**DELI, "horizon": {"type": "continuous", "days": 2, "min_days": 3}})


def test_load_scenario_imports_the_folder_oracle(tmp_path):
    """oracle.py in the folder registers its policies, wherever the folder lives."""
    raw = {**copy.deepcopy(DELI), "id": "folder_oracle", "policies": {"oracle": "folder_oracle_wait"}}
    folder = _folder(tmp_path, raw, oracle="""
        from dsz.eval.controls import NoOpPolicy
        from dsz.scenario.registries import POLICIES
        POLICIES.add("folder_oracle_wait", lambda instance, world, params: NoOpPolicy())
    """)
    assert load_scenario(folder).spec.oracle.name == "folder_oracle_wait"


def test_parse_errors_stop_at_s1(tmp_path):
    """A missing file or a structural error fails S1 and runs nothing else."""
    report = verify(tmp_path / "nowhere")
    assert _statuses(report) == {"S1 parse": FAIL} and not report.ok
    report = verify(_folder(tmp_path, {"id": "broken", "colour": "red"}))
    assert _statuses(report) == {"S1 parse": FAIL}
    assert any("unknown top-level key 'colour'" in p for p in report.stages[0].problems)


def test_missing_capability_fails_s2(tmp_path):
    """A fixture kind the platform lacks fails S2 with the capability named."""
    raw = copy.deepcopy(DELI)
    raw["fixtures"]["bc"] = "blast_chiller"
    report = verify(_folder(tmp_path, raw))
    assert _statuses(report) == {"S1 parse": PASS, "S2 compile": FAIL}
    assert "blast_chiller" in report.stages[1].problems[0]


def test_without_oracle_s4_runs_the_generic_oracle_and_derived_controls(tmp_path):
    """No oracle named: S4 runs the generic oracle, noop and the three derived controls.

    DELI's day-2 order cannot be met (the dairy ban leaves no filling), so the generic oracle
    fails and the report says the scenario must change.
    """
    report = verify(_folder(tmp_path, _claimed(DELI)), seeds=1)
    assert {r["policy"] for r in report.runs} == {"generic_oracle", "noop", "hidden_state_blind", "never_recover",
                                                  "memoryless"}
    assert _statuses(report)["S4 certify"] == FAIL
    assert report.stages[-1].problems[-1].startswith("The generic oracle cannot do this scenario")


def test_a_passing_control_fails_s4(tmp_path):
    """Criteria that noop can meet fail V1."""
    raw = _claimed(DELI)
    raw["success"] = {"criteria": {"work_completion": {"params": {"min_on_time": 0.0}}}}
    report = verify(_folder(tmp_path, raw), seeds=1)
    assert _statuses(report)["S4 certify"] == FAIL
    assert "control 'noop' passes" in report.stages[-1].problems[0]


def test_care_home_lunches_m1_fails_cr6():
    """The reference scenario's only P2 claim names places that the objective names (task spec section 4)."""
    report = verify(CARE_HOME, seeds=1)
    assert _statuses(report) == {"S1 parse": PASS, "S2 compile": PASS, "S3 claims": FAIL}
    assert report.stages[-1].problems == [
        "CR6: claim M1: hidden place 'fridge_main' is named in a text the robot gets",
        "CR6: claim M1: hidden place 'pantry' is named in a text the robot gets"]


def test_care_home_lunches_s4_holds_v1_but_not_r1_or_c1():
    """S4 on its own: V1, OC1, OC2, H1 and M1 hold; R1 and C1 do not, because early marinating dodges the move.

    The R1 and C1 probes are built on the generic oracle, which carries the delivered chicken
    into fridge_back before the co-worker moves it.
    """
    runs: list = []
    stage = _certify(load_scenario(CARE_HOME), 1, runs, PILOT_THRESHOLDS)
    assert {r["days"] for r in runs} == {3, 4}
    assert {p.split(":")[0] for p in stage.problems} == {"R1", "C1"}, stage.problems
    assert stage.summary.endswith("H1 2/2 pairs, M1 2/2 pairs, R1 0/2 pairs, C1 0/2 pairs")


def test_cli_exit_codes_and_json(tmp_path, capsys):
    """`dsz verify` exits 0 on pass and 1 on fail, and writes the JSON report."""
    out = tmp_path / "report.json"
    assert main(["verify", str(tmp_path / "nowhere"), "--json", str(out)]) == 1
    assert '"ok": false' in out.read_text(encoding="utf-8")
    assert "RESULT: FAIL" in capsys.readouterr().out


def test_vocabulary_json_has_names_and_a_content_stamp(capsys):
    """`dsz vocab --json` lists names by category; the stamp is stable and appears in the Markdown too."""
    assert main(["vocab", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert "fridge" in data["fixture_kinds"] and "relocate" in data["events"] and len(data["stamp"]) == 12
    assert data == vocabulary_data()
    assert f"Vocabulary stamp: `{data['stamp']}`" in vocabulary_markdown()


def test_vocabulary_lists_every_registry():
    """`dsz vocab` covers fixtures, items, processes, events, modules, actors, criteria and skills."""
    doc = vocabulary_markdown()
    for needle in ("| fridge |", "| chicken_breast |", "| marinate |", "### `relocate`", "### `spoilage`",
                   "### `supplier`", "### `work_completion`", "navigate_to("):
        assert needle in doc


def test_id_and_min_days_rules_fail_s2(tmp_path):
    """A non-snake_case id or a certified set shorter than 2 days fails S2."""
    raw = {**copy.deepcopy(DELI), "id": "Bad-Id", "horizon": {"type": "continuous", "days": 2, "min_days": 1}}
    report = verify(_folder(tmp_path, raw))
    assert _statuses(report)["S2 compile"] == FAIL
    assert any(p.startswith("ID:") for p in report.stages[1].problems)
    assert any("min_days" in p for p in report.stages[1].problems)


def test_step_list_in_objective_fails_s3(tmp_path):
    """A sequence of skills in the objective fails S3 and stops before S4."""
    raw = {**_claimed(DELI), "objective": "Open the fridge, take a cheese and put it on the counter."}
    report = verify(_folder(tmp_path, raw), seeds=1)
    assert _statuses(report) == {"S1 parse": PASS, "S2 compile": PASS, "S3 claims": FAIL}
    assert report.stages[-1].problems == [
        "CR6: claim M1: hidden place 'fridge' is named in a text the robot gets",
        "CR15: objective states a sequence of skills (open, pick, place): "
        "\"Open the fridge, take a cheese and put it on the counter\". State the outcome instead"]


def test_work_due_after_the_horizon_fails_s2(tmp_path):
    """A lead time that runs past the last day fails S2 (CR14)."""
    raw = copy.deepcopy(DELI)
    raw["generator"]["params"]["work"][0]["lead"] = [1440, 1440]
    report = verify(_folder(tmp_path, raw), seeds=1)
    assert _statuses(report)["S2 compile"] == FAIL
    assert report.stages[1].problems[0].startswith("CR14: at 2 days")
