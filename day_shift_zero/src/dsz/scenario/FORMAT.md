# Scenario format

A scenario is a folder with two files:

| File | Contents |
|---|---|
| `scenario.yaml` | The definition, including the `claims` (this file) |
| `DESIGN.md` | The design, and why each claim holds (the task spec defines what a claim must meet) |

`dsz verify <folder>` checks the folder. `VOCABULARY.md` (`dsz vocab`) lists every name you can use.

## Definition

```yaml
id: deli_lunches                      # lowercase snake_case, unique
description: One line for people.     # optional
objective: >                          # the goal, told to the robot at the start
  Pack and dispatch lunch boxes on time for three days. Keep cheese in the fridge.
horizon: {type: continuous, days: 3, min_days: 2}   # type: continuous | deadline
fixtures:                             # fixture id -> fixture kind
  fridge: fridge
  counter: counter
  cupboard: cabinet
  inbox: delivery_shelf
  dispatch: dispatch_shelf
modules: {spoilage: {}}               # dynamics modules and their params
actors:                               # role, name, then the role's params
  - {role: supplier, name: acme, fixture: inbox, lead_time_days: [1, 2]}
generator:
  name: template
  params: {...}                       # see "Generator"
success:
  criteria:                           # name -> {params?, weight?, required?}
    work_completion: {params: {min_on_time: 1.0}}
    no_violations: {}
    waste: {required: false, weight: 0.5}
claims: [...]                         # see "Claims"
```

| Key | Meaning |
|---|---|
| `horizon.days` | Longest certified horizon, h_max |
| `horizon.min_days` | Shortest certified horizon, h_min (default: `days`). `dsz verify` runs every h from `min_days` to `days` |
| `success.criteria` | Binary pass: every `required` criterion passes. Graded score: the weighted mean. Set the parameters once |

Do not add `policies` or `plugins`. The platform supplies the oracle and the controls.

## Generator

The `template` generator builds every instance from these parameters. All are optional.

```yaml
initial:                              # items in the kitchen at the start
  - {type: cheese, count: 4, at: fridge}
  - {type: butter, count: 2, at: {one_of: [fridge, cupboard]}}   # a choice: see "Choices"
pool: {cheese: 6}                     # parked stock for supplier orders and deliveries
subjects: [c01, c02]                  # who work can be for; each work item draws one
facts:                                # messages stated once, never repeated
  - id: c01_dairy
    at: {day: 0, minute: 500}         # day is zero-based; minute of the day
    text: "c01 cannot eat dairy."
    subject: c01                      # optional
    constraint: {exclude_allergens: [dairy]}   # optional: hidden constraint on later work
    channel: manager                  # optional (default manager)
    sender: manager                   # optional (default manager)
work:
  - kind: order
    per_day: [3, 6]                   # how many per day (inclusive range)
    window: [600, 1200]               # release minute of the day (inclusive range)
    lead: [45, 90]                    # minutes from release to deadline
    grace: 0                          # optional minutes after the deadline before the work expires
    collect: true                     # optional: a courier removes the delivered item
    channel: tickets                  # optional (default tickets)
    sender: front_desk                # optional (default system)
    variants:                         # one is drawn per work item
      - deliver: {item_type: meal_box, stages: [packed], at: dispatch}
        ticket: "Order {work_id} for {subject} by {due}."
events:
  - {kind: delivery, at: {day: 1, minute: 480}, payload: {fixture: inbox, items: [cheese_005]}}  # fixed time
  - {kind: relocate, id: cheese_moved, per_day: [0, 1], window: [0, 1440],                     # random time
     payload: {item_type: cheese, to: {one_of: [counter, cupboard]}}}                           # and place
```

**Item ids** are `<type>_<nnn>`, numbered per type: initial items in list order, then pool items. With the example above, `cheese_001`–`cheese_004` start in the fridge, and `cheese_005`–`cheese_010` are parked.

