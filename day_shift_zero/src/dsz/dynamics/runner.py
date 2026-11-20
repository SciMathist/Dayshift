"""Dynamics runner: advance all modules in fixed ticks, each with its own RNG stream."""

from __future__ import annotations

from typing import Sequence

from dsz.core.dynamics import DynamicsModule
from dsz.core.events import EventBus
from dsz.core.rng import RngStreams
from dsz.core.types import SimMinutes
from dsz.world.state import WorldState

DEFAULT_TICK: SimMinutes = 10


class DynamicsRunner:
    """Advance modules over [t0, t1) in ticks of at most `tick` minutes, in a fixed module order.

    Each module gets a generator derived from (module name, absolute tick index). Any part of
    the same tick sees the same draws, so effects that scale with elapsed time do not depend
    on how the agent's actions split time. This keeps exogenous dynamics agent-independent.
    """

    def __init__(self, modules: Sequence[DynamicsModule], rng: RngStreams, bus: EventBus,
                 tick: SimMinutes = DEFAULT_TICK) -> None:
        """Run `modules` with randomness from `rng` and events on `bus`."""
        if tick < 1:
            raise ValueError("tick must be at least one minute")
        self._modules = list(modules)
        self._rng = rng
        self._bus = bus
        self._tick = tick

    @property
    def modules(self) -> tuple[DynamicsModule, ...]:
        """Return the modules in run order."""
        return tuple(self._modules)

    def advance(self, world: WorldState, t0: SimMinutes, t1: SimMinutes) -> None:
        """Advance every module from `t0` to `t1`, cutting the interval at absolute tick boundaries."""
        t = t0
        while t < t1:
            k = t // self._tick
            nxt = min(t1, (k + 1) * self._tick)
            for m in self._modules:
                m.advance(world, t, nxt, self._rng.indexed(f"dynamics.{m.name}", k), self._bus)
            t = nxt
