"""Process runner: start, complete, abort and overrun semantic processes (bake, chill, proof...).

Lead-time mechanics (spec module 3) live here: a process completes only if its inputs stay
in the fixture for the full duration, and leaving them too long applies the overrun effect.
"""

from __future__ import annotations

from dsz.core.events import DomainEvent, EventBus
from dsz.core.types import Location, LocationKind, SimMinutes
from dsz.world.catalog import PROCESSES, ProcessSpec
from dsz.world.state import ActiveProcess, WorldState


class ProcessRunner:
    """Validate process starts from skills and resolve running processes as time passes."""

    def __init__(self, world: WorldState, bus: EventBus) -> None:
        """Run processes on `world` and publish their outcomes on `bus`."""
        self._world = world
        self._bus = bus
        self._products = 0

    def start(self, process: str, fixture_id: str, item_ids: tuple[str, ...]) -> str | None:
        """Start `process` on `item_ids` in `fixture_id`. Return None on success, else a reason.

        Reasons are sensor-plausible (what a cook would notice), never hidden state.
        """
        if process not in PROCESSES:
            return f"unknown process '{process}'"
        spec = PROCESSES.get(process)
        reason = self._check(spec, fixture_id, item_ids)
        if reason:
            return reason
        now = self._world.now
        self._world.processes.append(ActiveProcess(process, fixture_id, item_ids, now, now + spec.duration))
        self._bus.publish(DomainEvent(now, "process.started",
                                      {"process": process, "fixture": fixture_id, "items": list(item_ids)}))
        return None

    def advance(self, t: SimMinutes) -> None:
        """Resolve every process at time `t`: abort, complete, or apply overrun."""
        for proc in list(self._world.processes):
            spec = PROCESSES.get(proc.process)
            if not self._inputs_in_place(proc):
                if not proc.completed:
                    self._finish(proc, "process.aborted")
                else:
                    self._world.processes.remove(proc)  # collected after completion: done
                continue
            if not proc.completed and t >= proc.done_at:
                if spec.requires_power and not self._world.fixture(proc.fixture_id).powered_on:
                    self._finish(proc, "process.aborted")
                    continue
                self._complete(spec, proc)
            if proc.completed and spec.overrun_tolerance is not None and t > proc.done_at + spec.overrun_tolerance:
                self._overrun(spec, proc)

    # ---- internals ----------------------------------------------------------------------
    def _check(self, spec: ProcessSpec, fixture_id: str, item_ids: tuple[str, ...]) -> str | None:
        """Return why `spec` cannot start here, or None."""
        if fixture_id not in self._world.fixtures:
            return f"unknown fixture '{fixture_id}'"
        fixture = self._world.fixture(fixture_id)
        if fixture.kind not in spec.fixture_kinds:
            return f"{spec.name} needs one of {sorted(spec.fixture_kinds)}"
        if spec.requires_power and not fixture.powered_on:
            return f"{fixture_id} is off"
        if not item_ids:
            return "no items"
        for iid in item_ids:
            loc = self._world.item(iid).location
            if loc.kind is not LocationKind.FIXTURE or loc.fixture != fixture_id:
                return f"an item is not in {fixture_id}"
            if not spec.requires_stages <= self._world.item(iid).stages:
                return f"an item is not ready for {spec.name}"
        if any(set(item_ids) & set(p.item_ids) for p in self._world.processes):
            return "an item is already in a process"
        return None

    def _inputs_in_place(self, proc: ActiveProcess) -> bool:
        """Return True if every input (or the product, after combining) is still in the fixture."""
        return all(self._world.item(i).location.kind is LocationKind.FIXTURE
                   and self._world.item(i).location.fixture == proc.fixture_id
                   for i in proc.item_ids)

    def _complete(self, spec: ProcessSpec, proc: ActiveProcess) -> None:
        """Apply the process result and mark it completed."""
        if spec.combines:
            self._products += 1
            pid = f"{spec.name}_{self._products}"
            self._world.combine(pid, spec.product_type or self._world.item(proc.item_ids[0]).item_type,
                                proc.item_ids, Location.at(proc.fixture_id), spec.adds_stage)
            proc.item_ids = (pid,)
        else:
            for iid in proc.item_ids:
                self._world.add_stage(iid, spec.adds_stage)
        proc.completed = True
        self._bus.publish(DomainEvent(self._world.now, "process.completed", _payload(proc)))

    def _overrun(self, spec: ProcessSpec, proc: ActiveProcess) -> None:
        """Apply the overrun effect to the outputs and close the process."""
        for iid in proc.item_ids:
            if spec.overrun_effect is not None:
                self._world.degrade(iid, spec.overrun_effect, cause=f"{spec.name}.overrun")
        self._finish(proc, "process.overrun")

    def _finish(self, proc: ActiveProcess, kind: str) -> None:
        """Remove `proc` and publish `kind`."""
        self._world.processes.remove(proc)
        self._bus.publish(DomainEvent(self._world.now, kind, _payload(proc)))


def _payload(proc: ActiveProcess) -> dict:
    """Return the event payload describing `proc`."""
    return {"process": proc.process, "fixture": proc.fixture_id, "items": list(proc.item_ids)}
