"""Capability manifest: the vocabulary the platform offers, assembled from registries.

Injected registries (not imported globals) keep the manifest testable. They also let a
deployment restrict or extend what scenarios may use.
"""

from __future__ import annotations

from dataclasses import dataclass

from dsz.core.registry import Registry
from dsz.core.types import CapabilitySet


@dataclass(frozen=True)
class ManifestSources:
    """The registries that together define the platform vocabulary."""

    fixtures: Registry
    item_types: Registry
    processes: Registry
    modules: Registry
    actors: Registry
    events: Registry
    skills: Registry


def build_manifest(src: ManifestSources) -> CapabilitySet:
    """Return the capability set offered by the registries in `src`."""
    return CapabilitySet(
        fixtures=src.fixtures.names(),
        item_types=src.item_types.names(),
        processes=src.processes.names(),
        modules=src.modules.names(),
        actors=src.actors.names(),
        events=src.events.names(),
        skills=src.skills.names(),
    )


class MissingCapabilities(Exception):
    """A scenario needs capabilities that the platform does not offer."""

    def __init__(self, scenario_id: str, missing: dict[str, frozenset[str]]) -> None:
        """Record the scenario id and the missing capabilities by category."""
        self.scenario_id = scenario_id
        self.missing = missing
        detail = "; ".join(f"{k}: {sorted(v)}" for k, v in missing.items())
        super().__init__(f"scenario '{scenario_id}' needs capabilities the platform lacks: {detail}")


def check_requirements(scenario_id: str, required: CapabilitySet, offered: CapabilitySet) -> None:
    """Raise MissingCapabilities if `offered` does not cover `required`."""
    missing = required.missing_from(offered)
    if missing:
        raise MissingCapabilities(scenario_id, missing)
