"""Skill contract (Command pattern) and the narrow services a skill may use.

A skill sees only Actuation, Perception and three small services. It never sees
GroundTruth, the world state or the event bus, so skills cannot leak hidden state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Mapping, Protocol

from dsz.core.sim import Actuation, Perception
from dsz.core.types import SensorReading, SimMinutes


class SkillArgError(ValueError):
    """A skill call has missing, extra or mistyped arguments, or a value the skill cannot use."""


class ProcessControl(Protocol):
    """Start a semantic process on everything inside a fixture."""

    def start_in(self, process: str, fixture: str) -> str | None:
        """Start `process` in `fixture`. Return None on success, else a cook-visible reason."""
        ...


class OrderDesk(Protocol):
    """Place supply orders."""

    def place(self, supplier: str, item_type: str, qty: int) -> None:
        """Send an order to `supplier`. The supplier answers by message."""
        ...


class Speech(Protocol):
    """Say something (to a customer, the client, the manager)."""

    def say(self, to: str, text: str) -> None:
        """Deliver `text` to `to`. Evaluators may check what was said (e.g. reminders)."""
        ...


@dataclass(frozen=True, slots=True)
class SkillContext:
    """Everything a skill may use. Deliberately excludes GroundTruth, WorldState and the bus."""

    actuation: Actuation
    perception: Perception
    processes: ProcessControl
    orders: OrderDesk
    speech: Speech


@dataclass(frozen=True, slots=True)
class SkillOutcome:
    """What a skill did: elapsed time, sensor feedback and a sensor-grounded message."""

    elapsed: SimMinutes
    sensors: SensorReading = SensorReading()
    message: str = ""


class Skill(ABC):
    """One skill-level action.

    To add a skill: subclass, set `name`, `doc`, `args` (and `optional`), implement
    `run`, register in `SKILLS`. The executor validates arguments before `run`.
    """

    name: ClassVar[str]
    doc: ClassVar[str]
    args: ClassVar[Mapping[str, type]] = {}
    optional: ClassVar[Mapping[str, type]] = {}

    @abstractmethod
    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Execute with validated `args`. Raise SkillArgError for values the skill cannot use."""
