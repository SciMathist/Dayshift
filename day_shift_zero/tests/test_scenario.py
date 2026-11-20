"""Tests for dsz.scenario: parse, compile, generate, materialize, work tracking and success."""

import copy
import sys
import textwrap

import pytest
import yaml

from dsz.core.rng import RngStreams
from dsz.core.types import Location, LocationKind, SkillCall
from dsz.eval.controls import NoOpPolicy
from dsz.scenario import SpecError, compile_spec, load_spec, materialize, parse_spec
from dsz.world.manifest import MissingCapabilities

DELI = {
    "id": "test_deli",
    "objective": "Pack and dispatch lunch boxes on time.",
    "horizon": {"type": "continuous", "days": 2},
    "fixtures": {"fridge": "fridge", "counter": "counter", "dispatch": "dispatch_shelf",
                 "inbox": "delivery_shelf", "cupboard": "cabinet"},
    "modules": {"spoilage": {}},
    "actors": [{"role": "supplier", "name": "acme", "fixture": "inbox", "lead_time_days": [1, 1]}],
    "generator": {"name": "template", "params": {
        "initial": [{"type": "cheese", "count": 2, "at": "fridge"}, {"type": "bread", "count": 1, "at": "cupboard"}],
        "pool": {"cheese": 4},
        "subjects": ["c1"],
        "facts": [{"id": "c1_dairy", "subject": "c1", "text": "c1 cannot eat dairy.", "at": {"day": 0, "minute": 500},
                   "constraint": {"exclude_allergens": ["dairy"]}}],
        "work": [{"kind": "order", "per_day": [1, 1], "window": [600, 600], "lead": [120, 120], "collect": True,
                  "variants": [{"deliver": {"item_type": "meal_box", "stages": ["packed"], "at": "dispatch"},
                                "ticket": "Order {work_id} for {subject}: one lunch box by {due}."}]}],
        "events": [{"kind": "relocate", "payload": {"item_type": "bread", "to": "fridge"},
                    "at": {"day": 1, "minute": 60}}],
    }},
    "success": {"criteria": {"work_completion": {"params": {"min_on_time": 1.0}},
                             "no_violations": {}, "waste": {"required": False, "weight": 0.5}}},
    "policies": {"controls": ["noop"]},
}


def _deli(**override):
    """Return a deep copy of the DELI definition with top-level overrides."""
    d = copy.deepcopy(DELI)
    d.update(override)
    return d


def _instance(days=1, seed=0, raw=None):
    """Compile and generate an instance."""
    sc = compile_spec(parse_spec(raw or DELI))
    return sc, sc.generate(seed, sc.horizon(days), RngStreams(seed))


def test_parser_reports_every_problem_at_once():
    """Structural errors are collected, not raised one by one."""
    with pytest.raises(SpecError) as e:
        parse_spec({"id": 3, "horizon": {"type": "weekly"}, "fixtures": [], "colour": "red"})
    msgs = "\n".join(e.value.problems)
    for needle in ("'id' must be str", "missing 'objective'", "horizon.type", "'fixtures' must be dict",
                   "generator must be", "success.criteria", "unknown top-level key 'colour'"):
        assert needle in msgs


def test_compiler_rejects_unknown_plugins_capabilities_params_and_references():
    """Compile fails early, naming the problem."""
    with pytest.raises(SpecError, match="unknown success criterion 'vibes'"):
        compile_spec(parse_spec(_deli(success={"criteria": {"vibes": {}}})))
    with pytest.raises(MissingCapabilities, match="blast_chiller"):
        compile_spec(parse_spec(_deli(fixtures={**DELI["fixtures"], "bc": "blast_chiller"})))
    with pytest.raises(SpecError, match="invalid module or actor settings"):
        compile_spec(parse_spec(_deli(modules={"spoilage": {"rate": -1}})))
    bad = copy.deepcopy(DELI)
    bad["generator"]["params"]["initial"][0]["at"] = "garage"
    with pytest.raises(SpecError, match="unknown fixture 'garage'"):
        compile_spec(parse_spec(bad))


def test_generation_is_deterministic_and_prefix_stable():
    """Same seed, same instance; a 1-day instance is the prefix of a 2-day one."""
    _, a = _instance(days=2, seed=4)
    _, b = _instance(days=2, seed=4)
    _, one = _instance(days=1, seed=4)
    assert a == b
    assert a.prefix(1) == one
    assert [w.work_id for w in a.work] == ["order-d1-01", "order-d2-01"]


def test_fact_becomes_hidden_constraint_on_later_work():
    """The dairy fact joins the deliver predicate but never the ticket text."""
    _, inst = _instance(days=1)
    w = inst.work[0]
    assert w.spec["deliver"]["exclude_allergens"] == ["dairy"]
    assert "dairy" not in w.spec["ticket"]["text"]
    assert inst.facts[0].needed_by == ("order-d1-01",)


