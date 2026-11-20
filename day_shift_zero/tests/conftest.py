"""Shared pytest fixtures: a recording event bus and a small kitchen world."""

import pytest

from dsz.events.bus import RecordingBus
from dsz.world.state import WorldState
from dsz.world.vocabulary import register_default_vocabulary

register_default_vocabulary()


@pytest.fixture
def bus() -> RecordingBus:
    """Return a bus that records every published event."""
    return RecordingBus()


@pytest.fixture
def world(bus: RecordingBus) -> WorldState:
    """Return a world with fridge, freezer, counter, oven, cabinet, trash and delivery shelf."""
    w = WorldState(bus)
    for fid, kind in [("fridge", "fridge"), ("freezer", "freezer"), ("counter", "counter"),
                      ("oven", "oven"), ("cabinet_1", "cabinet"), ("trash", "trash"),
                      ("delivery_shelf", "delivery_shelf")]:
        w.add_fixture(fid, kind)
    return w
