"""Scenario definition: the declarative spec, its parser and its loader.

A definition names plugins (generator, criteria, policies) and gives them parameters. The
parser checks structure only and reports every problem at once. The compiler checks
names and capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml

from dsz.core.types import HorizonType


@dataclass(frozen=True, slots=True)
class PluginRef:
    """A plugin name plus its parameters."""

    name: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CriterionRef:
    """A success criterion with its weight in the graded score and whether it gates the binary pass."""

    name: str
    params: Mapping[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    required: bool = True


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """A parsed scenario definition."""

    scenario_id: str
    objective: str
    horizon_type: HorizonType
    default_days: int
    min_days: int  # shortest certified horizon; the certified set is min_days..default_days
    fixtures: Mapping[str, str]
    generator: PluginRef
    criteria: tuple[CriterionRef, ...]
    oracle: PluginRef | None = None
    controls: tuple[PluginRef, ...] = ()
    modules: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    actors: tuple[Mapping[str, Any], ...] = ()
    plugins: tuple[str, ...] = ()  # importable modules that register scenario-specific plugins
    claims: tuple[Mapping[str, Any], ...] = ()  # difficulty claims; dsz.certify.claim_checks checks them


class SpecError(ValueError):
    """A scenario definition is malformed. `problems` lists every issue found."""

    def __init__(self, problems: list[str]) -> None:
        """Record all problems."""
        self.problems = problems
        super().__init__("invalid scenario definition:\n- " + "\n- ".join(problems))


def load_spec(path: str | Path) -> ScenarioSpec:
    """Read a YAML definition from `path` and parse it."""
    with open(path, encoding="utf-8") as f:
        return parse_spec(yaml.safe_load(f) or {})


def parse_spec(raw: Mapping[str, Any]) -> ScenarioSpec:
    """Parse a definition mapping. Raise SpecError listing every structural problem."""
    p: list[str] = []
    sid = _req(raw, "id", str, p)
    objective = _req(raw, "objective", str, p)
    horizon = _req(raw, "horizon", dict, p) or {}
    htype = horizon.get("type")
    if htype not in {h.value for h in HorizonType}:
        p.append(f"horizon.type must be one of {[h.value for h in HorizonType]}")
    days = horizon.get("days", 1)
    if not isinstance(days, int) or days < 1:
        p.append("horizon.days must be a positive integer")
    min_days = horizon.get("min_days", days)
    if not isinstance(min_days, int) or not isinstance(days, int) or not 1 <= min_days <= days:
        p.append("horizon.min_days must be an integer from 1 to horizon.days")
    fixtures = _req(raw, "fixtures", dict, p) or {}
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in fixtures.items()):
        p.append("fixtures must map fixture id to kind (strings)")
    generator = _plugin(raw.get("generator"), "generator", p)
    criteria = _criteria(raw.get("success"), p)
    policies = raw.get("policies") or {}
    oracle = _plugin(policies["oracle"], "policies.oracle", p) if "oracle" in policies else None
    controls = tuple(_plugin(c, f"policies.controls[{i}]", p) for i, c in enumerate(policies.get("controls", [])))
    modules = raw.get("modules") or {}
    if not isinstance(modules, dict):
        p.append("modules must be a mapping of module name to params")
    actors = raw.get("actors") or []
    if not isinstance(actors, list) or not all(isinstance(a, dict) and "role" in a for a in actors):
        p.append("actors must be a list of mappings, each with a 'role'")
    plugins = raw.get("plugins") or []
    if not isinstance(plugins, list) or not all(isinstance(x, str) for x in plugins):
        p.append("plugins must be a list of module paths")
    claims = _claims(raw.get("claims"), p)
    known = {"id", "objective", "horizon", "fixtures", "generator", "success", "policies", "modules", "actors",
             "plugins", "description", "claims"}
    p.extend(f"unknown top-level key '{k}'" for k in sorted(set(raw) - known))
    if p:
        raise SpecError(p)
    return ScenarioSpec(
        scenario_id=sid, objective=objective, horizon_type=HorizonType(htype), default_days=days,
        min_days=min_days, fixtures=dict(fixtures), generator=generator, criteria=criteria, oracle=oracle,
        controls=tuple(c for c in controls if c), modules=dict(modules), actors=tuple(actors),
        plugins=tuple(plugins), claims=claims,
    )


def _claims(raw: Any, p: list[str]) -> tuple[Mapping[str, Any], ...]:
    """Parse `claims`: a list of mappings, each with a unique string `id`. The checks are in dsz.certify."""
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(c, dict) for c in raw):
        p.append("claims must be a list of mappings")
        return ()
    ids = [c.get("id") for c in raw]
    if not all(isinstance(i, str) for i in ids):
        p.append("each claim needs a string 'id'")
    elif len(set(ids)) < len(ids):
        p.append("claim ids must be unique")
    return tuple(raw)


def _req(raw: Mapping[str, Any], key: str, typ: type, p: list[str]) -> Any:
    """Return `raw[key]` if present and of type `typ`; else record a problem and return None."""
    if key not in raw:
        p.append(f"missing '{key}'")
        return None
    if not isinstance(raw[key], typ):
        p.append(f"'{key}' must be {typ.__name__}")
        return None
    return raw[key]


def _plugin(raw: Any, where: str, p: list[str]) -> PluginRef | None:
    """Parse `{name, params?}` or a bare name string."""
    if isinstance(raw, str):
        return PluginRef(raw)
    if isinstance(raw, dict) and isinstance(raw.get("name"), str):
        params = raw.get("params") or {}
        if isinstance(params, dict):
            return PluginRef(raw["name"], params)
    p.append(f"{where} must be a name or {{name, params}}")
    return None


def _criteria(raw: Any, p: list[str]) -> tuple[CriterionRef, ...]:
    """Parse `success: {criteria: {name: {params?, weight?, required?}}}`."""
    crit = (raw or {}).get("criteria") if isinstance(raw, dict) else None
    if not isinstance(crit, dict) or not crit:
        p.append("success.criteria must map at least one criterion name to its settings")
        return ()
    out = []
    for name, cfg in crit.items():
        cfg = cfg or {}
        weight, required = cfg.get("weight", 1.0), cfg.get("required", True)
        if not isinstance(weight, (int, float)) or weight < 0 or not isinstance(required, bool):
            p.append(f"success.criteria.{name}: weight must be >= 0 and required a boolean")
            continue
        out.append(CriterionRef(name, cfg.get("params") or {}, float(weight), required))
    return tuple(out)
