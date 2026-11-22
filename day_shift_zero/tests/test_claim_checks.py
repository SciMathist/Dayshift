"""Tests for dsz.certify.claim_checks: the kind-A checks on the definition's claims block."""

import copy

import pytest

from dsz.certify.claim_checks import check_claims
from dsz.core.rng import RngStreams
from dsz.scenario import SpecError, compile_spec, parse_spec
from tests.test_generic_oracle import KITCHEN


def _problems(edit=None, **claim_changes) -> list[str]:
    """Return the claim problems of KITCHEN after `edit(raw)` and changes to claim M1 or C1."""
    raw = copy.deepcopy(KITCHEN)
    if edit:
        edit(raw)
    for cid, change in claim_changes.items():
        claim = next(c for c in raw["claims"] if c["id"] == cid)
        claim.update({k: v for k, v in change.items() if v is not None})
        for k in [k for k, v in change.items() if v is None]:
            claim.pop(k, None)
    scenario = compile_spec(parse_spec(raw))
    return check_claims(scenario.spec, [scenario.generate(s, scenario.horizon(), RngStreams(s)) for s in range(2)])


def test_valid_claims_pass():
    """The test kitchen's claims meet every kind-A rule."""
    assert _problems() == []


def test_missing_claims_and_coverage():
    """No claims at all, a property without a claim, and a P4 without an irrecoverable claim all fail."""
    assert _problems(lambda raw: raw.pop("claims")) == ["P1-P4: the definition has no claims"]
    no_p1 = _problems(lambda raw: raw.update(claims=[c for c in raw["claims"] if c["id"] != "L1"]))
    assert no_p1 == ["P1: no claim supports P1"]
    one_p4 = _problems(lambda raw: raw.update(claims=[c for c in raw["claims"] if c["id"] != "R2"]))
    assert one_p4 == ["R1: P4 needs one recoverable and one irrecoverable claim"]


def test_cr1_and_cr2_need_known_labels_and_a_physical_consequence():
    """Property, mechanism and each part of the consequence must be known names."""
    problems = _problems(M1={"property": "P5", "mechanism": "vibes",
                             "consequence": {"object": "unicorn", "place": "attic", "action": "think"}})
    assert [p.split(":")[0] for p in problems] == ["CR1", "CR1", "CR2", "CR2", "CR2", "P2"]


def test_memory_rules():
    """MR1 class, MR2 content and numbers in the fact, MR3 fact and hidden places for class T."""
    def add_fact(raw):
        """Add a fact that states a time."""
        raw["generator"]["params"]["facts"] = [{"id": "noon", "at": {"day": 0, "minute": 60},
                                                "text": "Lunch is at 12:00."}]
    problems = _problems(add_fact, M1={"memory": "X", "content": "when", "fact": "noon"})
    assert [p.split(":")[0] for p in problems] == ["MR1", "MR2", "MR2"]
    problems = _problems(M1={"memory": "T", "mechanism": "facts", "hidden": None})
    assert [p.split(":")[0] for p in problems] == ["MR3", "CR6"]


def test_cr6_hidden_places_must_be_two_unnamed_fixtures():
    """Fewer than two candidates, an unknown fixture, or a place named in a text all fail."""
    assert _problems(M1={"hidden": ["fridge"]}) == ["CR6: claim M1: hidden must list at least 2 candidate fixtures"]
    assert _problems(M1={"hidden": ["fridge", "garage"]}) == ["CR6: claim M1: hidden place 'garage' is not a fixture"]
    named = _problems(lambda raw: raw.update(objective="Keep the chicken in the fridge."))
    assert named == ["CR6: claim M1: hidden place 'fridge' is named in a text the robot gets"]


def test_p3_claim_needs_an_unseen_unannounced_event():
    """A P3 claim names an event that the robot neither sees nor is told about (C1, CR5)."""
    assert _problems(C1={"event": None}) == ["C1: claim C1: a P3 claim names its `event`"]
    assert _problems(C1={"event": "nope"}) == ["S3: claim C1: unknown event 'nope' (give the event an `id`)"]

    def observable(raw):
        """Make the co-worker's move observable."""
        raw["generator"]["params"]["events"][1]["observable"] = True
    assert _problems(observable) == ["C1: claim C1: event 'coworker_move' is observable; the robot must not see "
                                     "it happen"]

    def announce(raw):
        """Tell the robot about the move in advance."""
        raw["generator"]["params"]["facts"] = [{"id": "warn", "at": {"day": 0, "minute": 60},
                                                "text": "At 13:00 someone will move a chicken to the counter."}]
    assert _problems(announce) == ["CR6: claim M1: hidden place 'counter' is named in a text the robot gets",
                                   "CR5: claim C1: a text states what, where and when of event 'coworker_move'"]


def test_parser_checks_claim_structure():
    """Claims must be a list of mappings with unique string ids (S1)."""
    for claims, message in (({"id": "x"}, "claims must be a list"), ([{"property": "P1"}], "string 'id'"),
                            ([{"id": "a"}, {"id": "a"}], "unique")):
        with pytest.raises(SpecError, match=message):
            parse_spec({**copy.deepcopy(KITCHEN), "claims": claims})
