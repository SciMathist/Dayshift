"""Scenario contract, the instance it generates, and the generator plugin contract.

A scenario is a task definition composed from the platform's capability vocabulary.
The platform never imports a specific scenario (open/closed).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Mapping, Protocol, Sequence, runtime_checkable

from dsz.core.types import CapabilitySet, Horizon, Location, SimMinutes

if TYPE_CHECKING:
    from dsz.core.policy import Policy
    from dsz.core.rng import RngStreams
    from dsz.core.success import SuccessCheck
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
    source: str | None = None  # id of the definition entry that made it, for claim checks


@dataclass(frozen=True, slots=True)
class Fact:
    """Information stated once on a channel and needed later (M1)."""

    fact_id: str
    revealed_at: SimMinutes
    channel: str
    text: str
    sender: str = "manager"
    needed_by: tuple[str, ...] = ()  # ids of work items that depend on it


@dataclass(frozen=True, slots=True)
class WorkItem:
    """A unit of requested work (an order, a contract milestone) with a deadline.

    `spec` holds the completion predicate under "deliver" (see dsz.scenario.work) and the
    ticket the robot receives under "ticket". Hidden constraints from facts are already
    merged into "deliver" but never appear in the ticket.
    """

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
    fixtures: Mapping[str, str]  # fixture id -> kind
    items: tuple[InitialItem, ...]
    facts: tuple[Fact, ...]
    work: tuple[WorkItem, ...]
    events: tuple[ScheduledEvent, ...]
    modules: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    actors: tuple[Mapping[str, Any], ...] = ()
    params: Mapping[str, Any] = field(default_factory=dict)

    def prefix(self, days: int) -> Instance:
        """Return the same instance truncated to `days` (spec: prefix property).

        Raises:
            ValueError: if `days` exceeds the instance horizon.
        """
        if days > self.horizon.days:
            raise ValueError("prefix longer than instance")
        end = Horizon(self.horizon.type, days).end
        work = tuple(w for w in self.work if w.released_at < end)
        kept = {w.work_id for w in work}
        facts = tuple(Fact(f.fact_id, f.revealed_at, f.channel, f.text, f.sender,
                           tuple(w for w in f.needed_by if w in kept))
                      for f in self.facts if f.revealed_at < end)
        return Instance(
            scenario_id=self.scenario_id,
            seed=self.seed,
            horizon=Horizon(self.horizon.type, days),
            objective=self.objective,
            fixtures=self.fixtures,
            items=self.items,
            facts=facts,
            work=work,
            events=tuple(e for e in self.events if e.t < end),
            modules=self.modules,
            actors=self.actors,
            params=self.params,
        )


@dataclass(frozen=True, slots=True)
class GenerationContext:
    """Scenario-level data a generator needs, independent of how the scenario was defined."""

    scenario_id: str
    objective: str
    fixtures: Mapping[str, str]
    modules: Mapping[str, Mapping[str, Any]]
    actors: tuple[Mapping[str, Any], ...]
    params: Mapping[str, Any]


class InstanceGenerator(ABC):
    """Sample an Instance from a scenario definition (Factory pattern).

    To add one: subclass, set `name`, implement `requires` and `generate`, register in
    `GENERATORS`. Generation must use only the given RNG streams.
    """

    name: ClassVar[str]

    @abstractmethod
    def requires(self, params: Mapping[str, Any]) -> CapabilitySet:
        """Return the capabilities that instances generated from `params` use."""

    @abstractmethod
    def generate(self, ctx: GenerationContext, seed: int, horizon: Horizon, rng: RngStreams) -> Instance:
        """Return a reproducible instance."""


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

    def success_check(self, instance: Instance) -> SuccessCheck:
        """Return a fresh success check for one run of `instance`."""
        ...

    def oracle(self, instance: Instance, world: WorldState) -> Policy:
        """Return the scripted solver (V1). It may read `world` (evaluator-side)."""
        ...

    def negative_controls(self, instance: Instance, world: WorldState) -> Sequence[Policy]:
        """Return trivial policies that must fail (no-op, ignores hidden state, never recovers)."""
        ...
