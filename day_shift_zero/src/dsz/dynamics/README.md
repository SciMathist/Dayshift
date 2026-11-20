# dsz.dynamics

`dynamics` changes the world as time passes. The agent does not cause these changes. Each change type is one plugin module.

## Contents

| Module | Main types | Purpose |
|---|---|---|
| `registry.py` | `MODULES`, `register_module`, `build_modules` | Plugin registry and factory |
| `runner.py` | `DynamicsRunner` | Advances all modules in fixed ticks |
| `spoilage.py` | `SpoilageModule` (`spoilage`) | Perishable items age against the shelf life of their zone |
| `wear.py` | `WearModule` (`wear`) | Fixture health drops each day; a failing fridge stops cooling |

## Where the six mechanisms live

The spec lists six mechanisms. Each uses the plugin type that fits it.

| Mechanism | Implementation |
|---|---|
| 1 `facts` | `message` event with `fact_id` (`dsz.events`) |
| 2 `hidden_state` | Closed doors and containers (`dsz.world`, backends) |
| 3 `lead_time` | `ProcessRunner` (`dsz.world.processes`) |
| 4 `resources` | `spoilage` module, `consume` event, `supplier` actor |
| 5 `drift` | `wear` module, `relocate`, `equipment_fault`, `door_left_open`, `goal_change` events |
| 6 `compounding` | Irreversible conditions (`dsz.world`), and scenario-level modules |

## Use

```python
modules = build_modules({"spoilage": {}, "wear": {"fixtures": ["fridge"], "per_day": 0.05}})
runner = DynamicsRunner(modules, RngStreams(seed), bus)
runner.advance(world, t0, t1)
```

## Rules

- A module must not read or react to agent actions. Use an `Actor` for reactions.
- Get randomness only from the `rng` argument. The runner derives it from (module name, tick index).
- Make effects scale with elapsed time. Then results do not depend on how time is split.
- Validate parameters in `validate()`. Bad parameters must fail at build time, not during a run.

## Extend

1. Subclass `DynamicsModule`. Set `name`.
2. Implement `advance(world, t0, t1, rng, bus)`. Optionally implement `validate()` and `requires()`.
3. Decorate the class with `@register_module`.
4. Name the module in the scenario `modules:` block. No other code changes.
