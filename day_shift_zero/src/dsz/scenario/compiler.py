"""Compiler: turn a parsed spec into a runnable Scenario, or fail early with every problem named.

`load_scenario` reads a scenario folder: the definition plus an optional `oracle.py`.
`compile_spec` then imports the spec's plugin modules; resolves plugin names; builds
modules and actors once to validate their params; collects requirements; checks them
against the platform manifest; and checks references in a one-day probe instance.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

from dsz.actors.registry import ACTORS, build_actors
from dsz.core.rng import RngStreams
from dsz.core.scenario import Instance
from dsz.core.types import CapabilitySet, Horizon, LocationKind
from dsz.dynamics.registry import MODULES, build_modules
from dsz.events.registry import EVENT_TYPES
from dsz.scenario.composed import SpecScenario
from dsz.scenario.registries import CRITERIA, GENERATORS, POLICIES
from dsz.scenario.spec import ScenarioSpec, SpecError, load_spec
from dsz.scenario.work import deliver_spec
from dsz.skills.registry import SKILLS
from dsz.world.catalog import FIXTURE_KINDS, ITEM_TYPES, PROCESSES
from dsz.world.manifest import ManifestSources, build_manifest, check_requirements


def platform_manifest() -> CapabilitySet:
    """Return what the platform offers now (all registered plugins and vocabulary)."""
    return build_manifest(ManifestSources(FIXTURE_KINDS, ITEM_TYPES, PROCESSES, MODULES, ACTORS, EVENT_TYPES, SKILLS))


def load_scenario(folder: str | Path) -> SpecScenario:
    """Parse and compile the scenario in `folder`.

    The folder holds `scenario.yaml` and, optionally, `oracle.py`. The oracle module is
    imported by file path, so a scenario folder works wherever it lives.

    Raises:
        FileNotFoundError: if `folder/scenario.yaml` does not exist.
        SpecError, MissingCapabilities: as `compile_spec`.
    """
    folder = Path(folder)
    spec = load_spec(folder / "scenario.yaml")
    oracle = folder / "oracle.py"
    if oracle.is_file():
        _import_file(f"dsz_scenarios.{spec.scenario_id}.oracle", oracle)
    return compile_spec(spec)


def _import_file(name: str, path: Path) -> None:
    """Import the module at `path` under `name`, once per process."""
    if name in sys.modules:
        return
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    try:
        module_spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise


def compile_spec(spec: ScenarioSpec) -> SpecScenario:
    """Return a SpecScenario. Raise SpecError (names, params, references) or MissingCapabilities."""
    for mod in spec.plugins:
        importlib.import_module(mod)
    problems = _check_names(spec)
    if problems:
        raise SpecError(problems)
    try:
        build_modules(spec.modules)
        build_actors(spec.actors)
    except (ValueError, KeyError) as e:
        raise SpecError([f"invalid module or actor settings: {e}"]) from e
    generator = GENERATORS.get(spec.generator.name)()
    gen_req = generator.requires(spec.generator.params)
    required = CapabilitySet(
        fixtures=frozenset(spec.fixtures.values()),
        item_types=gen_req.item_types,
        processes=gen_req.processes,
        modules=frozenset(spec.modules),
        actors=frozenset(a["role"] for a in spec.actors),
        events=gen_req.events,
        skills=gen_req.skills,
    )
    check_requirements(spec.scenario_id, required, platform_manifest())
    scenario = SpecScenario(spec, generator, required)
    probe = scenario.generate(0, Horizon(spec.horizon_type, 1), RngStreams(0))
    problems = validate_instance(probe)
    if problems:
        raise SpecError(problems)
    return scenario


def validate_instance(instance: Instance) -> list[str]:
    """Return referential problems: unknown fixtures in items, work and event payloads."""
    fixtures = set(instance.fixtures)
    p = [f"item {i.item_id} placed at unknown fixture '{i.location.fixture}'"
         for i in instance.items if i.location.kind is LocationKind.FIXTURE and i.location.fixture not in fixtures]
    for w in instance.work:
        try:
            at = deliver_spec(w)["at"]
        except ValueError as e:
            p.append(str(e))
            continue
        if at not in fixtures:
            p.append(f"work {w.work_id} delivers to unknown fixture '{at}'")
        if w.deadline < w.released_at:
            p.append(f"work {w.work_id} has a deadline before its release")
    for ev in instance.events:
        for key in ("fixture", "to", "from", "expect_at"):
            if key in ev.payload and ev.payload[key] not in fixtures:
                p.append(f"event {ev.kind}@{ev.t} references unknown fixture '{ev.payload[key]}'")
    for a in instance.actors:
        if "fixture" in a and a["fixture"] not in fixtures:
            p.append(f"actor {a.get('name', a['role'])} uses unknown fixture '{a['fixture']}'")
    return p


def _check_names(spec: ScenarioSpec) -> list[str]:
    """Return problems with plugin names in the spec."""
    p = []
    if spec.generator.name not in GENERATORS:
        p.append(f"unknown generator '{spec.generator.name}'; known: {sorted(GENERATORS)}")
    p += [f"unknown success criterion '{c.name}'; known: {sorted(CRITERIA)}"
          for c in spec.criteria if c.name not in CRITERIA]
    refs = ([spec.oracle] if spec.oracle else []) + list(spec.controls)
    p += [f"unknown policy '{r.name}'; known: {sorted(POLICIES)}" for r in refs if r.name not in POLICIES]
    return p
