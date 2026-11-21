"""Oracle and scenario-specific negative controls for care_home_lunches.

All three policies share one scripted planner. They are evaluator-side: the planner reads
the world state and the instance to decide, but it acts only through skill calls, and it
picks objects only by their index in the current detections.

| Policy | Behaviour |
|---|---|
| `care_home_oracle` | Follows every fact and recovers from every scheduled disturbance |
| `care_home_ignore_facts` | Never applies the east-wing diet fact: packs bread in every box |
| `care_home_no_recovery` | Never clears foreign items from the pack counter before packing |

Import path: `scenarios.care_home_lunches.plugins`. Run from `day_shift_zero/`.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Mapping

from dsz.certify.oracle import SkillCompiler, Step, call, pick
from dsz.core.policy import Action, Observation, Policy, TaskBrief
from dsz.core.scenario import Instance, WorkItem
from dsz.core.types import Condition
from dsz.scenario.registries import POLICIES
from dsz.world.state import Item, WorldState

STORE = {"chicken_breast": "fridge_main", "cheese": "fridge_main", "bread": "pantry"}
MARINATE_AHEAD = 16 * 60  # start the marinade when the next hot lunch is this close
COOK_MINUTES = 20
PACK_MINUTES = 5
IDLE_STEP = 30


class ScriptedKitchenPolicy:
    """Plan one task at a time from the world state, then emit its skill calls in order."""

    def __init__(self, instance: Instance, world: WorldState, ignore_facts: bool, recover: bool) -> None:
        """Plan for `instance` over `world`. The two flags turn the oracle into a control."""
        self._instance = instance
        self._world = world
        self._skills = SkillCompiler(world)
        self._ignore_facts = ignore_facts
        self._recover = recover
        self._queue: deque[Step] = deque()
        self._done: set[str] = set()

    def reset(self, brief: TaskBrief) -> None:
        """Clear any queued plan."""
        self._queue.clear()

    def act(self, obs: Observation) -> Action:
        """Return the next skill call of the current plan, planning anew when it is empty."""
        while True:
            if not self._queue:
                self._queue.extend(self._plan())
            skill_call = self._queue.popleft()(self._world)
            if skill_call is not None:
                return skill_call

    # ---- planning ------------------------------------------------------------------------
    def _plan(self) -> list[Step]:
        """Return the steps of the most urgent task."""
        for planner in (self._put_away_held, self._store_loose_stock, self._cook, self._marinate, self._pack):
            steps = planner()
            if steps:
                return steps
        return [call("wait", minutes=self._idle_minutes())]

    def _put_away_held(self) -> list[Step]:
        """Return steps that store an item left in the hand by an interrupted plan."""
        held = self._world.held()
        if held is None or held.item_type not in STORE:
            return []
        dest = STORE[held.item_type]
        return self._skills.visit(dest) + [call("place", fixture=dest)] + self._skills.leave(dest)

    def _store_loose_stock(self) -> list[Step]:
        """Return steps that move one stock item from the dock (or the pack counter) to its store."""
        places = ("dock", "pack_counter") if self._recover else ("dock",)
        for fixture in places:
            for item in sorted(self._world.items_at(fixture), key=lambda i: i.item_id):
                if item.item_type in STORE and item.condition is Condition.OK and not self._in_process(item):
                    return self._skills.move(item.item_id, fixture, STORE[item.item_type])
        return []

    def _cook(self) -> list[Step]:
        """Return steps that cook the marinated chicken and put it on the pass for a released ticket."""
        work = self._open_work("hot_lunch", released=True)
        piece = self._marinated_piece()
        if work is None or piece is None:
            return []
        self._done.add(work.work_id)
        return (self._skills.move(piece.item_id, "fridge_back", "stove")
                + [call("set_power", fixture="stove", on=True),
                   call("start_process", process="cook", fixture="stove"),
                   call("wait", minutes=COOK_MINUTES),
                   pick(lambda w: piece.item_id),
                   call("set_power", fixture="stove", on=False),
                   call("navigate_to", fixture="pass"),
                   call("place", fixture="pass")])

    def _marinate(self) -> list[Step]:
        """Return steps that start tomorrow's marinade in fridge_back with the freshest raw chicken."""
        nxt = self._open_work("hot_lunch", released=False)
        if nxt is None or nxt.released_at - self._world.now > MARINATE_AHEAD:
            return []
        if any(i.item_type == "chicken_breast" for i in self._world.items_at("fridge_back")):
            return []
        raw = [i for i in self._world.items_at("fridge_main")
               if i.item_type == "chicken_breast" and i.condition is Condition.OK]
        if not raw:
            return []
        piece = min(raw, key=lambda i: (i.spoilage, i.item_id))
        return (self._skills.move(piece.item_id, "fridge_main", "fridge_back")
                + [call("start_process", process="marinate", fixture="fridge_back")])

    def _pack(self) -> list[Step]:
        """Return steps that pack and dispatch a box for the released ticket with the earliest deadline."""
        work = self._open_work("sandwich_box", released=True)
        if work is None:
            return []
        clutter = self._store_loose_stock() if self._recover else []
        if clutter:
            return clutter
        filling = self._filling(work.spec["deliver"].get("exclude_allergens", ()))
        if filling is None:
            return []
        self._done.add(work.work_id)
        src = filling.location.fixture
        return (self._skills.move(filling.item_id, src, "pack_counter")
                + [call("start_process", process="pack", fixture="pack_counter"),
                   call("wait", minutes=PACK_MINUTES),
                   pick(_box_on_pack_counter),
                   call("navigate_to", fixture="pass"),
                   call("place", fixture="pass")])

    # ---- queries -------------------------------------------------------------------------
    def _filling(self, excluded: tuple[str, ...]) -> Item | None:
        """Return the stored filling to use: bread unless the box must be gluten-free, then cheese."""
        banned = set() if self._ignore_facts else set(excluded)
        for item_type in ("bread", "cheese"):
            stock = [i for i in self._world.items_at(STORE[item_type])
                     if i.item_type == item_type and i.condition is Condition.OK and not banned & set(i.allergens)]
            if stock:
                return min(stock, key=lambda i: i.item_id)
        return None

    def _marinated_piece(self) -> Item | None:
        """Return the chicken in fridge_back whose marinade has finished, if any."""
        for item in self._world.items_at("fridge_back"):
            if item.item_type == "chicken_breast" and "marinated" in item.stages and item.condition is Condition.OK:
                return item
        return None

    def _open_work(self, kind: str, released: bool) -> WorkItem | None:
        """Return the earliest-deadline work item of `kind` that this policy has not yet served."""
        now = self._world.now
        open_ = [w for w in self._instance.work
                 if w.kind == kind and w.work_id not in self._done and w.deadline >= now
                 and (w.released_at <= now) == released]
        return min(open_, key=lambda w: (w.deadline, w.work_id), default=None)

    def _in_process(self, item: Item) -> bool:
        """Return True if the item is an input of a running or finished process."""
        return any(item.item_id in p.item_ids for p in self._world.processes)

    def _idle_minutes(self) -> int:
        """Return how long to wait: until the next release or event, at most IDLE_STEP minutes."""
        now = self._world.now
        times = [w.released_at for w in self._instance.work if w.released_at > now]
        times += [e.t for e in self._instance.events if e.t > now]
        return max(1, min([IDLE_STEP] + [t - now for t in times]))


def _box_on_pack_counter(world: WorldState) -> str | None:
    """Return the id of the packed box on the pack counter."""
    boxes = [i.item_id for i in world.items_at("pack_counter") if i.item_type == "meal_box"]
    return min(boxes) if boxes else None


def _factory(ignore_facts: bool, recover: bool) -> Callable[[Instance, WorldState, Mapping[str, Any]], Policy]:
    """Return a policy factory for one planner configuration."""
    def build(instance: Instance, world: WorldState, params: Mapping[str, Any]) -> Policy:
        """Build the scripted planner for one run."""
        return ScriptedKitchenPolicy(instance, world, ignore_facts, recover)
    return build


for _name, _flags in {"care_home_oracle": (False, True), "care_home_ignore_facts": (True, True),
                      "care_home_no_recovery": (False, False)}.items():
    if _name not in POLICIES:
        POLICIES.add(_name, _factory(*_flags))
