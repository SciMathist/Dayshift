# dsz.actors

`actors` contains the people in the world: suppliers, customers, couriers and co-workers. An actor reacts to what happens. It also talks to the robot through channels.

## Contents

| Module | Main types | Purpose |
|---|---|---|
| `channels.py` | `ChannelHub` | Message log. The policy reads only new messages |
| `registry.py` | `ACTORS`, `register_actor`, `build_actors` | Plugin registry and factory |
| `supplier.py` | `Supplier` (`supplier`) | Delivers ordered items from the pool after a seeded lead time |

## Supplier

| Param | Meaning |
|---|---|
| `fixture` | Where deliveries arrive (required) |
| `lead_time_days` | Inclusive range of delivery delay, in days |
| `arrive_at_minute` | Time of day for deliveries (default 480 = 08:00) |
| `short_ship_p` | Chance that each unit is missing |

The supplier listens for `order.placed`. It confirms by message and schedules a `delivery` event. If the pool has no stock, it sends an out-of-stock message.

## Use

```python
for actor in build_actors(scenario_actors):
    actor.attach(engine.context(f"actors.{actor.name}"))
```

## Rules

- An actor may react to the agent. A dynamics module may not.
- Get randomness only from `ctx.rng`. Each actor has its own stream: `actors.<name>`.
- Tell the robot things only through `ctx.channels`.
- Make physical changes only through scheduled events or `ctx.editor`.

## Extend

1. Subclass `Actor`. Set `role`.
2. Implement `attach(ctx)`. Subscribe to the bus events the actor needs.
3. Decorate the class with `@register_actor`.
4. List the actor in the scenario `actors:` block. No other code changes.
