"""Domain events, the event bus contract (Observer), and scheduled-event handlers (Command).

Everything that happens (skill executed, item spoiled, delivery arrived, message sent) is
published once as a DomainEvent. The trace writer, metrics and failure labeler subscribe
independently. Scheduled events are executed by EventHandler plugins, one class per kind.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Mapping, Protocol

from dsz.core.types import SimMinutes

if TYPE_CHECKING:
    import numpy as np

    from dsz.core.channels import Channels
    from dsz.core.scenario import ScheduledEvent
    from dsz.core.sim import WorldEditor
    from dsz.world.state import WorldState


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


class EventScheduler(Protocol):
    """Add events to the timeline at run time (e.g. a supplier schedules a delivery)."""

    def schedule(self, event: ScheduledEvent) -> None:
        """Queue `event` for execution at `event.t`. It must not be in the past."""
        ...


@dataclass(frozen=True, slots=True)
class EventContext:
    """Everything an event handler may use. Deliberately excludes GroundTruth and the policy."""

    world: WorldState  # read for state-dependent effects; semantic-only changes allowed
    editor: WorldEditor  # all physical changes go through here
    channels: Channels
    bus: EventBus
    scheduler: EventScheduler
    rng: np.random.Generator  # the handler kind's own stream


class EventHandler(ABC):
    """Execute one kind of scheduled event (Command pattern).

    To add an event kind: subclass, set `kind`, implement `apply`, register in `EVENT_TYPES`.
    Effects apply to whatever state the handler finds; a handler may do nothing if its
    target is gone (spec principle 4).
    """

    kind: ClassVar[str]

    def touches(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        """Return fixture ids the event edits physically. The engine defers it until the robot is clear."""
        return ()

    @abstractmethod
    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Execute `event`. Publish what happened on `ctx.bus`."""
