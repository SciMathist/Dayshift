"""Work tracking: a generic, data-driven completion predicate for work items.

A work item's `spec["deliver"]` says what must exist where, by when:

    deliver:
      item_type: meal_box          # required
      at: dispatch_shelf           # required fixture id
      stages: [packed]             # stages the item must have (default none)
      exclude_allergens: [nuts]    # allergens it must not contain (may come from hidden facts)
    collect: true                  # a courier takes the item away on completion (default false)
    grace: 30                      # minutes after the deadline before the work expires (default 0)

Completion happens when a matching item is at the fixture. Items with a forbidden
allergen or a bad condition still complete the work (the courier takes what is there),
but each such delivery is recorded as a violation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from dsz.core.events import DomainEvent, EventBus
from dsz.core.scenario import WorkItem
from dsz.core.sim import WorldEditor
from dsz.core.types import Condition, SimMinutes
from dsz.world.state import Item, WorldState


@dataclass(slots=True)
class WorkStatus:
    """Evaluator-side progress of one work item."""

    work: WorkItem
    released: bool = False
    done_at: SimMinutes | None = None
    item_id: str | None = None
    violations: list[str] = field(default_factory=list)
    expired: bool = False

    @property
    def on_time(self) -> bool:
        """Return True if completed by the deadline."""
        return self.done_at is not None and self.done_at <= self.work.deadline


def deliver_spec(work: WorkItem) -> Mapping[str, Any]:
    """Return the work item's deliver predicate. Raise ValueError if it is missing or incomplete."""
    d = work.spec.get("deliver")
    if not isinstance(d, Mapping) or "item_type" not in d or "at" not in d:
        raise ValueError(f"work '{work.work_id}' needs deliver.item_type and deliver.at")
    return d


def matches(item: Item, deliver: Mapping[str, Any]) -> bool:
    """Return True if `item` has the right type and stages (allergens and condition are judged separately)."""
    return item.item_type == deliver["item_type"] and set(deliver.get("stages", ())) <= item.stages


def violations_of(item: Item, deliver: Mapping[str, Any]) -> list[str]:
    """Return the violations a delivery of `item` would cause."""
    out = []
    bad = set(deliver.get("exclude_allergens", ())) & set(item.allergens)
    if bad:
        out.append("allergen:" + ",".join(sorted(bad)))
    if item.condition is not Condition.OK:
        out.append("condition:" + item.condition.value)
    return out


class WorkTracker:
    """Track released work and detect completion after every time step (evaluator-side)."""

    def __init__(self, work: Sequence[WorkItem], world: WorldState, editor: WorldEditor, bus: EventBus) -> None:
        """Track `work`. Validate every deliver predicate up front."""
        for w in work:
            deliver_spec(w)
        self._status = {w.work_id: WorkStatus(w) for w in work}
        self._world = world
        self._editor = editor
        self._bus = bus
        self._claimed: set[str] = set()

    @property
    def status(self) -> Mapping[str, WorkStatus]:
        """Return status by work id."""
        return self._status

    def update(self) -> None:
        """Release due work, complete what is satisfied, and expire what is overdue."""
        now = self._world.now
        for st in sorted(self._status.values(), key=lambda s: (s.work.deadline, s.work.work_id)):
            w = st.work
            if st.done_at is not None or st.expired or w.released_at > now:
                continue
            st.released = True
            item = self._find(deliver_spec(w))
            if item is not None:
                self._complete(st, item)
            elif now > w.deadline + int(w.spec.get("grace", 0)):
                st.expired = True
                self._bus.publish(DomainEvent(now, "work.expired", {"work": w.work_id}))

    def _find(self, deliver: Mapping[str, Any]) -> Item | None:
        """Return the first unclaimed matching item at the target fixture (by id), or None."""
        for item in sorted(self._world.items_at(deliver["at"]), key=lambda i: i.item_id):
            if item.item_id not in self._claimed and matches(item, deliver):
                return item
        return None

    def _complete(self, st: WorkStatus, item: Item) -> None:
        """Record completion, claim or collect the item, and publish the outcome."""
        w = st.work
        st.done_at = self._world.now
        st.item_id = item.item_id
        st.violations = violations_of(item, deliver_spec(w))
        self._claimed.add(item.item_id)
        if w.spec.get("collect", False):
            self._editor.remove(item.item_id)
        self._bus.publish(DomainEvent(self._world.now, "work.completed",
                                      {"work": w.work_id, "item": item.item_id, "on_time": st.on_time,
                                       "violations": list(st.violations)}))
