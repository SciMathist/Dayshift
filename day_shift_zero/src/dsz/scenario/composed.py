"""SpecScenario: a Scenario assembled from a spec and registered plugins (Strategy + composition)."""

from __future__ import annotations

from typing import Sequence

from dsz.core.policy import Policy
from dsz.core.rng import RngStreams
from dsz.core.scenario import GenerationContext, Instance, InstanceGenerator
from dsz.core.success import SuccessCheck
from dsz.core.types import CapabilitySet, Horizon
from dsz.scenario.criteria import CompositeSuccess
from dsz.scenario.registries import CRITERIA, POLICIES
from dsz.scenario.spec import ScenarioSpec
from dsz.world.state import WorldState


class SpecScenario:
    """Implements the Scenario protocol by delegating to the plugins a spec names."""

    def __init__(self, spec: ScenarioSpec, generator: InstanceGenerator, requirements: CapabilitySet) -> None:
        """Wrap a compiled `spec`. Use `compile_spec` rather than calling this directly."""
        self.spec = spec
        self.scenario_id = spec.scenario_id
        self._generator = generator
        self._requirements = requirements

    def requirements(self) -> CapabilitySet:
        """Return the capabilities found by the compiler."""
        return self._requirements

    def horizon(self, days: int | None = None) -> Horizon:
        """Return the horizon for `days` (default: the spec's default)."""
        return Horizon(self.spec.horizon_type, days or self.spec.default_days)

    def generate(self, seed: int, horizon: Horizon, rng: RngStreams) -> Instance:
        """Delegate to the spec's generator."""
        s = self.spec
        ctx = GenerationContext(s.scenario_id, s.objective, s.fixtures, s.modules, s.actors, s.generator.params)
        return self._generator.generate(ctx, seed, horizon, rng)

    def success_check(self, instance: Instance) -> SuccessCheck:
        """Return a fresh composite of the spec's criteria."""
        return CompositeSuccess([(CRITERIA.get(c.name)(c.params), c.weight, c.required) for c in self.spec.criteria])

    def oracle(self, instance: Instance, world: WorldState) -> Policy:
        """Build the oracle named in the spec. Raise LookupError if the spec names none."""
        if self.spec.oracle is None:
            raise LookupError(f"scenario '{self.scenario_id}' has no oracle")
        return POLICIES.get(self.spec.oracle.name)(instance, world, self.spec.oracle.params)

    def negative_controls(self, instance: Instance, world: WorldState) -> Sequence[Policy]:
        """Build the controls named in the spec."""
        return [POLICIES.get(c.name)(instance, world, c.params) for c in self.spec.controls]
