"""Template generator: build instances from declarative parameters (no scenario code needed).

Parameters (all optional except where noted):

    pool:     {item_type: count}                 # parked stock for deliveries
    initial:  [{type, count, at, batch?}]        # items placed at the start; `at` may be a choice
    subjects: [str]                              # e.g. customer ids that work can be for
    facts:    [{id, text, at: {day, minute}, channel?, sender?, subject?,
                constraint?: {exclude_allergens: [..]}}]
    work:     [{kind, per_day: [lo, hi], window: [min_lo, min_hi], lead: [lo, hi],
                grace?, collect?, channel?, sender?,
                variants: [{deliver: {...}, ticket: "text with {work_id} {subject} {due}"}]}]
    events:   [{kind, payload, id?, observable?, at: {day, minute}}                       # fixed
               | {kind, payload, id?, observable?, per_day: [lo, hi], window: [lo, hi]}]  # random

A choice `{one_of: [a, b, ...]}` can stand for an initial item's `at` or for any event
payload value. Each seed draws one candidate from its own stream, so a choice never
shifts other draws. One choice covers every item of an `initial` entry.

A fact with a `subject` and a `constraint` silently applies to later work for that
subject: the constraint joins the deliver predicate, but the ticket never repeats it (M1).
Randomness is drawn per (template, day), so an N-day instance is an exact prefix of any
longer one.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from dsz.core.rng import RngStreams
from dsz.core.scenario import (
    Fact,
    GenerationContext,
    InitialItem,
    Instance,
    InstanceGenerator,
    ScheduledEvent,
    WorkItem,
)
from dsz.core.types import MINUTES_PER_DAY, CapabilitySet, Horizon, Location
from dsz.scenario.registries import register_generator
from dsz.world.catalog import PROCESSES


@register_generator
class TemplateGenerator(InstanceGenerator):
    """Data-driven instance generator (see module docstring for the parameter schema)."""

    name = "template"

    def requires(self, params: Mapping[str, Any]) -> CapabilitySet:
        """Collect item types, processes (from required stages) and event kinds the params use."""
        types = set(params.get("pool", {})) | {e["type"] for e in params.get("initial", [])}
        stages: set[str] = set()
        for tpl in params.get("work", []):
            for v in tpl.get("variants", []):
                types.add(v["deliver"]["item_type"])
                stages |= set(v["deliver"].get("stages", ()))
        procs = {name for name in PROCESSES if PROCESSES.get(name).adds_stage in stages}
        missing = stages - {PROCESSES.get(n).adds_stage for n in procs}
        procs |= {f"<stage:{s}>" for s in missing}  # unknown stages surface as missing processes
        events = {e["kind"] for e in params.get("events", [])} | {"message", "work_release"}
        return CapabilitySet(item_types=frozenset(types), processes=frozenset(procs), events=frozenset(events))

    def generate(self, ctx: GenerationContext, seed: int, horizon: Horizon, rng: RngStreams) -> Instance:
        """Sample the instance day by day."""
        p = ctx.params
        items = _items(p, rng)
        facts = _facts(p, horizon)
        work, needed = _work(p, facts, horizon, rng)
        facts = tuple(Fact(f.fact_id, f.revealed_at, f.channel, f.text, f.sender, tuple(needed.get(f.fact_id, ())))
                      for f in facts)
        return Instance(ctx.scenario_id, seed, horizon, ctx.objective, dict(ctx.fixtures), items, facts, work,
                        _events(p, horizon, rng), dict(ctx.modules), tuple(ctx.actors), dict(p))


def _t(at: Mapping[str, int]) -> int:
    """Convert {day, minute} (day is zero-based) to simulated minutes."""
    return int(at.get("day", 0)) * MINUTES_PER_DAY + int(at.get("minute", 0))


def _choose(value: Any, g: np.random.Generator) -> Any:
    """Return one candidate of a `{one_of: [...]}` choice drawn with `g`; return other values unchanged.

    Raises:
        ValueError: if the choice has no candidates.
    """
    if not (isinstance(value, Mapping) and "one_of" in value):
        return value
    options = list(value["one_of"])
    if not options:
        raise ValueError("one_of needs at least one candidate")
    return options[int(g.integers(len(options)))]


def _payload(e: Mapping[str, Any], g: np.random.Generator) -> dict[str, Any]:
    """Return the event payload with each choice resolved."""
    return {k: _choose(v, g) for k, v in e.get("payload", {}).items()}


def _items(p: Mapping[str, Any], rng: RngStreams) -> tuple[InitialItem, ...]:
    """Create initial items, then pool items; ids are <type>_<nnn> numbered per type."""
    counter: dict[str, int] = {}
    out = []

    def next_id(t: str) -> str:
        """Return the next id for item type `t`."""
        counter[t] = counter.get(t, 0) + 1
        return f"{t}_{counter[t]:03d}"

    for k, e in enumerate(p.get("initial", [])):
        at = _choose(e["at"], rng.indexed(f"initial.{k}.choice", 0))
        out += [InitialItem(next_id(e["type"]), e["type"], Location.at(at), e.get("batch"))
                for _ in range(int(e.get("count", 1)))]
    for t, n in sorted(p.get("pool", {}).items()):
        out += [InitialItem(next_id(t), t, Location.parked()) for _ in range(int(n))]
    return tuple(out)


def _facts(p: Mapping[str, Any], horizon: Horizon) -> list[Fact]:
    """Return facts revealed within the horizon, in reveal order."""
    out = [Fact(f["id"], _t(f["at"]), f.get("channel", "manager"), f["text"], f.get("sender", "manager"))
           for f in p.get("facts", []) if _t(f["at"]) < horizon.end]
    return sorted(out, key=lambda f: (f.revealed_at, f.fact_id))


def _work(p: Mapping[str, Any], facts: list[Fact], horizon: Horizon, rng: RngStreams,
          ) -> tuple[tuple[WorkItem, ...], dict[str, list[str]]]:
    """Sample work per template and day; merge hidden constraints from earlier facts."""
    by_id = {f["id"]: f for f in p.get("facts", [])}
    subjects = list(p.get("subjects", []))
    out: list[WorkItem] = []
    needed: dict[str, list[str]] = {}
    for ti, tpl in enumerate(p.get("work", [])):
        for day in range(horizon.days):
            g = rng.indexed(f"work.{ti}", day)
            lo, hi = tpl["per_day"]
            draws = []
            for _ in range(int(g.integers(lo, hi + 1))):
                release = day * MINUTES_PER_DAY + int(g.integers(tpl["window"][0], tpl["window"][1] + 1))
                lead = int(g.integers(tpl["lead"][0], tpl["lead"][1] + 1))
                variant = tpl["variants"][int(g.integers(len(tpl["variants"])))]
                subject = subjects[int(g.integers(len(subjects)))] if subjects else None
                draws.append((release, lead, variant, subject))
            for k, (release, lead, variant, subject) in enumerate(sorted(draws, key=lambda d: d[0])):
                wid = f"{tpl['kind']}-d{day + 1}-{k + 1:02d}"
                deliver = dict(variant["deliver"])
                excl = set(deliver.get("exclude_allergens", ()))
                for f in facts:
                    src = by_id[f.fact_id]
                    if subject and src.get("subject") == subject and f.revealed_at < release and "constraint" in src:
                        excl |= set(src["constraint"].get("exclude_allergens", ()))
                        needed.setdefault(f.fact_id, []).append(wid)
                if excl:
                    deliver["exclude_allergens"] = sorted(excl)
                due = release + lead
                text = variant.get("ticket", "{work_id}").format(work_id=wid, subject=subject or "",
                                                                  due=f"{(due % MINUTES_PER_DAY) // 60:02d}:"
                                                                      f"{due % 60:02d}")
                spec = {"deliver": deliver, "collect": bool(tpl.get("collect", False)),
                        "grace": int(tpl.get("grace", 0)), "subject": subject,
                        "ticket": {"channel": tpl.get("channel", "tickets"), "sender": tpl.get("sender", "system"),
                                   "text": text}}
                out.append(WorkItem(wid, tpl["kind"], release, due, spec))
    out.sort(key=lambda w: (w.released_at, w.work_id))
    return tuple(out), needed


def _events(p: Mapping[str, Any], horizon: Horizon, rng: RngStreams) -> tuple[ScheduledEvent, ...]:
    """Expand fixed and random event templates within the horizon."""
    out: list[ScheduledEvent] = []
    for ei, e in enumerate(p.get("events", [])):
        obs = bool(e.get("observable", False))
        if "at" in e:
            t = _t(e["at"])
            if t < horizon.end:
                choice = rng.indexed(f"events.{ei}.choice", t // MINUTES_PER_DAY)
                out.append(ScheduledEvent(t, e["kind"], _payload(e, choice), obs, e.get("id")))
            continue
        for day in range(horizon.days):
            g = rng.indexed(f"events.{ei}", day)
            choice = rng.indexed(f"events.{ei}.choice", day)
            lo, hi = e["per_day"]
            for _ in range(int(g.integers(lo, hi + 1))):
                t = day * MINUTES_PER_DAY + int(g.integers(e["window"][0], e["window"][1] + 1))
                out.append(ScheduledEvent(t, e["kind"], _payload(e, choice), obs, e.get("id")))
    return tuple(sorted(out, key=lambda ev: (ev.t, ev.kind)))
