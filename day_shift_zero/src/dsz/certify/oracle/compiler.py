"""Skill compiler: turn oracle steps (visit, leave, move, pick) into skill calls.

Evaluator-side. A step reads the world state when it runs, so it picks the detection
index that is correct at that moment. A step never edits the world (rule OC1).
"""

from __future__ import annotations

from typing import Any, Callable

from dsz.core.types import SkillCall
from dsz.world.state import WorldState

Step = Callable[[WorldState], "SkillCall | None"]
Select = Callable[[WorldState], "str | None"]


def call(name: str, **args: Any) -> Step:
    """Return a step that always issues the same skill call."""
    return lambda world: SkillCall(name, dict(args))


def pick(select: Select) -> Step:
    """Return a step that grasps the selected item by its index in the current detections.

    The index follows the symbolic backend's detection order (visible ids, sorted). The
    step returns None when the item is not visible, so the caller can skip it.
    """
    def step(world: WorldState) -> SkillCall | None:
        """Find the selected item among the visible ids and pick it by index."""
        iid = select(world)
        visible = sorted(i.item_id for i in world.items_at(world.robot_at)) if world.robot_at else []
        return SkillCall("pick", {"index": visible.index(iid)}) if iid in visible else None
    return step


class SkillCompiler:
    """Compile visits and moves for one world. Open and close doors where a fixture has one."""

    def __init__(self, world: WorldState) -> None:
        """Compile against `world`, which tells which fixtures have doors."""
        self._world = world

    def visit(self, fixture: str) -> list[Step]:
        """Return steps that drive to `fixture` and open its door if it has one."""
        door = [call("open", fixture=fixture)] if self._has_door(fixture) else []
        return [call("navigate_to", fixture=fixture)] + door

    def leave(self, fixture: str) -> list[Step]:
        """Return the step that closes the door of `fixture`, if it has one."""
        return [call("close", fixture=fixture)] if self._has_door(fixture) else []

    def move(self, item_id: str, src: str, dest: str) -> list[Step]:
        """Return steps that carry one item from `src` to `dest`."""
        return (self.visit(src) + [pick(lambda w: item_id)] + self.leave(src)
                + self.visit(dest) + [call("place", fixture=dest)] + self.leave(dest))

    def _has_door(self, fixture: str) -> bool:
        """Return True if the fixture's kind has a door."""
        return self._world.fixture(fixture).spec.has_door
