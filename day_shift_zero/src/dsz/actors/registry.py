"""Registry of actor classes, and the factory that builds actors from scenario config."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from dsz.core.actors import Actor
from dsz.core.registry import Registry

ACTORS: Registry[type[Actor]] = Registry("actor role")


def register_actor(cls: type[Actor]) -> type[Actor]:
    """Class decorator: register `cls` under `cls.role`."""
    return ACTORS.add(cls.role, cls)


def build_actors(config: Sequence[Mapping[str, Any]], registry: Registry[type[Actor]] = ACTORS) -> list[Actor]:
    """Instantiate actors from entries like {role, name?, **params}. The name defaults to the role."""
    out = []
    for entry in config:
        params = {k: v for k, v in entry.items() if k not in ("role", "name")}
        out.append(registry.get(entry["role"])(entry.get("name", entry["role"]), params))
    return out
