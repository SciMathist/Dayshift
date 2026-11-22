"""Tests for dsz.certify.text_checks: CR15 skill sequences and CR5 announced events."""

import copy

from dsz.certify.text_checks import announced_events, robot_texts, skill_sequences
from dsz.core.rng import RngStreams
from dsz.scenario import compile_spec, parse_spec
from tests.test_scenario import DELI


def _instance(objective: str | None = None, fact_text: str | None = None, ticket: str | None = None):
    """Return a 2-day DELI instance with the given texts replaced."""
    raw = copy.deepcopy(DELI)
    if objective is not None:
        raw["objective"] = objective
    if fact_text is not None:
        raw["generator"]["params"]["facts"][0]["text"] = fact_text
    if ticket is not None:
        raw["generator"]["params"]["work"][0]["variants"][0]["ticket"] = ticket
    sc = compile_spec(parse_spec(raw))
    return sc.generate(0, sc.horizon(2), RngStreams(0))


def test_robot_texts_cover_objective_facts_and_tickets():
    """Every text the robot receives is checked, in time order."""
    sources = [t.source for t in robot_texts(_instance())]
    assert sources[0] == "objective" and "fact c1_dairy" in sources
    assert any(s.startswith("ticket order-d1") for s in sources)


def test_goal_text_passes_cr15():
    """Outcomes, and one action per sentence, are not a sequence of skills."""
    inst = _instance(objective="Pack and dispatch lunch boxes on time. Keep cheese in the fridge. "
                               "The fridge door is open when someone forgets it. Take care of the counter.")
    assert skill_sequences(inst) == []


def test_step_lists_fail_cr15_wherever_they_appear():
    """Two or more different actions in one sentence fail, in the objective, a ticket or a fact."""
    assert "CR15: objective" in skill_sequences(_instance(objective="Open the fridge, take the cheese and put it "
                                                                    "on the counter."))[0]
    assert "CR15: ticket" in skill_sequences(_instance(ticket="{work_id}: go to the fridge and pick a cheese."))[0]
    problems = skill_sequences(_instance(fact_text="Switch the oven on and start the bake process."))
    assert problems and "(set_power, start_process)" in problems[0]


def test_announced_event_is_noted_for_cr5():
    """A message that names an event's item, place and time cannot back a P3 claim."""
    assert announced_events(_instance()) == []
    notes = announced_events(_instance(fact_text="On day 2 someone will move the bread to the fridge."))
    assert notes == ["CR5: fact c1_dairy states what, where and when of the relocate at fridge. "
                     "It cannot support a P3 claim"]


def test_partial_announcement_is_not_noted():
    """A message without the time (or the place) still leaves the robot to check: no CR5 note."""
    assert announced_events(_instance(fact_text="Someone sometimes moves the bread to the fridge.")) == []
    assert announced_events(_instance(fact_text="On day 2 someone will move the bread.")) == []
