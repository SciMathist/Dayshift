"""Skill executor: validate a SkillCall, run the skill, and wrap the outcome as a SkillResult."""

from __future__ import annotations

from typing import Any, Mapping

from dsz.core.registry import Registry
from dsz.core.skills import Skill, SkillArgError, SkillContext
from dsz.core.types import SkillCall, SkillResult
from dsz.skills.registry import SKILLS


class SkillExecutor:
    """Turn skill calls into results. Malformed calls are rejected without side effects."""

    def __init__(self, ctx: SkillContext, registry: Registry[type[Skill]] = SKILLS) -> None:
        """Execute skills from `registry` within `ctx`."""
        self._ctx = ctx
        self._registry = registry
        self._skills: dict[str, Skill] = {}

    def execute(self, call: SkillCall) -> SkillResult:
        """Run `call`. Return accepted=False with a reason if the call is invalid."""
        if call.name not in self._registry:
            return SkillResult(call, False, 0, message=f"unknown skill '{call.name}'")
        skill = self._skill(call.name)
        try:
            args = validate_args(skill, call.args)
            out = skill.run(self._ctx, args)
        except SkillArgError as e:
            return SkillResult(call, False, 0, message=str(e))
        return SkillResult(call, True, out.elapsed, out.sensors, out.message)

    def doc(self) -> str:
        """Return one line per skill, for the policy's TaskBrief."""
        return skills_doc(self._registry)

    def _skill(self, name: str) -> Skill:
        """Return the cached skill instance for `name`."""
        if name not in self._skills:
            self._skills[name] = self._registry.get(name)()
        return self._skills[name]


def validate_args(skill: Skill, args: Mapping[str, Any]) -> dict[str, Any]:
    """Check presence and types of `args` against the skill's declaration. Raise SkillArgError."""
    allowed = {**skill.args, **skill.optional}
    extra = set(args) - set(allowed)
    if extra:
        raise SkillArgError(f"unexpected argument(s) {sorted(extra)} for '{skill.name}'")
    missing = set(skill.args) - set(args)
    if missing:
        raise SkillArgError(f"missing argument(s) {sorted(missing)} for '{skill.name}'")
    for key, value in args.items():
        want = allowed[key]
        if (want is int and isinstance(value, bool)) or not isinstance(value, want):
            raise SkillArgError(f"argument '{key}' must be {want.__name__}")
    return dict(args)


def skills_doc(registry: Registry[type[Skill]] = SKILLS) -> str:
    """Return a stable, one-line-per-skill description: `name(arg: type, [opt: type]): doc`."""
    lines = []
    for name in registry:
        cls = registry.get(name)
        sig = [f"{k}: {v.__name__}" for k, v in cls.args.items()]
        sig += [f"[{k}: {v.__name__}]" for k, v in cls.optional.items()]
        lines.append(f"{name}({', '.join(sig)}): {cls.doc}")
    return "\n".join(lines)
