"""Tests for dsz.certify.oracle: the skill compiler."""

from dsz.certify.oracle import SkillCompiler, call, pick
from dsz.core.types import Location, SkillCall


def _calls(steps, world):
    """Run each step against `world` and return the skill calls it issues."""
    return [s(world) for s in steps]


def test_move_opens_and_closes_doors_only_where_a_fixture_has_one(world):
    """A move from the fridge (door) to the counter (no door) opens and closes only the fridge."""
    world.add_item("milk_1", "milk", Location.at("fridge"))
    world.robot_at = "fridge"
    names = [(c.name, c.args) for c in _calls(SkillCompiler(world).move("milk_1", "fridge", "counter"), world)]
    assert names == [("navigate_to", {"fixture": "fridge"}), ("open", {"fixture": "fridge"}),
                     ("pick", {"index": 0}), ("close", {"fixture": "fridge"}),
                     ("navigate_to", {"fixture": "counter"}), ("place", {"fixture": "counter"})]


def test_pick_uses_the_index_in_sorted_visible_ids(world):
    """The pick index is the item's position among the visible ids, sorted."""
    for iid in ("milk_2", "milk_1", "egg_1"):
        world.add_item(iid, iid.split("_")[0], Location.at("fridge"))
    world.robot_at = "fridge"
    assert pick(lambda w: "milk_1")(world) == SkillCall("pick", {"index": 1})


def test_pick_yields_none_when_the_item_is_not_visible(world):
    """A pick of an item at another fixture, or with the robot nowhere, issues no call."""
    world.add_item("milk_1", "milk", Location.at("fridge"))
    assert pick(lambda w: "milk_1")(world) is None
    world.robot_at = "counter"
    assert pick(lambda w: "milk_1")(world) is None


def test_call_issues_a_fresh_args_dict_each_time(world):
    """Two runs of one call step do not share the args dict."""
    step = call("wait", minutes=5)
    first = step(world)
    first.args["minutes"] = 9
    assert step(world) == SkillCall("wait", {"minutes": 5})
