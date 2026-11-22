"""Executor part of the generic oracle: greedy scheduler, monitor and skill steps (task spec section 6).

Each decision the executor replans from its belief:

1. Put down anything left in the hand.
2. Housekeeping: carry stock off delivery shelves; with the monitor on, also carry it off
   process fixtures and out of places where it spoils faster than in storage.
3. Work: take open work items in order of latest start (no search). Give each the most
   advanced matching item, oldest first. Plan the first one whose next step can run now.
4. Otherwise wait for the next release, event or process.

The executor acts only through skill calls (OC1) and draws no random numbers (OC2).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from dsz.certify.oracle.belief import Belief
from dsz.certify.oracle.compiler import SkillCompiler, Step, call, pick
from dsz.certify.oracle.recipe import KitchenPlan, Recipe, attended, shelf_life
from dsz.core.policy import Action, Observation, TaskBrief
from dsz.core.scenario import Instance
from dsz.core.types import Condition, SkillCall
from dsz.world.catalog import ITEM_TYPES, PROCESSES
from dsz.world.state import Item, WorldState

LOOKAHEAD = 24 * 60  # plan work whose latest start is within a day
MOVE_MINUTES = 10  # allowance per carry when estimating a latest start
IDLE_STEP = 30
MAX_EMPTY_PLANS = 5
MESSAGE_KINDS = ("message", "goal_change")


@dataclass(frozen=True)
class OracleConfig:
    """The fixed changes that turn the oracle into a control."""

    recover: bool = True  # the monitor: clear fixtures and rescue stock from bad places
    forget_after: int | None = None  # forget a fact once this many newer messages arrived


class GenericOracle:
    """Plan from the instance and a belief; act through skill calls only."""

    def __init__(self, instance: Instance, world: WorldState, belief: Belief, config: OracleConfig) -> None:
        """Plan for `instance` in `world`. Raise RecipeError if a work item has no recipe."""
        self._instance = instance
        self._world = world
        self._belief = belief
        self._cfg = config
        self._plan = KitchenPlan(instance)
        self._skills = SkillCompiler(world)
        self._queue: deque[Step] = deque()
        self._done: set[str] = set()
        self._messages = sorted([f.revealed_at for f in instance.facts]
                                + [w.released_at for w in instance.work if w.spec.get("ticket")]
                                + [e.t for e in instance.events if e.kind in MESSAGE_KINDS])

    def reset(self, brief: TaskBrief) -> None:
        """Drop any queued steps."""
        self._queue.clear()

    def act(self, obs: Observation) -> Action:
        """Return the next skill call. Replan when the queue is empty or a step no longer applies."""
        self._belief.observe(self._world)
        for _ in range(MAX_EMPTY_PLANS):
            if not self._queue:
                self._queue.extend(self._next_task())
            while self._queue:
                skill_call = self._queue.popleft()(self._world)
                if skill_call is None:  # the world differs from the plan: replan
                    self._queue.clear()
                    break
                return skill_call
        return SkillCall("wait", {"minutes": 1})

    # ---- tasks ---------------------------------------------------------------------------
    def _next_task(self) -> list[Step]:
        """Return the steps of the most urgent task."""
        held = self._world.held()
        if held is not None:
            return self._put_down(held)
        return self._housekeeping() or self._work() or [call("wait", minutes=self._idle_minutes())]

    def _put_down(self, item: Item) -> list[Step]:
        """Return steps that put a held item in its storage, or where the robot stands."""
        dest = self._plan.storage.get(item.item_type) or self._world.robot_at
        return self._skills.visit(dest) + [call("place", fixture=dest)] + self._skills.leave(dest)

    def _housekeeping(self) -> list[Step]:
        """Return steps that carry the most urgent loose stock item to its storage."""
        loose = [(self._life_left(i, f), i.item_id, f, store) for i, f, store in self._stored_badly()]
        if not loose:
            return []
        _, iid, src, dest = min(loose)
        return self._skills.move(iid, src, dest)

    def _stored_badly(self) -> list[tuple[Item, str, str]]:
        """Return (item, believed fixture, storage) for stock that should move to storage."""
        out = []
        running = self._running_fixtures()
        for item in self._world.in_world():
            f, store = self._belief.where(item.item_id), self._plan.storage.get(item.item_type)
            if f is None or store is None or f == store or f in self._plan.targets or f in running:
                continue
            if item.condition is not Condition.OK:
                continue
            on_shelf = self._plan.fixtures[f] == "delivery_shelf"
            in_the_way = f in self._plan.process_fixture.values()
            warmer = self._life_left(item, f) < self._life_left(item, store)
            if on_shelf or (self._cfg.recover and (in_the_way or warmer)):
                out.append((item, f, store))
        return out

    def _work(self) -> list[Step]:
        """Return steps for the first actionable work item, in order of latest start."""
        now, claimed = self._world.now, set()
        open_ = [r for r in self._plan.recipes.values()
                 if r.work.work_id not in self._done and now <= r.work.deadline + int(r.work.spec.get("grace", 0))
                 and _latest_start(r) - now <= LOOKAHEAD]
        for recipe in sorted(open_, key=lambda r: (_latest_start(r), r.work.work_id)):
            item = self._assign(recipe, claimed)
            if item is not None:
                claimed.add(item.item_id)
            steps = self._steps(recipe, item, claimed)
            if steps:
                return steps
        return []

    def _steps(self, recipe: Recipe, item: Item | None, claimed: set[str]) -> list[Step]:
        """Return the next steps for one work item, or [] if it cannot advance now."""
        released = self._world.now >= recipe.work.released_at
        running = self._running_fixtures()
        if item is None:
            if recipe.combine is None or (not released and attended(recipe.combine)):
                return []
            fixture = self._plan.process_fixture[recipe.combine]
            source = None if fixture in running else self._ingredient(recipe, claimed)
            if source is None:
                return []
            claimed.add(source.item_id)
            return self._run(recipe.combine, fixture, source, recipe)
        remaining = recipe.remaining(item.stages)
        if not remaining:
            if not released:
                return []
            self._done.add(recipe.work.work_id)
            return self._skills.move(item.item_id, self._belief.where(item.item_id), recipe.deliver["at"])
        fixture = self._plan.process_fixture[remaining[0]]
        if fixture in running or self._in_process(item) or (not released and all(map(attended, remaining))):
            return []
        return self._run(remaining[0], fixture, item, recipe)

    def _run(self, process: str, fixture: str, item: Item, recipe: Recipe) -> list[Step]:
        """Return steps that put `item` in `fixture`, run `process`, and collect the result if attended."""
        spec = PROCESSES.get(process)
        src = self._belief.where(item.item_id)
        steps = self._clear(fixture, keep=item.item_id) if self._cfg.recover else []
        steps += self._skills.move(item.item_id, src, fixture) if src != fixture else [
            call("navigate_to", fixture=fixture)]
        if spec.requires_power:
            steps.append(call("set_power", fixture=fixture, on=True))
        steps.append(call("start_process", process=process, fixture=fixture))
        if not attended(process):
            return steps
        result = spec.product_type if spec.combines else item.item_type
        steps += [call("wait", minutes=spec.duration)] + self._skills.visit(fixture)
        steps.append(pick(_newest(fixture, result) if spec.combines else (lambda w: item.item_id)))
        if spec.requires_power:
            steps.append(call("set_power", fixture=fixture, on=False))
        steps += self._skills.leave(fixture)
        last = not (recipe.stages if spec.combines else recipe.remaining(item.stages | {spec.adds_stage}))
        if last and self._world.now >= recipe.work.released_at:
            self._done.add(recipe.work.work_id)
            dest = recipe.deliver["at"]
        else:
            dest = self._plan.storage.get(result) or fixture
        return steps + self._skills.visit(dest) + [call("place", fixture=dest)] + self._skills.leave(dest)

    def _clear(self, fixture: str, keep: str) -> list[Step]:
        """Return steps that carry everything except `keep` out of `fixture` to storage."""
        steps: list[Step] = []
        for item in self._world.in_world():
            store = self._plan.storage.get(item.item_type)
            if item.item_id != keep and self._belief.where(item.item_id) == fixture and store and store != fixture:
                steps += self._skills.move(item.item_id, fixture, store)
        return steps

    # ---- choices -------------------------------------------------------------------------
    def _assign(self, recipe: Recipe, claimed: set[str]) -> Item | None:
        """Return the most advanced usable item for `recipe`, oldest first."""
        wanted = set(recipe.deliver.get("stages", ()))
        excluded = self._excluded(recipe)
        options = [i for i in self._usable(claimed) if i.item_type == recipe.item_type
                   and i.stages <= wanted and not excluded & set(i.allergens)]
        return min(options, key=lambda i: (-len(i.stages), -i.spoilage, i.item_id), default=None)

    def _ingredient(self, recipe: Recipe, claimed: set[str]) -> Item | None:
        """Return the input for a combining recipe, greedily.

        Prefer the ingredient type that the fewest open work items can accept (keep the
        flexible stock for constrained work), then the best-stocked type, then the oldest item.
        """
        excluded = self._excluded(recipe)
        options = [i for i in self._usable(claimed) if "ingredient" in ITEM_TYPES.get(i.item_type).tags
                   and i.item_type not in self._plan.delivered_types and not excluded & set(i.allergens)]
        types = {i.item_type for i in options}
        stock = {t: sum(i.item_type == t for i in options) for t in types}
        takers = {t: sum(1 for r in self._open_combines(recipe.combine)
                         if not self._excluded(r) & ITEM_TYPES.get(t).allergens) for t in types}
        return min(options, key=lambda i: (takers[i.item_type], -stock[i.item_type], -i.spoilage, i.item_id),
                   default=None)

    def _open_combines(self, process: str | None) -> list[Recipe]:
        """Return the open recipes that use the combining `process`."""
        return [r for r in self._plan.recipes.values() if r.combine == process
                and r.work.work_id not in self._done and r.work.deadline >= self._world.now]

    def _usable(self, claimed: set[str]) -> list[Item]:
        """Return items with a believed place, in good condition, not claimed and not already delivered."""
        return [i for i in self._world.in_world() if i.item_id not in claimed and i.condition is Condition.OK
                and self._belief.where(i.item_id) not in (None, *self._plan.targets)]

    def _excluded(self, recipe: Recipe) -> set[str]:
        """Return the allergens the delivery must avoid, minus any the policy has forgotten."""
        excluded = set(recipe.deliver.get("exclude_allergens", ()))
        if self._cfg.forget_after is None:
            return excluded
        constraints = {f["id"]: f.get("constraint", {}) for f in self._instance.params.get("facts", [])}
        for fact in self._instance.facts:
            newer = sum(fact.revealed_at < t <= self._world.now for t in self._messages)
            if recipe.work.work_id in fact.needed_by and newer >= self._cfg.forget_after:
                excluded -= set(constraints.get(fact.fact_id, {}).get("exclude_allergens", ()))
        return excluded

    # ---- queries -------------------------------------------------------------------------
    def _running_fixtures(self) -> set[str]:
        """Return fixtures with a process that has not completed."""
        return {p.fixture_id for p in self._world.processes if not p.completed}

    def _in_process(self, item: Item) -> bool:
        """Return True if `item` is an input of a process that has not completed."""
        return any(item.item_id in p.item_ids and not p.completed for p in self._world.processes)

    def _life_left(self, item: Item, fixture: str) -> float:
        """Return minutes until `item` spoils if it stays in `fixture`."""
        zone = self._world.fixture(fixture).effective_zone()
        return (1.0 - item.spoilage) * shelf_life(item.item_type, zone)

    def _idle_minutes(self) -> int:
        """Return how long to wait: until the next release, event, process end or planning window."""
        now = self._world.now
        times = [w.released_at for w in self._instance.work] + [e.t for e in self._instance.events]
        times += [p.done_at for p in self._world.processes if not p.completed]
        times += [_latest_start(r) - LOOKAHEAD for r in self._plan.recipes.values()]
        return max(1, min([IDLE_STEP] + [t - now for t in times if t > now]))


def _latest_start(recipe: Recipe) -> int:
    """Return the latest time the whole recipe can start and still meet the deadline."""
    procs = [p for p in (recipe.combine, *recipe.stages) if p]
    return recipe.work.deadline - sum(PROCESSES.get(p).duration for p in procs) - MOVE_MINUTES * (len(procs) + 1)


def _newest(fixture: str, item_type: str):
    """Return a selector for the most recently made item of `item_type` at `fixture`."""
    def select(world: WorldState) -> str | None:
        """Pick the newest matching item id."""
        found = [i for i in world.items_at(fixture) if i.item_type == item_type]
        return max(found, key=lambda i: (i.created_at, i.item_id)).item_id if found else None
    return select
