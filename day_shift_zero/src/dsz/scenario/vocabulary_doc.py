"""Render the platform vocabulary for scenario authors: Markdown (`dsz vocab`) or data (`dsz vocab --json`).

The text is built from the registries, so it always matches the code. It lists what a
definition can name: fixture kinds, item types, processes, events, dynamics modules,
actors, success criteria and the skills the robot has.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Iterable

from dsz.actors.registry import ACTORS
from dsz.dynamics.registry import MODULES
from dsz.events.registry import EVENT_TYPES
from dsz.scenario.registries import CRITERIA
from dsz.skills.executor import skills_doc
from dsz.skills.registry import SKILLS
from dsz.world.catalog import FIXTURE_KINDS, ITEM_TYPES, PROCESSES
from dsz.world.vocabulary import register_default_vocabulary


def vocabulary_data() -> dict:
    """Return the vocabulary's names by category, plus `stamp`: a hash of those names.

    The stamp changes only when the vocabulary changes, so a brief can tell which
    vocabulary it was written against.
    """
    register_default_vocabulary()
    names = {
        "fixture_kinds": sorted(FIXTURE_KINDS), "item_types": sorted(ITEM_TYPES), "processes": sorted(PROCESSES),
        "events": sorted(EVENT_TYPES), "modules": sorted(MODULES), "actors": sorted(ACTORS),
        "criteria": sorted(CRITERIA), "skills": sorted(SKILLS),
    }
    digest = hashlib.sha256(json.dumps(names, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {"stamp": digest, **names}


def vocabulary_markdown() -> str:
    """Return the whole vocabulary as one Markdown document."""
    register_default_vocabulary()
    parts = [
        "# Platform vocabulary",
        "Generated from the platform registries. A definition can name only what is listed here. "
        f"Vocabulary stamp: `{vocabulary_data()['stamp']}`.",
        _fixtures(), _items(), _processes(),
        _documented("Events", "`kind` in `generator.params.events`.", EVENT_TYPES),
        _documented("Dynamics modules", "Keys of `modules`.", MODULES),
        _documented("Actors", "`role` in `actors`.", ACTORS),
        _documented("Success criteria", "Keys of `success.criteria`.", CRITERIA),
        "## Skills\n\nWhat the robot can do. Tickets and messages must not spell out these steps (CR15).\n\n"
        "```\n" + skills_doc() + "\n```",
    ]
    return "\n\n".join(parts) + "\n"


def _fixtures() -> str:
    """Return the fixture-kind table."""
    rows = [(n, k.zone.value, _yes(k.has_door), _yes(k.powered), "unlimited" if k.capacity is None else k.capacity)
            for n, k in ((n, FIXTURE_KINDS.get(n)) for n in FIXTURE_KINDS)]
    return "## Fixture kinds\n\nValues of `fixtures`. Zone applies to powered fixtures only while on.\n\n" + _table(
        ("Kind", "Zone", "Door", "Powered", "Capacity"), rows)


def _items() -> str:
    """Return the item-type table."""
    rows = []
    for n in ITEM_TYPES:
        it = ITEM_TYPES.get(n)
        life = ", ".join(f"{z.value} {_minutes(m)}" for z, m in it.shelf_life.items() if m is not None)
        rows.append((n, ", ".join(sorted(it.tags)) or "-", ", ".join(sorted(it.allergens)) or "-", life or "never"))
    return ("## Item types\n\nItem ids are `<type>_<nnn>`, numbered per type: initial items first, then pool "
            "items. Shelf life is per zone; spoiling needs the `spoilage` module.\n\n"
            + _table(("Type", "Tags", "Allergens", "Spoils after"), rows))


def _processes() -> str:
    """Return the process table."""
    rows = []
    for n in PROCESSES:
        p = PROCESSES.get(n)
        overrun = (f"{p.overrun_effect.value} if left {_minutes(p.overrun_tolerance)} past done"
                   if p.overrun_effect else "-")
        rows.append((n, ", ".join(sorted(p.fixture_kinds)), _minutes(p.duration), p.adds_stage,
                     ", ".join(sorted(p.requires_stages)) or "-", _yes(p.requires_power), overrun,
                     f"all inputs into one {p.product_type}" if p.combines else "-"))
    return ("## Processes\n\nThe robot starts a process on everything in a fixture. It completes if the inputs "
            "stay put, and adds its stage. A work item asks for stages; the processes that add them are required.\n\n"
            + _table(("Process", "Fixture kinds", "Duration", "Adds stage", "Needs stages", "Needs power",
                      "Overrun", "Combines"), rows))


def _documented(title: str, intro: str, registry: Iterable[str]) -> str:
    """Return a section with each registered class's docstring."""
    entries = [f"### `{n}`\n\n{inspect.getdoc(registry.get(n))}" for n in registry]
    return f"## {title}\n\n{intro}\n\n" + "\n\n".join(entries)


def _table(head: tuple[str, ...], rows: Iterable[tuple]) -> str:
    """Return a Markdown table."""
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


def _minutes(m: int | None) -> str:
    """Return a duration in the largest whole unit: `2 d`, `8 h` or `20 min`."""
    if m is None:
        return "-"
    for unit, size in (("d", 1440), ("h", 60)):
        if m % size == 0:
            return f"{m // size} {unit}"
    return f"{m} min"


def _yes(flag: bool) -> str:
    """Return `yes` or `-`."""
    return "yes" if flag else "-"
