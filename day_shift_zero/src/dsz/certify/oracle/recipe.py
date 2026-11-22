"""Recipe part of the generic oracle: regress each work item's deliver stages to processes (task spec section 6).

A recipe is static. It names processes and the fixtures that run them, never items, times
or skill calls. The kitchen plan (`KitchenPlan`) fixes, once per instance, which fixture
runs each process and where each item type is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from dsz.core.scenario import Instance, WorkItem
from dsz.core.types import LocationKind, TempZone
from dsz.world.catalog import FIXTURE_KINDS, ITEM_TYPES, PROCESSES, ProcessSpec

ATTEND_LIMIT = 60  # minutes: the robot waits beside a process this short, or one that can overrun
NOT_STORAGE_KINDS = frozenset({"delivery_shelf", "dispatch_shelf", "trash"})


class RecipeError(ValueError):
    """The generic oracle cannot derive a recipe for a work item."""


@dataclass(frozen=True)
class Recipe:
    """The processes that turn stock into one work item's delivery."""

    work: WorkItem
    item_type: str
    combine: str | None  # the combining process that makes `item_type`, if any
    stages: tuple[str, ...]  # processes applied to the item itself, in order

    @property
    def deliver(self) -> Mapping:
        """Return the work item's deliver predicate."""
        return self.work.spec["deliver"]

    def remaining(self, done: set[str]) -> tuple[str, ...]:
        """Return the processes still needed for an item that already has the stages in `done`."""
        return tuple(p for p in self.stages if PROCESSES.get(p).adds_stage not in done)


def attended(process: str) -> bool:
    """Return True if the robot should wait beside `process` and collect it when done."""
    spec = PROCESSES.get(process)
    return spec.duration <= ATTEND_LIMIT or spec.overrun_tolerance is not None


def recipe_for(work: WorkItem, fixture_kinds: set[str]) -> Recipe:
    """Return the recipe for `work`, using only processes that some fixture in the kitchen can run.

    Raises:
        RecipeError: if a stage has no process, or the stages cannot be ordered.
    """
    deliver = work.spec["deliver"]
    item_type = deliver["item_type"]
    order: list[str] = []  # stages, each after its prerequisites (depth-first regression)

    def need(stage: str, path: tuple[str, ...]) -> None:
        """Add `stage` after the stages its process requires."""
        if stage in order:
            return
        if stage in path:
            raise RecipeError(f"work {work.work_id}: stage '{stage}' requires itself")
        for pre in sorted(_process_for(stage, fixture_kinds).requires_stages):
            need(pre, path + (stage,))
        order.append(stage)

    for stage in deliver.get("stages", ()):
        need(stage, ())
    procs = [_process_for(s, fixture_kinds) for s in order]
    combine = next((p.name for p in procs if p.combines and p.product_type == item_type), None)
    if combine and procs[0].name != combine:
        raise RecipeError(f"work {work.work_id}: {combine} must come first, since it makes the {item_type}")
    return Recipe(work, item_type, combine, tuple(p.name for p in procs if p.name != combine))


def _process_for(stage: str, fixture_kinds: set[str]) -> ProcessSpec:
    """Return the process that adds `stage` and can run on a fixture in the kitchen."""
    options = [PROCESSES.get(n) for n in PROCESSES
               if PROCESSES.get(n).adds_stage == stage and PROCESSES.get(n).fixture_kinds & fixture_kinds]
    if not options:
        raise RecipeError(f"no process in this kitchen adds stage '{stage}'")
    return min(options, key=lambda p: (p.duration, p.name))


class KitchenPlan:
    """Fixed per-instance choices: one fixture per process, one storage fixture per item type."""

    def __init__(self, instance: Instance) -> None:
        """Derive recipes, process fixtures and storage from `instance`."""
        self.fixtures: dict[str, str] = dict(instance.fixtures)  # fixture id -> kind
        kinds = set(self.fixtures.values())
        self.recipes = {w.work_id: recipe_for(w, kinds) for w in instance.work}
        self._initial = _initial_counts(instance)
        needed = {p for r in self.recipes.values() for p in (r.combine, *r.stages) if p}
        self.process_fixture = {p: self._fixture_for(p) for p in sorted(needed)}
        self.targets = frozenset(r.deliver["at"] for r in self.recipes.values())
        self.delivered_types = frozenset(r.item_type for r in self.recipes.values())
        self.storage = self._storage(instance)

    def _fixture_for(self, process: str) -> str:
        """Return the fixture that runs `process`: the one of a fitting kind with the fewest initial items."""
        options = [f for f, k in self.fixtures.items() if k in PROCESSES.get(process).fixture_kinds]
        return min(options, key=lambda f: (self._initial.get(f, 0), f))

    def _storage(self, instance: Instance) -> dict[str, str]:
        """Return item type -> storage fixture: where the type starts, else the best-zone fixture."""
        out: dict[str, str] = {}
        for it in instance.items:
            if it.location.kind is LocationKind.FIXTURE and it.item_type not in out:
                out[it.item_type] = it.location.fixture
        busy = set(self.process_fixture.values()) | self.targets
        candidates = [f for f, k in self.fixtures.items()
                      if k not in NOT_STORAGE_KINDS and f not in busy and not FIXTURE_KINDS.get(k).powered
                      and FIXTURE_KINDS.get(k).zone in (TempZone.CHILLED, TempZone.AMBIENT)]
        for it in instance.items:
            if it.item_type not in out and candidates:
                out[it.item_type] = max(candidates, key=lambda f: (_life(it.item_type, self.fixtures[f]),
                                                                   self._initial.get(f, 0), f))
        return out


def shelf_life(item_type: str, zone: TempZone) -> float:
    """Return minutes until a fresh item of `item_type` spoils in `zone` (infinity if never)."""
    life = ITEM_TYPES.get(item_type).shelf_life.get(zone)
    return float("inf") if life is None else float(life)


def _life(item_type: str, kind: str) -> float:
    """Return the shelf life of `item_type` in a fixture of `kind`."""
    return shelf_life(item_type, FIXTURE_KINDS.get(kind).zone)


def _initial_counts(instance: Instance) -> dict[str, int]:
    """Return fixture id -> number of items placed there at the start."""
    out: dict[str, int] = {}
    for it in instance.items:
        if it.location.kind is LocationKind.FIXTURE:
            out[it.location.fixture] = out.get(it.location.fixture, 0) + 1
    return out
