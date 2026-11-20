"""Contract for dynamics modules: continuous, time-driven change that is independent of the agent."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Mapping

from dsz.core.types import CapabilitySet, SimMinutes

if TYPE_CHECKING:
    import numpy as np

    from dsz.core.events import EventBus
    from dsz.world.state import WorldState


class DynamicsModule(ABC):
    """Evolve the semantic world over time, independent of the agent.

    The scenario's `modules:` block configures each module once. The runner then advances
    it in fixed ticks. A module must be deterministic given its own RNG stream.
    To add a module: subclass, set `name`, implement `advance`, register in `MODULES`.
    """

    name: ClassVar[str]

    def __init__(self, params: Mapping[str, Any]) -> None:
        """Store the module parameters from the scenario definition and validate them."""
        self.params = dict(params)
        self.validate()

    def validate(self) -> None:
        """Raise ValueError if `self.params` is invalid. Default: accept anything."""

    def requires(self) -> CapabilitySet:
        """Return the platform capabilities this module needs. Default: none."""
        return CapabilitySet()

    @abstractmethod
    def advance(
        self, world: WorldState, t0: SimMinutes, t1: SimMinutes, rng: np.random.Generator, bus: EventBus
    ) -> None:
        """Apply the module's effects over the interval [t0, t1)."""
