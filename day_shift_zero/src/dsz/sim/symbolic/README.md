# dsz.sim.symbolic

`SymbolicBackend` is the kitchen without geometry. It is the spec's `tau_sym`. It implements every role in `dsz.core.sim` on top of a `WorldState`.

## Behaviour

| Topic | Rule |
|---|---|
| Visibility | The robot sees items in the fixture where it stands, if the fixture has no door or the door is open |
| Reach | Door, place and power actions work only at the fixture where the robot stands |
| Grounding | Detections are labelled by item type. Their order is stable. They contain no ids |
| Failures | None by default. `grasp_fail_p` makes grasps fail. `break_on_fail_p` breaks fragile items on a failed grasp |
| Notes | Blocked actions return a note: "out of reach", "door is closed", "no space", "hand is full", "nothing there" |
| Time | Navigate 30 s, door 5 s, grasp 10 s, place 10 s, power 3 s. Skills round up to whole minutes |
| Checkpoint | Pickles world data, robot position and the noise RNG state |

## Use

```python
backend = SymbolicBackend(world, RngStreams(seed).get("noise"))
backend.build({"fridge": "fridge", "counter": "counter"}, pool={"egg_1": "egg"})
```

## Rules

- Keep failures off (0.0) for the E1 comparison. Turn them on only to test recovery.
- The pi_sym ablation gets full state from `ObservationBuilder(full_state=...)`, not from this backend.
