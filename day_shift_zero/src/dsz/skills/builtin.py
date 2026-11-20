"""Built-in skills. Each class is one skill (Command pattern); all feedback is sensor-derived."""

from __future__ import annotations

import math
from typing import Any, Mapping

from dsz.core.skills import Skill, SkillArgError, SkillContext, SkillOutcome
from dsz.core.types import SensorReading
from dsz.skills.registry import register_skill

MAX_WAIT_MINUTES = 8 * 60


def _minutes(seconds: float) -> int:
    """Convert actuation seconds to whole simulated minutes (at least one for physical skills)."""
    return max(1, math.ceil(seconds / 60.0))


def _outcome(seconds: float, sensors: SensorReading) -> SkillOutcome:
    """Wrap an actuation result; a backend note (e.g. "door is closed") becomes the message."""
    return SkillOutcome(_minutes(seconds), sensors, str(sensors.extra.get("note", "")))


@register_skill
class NavigateTo(Skill):
    """Drive to a fixture."""

    name = "navigate_to"
    doc = "Drive the base to the named fixture."
    args = {"fixture": str}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Move to the fixture's approach pose."""
        secs, sensors = ctx.actuation.navigate_to(args["fixture"])
        return _outcome(secs, sensors)


@register_skill
class Open(Skill):
    """Open a fixture door."""

    name = "open"
    doc = "Open the door of the fixture you are at."
    args = {"fixture": str}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Open the door."""
        secs, sensors = ctx.actuation.set_open(args["fixture"], True)
        return _outcome(secs, sensors)


@register_skill
class Close(Skill):
    """Close a fixture door."""

    name = "close"
    doc = "Close the door of the fixture you are at."
    args = {"fixture": str}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Close the door."""
        secs, sensors = ctx.actuation.set_open(args["fixture"], False)
        return _outcome(secs, sensors)


@register_skill
class Pick(Skill):
    """Grasp a visible object by its detection index."""

    name = "pick"
    doc = "Grasp the object with this index in your current detections."
    args = {"index": int}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Try the grasp; the gripper reading tells whether something is held."""
        secs, sensors = ctx.actuation.grasp(args["index"])
        return _outcome(secs, sensors)


@register_skill
class Place(Skill):
    """Put the held object in or on a fixture."""

    name = "place"
    doc = "Place the held object in or on the fixture you are at (optional slot, e.g. a shelf)."
    args = {"fixture": str}
    optional = {"slot": str}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Release the held object at the fixture."""
        secs, sensors = ctx.actuation.place(args["fixture"], args.get("slot"))
        return _outcome(secs, sensors)


@register_skill
class SetPower(Skill):
    """Switch a powered fixture on or off."""

    name = "set_power"
    doc = "Switch the fixture you are at on (on=true) or off (on=false)."
    args = {"fixture": str, "on": bool}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Toggle power."""
        secs, sensors = ctx.actuation.set_power(args["fixture"], args["on"])
        return _outcome(secs, sensors)


@register_skill
class StartProcess(Skill):
    """Start a process (bake, chill, marinate...) on everything in a fixture."""

    name = "start_process"
    doc = "Start a process on everything inside the fixture, e.g. bake in the oven."
    args = {"process": str, "fixture": str}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Ask the process control to start; report its reason on failure."""
        reason = ctx.processes.start_in(args["process"], args["fixture"])
        return SkillOutcome(1, SensorReading(), reason or f"{args['process']} started")


@register_skill
class Look(Skill):
    """Take a fresh look without moving."""

    name = "look"
    doc = "Observe again without acting."

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Do nothing physical; the next observation is fresh."""
        return SkillOutcome(1)


@register_skill
class Wait(Skill):
    """Let time pass."""

    name = "wait"
    doc = f"Let time pass, in minutes (1..{MAX_WAIT_MINUTES})."
    args = {"minutes": int}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Return the waiting time; the runtime advances the world."""
        m = args["minutes"]
        if not 1 <= m <= MAX_WAIT_MINUTES:
            raise SkillArgError(f"minutes must be 1..{MAX_WAIT_MINUTES}")
        return SkillOutcome(m)


@register_skill
class Order(Skill):
    """Order supplies."""

    name = "order"
    doc = "Order qty units of an item type from a supplier. The supplier replies by message."
    args = {"supplier": str, "item_type": str, "qty": int}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Send the order."""
        if args["qty"] < 1:
            raise SkillArgError("qty must be at least 1")
        ctx.orders.place(args["supplier"], args["item_type"], args["qty"])
        return SkillOutcome(1, message="order sent")


@register_skill
class Say(Skill):
    """Speak to someone."""

    name = "say"
    doc = "Say something to a person (customer, client, manager)."
    args = {"to": str, "text": str}

    def run(self, ctx: SkillContext, args: Mapping[str, Any]) -> SkillOutcome:
        """Deliver the words."""
        ctx.speech.say(args["to"], args["text"])
        return SkillOutcome(1)
