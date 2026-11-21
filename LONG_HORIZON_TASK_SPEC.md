# Long-Horizon Task Spec

Version 1.2, 2026-11-21. This file defines a valid Day Shift Zero task. If this file does not allow something, it is not allowed. Your instructions are in `scenarios/AGENTS.md`.

**How to use this file**

| You are | Read |
|---|---|
| Author | All sections |
| Reviewer | All sections. Give a verdict (pass, improve or discard). Cite a rule ID (P, MR, CR) in each finding |

**Contents**
1. Terms
2. Task definition (P1–P5)
3. Sources of difficulty
4. Memory (MR1–MR5)
5. Claim rules (CR1–CR14)
6. Oracle, controls and criteria
7. Acceptance stages (S1–S6)
8. Platform limits

## 1. Terms

Each term has one meaning in this file.

| Term | Meaning |
|---|---|
| Scenario | `scenario.yaml`, optional `plugins.py` and `DESIGN.md` |
| Instance | The output of one seed and one horizon. It holds all random choices |
| Horizon h | Number of simulated days. Day d is the same for every h ≥ d |
| Certified set | Each pair (seed, h) with the seed in the frozen list Σ and h_min ≤ h ≤ h_max. The scenario sets h_min ≥ 2 |
| Work item | One unit of work with a deliver predicate and a deadline |
| Slack | Time from the earliest start of a work item to its deadline, minus the oracle's time to do it |
| State s_t | All item locations, item conditions, fixture states and batch identities at time t |
| Observation o_t | The current view through open doors only, detections without global IDs, proprioception, clock and messages |
| Embodied run | The policy gets o_t |
| Symbolic run | The same instance, skills and failure rates. The policy gets s_t instead of the view |
| Exogenous event | A change that the robot does not cause: relocate, consume, delivery, fault, door left open, goal change |
| Cue | A change in o_t that shows an event or a failure. A clock time is not a cue |
| Physical consequence | An object, a place and a body action: find, tell apart, open, check, carry, unload or recover |
| Point of no return | The last time at which an action can still save the affected work item |
| Claim | One row in `DESIGN.md` that states one difficulty |
| Hedge | A fixed plan, chosen before the run, that avoids a difficulty. Examples: never use a fixture; over-order; check a place at a fixed time each day |

## 2. Task definition

A long-horizon embodied task makes one robot do many dependent actions over at least two days, in one kitchen that changes on its own, with no resets. All difficulty comes from the body.

A scenario must have all five properties. Each predicate must be true for **every** pair in the certified set.

| ID | Property | Predicate (must be true) |
|---|---|---|
| P1 | Dependency chain | **H1:** the oracle makes ≥ θ_L skill calls. The longest chain of calls where each call needs the effect of the one before has length ≥ θ_D. One link of that chain crosses a day boundary |
| P2 | Non-Markovian | **M1:** one memory requirement meets MR1–MR5 (section 4). The robot needs it ≥ k skill calls after it gets it |
| P3 | Changing world | **C1:** one exogenous event (a) is not seen when it occurs, (b) meets CR5, (c) causes a work item to fail for a policy that uses the state before the event, and (d) meets CR4 |
| P4 | Error recovery | **R1:** one reachable failure is recoverable and one is irrecoverable. Recoverable: a cue occurs and recovery fits before the point of no return. Irrecoverable: no policy can save the work item after it occurs |
| P5 | Embodiment | **E1:** (a) symbolic score − embodied score ≥ θ_E for the reference agents; (b) the embodied memory gap ≥ θ_M (section 4); (c) each claim appears in the failure attribution of embodied runs |
| — | Validity | **V1:** the oracle passes. Each control in section 6 fails |

- The thresholds θ_L, θ_D, k, θ_E, θ_M, θ_H and the seed list Σ come from pilot runs. Then they are frozen. Until then, label each number "pilot, not a benchmark result".
- Reject a scenario that cannot produce certified instances.

## 3. Sources of difficulty

**Rule.** Each difficulty has a physical consequence. Dependencies, memory, change and failure do not count by themselves. A text agent can also chain steps and remember facts.

**Allowed**

