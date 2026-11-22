"""Kind-A claim checks on the text a robot receives (task spec section 5).

| Check | Rule | Result |
|---|---|---|
| `skill_sequences` | CR15: goal, not steps | Problems: a sentence that names 2+ different actions |
| `announced_events` | CR5: not announced | Notes: events that cannot support a P3 claim |

Both read one generated instance: the objective, fact messages, ticket texts and the
texts of message-like events. They use word patterns, so they can miss a case; the
reviewer still reads the files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dsz.core.scenario import Instance, ScheduledEvent
from dsz.core.types import MINUTES_PER_DAY

# One pattern per motor skill. `look`, `wait`, `order` and `say` are not steps of a task.
SKILL_PHRASES: dict[str, re.Pattern[str]] = {
    "navigate_to": re.compile(r"\b(go|walk|drive|navigate) to\b|\bnavigate_to\b", re.I),
    "open": re.compile(r"(?<!left )(?<!is )(?<!are )(?<!was )(?<!stays )\bopen\b", re.I),
    "close": re.compile(r"\bclose\b(?! to\b)", re.I),
    "pick": re.compile(r"\b(pick|grab|take|fetch)\b", re.I),
    "place": re.compile(r"\b(put|place)\b", re.I),
    "set_power": re.compile(r"\b(switch|turn|power) (\w+ ){0,2}(on|off)\b|\bset_power\b", re.I),
    "start_process": re.compile(r"\bstart\b|\bstart_process\b", re.I),
}
SENTENCE_END = re.compile(r"[.!?;:\n]+")  # for CR15: a colon also ends an instruction
CLAUSE_END = re.compile(r"[.!?;\n]+")  # for CR5: keeps clock times such as 08:00 whole
TIME = re.compile(r"\b\d{1,2}:\d{2}\b|\bday \d+\b", re.I)
EXOGENOUS = {"relocate": ("move", "relocat"), "consume": ("use", "consum", "eat", "take"),
             "delivery": ("deliver",), "door_left_open": ("door", "open"), "equipment_fault": ("fault", "broke")}
WHERE_KEYS = ("to", "fixture", "from")


@dataclass(frozen=True)
class Text:
    """One text the robot receives, with where it comes from and when."""

    source: str
    t: int
    body: str


def robot_texts(instance: Instance) -> list[Text]:
    """Return every text the robot receives in `instance`, in time order."""
    out = [Text("objective", 0, instance.objective)]
    out += [Text(f"fact {f.fact_id}", f.revealed_at, f.text) for f in instance.facts]
    out += [Text(f"ticket {w.work_id}", w.released_at, w.spec["ticket"]["text"])
            for w in instance.work if w.spec.get("ticket")]
    out += [Text(f"event {e.kind} at {_clock(e.t)}", e.t, e.payload["text"])
            for e in instance.events if isinstance(e.payload.get("text"), str)]
    return sorted(out, key=lambda x: x.t)


def skill_sequences(instance: Instance) -> list[str]:
    """Return CR15 problems: sentences that name two or more different skills."""
    problems, seen = [], set()
    for text in robot_texts(instance):
        for sentence in filter(None, (s.strip() for s in SENTENCE_END.split(text.body))):
            skills = sorted(name for name, pattern in SKILL_PHRASES.items() if pattern.search(sentence))
            if len(skills) >= 2 and sentence not in seen:
                seen.add(sentence)
                problems.append(f"CR15: {text.source} states a sequence of skills ({', '.join(skills)}): "
                                f"\"{sentence}\". State the outcome instead")
    return problems


def announced_events(instance: Instance) -> list[str]:
    """Return CR5 notes: exogenous events whose what, where and when an earlier text states."""
    notes, seen = [], set()
    for event, source in announcements(instance):
        where = sorted(_where(event.payload))
        if (event.kind, tuple(where)) not in seen:
            seen.add((event.kind, tuple(where)))
            notes.append(f"CR5: {source} states what, where and when of the {event.kind} at "
                         f"{', '.join(where)}. It cannot support a P3 claim")
    return notes


def announcements(instance: Instance) -> list[tuple[ScheduledEvent, str]]:
    """Return each exogenous event that an earlier text announces, with that text's source."""
    item_types = {i.item_id: i.item_type for i in instance.items}
    out = []
    for event in instance.events:
        if event.kind in EXOGENOUS:
            what = set(EXOGENOUS[event.kind]) | _event_items(event.payload, item_types)
            source = _first_announcement(instance, event.t, _where(event.payload), what)
            if source:
                out.append((event, source))
    return out


def _where(payload: dict) -> set[str]:
    """Return the fixtures an event payload names."""
    return {payload[k] for k in WHERE_KEYS if isinstance(payload.get(k), str)}


def _first_announcement(instance: Instance, t: int, where: set[str], what: set[str]) -> str | None:
    """Return the source of the first sentence before `t` that names a time, a place in `where` and a `what`."""
    for text in robot_texts(instance):
        if text.t > t:
            break
        for sentence in CLAUSE_END.split(text.body.lower()):
            if (TIME.search(sentence) and any(w.lower() in sentence for w in where)
                    and any(w.replace("_", " ") in sentence or w in sentence for w in what)):
                return text.source
    return None


def _event_items(payload: dict, item_types: dict[str, str]) -> set[str]:
    """Return the item types an event payload names."""
    out = {payload["item_type"]} if isinstance(payload.get("item_type"), str) else set()
    ids = payload.get("items", []) + ([payload["item"]] if isinstance(payload.get("item"), str) else [])
    return out | {item_types[i] for i in ids if i in item_types}


def _clock(t: int) -> str:
    """Return `day N HH:MM` (day one-based) for simulated minute `t`."""
    day, minute = divmod(t, MINUTES_PER_DAY)
    return f"day {day + 1} {minute // 60:02d}:{minute % 60:02d}"
