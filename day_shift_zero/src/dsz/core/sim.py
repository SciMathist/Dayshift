"""Simulator backend roles (interface segregation).

A backend (RoboCasa or symbolic) implements all roles, but each consumer gets only the
role it needs. Policies and skills never receive `GroundTruth`, so evaluator-only state
cannot leak into observations by construction.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from dsz.core.types import Detection, Location, SensorReading


@runtime_checkable
class Actuation(Protocol):
    """Physical primitives used by skills. Each returns (elapsed simulated seconds, sensor reading)."""

    def navigate_to(self, fixture: str) -> tuple[float, SensorReading]:
        """Move the robot base to the approach pose of `fixture`."""
        ...

    def set_open(self, fixture: str, open_: bool) -> tuple[float, SensorReading]:
        """Open or close the door of `fixture`."""
        ...

    def grasp(self, detection_index: int) -> tuple[float, SensorReading]:
        """Try to grasp the object behind detection `detection_index` in the current view."""
        ...

    def place(self, fixture: str, slot: str | None) -> tuple[float, SensorReading]:
        """Place the held object in or on `fixture`, optionally in `slot`."""
        ...

    def set_power(self, fixture: str, on: bool) -> tuple[float, SensorReading]:
        """Switch a powered fixture (oven, stove, mixer) on or off."""
        ...


@runtime_checkable
class Perception(Protocol):
    """What the robot can sense now."""

    def detections(self) -> Sequence[Detection]:
        """Return the objects visible in the current view, indexed for grounding."""
        ...

    def images(self) -> Mapping[str, Any]:
        """Return camera name to HxWx3 uint8 image. Empty for the symbolic backend."""
        ...

    def proprio(self) -> Sequence[float]:
        """Return the proprioceptive state vector."""
        ...


@runtime_checkable
class WorldEditor(Protocol):
    """World edits for the event engine and scenario loader only (deliveries, relocations, faults)."""

    def spawn(self, item_id: str, at: Location) -> None:
        """Bring a parked pool item into the world at `at`."""
        ...

    def remove(self, item_id: str) -> None:
        """Take an item out of the world (consumed or picked up by a courier)."""
        ...

    def move(self, item_id: str, to: Location) -> None:
        """Relocate an item without the robot (e.g. a co-worker moves it)."""
        ...

    def set_fixture_open(self, fixture: str, open_: bool) -> None:
        """Open or close a fixture door without the robot."""
        ...

    def robot_clear_of(self, fixture: str) -> bool:
        """Return True if an edit at `fixture` cannot collide with the robot."""
        ...


@runtime_checkable
class GroundTruth(Protocol):
    """Evaluator-only queries. Never passed to policies or skills."""

    def locate(self, item_id: str) -> Location:
        """Return where the item really is."""
        ...

    def fixture_is_open(self, fixture: str) -> bool:
        """Return True if the fixture door is really open."""
        ...

    def held_item(self) -> str | None:
        """Return the id of the item really in the gripper, if any."""
        ...

    def visible_item_ids(self) -> Sequence[str]:
        """Return item ids in detection-index order, for labeling traces."""
        ...


@runtime_checkable
class Checkpointable(Protocol):
    """Save and restore the full backend state."""

    def checkpoint(self) -> bytes:
        """Serialize the backend state."""
        ...

    def restore(self, blob: bytes) -> None:
        """Restore a state produced by `checkpoint()`."""
        ...


class SimBackend(Actuation, Perception, WorldEditor, GroundTruth, Checkpointable, Protocol):
    """Full backend surface. Only the env composition root sees this type."""

    def build(self, fixtures: Mapping[str, str], pool: Mapping[str, str]) -> None:
        """Build the scene: `fixtures` maps fixture id to kind; `pool` maps item id to type, all parked."""
        ...
