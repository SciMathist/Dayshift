# dsz.events

`events` holds the event bus and runs scheduled events. Each event kind is one handler class (Command pattern).

## Contents

| Module | Main types | Purpose |
|---|---|---|
| `bus.py` | `InMemoryEventBus`, `RecordingBus` | Synchronous, ordered publish and subscribe |
| `engine.py` | `EventEngine` | Runs events in (time, insertion) order. Also an `EventScheduler` |
| `registry.py` | `EVENT_TYPES`, `register_event` | Plugin registry |
| `handlers.py` | built-in handlers | The event kinds below |

## Built-in event kinds

| Kind | Payload | Effect |
|---|---|---|
| `message` | channel, sender, text, fact_id? | Posts a message. With `fact_id`, records `fact.revealed` |
| `delivery` | items, fixture | Brings parked pool items into the world |
| `relocate` | item, to, expect_at? | Moves an item without the robot |
| `consume` | item_type, count, from? | Removes the oldest OK items. Reports any shortfall |
| `door_left_open` | fixture | Opens a fixture door |
| `equipment_fault` | fixture, health | Lowers fixture health at once |
| `goal_change` | change, channel, sender, text | Records the new goal. Tells the robot by message |

## Rules

- The engine defers an event while the robot stands at a fixture that the event touches. The deferral step is `defer` minutes.
- A handler applies its effect to the state it finds. If the target is gone, it publishes `event.noop`.
- Make all physical changes through `ctx.editor`. Only semantic fields (health, stages) may change directly.
- Each kind gets its own RNG stream: `events.<kind>`.
- `DomainEvent` is evaluator-only by default. Only messages are visible to the policy.

## Extend

1. Subclass `EventHandler`. Set `kind`.
2. Implement `apply(ctx, event)`. Implement `touches(payload)` if the event edits a fixture physically.
3. Decorate the class with `@register_event`.
4. Schedule the kind from a scenario generator or an actor. No other code changes.
