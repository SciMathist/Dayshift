"""Contract for dynamics modules (the six difficulty mechanisms, made reusable)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Mapping

from dsz.core.types import SimMinutes

if TYPE_CHECKING:
    import numpy as np

    from dsz.core.events import EventBus
    from dsz.world.state import WorldState


class DynamicsModule(ABC):
    """Evolve the semantic world over time, independent of the agent.

    The scenario's `modules:` block configures each module once. The clock then advances
    it. A module must be deterministic given its RNG stream.
    """

    name: ClassVar[str]

    def __init__(self, params: Mapping[str, Any]) -> None:
        """Store the module parameters from the scenario definition."""
        self.params = dict(params)

    @abstractmethod
    def advance(
        self, world: WorldState, t0: SimMinutes, t1: SimMinutes, rng: np.random.Generator, bus: EventBus
    ) -> None:
        """Apply the module's effects over the interval [t0, t1)."""
