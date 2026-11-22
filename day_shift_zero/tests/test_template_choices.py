"""Tests for `one_of` choices in the template generator: per-seed hidden placements and event targets."""

import copy

import pytest
import yaml

from dsz.certify.verify import FAIL, verify
from dsz.core.rng import RngStreams
from dsz.scenario import compile_spec, parse_spec
from tests.test_scenario import DELI

CHOICE = {"one_of": ["fridge", "cupboard"]}


def _raw(initial_at=None, relocate_to=None, random_event=False):
    """Return DELI with choices in the first initial entry and in the relocate event."""
    raw = copy.deepcopy(DELI)
    params = raw["generator"]["params"]
    if initial_at is not None:
        params["initial"][0]["at"] = initial_at
    if relocate_to is not None:
        params["events"][0]["payload"]["to"] = relocate_to
    if random_event:
        params["events"].append({"kind": "door_left_open", "per_day": [1, 2], "window": [0, 1440],
                                 "payload": {"fixture": {"one_of": ["fridge", "cupboard"]}}})
    return raw


def _instance(raw, seed=0, days=2):
    """Compile `raw` and generate one instance."""
    sc = compile_spec(parse_spec(raw))
    return sc.generate(seed, sc.horizon(days), RngStreams(seed))


def _cheese_places(inst):
    """Return the fixtures of the initial cheese items."""
    return {i.location.fixture for i in inst.items if i.item_type == "cheese" and i.location.in_world}


def test_initial_choice_is_per_seed_and_shared_by_the_entry():
    """Each seed puts the whole entry in one candidate; seeds differ; the same seed repeats."""
    raw = _raw(initial_at=CHOICE)
    places = [_cheese_places(_instance(raw, seed)) for seed in range(12)]
    assert all(len(p) == 1 for p in places)
    assert {next(iter(p)) for p in places} == {"fridge", "cupboard"}
    assert places[3] == _cheese_places(_instance(raw, 3))


def test_event_choice_is_per_seed_and_prefix_stable():
    """A choice in a payload varies by seed, and day 1 is the same at every horizon."""
    raw = _raw(relocate_to=CHOICE, random_event=True)
    targets = {e.payload["to"] for seed in range(12) for e in _instance(raw, seed).events if e.kind == "relocate"}
    assert targets == {"fridge", "cupboard"}
    for seed in range(5):
        short, long = _instance(raw, seed, days=1), _instance(raw, seed, days=2)
        assert list(short.events) == [e for e in long.events if e.t < 1440]


def test_a_choice_does_not_shift_other_draws():
    """Adding a choice leaves work and event times exactly as they were."""
    for seed in range(5):
        plain, chosen = _instance(_raw(), seed), _instance(_raw(initial_at=CHOICE, relocate_to=CHOICE), seed)
        assert plain.work == chosen.work
        assert [(e.t, e.kind) for e in plain.events] == [(e.t, e.kind) for e in chosen.events]


def test_empty_choice_is_rejected():
    """A choice needs at least one candidate."""
    with pytest.raises(ValueError, match="one_of needs at least one candidate"):
        _instance(_raw(relocate_to={"one_of": []}))


def test_verify_checks_choices_on_every_seed(tmp_path):
    """A bad candidate fails S2 even if seed 0 never draws it."""
    raw = _raw(initial_at={"one_of": ["fridge", "fridge", "fridge", "garage"]})
    bad_seeds = [s for s in range(40) if _raw_place(raw, s) == "garage"]
    assert bad_seeds and 0 not in bad_seeds  # the probe (seed 0) alone would miss it
    folder = tmp_path / "choice"
    folder.mkdir()
    (folder / "scenario.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    report = verify(folder, seeds=bad_seeds[0] + 1)
    assert report.stages[1].status == FAIL
    assert any("unknown fixture 'garage'" in p for p in report.stages[1].problems)


def _raw_place(raw, seed):
    """Return where seed `seed` puts the first initial entry, without compiling (no reference check)."""
    from dsz.scenario.template import _choose  # private helper: the draw the generator uses
    return _choose(raw["generator"]["params"]["initial"][0]["at"], RngStreams(seed).indexed("initial.0.choice", 0))
