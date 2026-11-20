"""Bus-backed implementations of the skill services (OrderDesk, Speech)."""

from __future__ import annotations

from typing import Callable

from dsz.core.events import DomainEvent, EventBus
from dsz.core.types import SimMinutes


class BusOrderDesk:
    """Publish `order.placed`; supplier actors pick it up."""

    def __init__(self, bus: EventBus, now: Callable[[], SimMinutes]) -> None:
        """Publish on `bus`, stamping events with `now()`."""
        self._bus = bus
        self._now = now

    def place(self, supplier: str, item_type: str, qty: int) -> None:
        """Publish the order."""
        self._bus.publish(DomainEvent(self._now(), "order.placed",
                                      {"supplier": supplier, "item_type": item_type, "qty": qty}))


class BusSpeech:
    """Publish `robot.said` for evaluators and actors."""

    def __init__(self, bus: EventBus, now: Callable[[], SimMinutes]) -> None:
        """Publish on `bus`, stamping events with `now()`."""
        self._bus = bus
        self._now = now

    def say(self, to: str, text: str) -> None:
        """Publish what the robot said."""
        self._bus.publish(DomainEvent(self._now(), "robot.said", {"to": to, "text": text}))
