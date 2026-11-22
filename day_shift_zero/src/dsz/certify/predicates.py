"""Trace-based predicate checks for stage S4 (task spec sections 2 and 4).

| Check | Measured on the oracle's trace for one (seed, horizon) pair |
|---|---|
| H1 | Motor skill calls >= theta_L; longest dependency chain >= theta_D; one link of it crosses a day |
| M1 | A P2 claim's item is used >= k motor calls after the robot last saw it, or after the fact was told |
| C1 (a) | The claimed event happens while the robot does not see its fixtures |

C1 (c) and R1 need extra runs; `dsz.certify.verify` does them. The thresholds are pilot
values until they are frozen (task spec section 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from dsz.core.scenario import Instance
from dsz.core.types import MINUTES_PER_DAY

MOTOR = frozenset({"navigate_to", "open", "close", "pick", "place", "set_power", "start_process"})
WHERE_KEYS = ("to", "from", "fixture", "expect_at")


@dataclass(frozen=True)
class Thresholds:
    """θ_L, θ_D and k from the task spec. Pilot values until frozen."""

    calls: int  # θ_L: motor skill calls the oracle makes
    chain: int  # θ_D: longest dependency chain, in calls
    memory_gap: int  # k: motor calls between getting and needing a memory


PILOT_THRESHOLDS = Thresholds(calls=50, chain=6, memory_gap=10)  # pilot, not benchmark values


@dataclass(frozen=True)
class Call:
    """One skill call in a trace, with what it touched."""

    t: int
    name: str
    args: Mapping[str, Any]
    at_before: str | None
    at_after: str | None
    held_before: str | None
    held_after: str | None
    inputs: tuple[str, ...] = ()  # start_process: the items in the fixture
    seen: tuple[str, ...] = ()  # item ids the robot can see after the call
    view: bool = False  # True if the robot can see into its fixture after the call

    @property
    def motor(self) -> bool:
        """Return True for a physical skill (not wait, look, order or say)."""
        return self.name in MOTOR


def h1(calls: list[Call], th: Thresholds) -> list[str]:
    """Return H1 problems for one oracle trace."""
    motor = [c for c in calls if c.motor]
    length, crosses = longest_chain(motor)
    out = []
    if len(motor) < th.calls:
        out.append(f"{len(motor)} motor skill calls < theta_L {th.calls}")
    if length < th.chain:
        out.append(f"longest dependency chain {length} < theta_D {th.chain}")
    if not crosses:
        out.append("no link of the longest dependency chain crosses a day boundary")
    return out


def longest_chain(motor: list[Call]) -> tuple[int, bool]:
    """Return the longest chain of calls that each need the effect of the one before, and if it crosses a day.

    A call needs the robot's position (from navigate_to), the fixture's state (from open,
    close, set_power) and the state of each item it handles (from pick, place, start_process).
    """
    last: dict[tuple, int] = {}
    best: list[tuple[int, bool]] = []
    for i, call in enumerate(motor):
        reads, writes = _effects(call)
        here = (1, False)
        for key in reads:
            j = last.get(key)
            if j is not None:
                length, crosses = best[j]
                here = max(here, (length + 1, crosses or _day(motor[j].t) != _day(call.t)))
        best.append(here)
        for key in writes:
            last[key] = i
    return max(best, default=(0, False))


def memory_gap(calls: list[Call], claim: Mapping[str, Any], instance: Instance, item_types: Mapping[str, str]) -> int:
    """Return the largest number of motor calls between getting and using the claim's memory (0 if never used)."""
    motor = [c for c in calls if c.motor]
    if claim.get("memory") == "T":
        return _told_gap(motor, claim, instance, item_types)
    return _seen_gap(motor, claim, item_types)


def unseen(calls: list[Call], instance: Instance, event_id: str) -> bool:
    """Return True if the robot saw none of the claimed event's fixtures when each occurrence happened.

    An event fires while time passes after a call, so the robot's place then is where the last
    call that started before the event left it.
    """
    for event in (e for e in instance.events if e.source == event_id):
        place = {event.payload[k] for k in WHERE_KEYS if isinstance(event.payload.get(k), str)}
        before = [c for c in calls if c.t < event.t]
        if before and before[-1].at_after in place and before[-1].view:
            return False
    return True


def _seen_gap(motor: list[Call], claim: Mapping[str, Any], item_types: Mapping[str, str]) -> int:
    """Return the gap for class S, D or I: last sight in an earlier visit to the place, then the pick."""
    hidden = set(claim.get("hidden") or ())
    target = (claim.get("consequence") or {}).get("object")
    best = 0
    for i, call in enumerate(motor):
        item = call.held_after
        if call.name != "pick" or item is None or item_types.get(item) != target or call.at_before not in hidden:
            continue
        arrival = i
        while arrival > 0 and motor[arrival - 1].at_after == call.at_before:
            arrival -= 1
        sight = next((j for j in range(arrival - 1, -1, -1) if item in motor[j].seen), None)
        if sight is not None:
            best = max(best, arrival - sight - 1)
    return best


def _told_gap(motor: list[Call], claim: Mapping[str, Any], instance: Instance,
              item_types: Mapping[str, str]) -> int:
    """Return the gap for class T: from the fact's reveal to a delivery for work that needs the fact."""
    fact = next((f for f in instance.facts if f.fact_id == claim.get("fact")), None)
    if fact is None:
        return 0
    needs = {(w.spec["deliver"]["at"], w.spec["deliver"]["item_type"]) for w in instance.work
             if w.work_id in fact.needed_by}
    told = sum(c.t < fact.revealed_at for c in motor)
    uses = [i for i, c in enumerate(motor) if c.name == "place" and c.t >= fact.revealed_at
            and (c.args.get("fixture"), item_types.get(c.held_before or "")) in needs]
    return max((i - told for i in uses), default=0)


def _effects(call: Call) -> tuple[list[tuple], list[tuple]]:
    """Return the state keys a call reads and writes."""
    robot = ("robot",)
    fixture = call.args.get("fixture")
    if call.name == "navigate_to":
        return [], [robot]
    if call.name in ("open", "close", "set_power"):
        return [robot], [("fixture", fixture)]
    if call.name == "pick":
        item = call.held_after
        return ([robot, ("fixture", call.at_before), ("item", item)], [("item", item)]) if item else ([robot], [])
    if call.name == "place":
        item = call.held_before
        return ([robot, ("fixture", fixture), ("item", item)], [("item", item)]) if item else ([robot], [])
    if call.name == "start_process":
        items = [("item", i) for i in call.inputs]
        return [("fixture", fixture), *items], items
    return [], []


def _day(t: int) -> int:
    """Return the zero-based day of minute `t`."""
    return t // MINUTES_PER_DAY

