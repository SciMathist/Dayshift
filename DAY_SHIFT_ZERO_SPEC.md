# Day Shift Zero: Environment Design Spec

Status: draft v0.2, 2026-11-21. Parent document: `LONG_HORIZON_EMBODIED_PROJECT.md` (the predicates and working rules there still apply).
v0.2: the environment is now a task-agnostic kitchen **platform**, and long-horizon work plugs in as **scenarios** (sections 3–5).

## 1. What it is

Day Shift Zero tests how a robot handles real-life long-horizon work that spans days. A robot works in one persistent kitchen with **no resets** for the length of a scenario. Example scenarios: run a cloud kitchen for N days, or deliver a five-tier wedding cake on a 10-day contract. The kitchen stays the same. What the scenario defines is the objective, the people involved, the work and the events.

**Definition.** A long-horizon embodied task requires a robot to carry out many dependent actions over an extended period in a persistent, changing world. To succeed, the robot must:
- remember what it did and what it was told;
- notice and recover from its own failures before they compound;
- keep up with a world that changes without it.

The difficulty has to come from having a body, not only from planning.

**Positioning.** Existing long-horizon embodied benchmarks chain subtasks inside episodes that reset: CALVIN, LIBERO-10, BEHAVIOR-1K, RoboCasa365 composites, Habitat rearrangement. Memory and lifelong-navigation benchmarks add some recall across episodes:
- FindingDory, RoboMME and EmbodiedMemory-Bench test memory.
- LiSoNav-COL and EvoNav-Bench move objects between episodes.

The closest work is **WorldLines** (2026): multi-day household traces with resident changes the robot doesn't see. It scores frozen samples offline in a semantic view, not as a closed-loop physical rollout. Vending-Bench runs a business over hundreds of simulated days, but only in text. Day Shift Zero is a closed-loop, physics-simulated kitchen that hosts multi-day scenarios with objectives, scored as curves over time.
*Source: a quick related-work check (about 10 searches, 2026-11-21). Verify the citations before publishing.*

## 2. Design principles

1. **The platform doesn't know the task.** The kitchen, dynamics, skills, interface and tracing never refer to any particular scenario. A new scenario is a new definition, not a code change to the platform (open/closed).
2. **Fixed rules, random difficulty.** Within a scenario the rules are fixed. A hard day can come at any point, as in real life. Later days are harder only because of what the agent carries from earlier days.
3. **Every instance is certified.** Every scenario instance passes the same predicate checks (section 7) or is resampled. A scenario that can't produce certified instances is rejected, no matter how interesting it sounds.
4. **Generation is code, seeded and reproducible.** Instances are sampled from the scenario definition by a deterministic program. Any natural-language wording is generated once per seed, cached and frozen. Exogenous events come from their own random stream and don't depend on the agent.
5. **Prefix property.** For a fixed seed, a shorter horizon is a prefix of a longer one.
6. **Evaluator-only state stays hidden.** Ground truth, the event log and success labels never reach the policy.

## 3. Architecture: platform vs. scenario

```
            Scenario definition (YAML + optional hooks)
                         │  compile against the capability manifest
                         ▼
   Generator(seed, horizon) ──► Instance ──► Certifier ──► accept / resample
                                                  │
                                                  ▼
 ┌──────────────────────────── Platform (task-agnostic) ───────────────────────────┐
 │ Sim backend (RoboCasa | symbolic) · World model · Dynamics modules · Processes   │
 │ Actors & channels · Event engine · Skills · Clock · Interface · Trace · Metrics  │
 └──────────────────────────────────────────────────────────────────────────────────┘
```

**The platform provides a vocabulary.** It publishes a **capability manifest** listing:
- fixtures: fridge, freezer, oven, stove, mixer, sink, dishwasher, cabinets, counters;
- item types and their properties: perishable, fragile, allergen tags, temperature needs;
- processes: `mix`, `bake`, `cool`, `chill`, `freeze`, `thaw`, `proof`, `marinate`, `assemble`, `decorate`, `wash`. Each has a duration, required fixture, preconditions and failure modes;
- dynamics modules (section 4), actor types, event types and skills.

