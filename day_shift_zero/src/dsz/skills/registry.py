"""Registry of skill classes."""

from __future__ import annotations

from dsz.core.registry import Registry
from dsz.core.skills import Skill

SKILLS: Registry[type[Skill]] = Registry("skill")


def register_skill(cls: type[Skill]) -> type[Skill]:
    """Class decorator: register `cls` under `cls.name`."""
    return SKILLS.add(cls.name, cls)
