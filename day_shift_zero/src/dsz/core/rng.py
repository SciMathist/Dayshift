"""Named, independent random streams derived from one seed.

Separate streams keep exogenous events independent of the agent and of task sampling:
drawing more numbers in one stream never shifts another (spec: separate RNG streams).
"""

from __future__ import annotations

import hashlib

import numpy as np

STANDARD_STREAMS = ("world", "work", "events", "noise", "language")


class RngStreams:
    """Lazily created numpy generators, one per stream name, all derived from one seed."""

    def __init__(self, seed: int) -> None:
        """Create the stream set for `seed`. Raise ValueError if the seed is negative."""
        if seed < 0:
            raise ValueError("seed must be non-negative")
        self._seed = seed
        self._streams: dict[str, np.random.Generator] = {}

    @property
    def seed(self) -> int:
        """Return the root seed."""
        return self._seed

    def get(self, name: str) -> np.random.Generator:
        """Return the generator for stream `name`, creating it on first use."""
        if name not in self._streams:
            self._streams[name] = np.random.default_rng(self._derive(name))
        return self._streams[name]

    def indexed(self, name: str, index: int) -> np.random.Generator:
        """Return a fresh generator for (`name`, `index`), independent of how often it was asked for.

        Use it when draws must not depend on call pattern, e.g. one generator per dynamics
        tick, so agent-dependent time splits cannot change exogenous randomness.
        """
        return np.random.default_rng(self._derive(f"{name}#{index}"))

    def _derive(self, name: str) -> int:
        """Derive a stable 64-bit stream seed from the root seed and the stream name."""
        digest = hashlib.sha256(f"{self._seed}:{name}".encode()).digest()
        return int.from_bytes(digest[:8], "little")

    def state(self) -> dict[str, dict]:
        """Return the bit-generator state of every created stream, for checkpoints."""
        return {k: g.bit_generator.state for k, g in self._streams.items()}

    def restore(self, state: dict[str, dict]) -> None:
        """Restore stream states captured by `state()`."""
        for name, s in state.items():
            self.get(name).bit_generator.state = s