**A scenario is composed only from that vocabulary.** A scenario that needs something missing is rejected at compile time with the missing capability named. The vocabulary grows through plugins: register a new process, item type or event, and nothing else changes.

**Processes are semantic; handling is physical.** The spike found that RoboCasa cooking is flag-based. So doneness, proofing and frosting quality are tracked in the world model. What's embodied is everything around them: fetching, carrying, storing, finding, opening, placing, and fragile handling (a dropped tier is ruined).

## 4. Platform: world, dynamics, actors

- **Scene.** One pinned RoboCasa kitchen layout and style, which is never reset (spike: `reset()` builds a new kitchen). Robot: PandaOmron.
- **Clock.** Configurable day segments. When the robot is idle, physics is frozen and only the semantic clock advances (spike: objects drift during idle physics).
- **Object pool.** Deliveries and new items come from a pool of objects parked off-scene, because the MuJoCo model is compiled once. Parked objects float under gravity compensation, and a delivery restores a resting pose recorded at build time. Verified in spike run 2.
- **Actors.** Clients, customers, a manager, suppliers and co-workers. Each communicates through channels (messages, order tickets, phone) and can act on the world (move items, consume them, deliver them).

**The six difficulty mechanisms**, made reusable. Each is built from one or more of the plugin types below, and each plugin type has its own ABC and registry. A new dynamic is a new class plus a registration; no platform code changes. The mapping is in `dsz/dynamics/README.md`.
- **`DynamicsModule`:** continuous change driven only by time, independent of the agent (spoilage, wear). Its random draws are indexed by tick, so the agent's timing can't change them.
- **`EventHandler`:** discrete scheduled events, one Command per kind (message, delivery, relocate, consume, door_left_open, equipment_fault, goal_change).
- **`Actor`:** reactions to the agent (a supplier fulfils an order after a seeded lead time).
- **`ProcessRunner`:** lead-time processes (bake, chill, proof, assemble).

| # | Module | What it provides | Predicate |
|---|---|---|---|
| 1 | `facts` | Information stated once on a channel and never encoded in the world | M1 |
| 2 | `hidden_state` | Storage behind closed doors; identical-looking containers; batch identity | M1, E1 |
| 3 | `lead_time` | Processes that span segments or days (proof, marinate, chill, cure) | H1 (D) |
| 4 | `resources` | Consumption, reordering with delivery lag, expiry, spoilage | R1, 2.5 |
| 5 | `drift` | Unseen relocations, goal or preference changes, gradual equipment degradation that can only be detected by sensing | C1 |
| 6 | `compounding` | Persistent damage and waste; reputation that feeds back into future demand | R1, 2.5 |

## 5. Scenarios

A scenario is a **definition** (YAML or dict), plus optional **plugin modules** for behaviour that the built-ins don't cover. The scenario layer (`dsz.scenario`, see its README) materializes it:

```
definition ──parse──► ScenarioSpec ──compile──► Scenario ──generate(seed, N)──► Instance ──materialize──► Run
```

- **Parse:** checks structure and reports every problem at once.
- **Compile:**
  - imports `plugins:` and resolves plugin names;
  - validates module and actor parameters;
  - checks capabilities against the platform manifest;
  - checks references in a 1-day probe instance.
- **Generate:** a plugin generator. The built-in one is `template` and needs no code. Day *d* is identical in every horizon (prefix property).
- **Materialize:** wires backend, items, events (exogenous events, fact reveals, work tickets), actors, modules, processes, the work tracker, the success check, skills and observations into a `Run`.

The definition names plugins and gives them parameters:

