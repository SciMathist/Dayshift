"""Built-in scheduled-event handlers. Each class is one event kind (Command pattern).

Payload keys are documented per class. Every handler applies its effect to the state it
finds; if its target is gone, it publishes `event.noop` instead of failing.
"""

from __future__ import annotations

from typing import Any, Mapping

from dsz.core.events import DomainEvent, EventContext, EventHandler
from dsz.core.scenario import ScheduledEvent
from dsz.core.types import Location, LocationKind, Message
from dsz.events.registry import register_event


def _noop(ctx: EventContext, ev: ScheduledEvent, why: str) -> None:
    """Publish that `ev` had no effect, and why."""
    ctx.bus.publish(DomainEvent(ctx.world.now, "event.noop", {"kind": ev.kind, "why": why}))


@register_event
class MessageEvent(EventHandler):
    """Post a message on a channel: facts, order tickets, brief changes.

    Payload: channel, sender, text; optional fact_id (recorded evaluator-side for M1 tracking).
    """

    kind = "message"

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Post the message and record any fact id."""
        p = event.payload
        ctx.channels.post(Message(ctx.world.now, p["channel"], p["sender"], p["text"]))
        if "fact_id" in p:
            ctx.bus.publish(DomainEvent(ctx.world.now, "fact.revealed", {"fact": p["fact_id"]}))


@register_event
class DeliveryEvent(EventHandler):
    """Bring pool items into the world at a fixture (supplier delivery).

    Payload: items (list of parked item ids), fixture.
    """

    kind = "delivery"

    def touches(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        """Return the delivery fixture."""
        return (payload["fixture"],)

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Spawn each still-parked item; skip any that is not parked."""
        fixture = event.payload["fixture"]
        arrived = []
        for iid in event.payload["items"]:
            if ctx.world.item(iid).location.kind is LocationKind.PARKED:
                ctx.editor.spawn(iid, Location.at(fixture))
                arrived.append(iid)
        if not arrived:
            _noop(ctx, event, "no parked items")
            return
        ctx.bus.publish(DomainEvent(ctx.world.now, "delivery.arrived", {"fixture": fixture, "items": arrived}))


@register_event
class RelocateEvent(EventHandler):
    """Move an item without the robot (a co-worker tidies up). Unobserved unless `observable`.

    Payload: to (fixture id) and either item (id) or item_type (the first such item by id);
    optional expect_at (fixture id the item must be in). Generators use item_type, because
    where items are depends on the agent.
    """

    kind = "relocate"

    def touches(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        """Return the destination and, if given, the expected source."""
        return tuple(f for f in (payload.get("expect_at"), payload["to"]) if f)

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Move the item if it is in the world, not held, and where expected."""
        p = event.payload
        iid = p.get("item") or self._pick(ctx, p)
        if iid is None:
            _noop(ctx, event, "no matching item")
            return
        loc = ctx.world.item(iid).location
        if loc.kind is not LocationKind.FIXTURE:
            _noop(ctx, event, f"item is {loc.kind.value}")
            return
        if p.get("expect_at") and loc.fixture != p["expect_at"]:
            _noop(ctx, event, "item not where expected")
            return
        try:
            ctx.editor.move(iid, Location.at(p["to"]))
        except ValueError as e:  # destination full
            _noop(ctx, event, str(e))

    @staticmethod
    def _pick(ctx: EventContext, p: Mapping[str, Any]) -> str | None:
        """Return the first item of `item_type` (at `expect_at`, if given) that is not already at `to`."""
        for item in ctx.world.items_of_type(p["item_type"], LocationKind.FIXTURE):
            if item.location.fixture != p["to"] and (not p.get("expect_at") or item.location.fixture == p["expect_at"]):
                return item.item_id
        return None


@register_event
class WorkReleaseEvent(EventHandler):
    """Hand a work ticket to the robot (an order, a milestone request).

    Payload: work_id, channel, sender, text. The ticket never contains hidden constraints.
    """

    kind = "work_release"

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Post the ticket and record the release evaluator-side."""
        p = event.payload
        ctx.channels.post(Message(ctx.world.now, p["channel"], p["sender"], p["text"]))
        ctx.bus.publish(DomainEvent(ctx.world.now, "work.released", {"work": p["work_id"]}))


@register_event
class ConsumeEvent(EventHandler):
    """An actor uses up items of a type (household member eats, staff takes stock).

    Payload: item_type, count; optional from (fixture id) to restrict where items are taken.
    Takes the oldest OK items first, so stock-keeping mistakes surface later.
    """

    kind = "consume"

    def touches(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        """Return the source fixture if restricted."""
        return (payload["from"],) if payload.get("from") else ()

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Remove up to `count` matching items; publish a shortfall if there are fewer."""
        p = event.payload
        pool = [i for i in ctx.world.items_of_type(p["item_type"], LocationKind.FIXTURE)
                if i.condition.value == "ok" and (not p.get("from") or i.location.fixture == p["from"])]
        pool.sort(key=lambda i: (i.created_at, i.item_id))
        taken = [i.item_id for i in pool[: int(p["count"])]]
        for iid in taken:
            ctx.editor.remove(iid)
        short = int(p["count"]) - len(taken)
        ctx.bus.publish(DomainEvent(ctx.world.now, "stock.consumed",
                                    {"item_type": p["item_type"], "taken": taken, "short": short}))


@register_event
class DoorLeftOpenEvent(EventHandler):
    """Someone leaves a fixture door open. Payload: fixture."""

    kind = "door_left_open"

    def touches(self, payload: Mapping[str, Any]) -> tuple[str, ...]:
        """Return the fixture."""
        return (payload["fixture"],)

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Open the door."""
        ctx.editor.set_fixture_open(event.payload["fixture"], True)


@register_event
class EquipmentFaultEvent(EventHandler):
    """Sudden equipment fault: lower a fixture's health. Payload: fixture, health (0..1).

    A fridge or freezer below health 0.5 works at ambient temperature, so its items
    spoil at the ambient rate. Symbolic detections do not show this.
    """

    kind = "equipment_fault"

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Lower the fixture health (never raises it) and publish the fault evaluator-side."""
        fx = ctx.world.fixture(event.payload["fixture"])
        fx.health = min(fx.health, float(event.payload["health"]))
        ctx.bus.publish(DomainEvent(ctx.world.now, "fixture.fault",
                                    {"fixture": fx.fixture_id, "health": fx.health}))


@register_event
class GoalChangeEvent(EventHandler):
    """The objective changes partway (client revises the brief).

    Payload: change (mapping the scenario's success check reads), channel, sender, text.
    The robot learns of it only through the message.
    """

    kind = "goal_change"

    def apply(self, ctx: EventContext, event: ScheduledEvent) -> None:
        """Record the change evaluator-side and tell the robot."""
        p = event.payload
        ctx.bus.publish(DomainEvent(ctx.world.now, "goal.changed", {"change": dict(p["change"])}))
        ctx.channels.post(Message(ctx.world.now, p["channel"], p["sender"], p["text"]))
