"""Event bus implementations, the event engine and the built-in event handlers.

Importing this package registers the built-in event kinds.
"""

from dsz.events import handlers  # noqa: F401  (registration side effect)
from dsz.events.engine import EventEngine
from dsz.events.registry import EVENT_TYPES, register_event

__all__ = ["EVENT_TYPES", "EventEngine", "register_event"]