def _solve_day_one(run, with_cheese: bool):
    """Scripted fetch-pack-dispatch for the day-1 order; returns the verdict."""
    run.act(SkillCall("wait", {"minutes": 480}))
    run.act(SkillCall("wait", {"minutes": 120}))
    run.act(SkillCall("navigate_to", {"fixture": "cupboard"}))
    run.act(SkillCall("open", {"fixture": "cupboard"}))
    run.act(SkillCall("pick", {"index": 0}))
    run.act(SkillCall("navigate_to", {"fixture": "counter"}))
    run.act(SkillCall("place", {"fixture": "counter"}))
    if with_cheese:
        run.act(SkillCall("navigate_to", {"fixture": "fridge"}))
        run.act(SkillCall("open", {"fixture": "fridge"}))
        run.act(SkillCall("pick", {"index": 0}))
        run.act(SkillCall("navigate_to", {"fixture": "counter"}))
        run.act(SkillCall("place", {"fixture": "counter"}))
    r = run.act(SkillCall("start_process", {"process": "pack", "fixture": "counter"}))
    assert r.message == "pack started"
    run.act(SkillCall("wait", {"minutes": 5}))
    run.act(SkillCall("pick", {"index": 0}))
    run.act(SkillCall("navigate_to", {"fixture": "dispatch"}))
    run.act(SkillCall("place", {"fixture": "dispatch"}))
    return run


def test_materialized_run_reveals_fact_and_ticket_then_tracks_delivery():
    """End to end: the robot hears the fact and the ticket, packs, dispatches; the courier collects."""
    sc, inst = _instance(days=1)
    run = materialize(sc, inst)
    assert run.observe().messages == ()
    run = _solve_day_one(run, with_cheese=False)
    texts = [m.text for m in run.hub.history]
    assert texts[0] == "c1 cannot eat dairy." and texts[1].startswith("Order order-d1-01 for c1")
    st = run.tracker.status["order-d1-01"]
    assert st.on_time and st.violations == []
    assert run.world.item(st.item_id).location.kind is LocationKind.DISCARDED  # collected
    run.advance_to(run.end)
    v = run.verdict()
    assert v.passed and v.components["work_completion"] == 1.0


def test_forgetting_the_fact_is_a_violation():
    """Packing cheese for c1 completes the work but breaks the hidden dairy constraint (M1 failure)."""
    sc, inst = _instance(days=1)
    run = _solve_day_one(materialize(sc, inst), with_cheese=True)
    assert run.tracker.status["order-d1-01"].violations == ["allergen:dairy"]
    run.advance_to(run.end)
    assert not run.verdict().passed


def test_noop_control_fails_and_exogenous_events_still_happen():
    """The no-op control misses all work; the day-2 relocation moves the bread anyway."""
    sc, inst = _instance(days=2)
    run = materialize(sc, inst)
    policy = NoOpPolicy()
    policy.reset(run.brief())
    obs = run.observe()
    while not run.done:
        result = run.act(policy.act(obs))
        obs = run.observe(result)
    v = run.verdict()
    assert not v.passed and v.components["work_completion"] == 0.0
    assert run.world.items_of_type("bread", LocationKind.FIXTURE)[0].location == Location.at("fridge")
    assert sum(e.kind == "work.expired" for e in run.bus.events) == 2


def test_full_state_only_when_requested():
    """pi_sym gets the world snapshot; the default run does not."""
    sc, inst = _instance(days=1)
    assert materialize(sc, inst).observe().state is None
    assert "cheese_001" in materialize(sc, inst, full_state=True).observe().state["items"]


def test_yaml_definition_and_scenario_plugin_module(tmp_path, monkeypatch):
    """A YAML file plus a plugin module registers and uses a scenario-specific criterion."""
    (tmp_path / "deli_plugins.py").write_text(textwrap.dedent('''
        """Test plugin: a criterion that always passes."""
        from dsz.core.success import Criterion, CriterionResult
        from dsz.scenario.registries import register_criterion

        @register_criterion
        class AlwaysPass(Criterion):
            """Pass unconditionally."""

            name = "test_always_pass"

            def evaluate(self, world, truth):
                """Return a perfect score."""
                return CriterionResult(True, 1.0)
    '''))
    monkeypatch.syspath_prepend(str(tmp_path))
    raw = _deli(plugins=["deli_plugins"], success={"criteria": {"test_always_pass": {}}})
    path = tmp_path / "deli.yaml"
    path.write_text(yaml.safe_dump(raw))
    sc = compile_spec(load_spec(path))
    inst = sc.generate(0, sc.horizon(1), RngStreams(0))
    run = materialize(sc, inst)
    run.advance_to(run.end)
    assert run.verdict().passed
    sys.modules.pop("deli_plugins", None)
