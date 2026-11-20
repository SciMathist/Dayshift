"""Value types shared across the platform. Immutable and dependency-free."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

SimMinutes = int
"""Simulated time in whole minutes since the start of the run. Integers keep runs deterministic."""

MINUTES_PER_DAY: SimMinutes = 24 * 60


class TempZone(str, Enum):
    """Temperature zone that governs spoilage and processes."""

    AMBIENT = "ambient"
    CHILLED = "chilled"
    FROZEN = "frozen"
    HOT = "hot"


class Condition(str, Enum):
    """Physical condition of an item. Any value other than OK is irreversible."""

    OK = "ok"
    SPOILED = "spoiled"
    DAMAGED = "damaged"
    CONTAMINATED = "contaminated"


class LocationKind(str, Enum):
    """Kind of place an item can be."""

    FIXTURE = "fixture"  # in or on a fixture (fridge shelf, counter, oven rack)
    HELD = "held"  # in the robot's gripper
    PARKED = "parked"  # in the off-scene object pool: not yet in the world
    DISCARDED = "discarded"  # trashed or consumed: gone from the world


@dataclass(frozen=True, slots=True)
class Location:
    """Where an item is: a fixture (with optional slot), the gripper, the pool, or gone."""

    kind: LocationKind
    fixture: str | None = None
    slot: str | None = None  # shelf, rack or region within the fixture

    @staticmethod
    def at(fixture: str, slot: str | None = None) -> Location:
        """Return a location in or on `fixture`, optionally in `slot`."""
        return Location(LocationKind.FIXTURE, fixture, slot)

    @staticmethod
    def held() -> Location:
        """Return the gripper location."""
        return Location(LocationKind.HELD)

    @staticmethod
    def parked() -> Location:
        """Return the off-scene pool location."""
        return Location(LocationKind.PARKED)

    @staticmethod
    def discarded() -> Location:
        """Return the location of trashed or consumed items."""
        return Location(LocationKind.DISCARDED)

    @property
    def in_world(self) -> bool:
        """Return True if the item is physically present in the kitchen."""
        return self.kind in (LocationKind.FIXTURE, LocationKind.HELD)


class HorizonType(str, Enum):
    """How a scenario ends."""

    CONTINUOUS = "continuous"  # open-ended operation for N days (e.g. cloud kitchen)
    DEADLINE = "deadline"  # a contract that ends at a fixed day (e.g. wedding cake)


@dataclass(frozen=True, slots=True)
class Horizon:
    """Length and type of a scenario run, in whole days."""

    type: HorizonType
    days: int

    def __post_init__(self) -> None:
        """Reject horizons shorter than one day."""
        if self.days < 1:
            raise ValueError("horizon must be at least one day")

    @property
    def end(self) -> SimMinutes:
        """Return the end of the horizon in simulated minutes."""
        return self.days * MINUTES_PER_DAY


@dataclass(frozen=True, slots=True)
class CapabilitySet:
    """Named capabilities: what the platform offers, or what a scenario needs."""

    fixtures: frozenset[str] = frozenset()
    item_types: frozenset[str] = frozenset()
    processes: frozenset[str] = frozenset()
    modules: frozenset[str] = frozenset()
    actors: frozenset[str] = frozenset()
    events: frozenset[str] = frozenset()
    skills: frozenset[str] = frozenset()

    def missing_from(self, offered: CapabilitySet) -> dict[str, frozenset[str]]:
        """Return the capabilities in self that `offered` lacks, by category. Empty if all are offered."""
        out: dict[str, frozenset[str]] = {}
        for cat in ("fixtures", "item_types", "processes", "modules", "actors", "events", "skills"):
            gap = getattr(self, cat) - getattr(offered, cat)
            if gap:
                out[cat] = gap
        return out


@dataclass(frozen=True, slots=True)
class Verdict:
    """Scenario outcome: binary pass (spec G) plus a graded score and its components."""

    passed: bool
    score: float
    components: Mapping[str, float] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Message:
    """Something an actor tells the robot on a channel. Visible to the policy."""

    t: SimMinutes
    channel: str
    sender: str
    text: str


@dataclass(frozen=True, slots=True)
class Detection:
    """An object the robot can see now. `index` is the only handle a policy gets (no global IDs)."""

    index: int
    label: str
    bbox: tuple[int, int, int, int] | None = None  # x0, y0, x1, y1 in the source camera image
    camera: str | None = None


@dataclass(frozen=True, slots=True)
class SensorReading:
    """Sensor-derived feedback from a skill. Never a ground-truth success flag."""

    gripper_width: float | None = None
    contact: bool | None = None
    holding_something: bool | None = None  # inferred from width and contact, as a real gripper would
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillCall:
    """A skill-level action: skill name plus arguments."""

    name: str
    args: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillResult:
    """What the policy learns after a skill: acceptance, elapsed time and sensor feedback."""

    call: SkillCall
    accepted: bool  # False if the call was malformed or not executable (e.g. unknown fixture)
    elapsed: SimMinutes
    sensors: SensorReading = SensorReading()
    message: str = ""  # policy-visible text, sensor-grounded only
