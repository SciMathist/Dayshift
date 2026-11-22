"""Tests for the generic oracle (dsz.certify.oracle): recipe regression, oracle runs and derived controls."""

import copy

import pytest
import yaml

from dsz.certify.oracle import DERIVED_CONTROLS, GENERIC_ORACLE, RecipeError, recipe_for
from dsz.certify.predicates import Thresholds
from dsz.certify.runner import run_policy
from dsz.certify.verify import PASS, verify
from dsz.core.scenario import WorkItem
from dsz.scenario import compile_spec, parse_spec

KITCHEN = {
    "id": "test_kitchen",
    "objective": "Serve one cooked chicken lunch on the pass each day.",
    "horizon": {"type": "continuous", "days": 2, "min_days": 2},
    "fixtures": {"fridge": "fridge", "counter": "counter", "stove": "stove", "dock": "delivery_shelf",
                 "pass": "dispatch_shelf"},
    "modules": {"spoilage": {}},
    "generator": {"name": "template", "params": {
        "initial": [{"type": "chicken_breast", "count": 1, "at": "fridge"}],
        "pool": {"chicken_breast": 1},
        "work": [{"kind": "lunch", "per_day": [1, 1], "window": [600, 660], "lead": [90, 120], "collect": True,
                  "variants": [{"deliver": {"item_type": "chicken_breast", "stages": ["cooked"], "at": "pass"},
                                "ticket": "{work_id}: a cooked chicken lunch on the pass by {due}."}]}],
        # Day 2's chicken arrives on day 1; after the robot stores it, a co-worker leaves it on the warm counter.
        "events": [{"kind": "delivery", "at": {"day": 0, "minute": 420},
                    "payload": {"fixture": "dock", "items": ["chicken_breast_002"]}},
                   {"kind": "relocate", "id": "coworker_move", "at": {"day": 0, "minute": 780},
                    "payload": {"item": "chicken_breast_002", "expect_at": "fridge", "to": "counter"}}],
    }},
    "success": {"criteria": {"work_completion": {"params": {"min_on_time": 1.0}}, "no_violations": {}}},
    "claims": [
        {"id": "L1", "property": "P1", "mechanism": "resources",
         "consequence": {"object": "chicken_breast", "place": "dock", "action": "carry"}},
        {"id": "M1", "property": "P2", "mechanism": "hidden_state", "memory": "D", "content": "where",
         "hidden": ["fridge", "counter"],
         "consequence": {"object": "chicken_breast", "place": "fridge", "action": "find"}},
        {"id": "C1", "property": "P3", "mechanism": "drift", "event": "coworker_move",
         "consequence": {"object": "chicken_breast", "place": "counter", "action": "recover"}},
        {"id": "R1", "property": "P4", "mechanism": "drift", "recovery": "recoverable",
         "consequence": {"object": "chicken_breast", "place": "counter", "action": "recover"}},
        {"id": "R2", "property": "P4", "mechanism": "compounding", "recovery": "irrecoverable",
         "consequence": {"object": "chicken_breast", "place": "counter", "action": "check"}},
    ],
}
KINDS = {"oven", "fridge", "counter", "stove"}


def _work(item_type: str, stages: list[str]) -> WorkItem:
    """Return a work item that asks for `item_type` with `stages` on the pass."""
    return WorkItem("w1", "order", 0, 600, {"deliver": {"item_type": item_type, "stages": stages, "at": "pass"}})


def test_recipe_regresses_prerequisite_stages():
    """Frosting needs cooled and chilled; cooling needs baked. The recipe adds them, in order."""
    assert recipe_for(_work("cupcake", ["frosted"]), KINDS).stages == ("chill", "bake", "cool", "frost")


def test_recipe_uses_the_combining_process_for_its_product():
    """A packed meal box is made by `pack`, which combines inputs into the box."""
    recipe = recipe_for(_work("meal_box", ["packed"]), KINDS)
    assert recipe.combine == "pack" and recipe.stages == ()


def test_recipe_rejects_a_stage_no_fixture_can_add():
    """A stage without a process that this kitchen can run has no recipe."""
    with pytest.raises(RecipeError, match="smoked"):
        recipe_for(_work("steak", ["smoked"]), KINDS)
    with pytest.raises(RecipeError, match="baked"):
        recipe_for(_work("cupcake", ["baked"]), {"fridge", "counter"})


@pytest.mark.parametrize("seed", [0, 1])
def test_generic_oracle_passes_and_every_derived_control_fails(seed):
    """The oracle stores the delivery and rescues the moved chicken; each control loses day 2."""
    scenario = compile_spec(parse_spec(copy.deepcopy(KITCHEN)))
    assert run_policy(scenario, GENERIC_ORACLE, {}, seed, 2).passed
    for control in (*DERIVED_CONTROLS, "noop"):
        result = run_policy(scenario, control, {}, seed, 2)
        assert result.error is None and not result.passed, control


def test_generic_oracle_is_deterministic():
    """OC2: the same seed gives the same skill calls."""
    scenario = compile_spec(parse_spec(copy.deepcopy(KITCHEN)))
    first, second = (run_policy(scenario, GENERIC_ORACLE, {}, 0, 2).calls for _ in range(2))
    assert first == second


def _kitchen_folder(tmp_path):
    """Write KITCHEN as a scenario folder and return it."""
    folder = tmp_path / "test_kitchen"
    folder.mkdir()
    (folder / "scenario.yaml").write_text(yaml.safe_dump(KITCHEN), encoding="utf-8")
    return folder


def test_verify_certifies_a_scenario_with_no_oracle_of_its_own(tmp_path):
    """Without `policies`, S4 runs the generic oracle, its controls and the predicates, and passes.

    The kitchen is small (38 motor calls), so this test sets theta_L below the pilot value.
    """
    report = verify(_kitchen_folder(tmp_path), seeds=2, thresholds=Thresholds(calls=30, chain=6, memory_gap=10))
    assert report.ok, report.to_text()
    assert report.stages[-1].stage == "S4 certify" and report.stages[-1].status == PASS
    assert report.stages[-1].summary.endswith("H1 2/2 pairs, M1 2/2 pairs, R1 2/2 pairs, C1 2/2 pairs")


def test_pilot_thresholds_reject_a_short_scenario(tmp_path):
    """At the pilot theta_L (50 motor calls) the 2-day kitchen fails H1 on every pair."""
    report = verify(_kitchen_folder(tmp_path), seeds=1)
    assert report.stages[-1].problems == ["H1: at seed 0, 2 days: 38 motor skill calls < theta_L 50"]
