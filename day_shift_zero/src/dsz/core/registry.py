"""Generic named registry: the plugin mechanism for skills, processes, events, modules and item types."""

from __future__ import annotations

from typing import Callable, Generic, Iterator, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Map unique names to entries. Duplicate names are an error; unknown names list the known ones."""

    def __init__(self, kind: str) -> None:
        """Create an empty registry. `kind` names the entry type in error messages."""
        self._kind = kind
        self._entries: dict[str, T] = {}

    def add(self, name: str, entry: T) -> T:
        """Register `entry` under `name` and return it. Raise KeyError on a duplicate name."""
        if name in self._entries:
            raise KeyError(f"{self._kind} '{name}' already registered")
        self._entries[name] = entry
        return entry

    def register(self, name: str) -> Callable[[T], T]:
        """Return a decorator that registers its target under `name`: `@registry.register("bake")`."""

        def deco(entry: T) -> T:
            """Register `entry` and return it unchanged."""
            return self.add(name, entry)

        return deco

    def get(self, name: str) -> T:
        """Return the entry for `name`. Raise KeyError that lists known names if it is missing."""
        try:
            return self._entries[name]
        except KeyError:
            raise KeyError(f"unknown {self._kind} '{name}'; known: {sorted(self._entries)}") from None

    def __contains__(self, name: object) -> bool:
        """Return True if `name` is registered."""
        return name in self._entries

    def __iter__(self) -> Iterator[str]:
        """Iterate over registered names in sorted order."""
        return iter(sorted(self._entries))

    def names(self) -> frozenset[str]:
        """Return all registered names."""
        return frozenset(self._entries)
