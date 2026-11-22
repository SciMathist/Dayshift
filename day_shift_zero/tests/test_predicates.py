"""Tests for dsz.certify.predicates and dsz.certify.runner: H1 chains, M1 gaps, C1 (a), OC1 and the C1 probe."""

import copy

from dsz.certify.predicates import Call, Thresholds, h1, longest_chain, memory_gap, unseen
from dsz.certify.runner import run_policy
from dsz.core.policy import Observation, TaskBrief
from dsz.core.rng import RngStreams
from dsz.core.types import Location, SkillCall
from dsz.scenario import POLICIES, compile_spec, parse_spec
from tests.test_generic_oracle import KITCHEN

DAY = 1440


def _call(t, name, at=None, held_before=None, held_after=None, seen=(), view=False, **args):
    """Return one recorded call; `at` is where the robot is after it."""
    return Call(t, name, args, at, at, held_before, held_after, seen=tuple(seen), view=view)


def _fetch_and_store(t, item, src, dest):
    """Return the calls that carry `item` from `src` to `dest`."""
    return [_call(t, "navigate_to", src, fixture=src), _call(t + 1, "pick", src, held_after=item, index=0),
            _call(t + 2, "navigate_to", dest, held_before=item, held_after=item, fixture=dest),
            _call(t + 3, "place", dest, held_before=item, seen=[item], view=True, fixture=dest)]


def test_chain_follows_an_item_across_a_day():
    """Store an item on day 1 and use it on day 2: the chain links through the item and crosses the day.

    navigate_to needs nothing, so the chain is navigate, pick, place (day 1), pick, place (day 2).
    """
    calls = _fetch_and_store(100, "x", "dock", "fridge") + _fetch_and_store(DAY + 100, "x", "fridge", "pass")
    assert longest_chain(calls) == (5, True)
    assert longest_chain(_fetch_and_store(100, "x", "dock", "fridge")) == (3, False)


def test_unrelated_calls_do_not_lengthen_the_chain():
    """Moving two different items gives two chains, not one long chain."""
    calls = _fetch_and_store(100, "x", "dock", "fridge") + _fetch_and_store(200, "y", "dock", "pantry")
    assert longest_chain(calls)[0] == 3


def test_h1_reports_each_threshold_it_misses():
    """Too few calls, too short a chain and no day crossing are three separate problems."""
    calls = _fetch_and_store(100, "x", "dock", "fridge")
    assert h1(calls, Thresholds(calls=10, chain=5, memory_gap=1)) == [
        "4 motor skill calls < theta_L 10", "longest dependency chain 3 < theta_D 5",
        "no link of the longest dependency chain crosses a day boundary"]


def test_memory_gap_counts_calls_between_last_sight_and_the_pick():
    """Class S: seen when stored, used after 3 unrelated calls elsewhere."""
    calls = _fetch_and_store(100, "x", "dock", "fridge") + [
        _call(110, "navigate_to", "stove", fixture="stove"), _call(111, "set_power", "stove", fixture="stove", on=True),
        _call(112, "set_power", "stove", fixture="stove", on=False),
        _call(120, "navigate_to", "fridge", fixture="fridge"), _call(121, "pick", "fridge", held_after="x", index=0)]
    claim = {"memory": "S", "hidden": ["fridge", "pantry"], "consequence": {"object": "chicken_breast"}}
    assert memory_gap(calls, claim, None, {"x": "chicken_breast"}) == 3


def test_event_seen_only_if_the_robot_could_see_its_fixture_when_it_fired():
    """The robot's place at an event is where the last call before the event left it."""
    scenario = compile_spec(parse_spec(copy.deepcopy(KITCHEN)))
    instance = scenario.generate(0, scenario.horizon(), RngStreams(0))  # the move fires at minute 780
    at_counter = [_call(700, "navigate_to", "counter", view=True, fixture="counter")]
    elsewhere = at_counter + [_call(770, "navigate_to", "pass", view=True, fixture="pass"),
                              _call(780, "navigate_to", "counter", view=True, fixture="counter")]
    assert not unseen(at_counter, instance, "coworker_move")
    assert unseen(elsewhere, instance, "coworker_move")


class _Cheat:
    """A policy that moves an item by hand while deciding (breaks OC1)."""

    def __init__(self, world):
        """Keep the world."""
        self._world = world

    def reset(self, brief: TaskBrief) -> None:
        """Nothing to reset."""

    def act(self, obs: Observation) -> SkillCall:
        """Teleport the chicken to the pass, then wait."""
        self._world.move("chicken_breast_001", Location.at("pass"), cause="cheat")
        return SkillCall("wait", {"minutes": 60})


def test_oc1_catches_a_policy_that_edits_the_world():
    """A world change made inside act() is reported; a fair policy is not."""
    if "test_cheat" not in POLICIES:
        POLICIES.add("test_cheat", lambda instance, world, params: _Cheat(world))
    scenario = compile_spec(parse_spec(copy.deepcopy(KITCHEN)))
    assert run_policy(scenario, "test_cheat", {}, 0, 2, check_oc1=True).oc1.startswith("OC1: the world changed")
    assert run_policy(scenario, "generic_oracle", {}, 0, 2, check_oc1=True).oc1 is None


def test_stale_probe_misses_the_event_and_loses_work():
    """The C1 probe believes the moved chicken is still in the fridge, so it misses day 2's lunch."""
    scenario = compile_spec(parse_spec(copy.deepcopy(KITCHEN)))
    oracle = run_policy(scenario, "generic_oracle", {}, 0, 2)
    probe = run_policy(scenario, "stale_after_event", {"event": "coworker_move"}, 0, 2)
    assert (oracle.on_time, probe.on_time) == (2, 1)
