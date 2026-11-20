"""Registry of dynamics module classes, and the factory that builds them from scenario config."""

from __future__ import annotations

from typing import Any, Mapping

from dsz.core.dynamics import DynamicsModule
from dsz.core.registry import Registry

MODULES: Registry[type[DynamicsModule]] = Registry("dynamics module")


def register_module(cls: type[DynamicsModule]) -> type[DynamicsModule]:
    """Class decorator: register `cls` under `cls.name`."""
    return MODULES.add(cls.name, cls)


def build_modules(config: Mapping[str, Mapping[str, Any]], registry: Registry[type[DynamicsModule]] = MODULES,
                  ) -> list[DynamicsModule]:
    """Instantiate the modules named in `config` (name → params), in sorted name order for determinism."""
    return [registry.get(name)(params or {}) for name, params in sorted(config.items())]
