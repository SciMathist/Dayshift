"""Registries for scenario-layer plugins: generators, success criteria and policy factories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Mapping

from dsz.core.registry import Registry
from dsz.core.scenario import InstanceGenerator
from dsz.core.success import Criterion

if TYPE_CHECKING:
    from dsz.core.policy import Policy
    from dsz.core.scenario import Instance
    from dsz.world.state import WorldState

PolicyFactory = Callable[["Instance", "WorldState", Mapping[str, Any]], "Policy"]
"""Build an evaluator-side policy (oracle or negative control) for one run."""

GENERATORS: Registry[type[InstanceGenerator]] = Registry("generator")
CRITERIA: Registry[type[Criterion]] = Registry("success criterion")
POLICIES: Registry[PolicyFactory] = Registry("policy factory")


def register_generator(cls: type[InstanceGenerator]) -> type[InstanceGenerator]:
    """Class decorator: register `cls` under `cls.name`."""
    return GENERATORS.add(cls.name, cls)


def register_criterion(cls: type[Criterion]) -> type[Criterion]:
    """Class decorator: register `cls` under `cls.name`."""
    return CRITERIA.add(cls.name, cls)
