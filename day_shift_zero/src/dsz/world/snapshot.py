"""Plain-data snapshot of the world, for the full-state (pi_sym) ablation and for traces."""

from __future__ import annotations

from typing import Any

from dsz.world.state import WorldState


def world_snapshot(world: WorldState) -> dict[str, Any]:
    """Return items in the world, fixtures and the robot position as JSON-ready data."""
    items = {
        i.item_id: {
            "type": i.item_type,
            "at": i.location.fixture if i.location.fixture else i.location.kind.value,
            "slot": i.location.slot,
            "stages": sorted(i.stages),
            "condition": i.condition.value,
            "spoilage": round(i.spoilage, 3),
            "allergens": sorted(i.allergens),
        }
        for i in sorted(world.in_world(), key=lambda x: x.item_id)
    }
    fixtures = {
        f.fixture_id: {"kind": f.kind, "open": f.is_open, "on": f.powered_on, "zone": f.effective_zone().value}
        for f in sorted(world.fixtures.values(), key=lambda x: x.fixture_id)
    }
    return {"t": world.now, "robot_at": world.robot_at, "items": items, "fixtures": fixtures}