**Work.** Work ids are `<kind>-d<day>-<nn>` (day is one-based). A work item is done when an item of `item_type` with every stage in `stages` is at `at`. It expires `grace` minutes after its deadline. `exclude_allergens` in `deliver` forbids allergens. A delivery that breaks it still completes the work, and it records a violation. Ticket placeholders: `{work_id}`, `{subject}`, `{due}` (HH:MM).

**Hidden constraints.** A fact with `subject` and `constraint` adds the constraint to that subject's work that is released after the fact is revealed. The ticket does not repeat it.

**Events.** An event has `kind`, `payload` and either `at` (fixed) or `per_day` plus `window` (random). Give it an `id` if a claim names it. `observable: true` labels an event as seen for the checks; it does not tell the robot anything (use a fact for that). Payloads are listed per kind in `VOCABULARY.md`.

**Choices.** Write `{one_of: [a, b, ...]}` in place of an initial item's `at`, or of any event payload value. Each seed draws one candidate. Use a choice when a fixed rule could stand in for looking or remembering ("the batch is always in fridge_a"): a fixed rule is a hedge (CR8). One choice places every item of an `initial` entry. A choice never changes the other random draws.

**Randomness** is drawn per template and per day. Day *d* is the same for every horizon ≥ *d*.

## Claims

Each claim states one difficulty. `dsz verify` checks the rules it can from the files (stage S3). `DESIGN.md` explains why each claim holds.

```yaml
claims:
  - id: M1
    property: P2                      # P1 | P2 | P3 | P4
    mechanism: hidden_state           # facts | hidden_state | lead_time | resources | drift | compounding
    consequence: {object: cheese, place: cupboard, action: find}   # CR2
    memory: S                         # P2 only: S | D | I | T (MR1)
    content: where                    # P2 only: where | which | state | done (MR2)
    hidden: [cupboard, counter]       # candidate places the robot must check (CR6)
    fact: c01_dairy                   # optional: the fact the claim uses
  - id: C1
    property: P3
    mechanism: drift
    event: cheese_moved               # P3 only: the event's id (C1, CR5)
    consequence: {object: cheese, place: counter, action: recover}
  - id: R1
    property: P4
    mechanism: drift
    recovery: recoverable             # P4 only: recoverable | irrecoverable (R1)
    consequence: {object: cheese, place: counter, action: recover}
```

| Field | Rule that `dsz verify` checks |
|---|---|
| `property`, `mechanism` | CR1: known values. Each of P1–P4 has a claim. P4 has a recoverable and an irrecoverable claim |
| `consequence` | CR2: `object` is an item type in the scenario, `place` a fixture, `action` one of find, tell_apart, open, check, carry, unload, recover |
| `memory`, `content` | MR1, MR2. The claim's `fact` must not state a time, duration or count |
| `hidden` | CR6: at least 2 fixtures, none named in the objective, a fact or a ticket. Needed for `hidden_state` and for memory class T (MR3) |
| `event` | C1, CR5: the event is not `observable`, and no text states its what, where and when |

## Platform limits

These limits apply now. Do not claim a difficulty that they block. List what you need under capability requests in `DESIGN.md`.

| Limit | Blocks |
|---|---|
| The generic oracle never orders from a supplier | Scenarios whose stock must be reordered |
| The generic oracle runs each process in one fixture (of the right kind, with the fewest items at the start), stores each item type where it starts, and prepares work at most 24 h ahead | Scenarios that need another choice to pass |
| Work items cannot require contents (for example "contains bread"). Messages can only forbid | Facts that select a filling |
| Symbolic detections show the item type only. Condition, spoilage and temperature are not visible | Cues for spoilage and faults (CR4, CR11) |
| `door_left_open` does not warm a fridge | Spoilage from an open door |
| Grasp failure rates cannot be set in a definition | Misgrasp recovery (CR12) |
| Work templates cannot have their own subject lists | Per-template subjects |
| The pass gives a delivered item to the released work item with the earliest deadline, not to its subject | Per-subject checks of delivered items |
| Supplier orders take the lowest parked pool id, including ids that a scheduled delivery names | Mixing supplier orders and scheduled deliveries (CR11) |
| A delivery to a full fixture can crash the run (reported, not reproduced) | Deliveries to a full fixture |
