"""Symbolic backend: the kitchen without geometry (the spec's tau_sym).

It implements every role in `dsz.core.sim` on top of a WorldState. Skills are atomic and
deterministic by default. `grasp_fail_p` and `break_on_fail_p` inject seeded physical
failures, so recovery logic can be tested without physics.

Visibility: the robot sees the items in the fixture it stands at, if that fixture has no
door or its door is open. It sees nothing else.
"""

from __future__ import annotations

import pickle
from typing import Any, Mapping, Sequence

import numpy as np

from dsz.core.types import Condition, Detection, Location, SensorReading
from dsz.world.editor import SemanticWorldEditor
from dsz.world.state import WorldState

# Nominal actuation durations in seconds.
NAV_S, DOOR_S, GRASP_S, PLACE_S, POWER_S = 30.0, 5.0, 10.0, 10.0, 3.0
GRIP_HOLD_WIDTH = 0.03  # metres: closed on an object
GRIP_EMPTY_WIDTH = 0.0  # metres: closed on nothing


class SymbolicBackend:
    """All backend roles over a WorldState. Construct with the world and a noise generator."""

    def __init__(self, world: WorldState, noise: np.random.Generator,
                 grasp_fail_p: float = 0.0, break_on_fail_p: float = 0.0) -> None:
        """Wrap `world`. Failure probabilities default to 0 (deterministic tau_sym)."""
        if not (0.0 <= grasp_fail_p <= 1.0 and 0.0 <= break_on_fail_p <= 1.0):
            raise ValueError("probabilities must be in [0, 1]")
        self._world = world
        self._editor = SemanticWorldEditor(world)
        self._noise = noise
        self._grasp_fail_p = grasp_fail_p
        self._break_p = break_on_fail_p

    # ---- SimBackend.build -----------------------------------------------------------------
    def build(self, fixtures: Mapping[str, str], pool: Mapping[str, str]) -> None:
        """Create fixtures (id → kind) and park pool items (id → type)."""
        for fid, kind in fixtures.items():
            self._world.add_fixture(fid, kind)
        for iid, itype in pool.items():
            self._world.add_item(iid, itype, Location.parked())

    # ---- Actuation ------------------------------------------------------------------------
    def navigate_to(self, fixture: str) -> tuple[float, SensorReading]:
        """Move to `fixture` if it exists."""
        if fixture not in self._world.fixtures:
            return NAV_S, _note("no such place")
        self._world.robot_at = fixture
        return NAV_S, self._grip()

    def set_open(self, fixture: str, open_: bool) -> tuple[float, SensorReading]:
        """Open or close a door at the robot's fixture."""
        blocked = self._reach(fixture)
        if blocked:
            return DOOR_S, _note(blocked)
        fx = self._world.fixture(fixture)
        if not fx.spec.has_door:
            return DOOR_S, _note("it has no door")
        fx.is_open = open_
        return DOOR_S, self._grip()

    def grasp(self, detection_index: int) -> tuple[float, SensorReading]:
        """Grasp the detected item; may fail (and break a fragile item) with seeded noise."""
        if self._world.held() is not None:
            return GRASP_S, _note("hand is full", holding=True)
        visible = self.visible_item_ids()
        if not 0 <= detection_index < len(visible):
            return GRASP_S, _note("nothing there", holding=False)
        iid = visible[detection_index]
        if self._grasp_fail_p and self._noise.random() < self._grasp_fail_p:
            item = self._world.item(iid)
            if item.type.fragile and self._break_p and self._noise.random() < self._break_p:
                self._world.degrade(iid, Condition.DAMAGED, cause="grasp.broke")
            return GRASP_S, self._grip()
        self._world.move(iid, Location.held(), cause="skill.pick")
        return GRASP_S, self._grip()

    def place(self, fixture: str, slot: str | None) -> tuple[float, SensorReading]:
        """Place the held item at the robot's fixture."""
        blocked = self._reach(fixture) or self._door_closed(fixture)
        if blocked:
            return PLACE_S, _note(blocked, holding=self._world.held() is not None)
        held = self._world.held()
        if held is None:
            return PLACE_S, _note("hand is empty", holding=False)
        try:
            self._world.move(held.item_id, Location.at(fixture, slot), cause="skill.place")
        except ValueError:
            return PLACE_S, _note("no space", holding=True)
        return PLACE_S, self._grip()

    def set_power(self, fixture: str, on: bool) -> tuple[float, SensorReading]:
        """Switch a powered fixture at the robot's position."""
        blocked = self._reach(fixture)
        if blocked:
            return POWER_S, _note(blocked)
        fx = self._world.fixture(fixture)
        if not fx.spec.powered:
            return POWER_S, _note("it has no switch")
        fx.powered_on = on
        return POWER_S, self._grip()

    # ---- Perception -----------------------------------------------------------------------
    def detections(self) -> Sequence[Detection]:
        """Return visible items as detections labelled by item type (no ids)."""
        return tuple(Detection(i, self._world.item(iid).item_type) for i, iid in enumerate(self.visible_item_ids()))

    def images(self) -> Mapping[str, Any]:
        """Return no images (symbolic)."""
        return {}

    def proprio(self) -> Sequence[float]:
        """Return [gripper width]."""
        return (GRIP_HOLD_WIDTH if self._world.held() else GRIP_EMPTY_WIDTH,)

    # ---- WorldEditor (delegated) ---------------------------------------------------------
    def spawn(self, item_id: str, at: Location) -> None:
        """Bring a pool item into the world."""
        self._editor.spawn(item_id, at)

    def remove(self, item_id: str) -> None:
        """Take an item out of the world."""
        self._editor.remove(item_id)

    def move(self, item_id: str, to: Location) -> None:
        """Relocate an item without the robot."""
        self._editor.move(item_id, to)

    def set_fixture_open(self, fixture: str, open_: bool) -> None:
        """Open or close a door without the robot."""
        self._editor.set_fixture_open(fixture, open_)

    def robot_clear_of(self, fixture: str) -> bool:
        """Return True unless the robot stands at `fixture`."""
        return self._editor.robot_clear_of(fixture)

    # ---- GroundTruth ----------------------------------------------------------------------
    def locate(self, item_id: str) -> Location:
        """Return the true location."""
        return self._world.item(item_id).location

    def fixture_is_open(self, fixture: str) -> bool:
        """Return the true door state."""
        return self._world.fixture(fixture).is_open

    def held_item(self) -> str | None:
        """Return the id of the held item."""
        held = self._world.held()
        return held.item_id if held else None

    def visible_item_ids(self) -> Sequence[str]:
        """Return ids of visible items in detection order (sorted by id for determinism)."""
        at = self._world.robot_at
        if at is None:
            return ()
        fx = self._world.fixture(at)
        if fx.spec.has_door and not fx.is_open:
            return ()
        return tuple(sorted(i.item_id for i in self._world.items_at(at)))

    # ---- Checkpointable -------------------------------------------------------------------
    def checkpoint(self) -> bytes:
        """Serialize world data, robot position and the noise generator state."""
        w = self._world
        return pickle.dumps({"items": w.items, "fixtures": w.fixtures, "processes": w.processes, "now": w.now,
                             "robot_at": w.robot_at, "noise": self._noise.bit_generator.state})

    def restore(self, blob: bytes) -> None:
        """Restore a state from `checkpoint()`."""
        d = pickle.loads(blob)
        w = self._world
        w.items, w.fixtures, w.processes, w.now, w.robot_at = (d["items"], d["fixtures"], d["processes"],
                                                                d["now"], d["robot_at"])
        self._noise.bit_generator.state = d["noise"]

    # ---- internals ------------------------------------------------------------------------
    def _reach(self, fixture: str) -> str | None:
        """Return why the robot cannot act on `fixture` from where it stands, or None."""
        if fixture not in self._world.fixtures:
            return "no such place"
        if self._world.robot_at != fixture:
            return "out of reach"
        return None

    def _door_closed(self, fixture: str) -> str | None:
        """Return 'door is closed' if the fixture has a closed door."""
        fx = self._world.fixture(fixture)
        return "door is closed" if fx.spec.has_door and not fx.is_open else None

    def _grip(self) -> SensorReading:
        """Return the gripper reading for the current hand state."""
        holding = self._world.held() is not None
        return SensorReading(gripper_width=GRIP_HOLD_WIDTH if holding else GRIP_EMPTY_WIDTH,
                             contact=holding, holding_something=holding)


def _note(text: str, holding: bool | None = None) -> SensorReading:
    """Return a reading that carries a sensor-plausible note (what the robot would perceive)."""
    width = None if holding is None else (GRIP_HOLD_WIDTH if holding else GRIP_EMPTY_WIDTH)
    return SensorReading(gripper_width=width, contact=holding, holding_something=holding, extra={"note": text})