```yaml
id: deli
objective: "Pack and dispatch lunch boxes on time."
horizon: {type: continuous, days: 3}            # or deadline
fixtures: {fridge: fridge, counter: counter, dispatch: dispatch_shelf, inbox: delivery_shelf}
modules: {spoilage: {}, wear: {fixtures: [fridge], per_day: 0.05}}
actors: [{role: supplier, name: acme, fixture: inbox, lead_time_days: [1, 2]}]
generator:
  name: template
  params:
    initial: [{type: cheese, count: 4, at: fridge}]
    pool: {cheese: 12}
    subjects: [c01, c02]
    facts: [{id: c01_dairy, subject: c01, text: "c01 cannot eat dairy.", at: {day: 0, minute: 500},
             constraint: {exclude_allergens: [dairy]}}]          # hidden constraint on later work (M1)
    work: [{kind: order, per_day: [3, 6], window: [600, 1200], lead: [45, 90], collect: true,
            variants: [{deliver: {item_type: meal_box, stages: [packed], at: dispatch},
                        ticket: "Order {work_id} for {subject} by {due}."}]}]
    events: [{kind: relocate, payload: {item_type: cheese, to: counter}, per_day: [0, 1], window: [0, 1440]}]
success:
  criteria:
    work_completion: {params: {min_on_time: 0.9}}
    no_violations: {}
    waste: {required: false, weight: 0.5}
policies: {oracle: deli_oracle, controls: [noop]}
plugins: [scenarios.deli.plugins]
```

**Success** is a composite of `Criterion` plugins:
- **Binary:** every required criterion passes.
- **Graded:** the weighted mean of the criterion scores.

Work completion is a generic `deliver` predicate: item type, stages, fixture, allergens to exclude, deadline, and optional courier collection.

**Reference scenarios**

| Scenario | Horizon | Why it's long horizon |
|---|---|---|
| **Cloud kitchen** | Continuous, N days, with a business objective (≥X% of orders on time, zero allergen incidents, margin ≥ Y) | Demand forecasting and prep, stock and reorders, repeat-customer notes stated once, reputation feedback |
| **Wedding cake contract** | Deadline, 10 days | Long lead-time process graph, a fragile final assembly, brief changes partway through, early prep stored for days |

Guardrails for any scenario:
- It must not collapse into abstract scheduling (fails E1) or rely on tickets that can be re-read (fails M1). Certification (section 7) enforces this.
- Volume stays within what one robot can do at simulation speed.

## 6. Interface

- **Split process.** The environment runs as a server in a pinned container (assets mounted as a volume; they are 23 GB). API: `reset(scenario, seed, horizon)`, `observe()`, `step(action)`, `close()`. The environment is also available as a Gymnasium env for LeRobot tooling.
- **Model agnostic: the environment and the model are separate.**
  - The env container holds no model code and no model dependencies.
  - The wire API (`dsz.api`) is the only contract.
  - Adapters live in a separate client package (`clients/dsz_client`) that runs anywhere and never imports env internals. There is one adapter per model type:
    - VLA / LeRobot policy
    - VLM with harness
    - agent as policy
    - world action model (format still to be defined)
  - The oracle and the negative controls are evaluator-side, so they run in-process through `core.Policy`. Models always connect through the API.
- **Two action spaces, one verifier behind both:**
  - low level: the native 12-dim RoboCasa control at 20 Hz;
  - skill level: `navigate_to`, `open/close`, `pick`, `place`, `start_process(process, fixture)`, `look`, `wait`, `order`, `say`.
- **Grounding.** The agent can name fixtures. For objects it picks an index from a detection list built from the current view only (the default) or gives a pixel point (a switch). There are no global object IDs.
- **Skill feedback comes from sensors only.** Skills return gripper width, contact and a post-action image. They never return a success flag.
- **Observation.** Three RGB views at 256², rendered only when the agent makes a decision; proprioception; the clock; channel messages. The harness memory policy is fixed and logged per run.

## 7. Instance certification (any scenario, per seed and horizon)

| Check | Rule |
|---|---|
| H1 | Oracle length L ≥ θ_L, and dependency depth D ≥ θ_D at the skill level |
| M1 | At least one fact stated only on a channel (not encoded in the world) is needed more than k steps after it is revealed, under a deadline that makes exhaustive re-search infeasible |
| R1 | At least one reachable failure in each branch, recoverable and irrecoverable |
| C1 | At least one unobserved exogenous event changes state that later work depends on |
| V1 | The oracle passes under all scheduled events. The no-op, hidden-state-ignoring and never-recovering controls all fail |
| E1 | Measured per scenario and horizon as the gap between the symbolic and embodied versions. A scenario whose gap is near zero is flagged as an abstract task |

