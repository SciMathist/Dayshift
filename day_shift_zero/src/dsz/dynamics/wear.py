"""Equipment wear module: fixtures lose health over time; a failing fridge stops cooling.

The failure is evaluator-only. The robot must notice it through sensing (for example,
spoilage it can see, or a temperature reading where the backend offers one).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dsz.core.dynamics import DynamicsModule
from dsz.core.events import DomainEvent, EventBus
from dsz.core.types import MINUTES_PER_DAY, SimMinutes
from dsz.dynamics.registry import register_module
from dsz.world.state import WorldState

if TYPE_CHECKING:
    import numpy as np

FAILING = 0.5


@register_module
class WearModule(DynamicsModule):
    """Reduce the health of the listed fixtures by a noisy daily rate.

    Params:
        fixtures (list[str]): fixture ids that wear.
        per_day (float): mean health loss per day (health starts at 1.0).
        jitter (float, default 0.0): std of a multiplicative noise factor per tick.
    """

    name = "wear"

    def validate(self) -> None:
        """Require a fixture list and a non-negative rate."""
        if not self.params.get("fixtures"):
            raise ValueError("wear.fixtures must list at least one fixture")
        if float(self.params.get("per_day", 0.0)) < 0:
            raise ValueError("wear.per_day must be non-negative")

    def advance(self, world: WorldState, t0: SimMinutes, t1: SimMinutes, rng: np.random.Generator,
                bus: EventBus) -> None:
        """Lower health over [t0, t1) and publish `fixture.failing` once when it crosses the threshold."""
        base = float(self.params["per_day"]) * (t1 - t0) / MINUTES_PER_DAY
        jitter = float(self.params.get("jitter", 0.0))
        for fid in self.params["fixtures"]:
            fx = world.fixture(fid)
            noise = max(0.0, 1.0 + jitter * float(rng.standard_normal())) if jitter else 1.0
            before = fx.health
            fx.health = max(0.0, fx.health - base * noise)
            if before >= FAILING > fx.health:
                bus.publish(DomainEvent(t1, "fixture.failing", {"fixture": fid, "health": round(fx.health, 3)}))
