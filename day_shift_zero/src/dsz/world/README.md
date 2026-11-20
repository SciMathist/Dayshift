# dsz.world

`world` is the semantic model of the kitchen. It does not know MuJoCo. The symbolic backend uses it as the full world. The RoboCasa backend syncs item locations into it after each skill.

## Contents

| Module | Main types | Purpose |
|---|---|---|
| `catalog.py` | `FixtureKind`, `ItemType`, `ProcessSpec`, registries | The kinds of things that can exist |
| `vocabulary.py` | `register_default_vocabulary()` | Default kitchen: 14 fixture kinds, 16 item types, 13 processes |
| `state.py` | `WorldState`, `Item`, `Fixture`, `ActiveProcess` | The current world, with safe changes |
| `clock.py` | `SimClock` | Simulated time in whole minutes |
| `manifest.py` | `build_manifest()`, `check_requirements()` | What the platform offers; rejects scenarios that need more |

## Use

```python
bus = RecordingBus()
register_default_vocabulary()
world = WorldState(bus)
world.add_fixture("fridge", "fridge")
world.add_item("egg_1", "egg", Location.at("fridge"))
world.move("egg_1", Location.held(), cause="skill.pick")
```

## Rules

- Change state only through `WorldState` methods. Each change publishes a `DomainEvent`.
- A condition other than OK is permanent. `degrade()` refuses `Condition.OK`.
- The gripper holds one item. A full fixture refuses more items.
- A combined product gets all allergens of its inputs. A bad input makes the product bad.
- Processes are semantic. Doneness, proofing and frosting are stages on items, not physics.
- The values in `vocabulary.py` are plausible defaults. They are not calibrated thresholds.

## Extend

- To add an item, fixture or process, register it in the matching registry.
- Give each new item an asset that exists in the backend, or tag it `proxy`.
- Then add it to the scenario's `requirements()`. The manifest check finds missing entries.