The thresholds are set from pilot runs, then frozen.

## 8. Success and metrics

- **Binary and graded success** are defined per scenario through `success()`. Binary is the spec's G: the objective is met with no invariant violated. Graded is the scenario's continuous score.
- **Platform metrics** (the same for every scenario):
  - graded score over time;
  - sustainable horizon (continuous scenarios);
  - milestone timeliness (deadline scenarios);
  - survival to the first irrecoverable failure;
  - backlog;
  - belief drift: the agent's picture of the world against ground truth;
  - a load log per day or segment.
- **Failure attribution** by module (1–6), labeled automatically from evaluator-only state.

**Ablations** (one factor at a time, matched seeds):
- full history vs. last-k (M1);
- symbolic vs. embodied (E1);
- adaptive vs. plan-once (C1);
- recovery-aware vs. failure-blind (R1).

## 9. Project structure

```
day_shift_zero/
  pyproject.toml
  docker/                 # pinned images (arm64 and amd64); assets mounted, not baked in
  configs/                # run configs; thresholds unset until pilots
  scenarios/              # task definitions only, no platform code
    cloud_kitchen/        # scenario.yaml, hooks.py, oracle.py
    wedding_cake/
  src/dsz/
    core/                 # interfaces only: SimBackend, Scenario, Policy, ActionSpace, Clock, RngStreams
    world/                # semantic world model: items, containers, fixtures, processes, capability manifest
    dynamics/             # the six modules
    actors/               # actor types and channels
    events/               # event types and engine
    scenario/             # loader, compiler (checks against the manifest), generator runtime
    certify/              # instance checks (section 7)
    skills/               # one class per skill (Command pattern) + registry
    sim/
      robocasa/           # embodied backend: pinned scene, object pool, render-on-decision
      symbolic/           # symbolic backend (the E1 comparison)
    api/                  # wire schemas + serialization: the only surface clients see
    env/                  # Gymnasium env and env server (composition root)
    eval/                 # metrics, ablation runner, negative-control policies
    trace/                # trace writer and failure labeler
  tests/
clients/
  dsz_client/             # separate package: API client + model adapters (vla, vlm, agent, wam); no env imports
spike/                    # throwaway experiments, never imported by src/
```

**Patterns and SOLID:**
- **Strategy:** simulator backends, policy adapters and scenarios.
- **Command plus a registry:** skills, processes, events and dynamics modules.
- **Observer:** an event bus feeds the trace writer and the metrics.
- **Factory:** the scenario generator builds instances.
- **Dependency injection:** the env is constructed with its backend, scenario, clock and random streams, with no globals.
- `core/` holds only abstractions, and every other package depends on `core/` (dependency inversion).
- `world/` knows nothing about MuJoCo, and `src/` knows nothing about any specific scenario.

## 10. Two-day ship scope

| In | Out (later) |
|---|---|
| Platform with the six modules (1, 2, 4, 5 complete; 3, 6 minimal) and a capability manifest | VLA runs (the low-level space is exposed but not evaluated) |
| **Cloud kitchen** scenario: symbolic curves for N = 1 to 6+, embodied for N = 1 to about 3 | Threshold calibration and frozen seeds |
| **Wedding cake** scenario on the symbolic backend, to prove the platform really is decoupled | Level 1 proposer loop (LLM-written scenarios) |
| Oracle, negative controls, determinism test, trace labels | Rooms beyond the kitchen |

Every number in the ship is labeled **pilot, not a benchmark result**. A separate reviewer verifies the build.

## 11. Open questions

1. What exactly are WAM and RAX (formats)?
2. Which models will we run, and do we have API keys?
3. ~~Asset coverage~~ and ~~object pool vs. recompile~~: resolved, see section 12 run 2.

## 12. Spike log

