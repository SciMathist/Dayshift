"""Generic negative-control policies, registered as policy factories.

Scenario-specific controls (ignores hidden state, never recovers) are usually variants
of the scenario's oracle and live with it.
"""

from __future__ import annotations

from typing import Any, Mapping

from dsz.core.policy import Action, Observation, Policy, TaskBrief
from dsz.core.scenario import Instance
from dsz.core.types import SkillCall
from dsz.scenario.registries import POLICIES
from dsz.world.state import WorldState


class NoOpPolicy:
    """Do nothing useful: wait in fixed steps forever."""

    def __init__(self, step_minutes: int = 60) -> None:
        """Wait `step_minutes` per action."""
        self._call = SkillCall("wait", {"minutes": step_minutes})

    def reset(self, brief: TaskBrief) -> None:
        """Ignore the brief."""

    def act(self, obs: Observation) -> Action:
        """Always wait."""
        return self._call


def _noop_factory(instance: Instance, world: WorldState, params: Mapping[str, Any]) -> Policy:
    """Build a NoOpPolicy; params: step_minutes (default 60)."""
    return NoOpPolicy(int(params.get("step_minutes", 60)))


POLICIES.add("noop", _noop_factory)
