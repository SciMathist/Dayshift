"""Spoilage module: perishable items age against the shelf life of the zone they are in."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dsz.core.dynamics import DynamicsModule
from dsz.core.events import EventBus
from dsz.core.types import Condition, SimMinutes
from dsz.dynamics.registry import register_module
from dsz.world.state import WorldState

if TYPE_CHECKING:
    import numpy as np


@register_module
class SpoilageModule(DynamicsModule):
    """Accumulate spoilage as elapsed time / zone shelf life; at 1.0 the item is spoiled for good.

    Params:
        rate (float, default 1.0): global multiplier on ageing speed.
    """

    name = "spoilage"

    def validate(self) -> None:
        """Require a positive `rate`."""
        if float(self.params.get("rate", 1.0)) <= 0:
            raise ValueError("spoilage.rate must be positive")

    def advance(self, world: WorldState, t0: SimMinutes, t1: SimMinutes, rng: np.random.Generator,
                bus: EventBus) -> None:
        """Age every OK, in-world item over [t0, t1)."""
        dt = (t1 - t0) * float(self.params.get("rate", 1.0))
        for item in world.in_world():
            if item.condition is not Condition.OK:
                continue
            life = item.type.shelf_life.get(world.zone_of(item))
            if life is None:
                continue
            item.spoilage = min(1.0, item.spoilage + dt / life)
            if item.spoilage >= 1.0:
                world.degrade(item.item_id, Condition.SPOILED, cause="spoilage")
