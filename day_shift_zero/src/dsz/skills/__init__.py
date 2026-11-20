"""Skill-level actions: one Command class per skill, the registry, the executor and services.

Importing this package registers the built-in skills.
"""

from dsz.skills import builtin  # noqa: F401  (registration side effect)
from dsz.skills.executor import SkillExecutor, skills_doc, validate_args
from dsz.skills.registry import SKILLS, register_skill
from dsz.skills.services import BusOrderDesk, BusSpeech

__all__ = ["SKILLS", "BusOrderDesk", "BusSpeech", "SkillExecutor", "register_skill", "skills_doc", "validate_args"]