| Source | Examples |
|---|---|
| Finding things | Items behind closed doors; identical containers; batch identity; unseen relocations |
| State that only sensing shows | A door left ajar; equipment wear; a spill; visible spoilage |
| Physical handling | Fragile items; stacking; space in a fridge or on a counter; reach |
| Grounding | Objects chosen only from detections in the current view |
| Recovery from physical failure | Misgrasps, drops and blocked placements, seen from gripper, contact and images |
| One body in one place | Travel time; work at different fixtures that competes for the robot (CR9) |
| Memory with a physical consequence | Section 4 |
| Lead time with handling | Start, check and unload a process by hand; store prep and find it again days later |

**Excluded.** A parameter can exist, but choosing it must not be the hard part.

| Excluded | Allowed form |
|---|---|
| Choosing temperatures, durations or power levels | The value is given. The robot still operates the fixture |
| Quantities, ratios, recipe arithmetic | Quantities are given or trivial |
| Schedule optimization, forecasting, stock planning | A greedy order succeeds (the generic oracle tests this, section 6) |
| Remembering times, durations, counts or shelf lives | Not used (MR2) |
| Pricing, margins, costs | Not used |
| Puzzles in ticket text | Tickets are plain requests |

## 4. Memory

A text agent can remember too. This section says which memory counts.

**Memory requirement.** A variable x is a memory requirement at time t when a correct action at t needs x, and x is not in the policy's input at t.

**Classes**

| Class | x is | Embodied run needs it | Symbolic run needs it |
|---|---|---|---|
| T, told | A message from an earlier time | Yes | Yes |
| S, seen | State the robot saw earlier and cannot see now | Yes | No |
| D, done | State that the robot's own earlier action set, and that it cannot see now | Yes | No |
| I, identity | Which of several identical items is which. No single view shows it | Yes | No |

Change detection compares an earlier view with the current view. It is class S or D.

**Look-again cost κ(x, t).** The time the robot needs to get x again: travel, opening doors, moving items, and searching all candidate places.

**Admissibility.** A memory requirement counts for predicate M1 only if all are true:

| ID | Rule |
|---|---|
| MR1 | It is class S, D or I, or it is class T and meets MR3 |
| MR2 | Its content is *where*, *which*, *what state* or *whether done*. It is never a time, a duration, a count or another number used in arithmetic |
| MR3 | Class T only: the message selects a target that the robot must find or tell apart by S, D or I memory or by search. No text that the robot gets names the target's place (CR6) |
| MR4 | κ(x, t) > slack of the work that needs x |
| MR5 | It occurs on every pair in the certified set |

**Embodied memory gap.** Run each version with full history and with only the last k inputs:
- G_E = embodied(full) − embodied(last k);
- G_S = symbolic(full) − symbolic(last k);
- the embodied memory gap is G_E − G_S.

**Examples**

| Requirement | Verdict |
|---|---|
| Which of two identical tubs holds the dairy-free batch | Counts (I) |
| Which of five closed cabinets holds the day-1 prep, if searching takes longer than the slack | Counts (S, D) |
| Whether the stove behind the closed oven door is still on | Counts (D) |
| "No gluten", then fetch cheese from the fridge that the objective names | Does not count (MR3) |
| "The delivery arrives at 08:00" | Does not count (MR2, MR3) |

## 5. Claim rules

Each claim must meet every rule. A claim that fails a rule counts for no predicate.

**Check kinds**

| Kind | Meaning |
|---|---|
| A | Schema: a check on the files only |
| B | Trace: a check on one run of the oracle |
| C | Counterfactual: compare runs that differ in one thing, with the same seeds |

