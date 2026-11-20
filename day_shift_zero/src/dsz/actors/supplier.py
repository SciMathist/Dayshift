"""Supplier actor: fulfils robot orders from the object pool after a seeded lead time."""

from __future__ import annotations

from typing import Any, Mapping

from dsz.actors.registry import register_actor
from dsz.core.actors import Actor
from dsz.core.events import DomainEvent, EventContext
from dsz.core.scenario import ScheduledEvent
from dsz.core.types import MINUTES_PER_DAY, LocationKind, Message


@register_actor
class Supplier(Actor):
    """React to `order.placed` by scheduling a delivery of parked pool items.

    Params:
        lead_time_days (list[int, int]): inclusive range of delivery lag in days.
        fixture (str): where deliveries land (e.g. "delivery_shelf").
        arrive_at_minute (int, default 480): time of day deliveries arrive (08:00).
        short_ship_p (float, default 0.0): chance that each unit is missing from the delivery.

    Out-of-stock (pool exhausted) is reported to the robot as a message, as a real supplier would.
    """

    role = "supplier"

    def __init__(self, name: str, params: Mapping[str, Any]) -> None:
        """Create the supplier. Raise ValueError if no delivery fixture is given."""
        super().__init__(name, params)
        if "fixture" not in self.params:
            raise ValueError("supplier needs a delivery 'fixture'")
        self._pending: list[set[str]] = []
        self._ctx: EventContext | None = None

    def attach(self, ctx: EventContext) -> None:
        """Subscribe to order placements."""
        self._ctx = ctx
        ctx.bus.subscribe("order.placed", self._on_order)

    def _on_order(self, ev: DomainEvent) -> None:
        """Reserve pool items, draw lead time and shortfall, and schedule the delivery."""
        ctx = self._ctx
        if ev.data.get("supplier", self.name) != self.name:
            return
        item_type, qty = ev.data["item_type"], int(ev.data["qty"])
        reserved = self._reserved()
        parked = ctx.world.items_of_type(item_type, LocationKind.PARKED)
        stock = [i.item_id for i in parked if i.item_id not in reserved]
        lo, hi = self.params.get("lead_time_days", [1, 1])
        days = int(ctx.rng.integers(lo, hi + 1))
        short_p = float(self.params.get("short_ship_p", 0.0))
        units = [iid for iid in stock[:qty] if ctx.rng.random() >= short_p]
        day = ctx.world.now // MINUTES_PER_DAY + days
        t = day * MINUTES_PER_DAY + int(self.params.get("arrive_at_minute", 480))
        if units:
            self._pending.append(set(units))
            ctx.scheduler.schedule(ScheduledEvent(t, "delivery", {"items": units, "fixture": self.params["fixture"]}))
        text = (f"Order confirmed: {len(units)} x {item_type}, arriving in {days} day(s)." if units
                else f"Sorry, {item_type} is out of stock.")
        ctx.channels.post(Message(ctx.world.now, "supplier", self.name, text))
        ctx.bus.publish(DomainEvent(ctx.world.now, "order.accepted",
                                    {"supplier": self.name, "item_type": item_type, "requested": qty,
                                     "shipped": len(units), "arrive_t": t if units else None}))

    def _reserved(self) -> set[str]:
        """Return pool items already promised to an undelivered order."""
        world = self._ctx.world
        still = [s for s in self._pending if any(world.item(i).location.kind is LocationKind.PARKED for i in s)]
        self._pending = still
        return set().union(*still) if still else set()
