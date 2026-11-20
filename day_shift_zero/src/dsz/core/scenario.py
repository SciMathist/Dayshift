"""Scenario contract and the instance it generates.

A scenario is a task definition composed from the platform's capability vocabulary.
The platform never imports a specific scenario (open/closed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping, Protocol, Sequence, runtime_checkable

from dsz.core.types import CapabilitySet, Horizon, Location, SimMinutes, Verdict

if TYPE_CHECKING:
    from dsz.core.policy import Policy
    from dsz.core.rng import RngStreams
    from dsz.core.sim import GroundTruth
    from dsz.world.state import WorldState


@dataclass(frozen=True, slots=True)
class InitialItem:
    """An item that exists at the start, either placed in the world or parked for a later delivery."""

    item_id: str
    item_type: str
    location: Location  # Location.parked() for items that arrive later via deliveries
    batch: str | None = None


@dataclass(frozen=True, slots=True)
class ScheduledEvent:
    """An exogenous event fixed at generation time (independent of the agent)."""

    t: SimMinutes
    kind: str  # must be a registered event type
    payload: Mapping[str, Any] = field(default_factory=dict)
    observable: bool = False  # whether the robot is told about it


@dataclass(frozen=True, slots=True)
class Fact:
    """Information stated once on a channel and needed later (M1)."""

    fact_id: str
    revealed_at: SimMinutes
    channel: str
    text: str
    needed_by: tuple[str, ...] = ()  # ids of work items that depend on it


@dataclass(frozen=True, slots=True)
class WorkItem:
    """A unit of requested work (an order, a contract milestone) with a deadline."""

    work_id: str
    kind: str
    released_at: SimMinutes
    deadline: SimMinutes
    spec: Mapping[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Instance:
    """A fully sampled, reproducible scenario run. The seed alone decides everything here."""

    scenario_id: str
    seed: int
    horizon: Horizon
    objective: str
    fixtures: tuple[str, ...]
    items: tuple[InitialItem, ...]
    facts: tuple[Fact, ...]
    work: tuple[WorkItem, ...]
    events: tuple[ScheduledEvent, ...]
    params: Mapping[str, Any] = field(default_factory=dict)

    def prefix(self, days: int) -> Instance:
        """Return the same instance truncated to `days` (spec: prefix property).

        Raises:
            ValueError: if `days` exceeds the instance horizon.
        """
        if days > self.horizon.days:
            raise ValueError("prefix longer than instance")
        end = Horizon(self.horizon.type, days).end
        return Instance(
            scenario_id=self.scenario_id,
            seed=self.seed,
            horizon=Horizon(self.horizon.type, days),
            objective=self.objective,
            fixtures=self.fixtures,
            items=self.items,
            facts=tuple(f for f in self.facts if f.revealed_at < end),
            work=tuple(w for w in self.work if w.released_at < end),
            events=tuple(e for e in self.events if e.t < end),
            params=self.params,
        )


@runtime_checkable
class Scenario(Protocol):
    """A pluggable long-horizon task definition."""

    scenario_id: str

    def requirements(self) -> CapabilitySet:
        """Return the capabilities this scenario needs from the platform."""
        ...

    def generate(self, seed: int, horizon: Horizon, rng: RngStreams) -> Instance:
        """Sample a reproducible instance for `seed` and `horizon`."""
        ...

    def success(self, instance: Instance, world: WorldState, truth: GroundTruth) -> Verdict:
        """Judge a finished run: binary pass plus graded score."""
        ...

    def oracle(self, instance: Instance) -> Policy:
        """Return the scripted solver for `instance` (V1 solvability)."""
        ...

    def negative_controls(self, instance: Instance) -> Sequence[Policy]:
        """Return trivial policies that must fail (no-op, ignores hidden state, never recovers)."""
        ...
