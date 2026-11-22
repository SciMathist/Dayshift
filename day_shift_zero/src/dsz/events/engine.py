"""Event engine: execute scheduled events in time order, deferring physical edits near the robot."""

from __future__ import annotations

import heapq
from typing import Iterable

from dsz.core.channels import Channels
from dsz.core.events import DomainEvent, EventBus, EventContext, EventHandler
from dsz.core.registry import Registry
from dsz.core.rng import RngStreams
from dsz.core.scenario import ScheduledEvent
from dsz.core.sim import WorldEditor
from dsz.core.types import SimMinutes
from dsz.events.registry import EVENT_TYPES
from dsz.world.state import WorldState

DEFAULT_DEFER: SimMinutes = 5


class EventEngine:
    """Priority queue of scheduled events, ordered by (time, insertion order).

    An event whose handler touches a fixture where the robot stands is deferred by
    `defer` minutes until the robot is clear (spec 5.6: never edit onto the robot).
    The engine also implements `EventScheduler`, so actors can add events at run time.
    """

    def __init__(self, world: WorldState, editor: WorldEditor, channels: Channels, bus: EventBus,
                 rng: RngStreams, handlers: Registry[type[EventHandler]] = EVENT_TYPES,
                 defer: SimMinutes = DEFAULT_DEFER) -> None:
        """Create an engine that applies events to `world` through `editor`."""
        self._world = world
        self._editor = editor
        self._channels = channels
        self._bus = bus
        self._rng = rng
        self._handlers = handlers
        self._defer = defer
        self._queue: list[tuple[SimMinutes, int, ScheduledEvent]] = []
        self._seq = 0
        self._instances: dict[str, EventHandler] = {}

    def load(self, events: Iterable[ScheduledEvent]) -> None:
        """Queue the instance's pre-generated events."""
        for ev in events:
            self.schedule(ev)

    def schedule(self, event: ScheduledEvent) -> None:
        """Queue `event`. Raise ValueError if it is in the past or its kind is unknown."""
        if event.t < self._world.now:
            raise ValueError(f"cannot schedule '{event.kind}' in the past ({event.t} < {self._world.now})")
        self._handler(event.kind)  # fail fast on unknown kinds
        heapq.heappush(self._queue, (event.t, self._seq, event))
        self._seq += 1

    def next_time(self) -> SimMinutes | None:
        """Return the time of the next queued event, or None."""
        return self._queue[0][0] if self._queue else None

    def run_until(self, t: SimMinutes) -> int:
        """Execute every event due at or before `t`. Return how many fired."""
        fired = 0
        while self._queue and self._queue[0][0] <= t:
            due, _, ev = heapq.heappop(self._queue)
            handler = self._handler(ev.kind)
            blocked = [f for f in handler.touches(ev.payload) if not self._editor.robot_clear_of(f)]
            if blocked:
                later = ScheduledEvent(max(due, self._world.now) + self._defer, ev.kind, ev.payload, ev.observable,
                                       ev.source)
                heapq.heappush(self._queue, (later.t, self._seq, later))
                self._seq += 1
                self._bus.publish(DomainEvent(self._world.now, "event.deferred", {"kind": ev.kind, "blocked": blocked}))
                continue
            handler.apply(self._context(ev.kind), ev)
            fired_data = {"kind": ev.kind, "payload": dict(ev.payload), "observable": ev.observable}
            self._bus.publish(DomainEvent(self._world.now, "event.fired", fired_data))
            fired += 1
        return fired

    def context(self, stream: str) -> EventContext:
        """Return an EventContext whose RNG is stream `stream` (used to attach actors)."""
        return EventContext(self._world, self._editor, self._channels, self._bus, self, self._rng.get(stream))

    def _context(self, kind: str) -> EventContext:
        """Return the context for handlers of `kind` (own stream per kind)."""
        return self.context(f"events.{kind}")

    def _handler(self, kind: str) -> EventHandler:
        """Return the cached handler instance for `kind`."""
        if kind not in self._instances:
            self._instances[kind] = self._handlers.get(kind)()
        return self._instances[kind]
