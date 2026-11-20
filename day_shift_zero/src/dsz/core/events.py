"""Domain events and the event bus contract (Observer pattern).

Everything that happens (skill executed, item spoiled, delivery arrived, message sent) is
published once. The trace writer, metrics and failure labeler subscribe independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from dsz.core.types import SimMinutes


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """A fact about the run, stamped with simulated time. Evaluator-only unless marked otherwise."""

    t: SimMinutes
    kind: str  # e.g. "skill.executed", "item.spoiled", "delivery.arrived", "message.sent"
    data: Mapping[str, Any] = field(default_factory=dict)
    evaluator_only: bool = True  # closed by default: policy-visible events must opt in


Handler = Callable[[DomainEvent], None]


class EventBus(Protocol):
    """Publish and subscribe by event-kind prefix."""

    def publish(self, event: DomainEvent) -> None:
        """Deliver `event` to every handler whose prefix matches its kind."""
        ...

    def subscribe(self, kind_prefix: str, handler: Handler) -> None:
        """Call `handler` for every event whose kind starts with `kind_prefix`."""
        ...
