"""Simulated clock. Integer minutes; it only moves forward."""

from __future__ import annotations

from dsz.core.types import MINUTES_PER_DAY, SimMinutes


class SimClock:
    """Monotonic simulated clock with day and time-of-day helpers."""

    def __init__(self, start: SimMinutes = 0) -> None:
        """Create a clock at `start` minutes."""
        self._now = start

    @property
    def now(self) -> SimMinutes:
        """Return the current simulated time."""
        return self._now

    @property
    def day(self) -> int:
        """Return the zero-based day index."""
        return self._now // MINUTES_PER_DAY

    @property
    def minute_of_day(self) -> int:
        """Return minutes since midnight of the current day."""
        return self._now % MINUTES_PER_DAY

    def advance_to(self, t: SimMinutes) -> None:
        """Move the clock to `t`. Raise ValueError if `t` is in the past."""
        if t < self._now:
            raise ValueError(f"clock cannot go back: {t} < {self._now}")
        self._now = t

    def advance(self, dt: SimMinutes) -> None:
        """Move the clock forward by `dt` minutes."""
        self.advance_to(self._now + dt)

    def stamp(self) -> str:
        """Return a human-readable stamp, e.g. 'day 2 01:30' (days are one-based)."""
        m = self.minute_of_day
        return f"day {self.day + 1} {m // 60:02d}:{m % 60:02d}"
