"""Semantic implementation of the WorldEditor role.

The symbolic backend uses it directly. The RoboCasa backend applies the physical edit
first, then delegates here so the semantic state stays in sync (decorator-style).
"""

from __future__ import annotations

from dsz.core.types import Location, LocationKind
from dsz.world.state import WorldState


class SemanticWorldEditor:
    """Apply world edits (deliveries, relocations, removals, door changes) to a WorldState."""

    def __init__(self, world: WorldState) -> None:
        """Edit `world`."""
        self._world = world

    def spawn(self, item_id: str, at: Location) -> None:
        """Bring a parked pool item into the world. Raise ValueError if the item is not parked."""
        item = self._world.item(item_id)
        if item.location.kind is not LocationKind.PARKED:
            raise ValueError(f"item '{item_id}' is not in the pool")
        item.created_at = self._world.now  # freshness starts on arrival
        self._world.move(item_id, at, cause="editor.spawn")

    def remove(self, item_id: str) -> None:
        """Take an item out of the world (consumed, or collected by a courier)."""
        self._world.move(item_id, Location.discarded(), cause="editor.remove")

    def move(self, item_id: str, to: Location) -> None:
        """Relocate an item without the robot."""
        self._world.move(item_id, to, cause="editor.move")

    def set_fixture_open(self, fixture: str, open_: bool) -> None:
        """Open or close a fixture door without the robot."""
        self._world.fixture(fixture).is_open = open_

    def robot_clear_of(self, fixture: str) -> bool:
        """Return True unless the robot stands at `fixture`."""
        return self._world.robot_at != fixture
