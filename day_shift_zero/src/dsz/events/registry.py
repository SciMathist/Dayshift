"""Registry of scheduled-event handler classes (one per event kind)."""

from __future__ import annotations

from dsz.core.events import EventHandler
from dsz.core.registry import Registry

EVENT_TYPES: Registry[type[EventHandler]] = Registry("event type")


def register_event(cls: type[EventHandler]) -> type[EventHandler]:
    """Class decorator: register `cls` under `cls.kind`."""
    return EVENT_TYPES.add(cls.kind, cls)
