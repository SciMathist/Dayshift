# dsz.core

`core` defines the contracts between all layers. It contains interfaces and value types only. It has no runtime dependencies on other `dsz` packages.

## Contents

| Module | Main types | Purpose |
|---|---|---|
| `types.py` | `Location`, `Horizon`, `CapabilitySet`, `Verdict`, `SkillCall`, `SkillResult`, `SensorReading`, `Detection`, `Message` | Immutable value types |
| `rng.py` | `RngStreams` | One independent random stream for each name, all from one seed |
| `registry.py` | `Registry` | Plugin mechanism: a unique name maps to one entry |
| `sim.py` | `Actuation`, `Perception`, `WorldEditor`, `GroundTruth`, `Checkpointable`, `SimBackend` | Simulator backend roles |
| `policy.py` | `Policy`, `Observation`, `TaskBrief`, `Action` | The one protocol for all models |
| `scenario.py` | `Scenario`, `Instance`, `WorkItem`, `Fact`, `ScheduledEvent` | Task definitions and their sampled instances |
| `dynamics.py` | `DynamicsModule` | Base class for the six difficulty modules |
| `events.py` | `DomainEvent`, `EventBus` | Observer contract for everything that occurs in a run |

## Backend roles

A backend implements all roles. Each consumer gets only the role it needs.

| Role | Consumer | Purpose |
|---|---|---|
| `Actuation` | skills | Move, open, grasp, place, switch power |
| `Perception` | observation builder | Detections, images, proprioception |
| `WorldEditor` | event engine, scenario loader | Deliveries, relocations, faults |
| `GroundTruth` | evaluator only | True locations and states |
| `Checkpointable` | env | Save and restore |

## Rules

- Do not give `GroundTruth` to a policy or a skill.
- Get all randomness from `RngStreams`. Use one stream name for each purpose (`world`, `work`, `events`, `noise`, `language`).
- `Instance` holds everything that the seed decides. Do not sample during a run.
- `Instance.prefix(days)` must give the start of the longer run, unchanged.
- `SkillResult` and `SensorReading` contain sensor data only. Do not add a success flag.

## Extend

- To add a backend, implement every role in `sim.py`.
- To add a model type, write an adapter that implements `Policy`.
- To add a scenario, implement `Scenario`. Do not change `core`.
