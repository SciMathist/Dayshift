"""In-process event bus (Observer). Synchronous and ordered, so traces are deterministic."""

from __future__ import annotations

from dsz.core.events import DomainEvent, Handler


class InMemoryEventBus:
    """Deliver events to subscribers in subscription order, on the caller's thread."""

    def __init__(self) -> None:
        """Create a bus with no subscribers."""
        self._subs: list[tuple[str, Handler]] = []

    def subscribe(self, kind_prefix: str, handler: Handler) -> None:
        """Call `handler` for every event whose kind starts with `kind_prefix`."""
        self._subs.append((kind_prefix, handler))

    def publish(self, event: DomainEvent) -> None:
        """Deliver `event` to every matching subscriber."""
        for prefix, handler in self._subs:
            if event.kind.startswith(prefix):
                handler(event)


class RecordingBus(InMemoryEventBus):
    """Bus that also keeps every event, for tests and the trace writer."""

    def __init__(self) -> None:
        """Create a bus that records all events in `self.events`."""
        super().__init__()
        self.events: list[DomainEvent] = []
        self.subscribe("", self.events.append)
