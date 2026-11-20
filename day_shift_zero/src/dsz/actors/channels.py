"""In-memory channel hub: actors post messages, the observation builder drains them."""

from __future__ import annotations

from typing import Sequence

from dsz.core.events import DomainEvent, EventBus
from dsz.core.types import Message


class ChannelHub:
    """Ordered message log with a read cursor for the policy. Every post is also published."""

    def __init__(self, bus: EventBus) -> None:
        """Create an empty hub that publishes `message.sent` on `bus`."""
        self._bus = bus
        self._log: list[Message] = []
        self._cursor = 0

    def post(self, message: Message) -> None:
        """Append `message` and publish it as a policy-visible event."""
        self._log.append(message)
        self._bus.publish(DomainEvent(message.t, "message.sent",
                                      {"channel": message.channel, "sender": message.sender, "text": message.text},
                                      evaluator_only=False))

    def drain(self) -> Sequence[Message]:
        """Return messages since the last drain."""
        new = self._log[self._cursor:]
        self._cursor = len(self._log)
        return tuple(new)

    @property
    def history(self) -> Sequence[Message]:
        """Return every message so far (evaluator and trace use)."""
        return tuple(self._log)
