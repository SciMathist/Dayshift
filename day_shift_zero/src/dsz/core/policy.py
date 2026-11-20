"""The single policy protocol that every model adapter implements (VLA, VLM with harness, agent, WAM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Sequence, Union, runtime_checkable

from dsz.core.types import Detection, Message, SimMinutes, SkillCall, SkillResult


@dataclass(frozen=True, slots=True)
class TaskBrief:
    """What the policy is told at the start: the objective in words, plus interface docs."""

    scenario_id: str
    objective: str
    skills_doc: str
    horizon_days: int


@dataclass(frozen=True, slots=True)
class Observation:
    """Policy-visible observation, built only from Perception, the clock and channels."""

    t: SimMinutes
    detections: Sequence[Detection]
    images: Mapping[str, Any] = field(default_factory=dict)
    proprio: Sequence[float] = ()
    messages: Sequence[Message] = ()  # new since the last observation
    last_result: SkillResult | None = None
    state: Mapping[str, Any] | None = None  # full world state; set ONLY in the pi_sym (E1) ablation


@dataclass(frozen=True, slots=True)
class LowLevelAction:
    """Native continuous control (RoboCasa: 12-dim at 20 Hz)."""

    vector: Sequence[float]


Action = Union[SkillCall, LowLevelAction]


@runtime_checkable
class Policy(Protocol):
    """Any decision maker: a model behind an adapter, the oracle, or a negative control."""

    def reset(self, brief: TaskBrief) -> None:
        """Start a new run with `brief`."""
        ...

    def act(self, obs: Observation) -> Action:
        """Return the next action for `obs`."""
        ...
