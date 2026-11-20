"""Observation builder: the only path from the world to the policy."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from dsz.core.channels import Channels
from dsz.core.policy import Observation
from dsz.core.sim import Perception
from dsz.core.types import SimMinutes, SkillResult

StateProvider = Callable[[], Mapping[str, Any]]


class ObservationBuilder:
    """Assemble observations from Perception, the clock and channels.

    `full_state` is for the pi_sym ablation only (spec E1). The composition root must pass
    it explicitly; by default the observation carries no hidden state.
    """

    def __init__(self, perception: Perception, channels: Channels, now: Callable[[], SimMinutes],
                 full_state: StateProvider | None = None) -> None:
        """Build observations from `perception` and `channels`, stamped with `now()`."""
        self._perception = perception
        self._channels = channels
        self._now = now
        self._full_state = full_state

    def build(self, last_result: SkillResult | None = None) -> Observation:
        """Return the current observation; drains new channel messages."""
        return Observation(
            t=self._now(),
            detections=tuple(self._perception.detections()),
            images=dict(self._perception.images()),
            proprio=tuple(self._perception.proprio()),
            messages=tuple(self._channels.drain()),
            last_result=last_result,
            state=self._full_state() if self._full_state else None,
        )