| ID | Rule | Check |
|---|---|---|
| CR1 | One claim has one property (P1–P4). The label matches section 2 | A |
| CR2 | The claim names its physical consequence: object, place, action | A |
| CR3 | **Binding.** Remove the claimed mechanism. The oracle's physical actions or verdict must change on every certified pair. A fact that only forbids, where a plan can ignore it at equal cost, fails | C: oracle with and without the mechanism |
| CR4 | **Cue.** Each claimed change or failure gives a cue in each backend where the claim is certified. For a recoverable failure, the cue occurs before the point of no return. A timer is not a cue | B: the changed variable is visible to the oracle in that interval |
| CR5 | **Not announced.** A change is not P3 if a message states its what, where and when. A partial message, such as a time window, is allowed if the robot must still search or check | A: compare message payloads with the event |
| CR6 | **Named is not hidden.** A place named in the objective, brief, a ticket or a message is not hidden. Hidden state needs ≥ 2 candidate places or items that the robot cannot tell apart without looking or memory | A and B: names in text; count of candidates in the instance |
| CR7 | **Every seed.** The claim is true on every certified pair. Pin a random draw that can remove it | C: all certified pairs |
| CR8 | **No hedge.** No hedge gets the oracle's verdict with a graded score within θ_H of the oracle | C: run a fixed hedge library for the claim's kind |
| CR9 | **Competition for the body.** A "one place" claim shows two tasks at different fixtures in time windows that overlap, so that one of them misses its slack if the other goes first | B: windows and travel times in the instance |
| CR10 | **Recovery by sensing.** The oracle finds each recoverable failure through o_t, not through ground truth | B: the trace shows detection from an observation |
| CR11 | **Observable outcome.** Each condition that a criterion uses is observable, set by the robot (class D) or stated in a message. Nothing else changes an outcome without a cue (CR4) | A: map each criterion to its inputs |
| CR12 | **Exercised.** A mechanism that cannot occur in the S4 backend is marked "not exercised" and counts for no predicate | A: backend capability list |
| CR13 | **Not parametric.** The difficulty is not in the excluded table (section 3) | C: the greedy generic oracle passes; E1 |
| CR14 | **Every horizon.** The claim is true for each h from h_min to h_max | C: all horizons |

Until the verifier exists, the reviewer applies these checks by reading the files.

## 6. Oracle, controls and criteria

**Oracle**
- It runs on the evaluator side. It can read the instance and ground truth to plan.
- It finds recoverable failures only through o_t (CR10).
- It is deterministic. Its randomness comes from `RngStreams` only.

| Scenario | Oracle | Written by |
|---|---|---|
| Built-in plugins only | The generic oracle. It is greedy. For each work item it follows the stages back, finds the items, runs the processes, moves the items and replans after a failed skill | The platform, once for all scenarios |
| Has `plugins.py` | `scenarios/<id>/oracle.py` | A separate oracle agent, after the definition is final |

- Authors do not write an oracle or a control.
- If the generic oracle fails, the scenario needs scheduling. Reject it (section 3).

**Controls.** Each control is the oracle with one fixed change. All must fail.

| Control | Change | Tests |
|---|---|---|
| `noop` | Waits forever | V1 |
| `hidden_state_blind` | No ground truth about closed fixtures or unseen events | P2, P3 |
| `never_recover` | No replanning after a failure | P4 |
| `memoryless` | Keeps only the last k observations and messages | P2 |

**Criteria.** Set the criterion parameters in the definition before any run. Do not change a parameter because a control passed. A control that passes shows a missing difficulty. Fix the scenario.

## 7. Acceptance stages

Run the stages in order. Stop at the first stage that fails.

| Stage | Checks | By |
|---|---|---|
| S1 Parse | Structure | Verifier |
| S2 Compile | Plugins, parameters, capabilities, references in a 1-day probe, ID rules | Verifier |
| S3 Claims | CR1–CR14 and MR1–MR5, as far as the files show | Reviewer (later: the verifier, for kind A) |
| S4 Certify | H1, M1, R1, C1, V1 on the symbolic backend, every certified pair | Verifier |
| S5 Embodiment | E1 | Verifier |
| S6 Review | Definition, `DESIGN.md` and report | Person |

## 8. Platform limits

These limits block some claims now. Do not claim what they block.

| Limit | Blocks |
|---|---|
| Work items cannot require contents (for example "contains bread"). Messages can only forbid | Facts that select a filling |
| Symbolic detections show the item type only. Condition, spoilage and temperature are not visible | Cues for spoilage and faults (CR4, CR11) |
| `door_left_open` does not warm a fridge | Spoilage from an open door |
| `grasp_fail_p` and `break_on_fail_p` cannot be set in a definition | Misgrasp recovery (CR12) |
| Work templates cannot have their own subject lists | Per-template subjects |
| The pass gives a box to the earliest-deadline ticket, not to its subject | Per-subject box checks |
| Supplier orders take the lowest free pool ID, also IDs that a scheduled delivery needs | Mixing orders and scheduled deliveries (CR11) |
| `DeliveryEvent` can crash when the fixture is full (reported, not reproduced) | Deliveries to a full fixture |
| The import path for `plugins:` modules is not specified | Running plugins outside the repo root |

