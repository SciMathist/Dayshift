# dsz.skills

`skills` holds the skill-level actions. Each skill is one class (Command pattern). The executor checks each call before it runs it.

## Contents

| Module | Main types | Purpose |
|---|---|---|
| `registry.py` | `SKILLS`, `register_skill` | Plugin registry |
| `builtin.py` | the skills below | Built-in skills |
| `executor.py` | `SkillExecutor`, `validate_args`, `skills_doc` | Checks and runs calls. Makes the skill list for the policy |
| `services.py` | `BusOrderDesk`, `BusSpeech` | Bus-backed `OrderDesk` and `Speech` |

## Built-in skills

| Skill | Arguments | Effect |
|---|---|---|
| `navigate_to` | fixture | Drives to the fixture |
| `open`, `close` | fixture | Opens or closes the door of the fixture at the robot |
| `pick` | index | Grasps detection `index` from the current view |
| `place` | fixture, slot? | Puts the held object in or on the fixture at the robot |
| `set_power` | fixture, on | Switches a powered fixture |
| `start_process` | process, fixture | Starts a process on everything in the fixture |
| `look` | — | Observes again (1 min) |
| `wait` | minutes | Lets time pass (1..480) |
| `order` | supplier, item_type, qty | Sends an order. The supplier replies by message |
| `say` | to, text | Speaks to a person |

## Rules

- A skill gets only `SkillContext`: `Actuation`, `Perception`, `ProcessControl`, `OrderDesk`, `Speech`. It never gets `GroundTruth`, `WorldState` or the bus.
- Feedback is sensor data plus a short note. Never return a success flag.
- An invalid call returns `accepted=False`, takes 0 minutes and changes nothing.
- A physical skill takes at least 1 simulated minute.

## Extend

1. Subclass `Skill`. Set `name`, `doc`, `args` and `optional`.
2. Implement `run(ctx, args)`. Raise `SkillArgError` for values the skill cannot use.
3. Decorate the class with `@register_skill`. The executor and `skills_doc` find it automatically.
