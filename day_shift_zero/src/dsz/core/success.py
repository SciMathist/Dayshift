"""Success contracts: a SuccessCheck judges a run; Criterion plugins are its reusable parts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Mapping

from dsz.core.types import Verdict

if TYPE_CHECKING:
    from dsz.core.events import EventBus
    from dsz.core.scenario import Instance
    from dsz.core.sim import GroundTruth
    from dsz.world.state import WorldState


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """One criterion's outcome. `passed` is None for graded-only criteria."""

    passed: bool | None
    score: float  # 0..1
    notes: tuple[str, ...] = ()


class Criterion(ABC):
    """A reusable success criterion (Observer: it may listen to the bus during the run).

    To add one: subclass, set `name`, implement `evaluate` (and `attach` if it needs
    events), register in `CRITERIA`. Then name it in a scenario's `success:` block.
    """

    name: ClassVar[str]

    def __init__(self, params: Mapping[str, Any]) -> None:
        """Store parameters and validate them."""
        self.params = dict(params)
        self.validate()

    def validate(self) -> None:
        """Raise ValueError on invalid parameters. Default: accept anything."""

    def attach(self, bus: EventBus, instance: Instance) -> None:
        """Subscribe to the events this criterion needs. Default: none."""

    @abstractmethod
    def evaluate(self, world: WorldState, truth: GroundTruth) -> CriterionResult:
        """Judge the run at its end."""


class SuccessCheck(ABC):
    """Judge a whole run: attach before it starts, ask for the verdict at its end."""

    @abstractmethod
    def attach(self, bus: EventBus, instance: Instance) -> None:
        """Subscribe to run events."""

    @abstractmethod
    def verdict(self, world: WorldState, truth: GroundTruth) -> Verdict:
        """Return the binary pass and graded score."""