**Run 1 (2026-11-21).**
- Setup: native macOS on an Apple M4 with 16 GB, Python 3.11.18. RoboCasa @ `7bfc60c`, robosuite 1.5.2 @ `5ce6643`, MuJoCo 3.3.1, LeRobot 0.3.3, numpy 2.2.5.
- Task: `LoadFridgeByType`, seed 0, PandaOmron.
- Script: `spike/probes/robocasa_probe.py`. Raw output: `spike/probes/report_run1.json`.

| Question | Result | Implication |
|---|---|---|
| Install on Mac | Works. Assets are **23 GB extracted** (the README says about 10 GB). Offscreen rendering uses CGL/GLFW natively; EGL is Linux only | The container image will be large: mount the assets as a volume, don't bake them in |
| Load and reset | Build 0.7 s, reset 2.4–5.3 s. Actions are 12-dim at 20 Hz | — |
| Step rate | **58 steps/s with no cameras (2.9× real time)**; **26 steps/s with 3×256² RGB (1.3×)** | Render only when the agent makes a decision, not on every physics step. Real-time physics for a whole simulated day is out of reach, so **time skipping is required** |
| Object pose edits mid-episode | Work (`set_joint_qpos` + `forward`). An object dropped from 0.3 m ended up 14 cm off target | Events must place objects **at rest height**, never drop them |
| Fixture state edits mid-episode | Work. A cabinet set to open stayed at 0.95–0.98 after 40 steps | Exogenous fixture events (a door left ajar) are feasible |
| Drift during long idle stretches | 2,000 idle steps (100 s simulated): items in bowls drifted up to 2 cm | Over a simulated day this adds up. **Freeze physics while the robot is idle** and advance only the semantic clock |
| Checkpoint and restore | Exact (error 0.0 on a 221-dim state) | Checkpoint and resume of the full world is feasible |
| Persistence across tasks | **No.** `reset()` builds a new kitchen every time (layout 52 → 14 → 11, new styles, model rebuilt) | Never call `reset()` during a run. Pin `layout_ids` and `style_ids`. Day Shift Zero has its own kitchen subclass and task layer; RoboCasa's task classes serve only as scene and fixture examples |
| Physical vs. flag-based cooking | Flag-based, from the code (not run): stove flames are a color toggle driven by knob angle; toaster and oven state is read from joint positions | Processes are semantic and live in `world/`. Handling is physical (section 3) |

**Run 2: object pool (2026-11-21).**
- Script: `spike/probes/object_pool_probe.py`. Raw output: `spike/probes/report_pool.json`.
- Kitchen layout 1, style 1.
- Pool: egg, butter_stick, milk, chicken_breast, cake, tupperware.

| Question | Result | Implication |
|---|---|---|
| Can objects be parked off-scene? | Yes. They float with `body_gravcomp=1` and zero velocity: **0.0 m drift over 400 steps**. Gotcha: MuJoCo ignores runtime gravcomp unless `ngravcomp > 0` at compile time. A static, contact-free anchor body with `gravcomp="1"` fixes this (verified in plain MuJoCo and in RoboCasa) | The object pool works; no recompile is needed for deliveries |
| Do delivered objects land where expected? | Restoring the rest pose recorded from RoboCasa's own placement sampler: **settle error ≤ 0.1 mm** | Record valid rest poses at build time and deliver to them |
| Asset coverage | cake, cupcake, egg, butter_stick, milk, cream_cheese_stick, chicken_breast, steak, tupperware, plate, tray, oven_tray are all available. **butter_stick and chicken_breast exist only in the `aigen` registry**, which is off by default, so pass `obj_registries=("objaverse","lightwheel","aigen")`. `flour_bag` is not graspable. There is no peanut-butter jar or sugar flower | Use proxies for the missing items. Enable all three registries |
| Checkpoints | `body_gravcomp` is a model field, not part of the sim state | Checkpoints must save the pool's park/active flags alongside qpos/qvel |

**Not verified yet:**
- Rendering cost inside the container.
- Skill-level timing (wall time per pick or place).
