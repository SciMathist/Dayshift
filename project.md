# Day Shift Zero: Project

Status: draft v0.3, 2026-11-22. Parent document: `LONG_HORIZON_EMBODIED_PROJECT.md` (the predicates and working rules there still apply).
v0.3: measurement is policy-agnostic. The task input is a goal, tracks follow the action space, and skills have two backends (sections 2, 6, 8).

## 1. What it is

Day Shift Zero tests how a robot handles real-life long-horizon work that spans days. A robot works in one persistent kitchen with **no resets** for the length of a scenario. Example scenarios: run a cloud kitchen for N days, or deliver a five-tier wedding cake on a 10-day contract. The kitchen stays the same. What the scenario defines is the objective, the people involved, the work and the events.

**Definition.** `LONG_HORIZON_TASK_SPEC.md` formally defines a long-horizon embodied task and the certification predicates. Section 5 explains how scenarios are authored.

**Positioning.** Existing long-horizon embodied benchmarks chain subtasks inside episodes that reset: CALVIN, LIBERO-10, BEHAVIOR-1K, RoboCasa365 composites (a step-list instruction per task; median demo 46 s, longest 166 s), Habitat rearrangement. Memory and lifelong-navigation benchmarks add some recall across episodes:
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
6. **Evaluator-only state stays hidden.** Ground truth, the event log and success labels never reach the policy. The only exceptions are the diagnostic ablations in section 8, which never count as scores.
7. **Difficulty comes only from embodiment.** Each difficulty has a physical consequence, and parametric choices don't count (`LONG_HORIZON_TASK_SPEC.md` section 3). E1 (section 7) rejects an instance that breaks this.
8. **The policy is a black box.** The platform fixes the task, the interface and the measurement. A policy is anything behind `Policy.reset` and `Policy.act`. Every score and diagnostic reads world state and traces, never policy internals, so no metric depends on the model type.

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
# policies: set only by the scenario's oracle.py until the generic oracle exists
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
- It must not rely on tickets that can be re-read (fails M1, section 7).
- The cloud-kitchen objective above uses demand forecasting, stock reordering and margin, which are parametric (principle 7). Rewrite it before the scenario is certified.
- Volume stays within what one robot can do at simulation speed.

**Scenario authoring.** Agents write scenarios in a sandbox, and people review them. How to run the loop: `authoring/README.md`.

| Role | Sees | Produces |
|---|---|---|
| Author agent | A sandbox outside the repository: the task spec, the format reference, the generated vocabulary and its own `scenario/` folder. It can run only `dsz verify` | `scenario.yaml` and `DESIGN.md` |
| Verifier (`dsz verify`) | The scenario folder | A report with stage results and rule IDs. Deterministic, no LLM |
| Reviewer agent | The same sandbox, read-only, plus the verify output and the author's report | A verdict (pass, improve or discard) and findings with rule IDs |
| Loop (`authoring/loop.py`) | Everything the agents produce | Passes outputs on word for word. Copies a passed scenario to `day_shift_zero/scenarios/<id>/` |
| Person | Everything | The merge decision |

The loop:
1. The author writes the scenario and runs `dsz verify` until it passes.
2. The loop runs `dsz verify` itself. If it passes, a fresh reviewer gives a verdict.
3. The author gets both outputs and improves the scenario, or discards it and starts a new one.
4. It stops on a passed verify plus a `pass` verdict, or after 3 rounds.
5. A passed scenario goes to human review.

Why a sandbox:
- The agents cannot copy or tune to other scenarios, the platform code or this document.
- The agents cannot write code. A missing capability becomes a capability request in `DESIGN.md`.
- One source per subject: the task spec holds the rules, `FORMAT.md` the definition format and the platform limits, and `dsz vocab` the vocabulary, generated from the registries.

**Verifier.** `dsz verify <dir> [--seeds N] [--json PATH]`. Exit codes: 0 pass, 1 fail, 2 verifier error.

| Built | Not built yet |
|---|---|
| S1 parse; S2 compile, ID and h_min rules, references on every pair, work due within the horizon (CR14); S3 kind-A checks on the `claims` block (CR1, CR2, CR5, CR6, MR1–MR3, C1, R1, P1–P4 coverage) and on the texts (CR15; CR5 notes); S4 V1 with the generic oracle and its derived controls, and OC2 | S4 H1, M1, R1, C1; S5 (E1); the hedge library (CR8); the `recipe:` block |

S4 uses the generic oracle (`dsz.certify.oracle`) unless the scenario has its own `oracle.py`. Its controls are `noop`, `hidden_state_blind`, `never_recover` and `memoryless`, each the oracle with one part swapped.

Open items:
- the hedge library (CR8) and the `recipe:` block;
- a sensing belief for the oracle (CR10: it now reads ground truth);
- the H1, M1, R1 and C1 checks;
- E1 measurement and the reference agents;
- frozen thresholds and seed list;
- the CI path check for scenario pull requests.

## 6. Interface

- **Split process.** The environment runs as a server in a pinned container (assets mounted as a volume; they are 23 GB). API: `reset(scenario, seed, horizon)`, `observe()`, `step(action)`, `close()`. The environment is also available as a Gymnasium env for LeRobot tooling.
- **The environment and the model are separate (principle 8).**
  - The env container holds no model code and no model dependencies.
  - The wire API (`dsz.api`) is the only contract.
  - Adapters live in a separate client package (`clients/dsz_client`) that runs anywhere and never imports env internals. There is one adapter per model type: VLA / LeRobot policy, VLM with harness, agent as policy, world action model (WAM). An adapter converts format only, never content.
  - The oracle and the negative controls are evaluator-side, so they run in-process through `core.Policy`. Models always connect through the API.
