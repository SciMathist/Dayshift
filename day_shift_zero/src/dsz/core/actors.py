"""Actor contract: agents of the world (suppliers, customers, couriers) that react to what happens."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Mapping

from dsz.core.events import EventContext


class Actor(ABC):
    """React to domain events by scheduling events or posting messages.

    Actors make the world respond to the agent (an order placed → a delivery later)
    while staying deterministic: each actor draws only from its own RNG stream.
    To add an actor: subclass, set `role`, implement `attach`, register in `ACTORS`.
    """

    role: ClassVar[str]

    def __init__(self, name: str, params: Mapping[str, Any]) -> None:
        """Create the actor `name` with parameters from the scenario definition."""
        self.name = name
        self.params = dict(params)

    @abstractmethod
    def attach(self, ctx: EventContext) -> None:
        """Subscribe to the bus events this actor reacts to. Called once per run."""
