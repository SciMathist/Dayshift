"""Built-in success criteria and the composite success check that combines them."""

from __future__ import annotations

from typing import Sequence

from dsz.core.events import DomainEvent, EventBus
from dsz.core.scenario import Instance
from dsz.core.sim import GroundTruth
from dsz.core.success import Criterion, CriterionResult, SuccessCheck
from dsz.core.types import Verdict
from dsz.scenario.registries import register_criterion
from dsz.world.state import WorldState


@register_criterion
class WorkCompletion(Criterion):
    """Fraction of work items completed on time.

    Params:
        min_on_time (float, default 1.0): pass threshold for the on-time fraction.
    """

    name = "work_completion"

    def validate(self) -> None:
        """Require 0 <= min_on_time <= 1."""
        if not 0.0 <= float(self.params.get("min_on_time", 1.0)) <= 1.0:
            raise ValueError("work_completion.min_on_time must be in [0, 1]")

    def attach(self, bus: EventBus, instance: Instance) -> None:
        """Count work items and listen for completions."""
        self._total = len(instance.work)
        self._on_time = 0
        self._late = 0
        bus.subscribe("work.completed", self._on_done)

    def _on_done(self, ev: DomainEvent) -> None:
        """Tally one completion."""
        if ev.data["on_time"]:
            self._on_time += 1
        else:
            self._late += 1

    def evaluate(self, world: WorldState, truth: GroundTruth) -> CriterionResult:
        """Return the on-time fraction; an instance with no work scores 1."""
        score = self._on_time / self._total if self._total else 1.0
        return CriterionResult(score >= float(self.params.get("min_on_time", 1.0)), score,
                               (f"on_time={self._on_time} late={self._late} total={self._total}",))


@register_criterion
class NoViolations(Criterion):
    """No delivery may break a constraint (forbidden allergen, bad condition).

    Params:
        kinds (list[str], default ["allergen", "condition"]): violation kinds that count.
    """

    name = "no_violations"

    def attach(self, bus: EventBus, instance: Instance) -> None:
        """Listen for completions and collect their violations."""
        self._total = max(1, len(instance.work))
        self._found: list[str] = []
        bus.subscribe("work.completed", self._on_done)

    def _on_done(self, ev: DomainEvent) -> None:
        """Record counted violations of one delivery."""
        kinds = set(self.params.get("kinds", ["allergen", "condition"]))
        self._found += [f"{ev.data['work']}:{v}" for v in ev.data["violations"] if v.split(":")[0] in kinds]

    def evaluate(self, world: WorldState, truth: GroundTruth) -> CriterionResult:
        """Pass only with zero violations; score drops per violation."""
        return CriterionResult(not self._found, max(0.0, 1.0 - len(self._found) / self._total), tuple(self._found))


@register_criterion
class Waste(Criterion):
    """Graded penalty for items that spoiled, broke or got contaminated during the run.

    Params:
        budget (int, default 10): number of wasted items that drives the score to 0.
    """

    name = "waste"

    def validate(self) -> None:
        """Require a positive budget."""
        if int(self.params.get("budget", 10)) < 1:
            raise ValueError("waste.budget must be at least 1")

    def attach(self, bus: EventBus, instance: Instance) -> None:
        """Count degradation events."""
        self._wasted = 0
        for kind in ("item.spoiled", "item.damaged", "item.contaminated"):
            bus.subscribe(kind, self._on_waste)

    def _on_waste(self, ev: DomainEvent) -> None:
        """Tally one wasted item."""
        self._wasted += 1

    def evaluate(self, world: WorldState, truth: GroundTruth) -> CriterionResult:
        """Return a graded score only (passed=None)."""
        budget = int(self.params.get("budget", 10))
        return CriterionResult(None, max(0.0, 1.0 - self._wasted / budget), (f"wasted={self._wasted}",))


class CompositeSuccess(SuccessCheck):
    """Combine criteria: binary pass = all required criteria pass; score = weighted mean of scores."""

    def __init__(self, criteria: Sequence[tuple[Criterion, float, bool]]) -> None:
        """Take (criterion, weight, required) triples."""
        if not criteria:
            raise ValueError("at least one criterion is required")
        self._criteria = list(criteria)

    def attach(self, bus: EventBus, instance: Instance) -> None:
        """Attach every criterion."""
        for c, _, _ in self._criteria:
            c.attach(bus, instance)

    def verdict(self, world: WorldState, truth: GroundTruth) -> Verdict:
        """Evaluate all criteria and combine them."""
        passed, total_w, acc, comps, notes = True, 0.0, 0.0, {}, []
        for c, weight, required in self._criteria:
            r = c.evaluate(world, truth)
            if required and r.passed is False:
                passed = False
            total_w += weight
            acc += weight * r.score
            comps[c.name] = r.score
            notes += [f"{c.name}: {n}" for n in r.notes]
        return Verdict(passed, acc / total_w if total_w else 0.0, comps, tuple(notes))
