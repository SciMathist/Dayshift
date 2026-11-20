"""Scenario layer: definitions, compiler, generator, work tracking, success criteria, materializer.

Importing this package registers the built-in generator (`template`), criteria
(`work_completion`, `no_violations`, `waste`) and the `noop` control policy.
"""

from dsz import actors, dynamics, events, skills  # noqa: F401  (register built-in plugins)
from dsz.eval import controls  # noqa: F401  (registers "noop")
from dsz.scenario import criteria, template  # noqa: F401  (registration side effect)
from dsz.scenario.compiler import compile_spec, platform_manifest, validate_instance
from dsz.scenario.composed import SpecScenario
from dsz.scenario.materialize import Run, materialize, symbolic_backend
from dsz.scenario.registries import CRITERIA, GENERATORS, POLICIES, register_criterion, register_generator
from dsz.scenario.spec import ScenarioSpec, SpecError, load_spec, parse_spec
from dsz.world.vocabulary import register_default_vocabulary

register_default_vocabulary()

__all__ = [
    "CRITERIA", "GENERATORS", "POLICIES", "Run", "ScenarioSpec", "SpecError", "SpecScenario", "compile_spec",
    "load_spec", "materialize", "parse_spec", "platform_manifest", "register_criterion", "register_generator",
    "symbolic_backend", "validate_instance",
]