- **The task input is a goal, never a step list.** `TaskBrief.objective` states the goal. Work and facts arrive on channels. Every model type in a track gets the same input.
  - RoboCasa instead passes each policy one fixed step-list instruction (`ep_meta["lang"]`, e.g. "Pick the mug from the cabinet, place it under the coffee machine dispenser, and press the start button.").
  - At multi-day horizons a step list gives away what we measure: what to do, in what order and when.
- **Two tracks, one per action space.** They are scored separately and never merged. One verifier is behind both.
  - **Skill level:** the policy decomposes the goal and calls `navigate_to`, `open/close`, `pick`, `place`, `start_process(process, fixture)`, `look`, `wait`, `order`, `say`. Each motor skill call matches one RoboCasa atomic task, the vocabulary RoboCasa uses for its subtask labels (`robocasa/utils/subtask_labeling/subtask_bank.py`). `look`, `wait`, `order` and `say` are not motor skills.
  - **Low level:** the native 12-dim RoboCasa control at 20 Hz. A flat VLA or WAM runs here. Failing a full scenario is a valid result, not a design flaw.
- **Skill backends.** Each motor skill has two interchangeable backends: **scripted** (IK motion planning) and **learned** (a policy per atomic task, such as a VLA). Both run in the simulator and can fail. Nothing teleports.
- **Grounding.** The agent can name fixtures. For objects it picks an index from a detection list built from the current view only (the default) or gives a pixel point (a switch). There are no global object IDs.
- **Skill feedback comes from sensors only.** Skills return gripper width, contact and a post-action image. They never return a success flag.
- **Observation.** Three RGB views at 256², rendered only when the agent makes a decision; proprioception; the clock; channel messages. The harness memory policy is fixed and logged per run.

## 7. Instance certification (any scenario, per seed and horizon)

Every instance must pass the predicates H1, M1, R1, C1, V1 and E1. `LONG_HORIZON_TASK_SPEC.md` section 2 defines them. The thresholds are set from pilot runs, then frozen.

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
- recovery-aware vs. failure-blind (R1);
- scripted vs. learned skill backend (section 6): the gap isolates motor failure from planning failure;
- own plan vs. oracle plan: at each decision the evaluator gives the policy the oracle's next step for the current state. A large gain means planning was the bottleneck; no gain means execution was.

The symbolic and oracle-plan ablations give the policy evaluator-derived data, so they are diagnostics only (principle 6).

## 9. Project structure

```
day_shift_zero/
  pyproject.toml
  docker/                 # pinned images (arm64 and amd64); assets mounted, not baked in
  configs/                # run configs; thresholds unset until pilots
  scenarios/              # task definitions only, no platform code
    cloud_kitchen/        # scenario.yaml, DESIGN.md, optional oracle.py
    wedding_cake/
  src/dsz/
    core/                 # interfaces only: SimBackend, Scenario, Policy, ActionSpace, Clock, RngStreams
    world/                # semantic world model: items, containers, fixtures, processes, capability manifest
    dynamics/             # the six modules
    actors/               # actor types and channels
    events/               # event types and engine
    scenario/             # loader, compiler (checks against the manifest), generator runtime
    certify/              # verifier (`dsz verify`), oracle parts, instance checks (section 7)
    skills/               # one class per skill (Command pattern) + registry
    sim/
      robocasa/           # embodied backend: pinned scene, object pool, render-on-decision
      symbolic/           # symbolic backend (the E1 comparison)
    api/                  # wire schemas + serialization: the only surface clients see
    env/                  # Gymnasium env and env server (composition root)
    eval/                 # metrics, ablation runner, negative-control policies
    trace/                # trace writer and failure labeler
  tests/
authoring/                # scenario loop: agent briefs, sandbox guard, loop script
clients/
  dsz_client/             # API client + model adapters (section 6)
spike/                    # throwaway experiments, never imported by src/
```

**Patterns and dependency rules:** `CLAUDE.md`, engineering rules 1–2. Two rules specific to this layout:
- The event bus feeds the trace writer and the metrics.
- `world/` knows nothing about MuJoCo.

## 10. Two-day ship scope

| In | Out (later) |
|---|---|
| Platform with the six modules (1, 2, 4, 5 complete; 3, 6 minimal) and a capability manifest | VLA runs (the low-level space is exposed but not evaluated) |
| **Cloud kitchen** scenario: symbolic curves for N = 1 to 6+, embodied for N = 1 to about 3 | Threshold calibration and frozen seeds |
| **Wedding cake** scenario on the symbolic backend, to prove the platform really is decoupled | Level 1 proposer loop (LLM-written scenarios) |
| Oracle, negative controls, determinism test, trace labels | Rooms beyond the kitchen |
| Scripted skill backend | Learned skill backend and the oracle-plan ablation |

Every number in the ship is labeled **pilot, not a benchmark result**. A separate reviewer verifies the build.

## 11. Open questions

1. What are the adapter formats for WAM and RAX?
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
| Physical vs. flag-based cooking | Flag-based, from the code (not run): stove flames are a color toggle driven by knob angle; toaster and oven state is read from joint positions | See section 3 |

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
