"""Kind-A checks on the definition's `claims:` block (task spec sections 2, 4 and 5).

| Rule | Check |
|---|---|
| CR1 | `property` is P1–P4 and `mechanism` is one of the six modules |
| CR2 | `consequence` names an item type, a fixture and a physical action |
| MR1 | A P2 claim has a memory class S, D, I or T |
| MR2 | A P2 claim's content is where, which, state or done; its fact states no time, duration or count |
| MR3 | A class-T claim names the fact and the hidden candidate places |
| CR6 | Hidden places: at least 2, and no text the robot gets names one |
| C1, CR5 | A P3 claim names an event that is not observable and that no text announces |
| R1 | P4 has a recoverable and an irrecoverable claim |
| P1–P4 | Each property has at least one claim |

Every other rule needs runs or judgement: the reviewer checks it, or a later stage will.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from dsz.certify.text_checks import announcements, robot_texts
from dsz.core.scenario import Instance
from dsz.scenario.spec import ScenarioSpec

PROPERTIES = ("P1", "P2", "P3", "P4")
MECHANISMS = ("facts", "hidden_state", "lead_time", "resources", "drift", "compounding")
ACTIONS = ("find", "tell_apart", "open", "check", "carry", "unload", "recover")
MEMORY = ("S", "D", "I", "T")
CONTENT = ("where", "which", "state", "done")
RECOVERY = ("recoverable", "irrecoverable")
NUMBER = re.compile(r"\b\d{1,2}:\d{2}\b|\b\d+\s*(minutes?|min|hours?|h|days?|items?|pieces?|portions?)\b", re.I)


def check_claims(spec: ScenarioSpec, instances: Iterable[Instance]) -> list[str]:
    """Return every rule break in the claims, checked against `instances` (one per seed)."""
    if not spec.claims:
        return ["P1-P4: the definition has no claims"]
    instances = list(instances)
    ctx = _Context(spec, instances)
    out = [p for claim in spec.claims for p in _check(claim, ctx)]
    return out + _coverage(spec.claims)


class _Context:
    """What the checks look claims up against."""

    def __init__(self, spec: ScenarioSpec, instances: list[Instance]) -> None:
        """Collect names and robot texts from the definition and its instances."""
        params = spec.generator.params
        self.fixtures = set(spec.fixtures)
        self.facts = {f["id"]: f for f in params.get("facts", [])}
        self.events = {e["id"]: e for e in params.get("events", []) if "id" in e}
        self.item_types = ({i.item_type for inst in instances for i in inst.items}
                           | {w.spec["deliver"]["item_type"] for inst in instances for w in inst.work})
        self.texts = {t.body.lower() for inst in instances for t in robot_texts(inst)}
        self.announced = {ev.source for inst in instances for ev, _ in announcements(inst) if ev.source}


def _check(claim: Mapping[str, Any], ctx: _Context) -> list[str]:
    """Return the rule breaks of one claim."""
    cid, prop = claim["id"], claim.get("property")
    out = []
    if prop not in PROPERTIES:
        out.append(f"CR1: claim {cid}: property must be one of {', '.join(PROPERTIES)}")
    if claim.get("mechanism") not in MECHANISMS:
        out.append(f"CR1: claim {cid}: mechanism must be one of {', '.join(MECHANISMS)}")
    out += _consequence(cid, claim.get("consequence"), ctx)
    out += _references(cid, claim, ctx)
    if prop == "P2":
        out += _memory(cid, claim, ctx)
    if claim.get("hidden") is not None or claim.get("mechanism") == "hidden_state" or claim.get("memory") == "T":
        out += _hidden(cid, claim.get("hidden"), ctx)
    if prop == "P3":
        out += _change(cid, claim.get("event"), ctx)
    if prop == "P4" and claim.get("recovery") not in RECOVERY:
        out.append(f"R1: claim {cid}: recovery must be one of {', '.join(RECOVERY)}")
    return out


def _consequence(cid: str, c: Any, ctx: _Context) -> list[str]:
    """Return CR2 breaks: the consequence must name an object, a place and an action."""
    if not isinstance(c, Mapping):
        return [f"CR2: claim {cid}: consequence must be {{object, place, action}}"]
    out = []
    if c.get("object") not in ctx.item_types:
        out.append(f"CR2: claim {cid}: consequence.object '{c.get('object')}' is not an item type in this scenario")
    if c.get("place") not in ctx.fixtures:
        out.append(f"CR2: claim {cid}: consequence.place '{c.get('place')}' is not a fixture")
    if c.get("action") not in ACTIONS:
        out.append(f"CR2: claim {cid}: consequence.action must be one of {', '.join(ACTIONS)}")
    return out


def _references(cid: str, claim: Mapping[str, Any], ctx: _Context) -> list[str]:
    """Return breaks for a fact or event id that the definition does not have."""
    out = []
    if claim.get("fact") is not None and claim["fact"] not in ctx.facts:
        out.append(f"S3: claim {cid}: unknown fact '{claim['fact']}'")
    if claim.get("event") is not None and claim["event"] not in ctx.events:
        out.append(f"S3: claim {cid}: unknown event '{claim['event']}' (give the event an `id`)")
    return out


def _memory(cid: str, claim: Mapping[str, Any], ctx: _Context) -> list[str]:
    """Return MR1, MR2 and MR3 breaks of a P2 claim."""
    out = []
    memory = claim.get("memory")
    if memory not in MEMORY:
        out.append(f"MR1: claim {cid}: memory must be one of {', '.join(MEMORY)}")
    if claim.get("content") not in CONTENT:
        out.append(f"MR2: claim {cid}: content must be one of {', '.join(CONTENT)}")
    fact = ctx.facts.get(claim.get("fact"))
    if fact is not None and NUMBER.search(fact["text"]):
        out.append(f"MR2: claim {cid}: fact '{fact['id']}' states a time, duration or count")
    if memory == "T" and (fact is None or not claim.get("hidden")):
        out.append(f"MR3: claim {cid}: class T needs `fact` and the `hidden` places the robot must find")
    return out


def _hidden(cid: str, hidden: Any, ctx: _Context) -> list[str]:
    """Return CR6 breaks: at least two candidate places, none named in a text the robot gets."""
    if not isinstance(hidden, list) or len(hidden) < 2:
        return [f"CR6: claim {cid}: hidden must list at least 2 candidate fixtures"]
    out = [f"CR6: claim {cid}: hidden place '{f}' is not a fixture" for f in hidden if f not in ctx.fixtures]
    named = [f for f in hidden if any(f.lower() in t or f.lower().replace("_", " ") in t for t in ctx.texts)]
    out += [f"CR6: claim {cid}: hidden place '{f}' is named in a text the robot gets" for f in named]
    return out


def _change(cid: str, event_id: Any, ctx: _Context) -> list[str]:
    """Return C1 and CR5 breaks of a P3 claim."""
    if event_id is None:
        return [f"C1: claim {cid}: a P3 claim names its `event`"]
    event = ctx.events.get(event_id)
    if event is None:
        return []  # reported by _references
    out = []
    if event.get("observable"):
        out.append(f"C1: claim {cid}: event '{event_id}' is observable; the robot must not see it happen")
    if event_id in ctx.announced:
        out.append(f"CR5: claim {cid}: a text states what, where and when of event '{event_id}'")
    return out


def _coverage(claims: Iterable[Mapping[str, Any]]) -> list[str]:
    """Return properties without a claim, and a P4 without both kinds of failure."""
    claims = list(claims)
    out = [f"{p}: no claim supports {p}" for p in PROPERTIES if not any(c.get("property") == p for c in claims)]
    kinds = {c.get("recovery") for c in claims if c.get("property") == "P4"}
    if any(c.get("property") == "P4" for c in claims) and not set(RECOVERY) <= kinds:
        out.append("R1: P4 needs one recoverable and one irrecoverable claim")
    return out
