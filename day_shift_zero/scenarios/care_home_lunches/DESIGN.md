# care_home_lunches

## Summary

The robot runs the lunch service for the east wing of a care home for four days. Each day it cooks one hot lunch of marinated chicken and packs two or three sandwich boxes. Stock arrives and moves while the robot does not watch. A diet instruction from day 2 changes which stock the robot must fetch.

Activity family: institutional catering. Activity: daily ward meals with a diet instruction.

## Revision log

| Round | Decision | Reason |
|---|---|---|
| 1 | Improve | The reviewer accepted the core (marinade lead time, dock spoilage, stove pull-off, pack-counter sweep). The faults were specific claims and missing feasibility evidence. None of them breaks section 3 |

Round 1 changes, by reviewer finding:

| # | Finding | Change |
|---|---|---|
| 1 | Fridge fault has no sensor cue | Removed. Replaced by an observable drift: a co-worker leaves the only day-3 chicken on the pack counter |
| 2 | Diet facts only forbid; several rows did not bind | Removed nut spread, the dairy and nut facts, the cheese and nut-spread relocations and the night consume. One fact stays: no gluten for the east wing. It binds: the default filling (bread) becomes forbidden, so the robot must fetch cheese from a fridge instead |
| 3 | Chicken chain not shown feasible | Standing deliveries moved to day 2 and day 3, so no freezing is needed. Day-by-day chain below. A scripted oracle in `oracle.py` passes on seeds 0–19 |
| 4 | Seed-dependent claims | One subject (`east_wing`), so every box after the fact is constrained on every seed. The pack-counter trap fires at 09:50 on day 2, before any box ticket of that day, so it holds on every seed |
| 5 | Raw and marinated chicken look the same | `fridge_back` is the marinade fridge. The marinated piece is the chicken in `fridge_back`. Memory of identity is no longer claimed |
| 6 | Standing-delivery fact is weak for M1 | No longer an M1 claim. Relabelled as a scheduled exogenous delivery with a handling deadline |
| 7 | Misgrasp cannot happen in symbolic runs | Marked "not exercised by S4" |
| 8 | No oracle | Added `care_home_oracle` and two scenario controls in `oracle.py` |
| 9 | Order ids and dock overflow | The whole pool is 10 items, the dock capacity, so the dock cannot overflow. Orders beyond the free pool take ids from later standing deliveries (documented below) |
| 10 | Constraint attaches to hot_lunch silently | Both tickets now name the east wing. Chicken has no gluten, so the constraint never changes the hot lunch |

## Blueprint

### Objective and horizon

| Field | Value |
|---|---|
| Horizon | `continuous`, 4 days (day 1 to day 4; the definition uses zero-based days). Certify only horizons of 3 or 4 days (see "Horizon limits") |
| Work per day | 1 `hot_lunch` and 2–3 `sandwich_box`. 13–16 items in total for seeds 0–2 |
| Hot lunch | `chicken_breast` with stages `marinated` and `cooked`, on `pass`. Ticket at 09:00–10:00, due 2.5–3.5 h later |
| Sandwich box | `meal_box` with stage `packed`, on `pass`. Ticket at 10:00–12:00, due 1.5–2.5 h later |
| Success | `work_completion` with `min_on_time: 1.0`, `no_violations` (both required); `waste` (graded, weight 0.5) |

### Fixtures, items and actors

| Kind | Ids |
|---|---|
| Fixtures | `fridge_main` (stock), `fridge_back` (marinade), `pantry` (cabinet), `pack_counter`, `stove`, `dock` (delivery_shelf), `pass` (dispatch_shelf), `bin` (trash) |
| Initial items | 4 `bread` in `pantry`; 9 `cheese` and 2 `chicken_breast` in `fridge_main` |
| Standing deliveries | Day 2, 08:00: `chicken_breast_006`, `cheese_012`. Day 3, 08:00: `chicken_breast_005`, `bread_007` |
| Free pool (orderable) | `chicken_breast_003..004`, `cheese_010..011`, `bread_005..006` |
| Actor | `farm_coop` (supplier): delivers to `dock` at 08:00 the next day |
| Not stocked | `plate`, `tray`, `meal_box`, `nut_spread`. The only gluten-free fillings are cheese and the scarce chicken |

Order ids: the supplier takes the lowest parked id that no open order holds. After two chicken orders, a third order takes `chicken_breast_005`. The day-3 standing delivery then arrives without it. In effect, the free pool is the limit.

### Dependency graph (P1)

```
day 2/3 08:00 delivery ──► dock ──► fridge_main (chicken spoils after 2 h at room temperature)
fridge_main ──► fridge_back ──► start marinate (8 h) ──► stove: power on, place, cook 20 min
            ──► pick within 10 min ──► power off ──► pass                       (hot_lunch)
pantry bread (day 1) or fridge_main cheese (day 2+) ──► pack_counter (must hold nothing else)
            ──► start pack (5 min) ──► pick box ──► pass                           (sandwich_box)
```

Day-by-day oracle chain (as `care_home_oracle` runs it):

| Day | Hot lunch chicken | Marinade start | Sandwich boxes |
|---|---|---|---|
| 1 | `chicken_breast_001` (initial) | 00:00 day 1 (ticket at 09:00–10:00; marinade done 08:00) | Bread from the pantry |
| 2 | `chicken_breast_002` (initial, 36 h chilled, below the 48 h limit) | ~17:00 day 1, when the next ticket is ≤ 16 h away | Cheese from `fridge_main` (fact at 07:30). First move `chicken_breast_006` from the pack counter back to `fridge_main` |
| 3 | `chicken_breast_006` (day-2 delivery, stored within minutes) | ~17:00 day 2 | Cheese |
| 4 | `chicken_breast_005` (day-3 delivery) | ~17:00 day 3 | Cheese |

Shelf-life check: raw chicken lasts 48 h chilled and 2 h at room temperature (vocabulary defaults). Each piece is used within 36 h of arrival, so no freezing and no stock arithmetic are needed. The rule is greedy: each evening, marinate the freshest raw chicken in `fridge_main`.

### Facts and state that only sensing reveals (P2)

| Id | Revealed | Text (short) | Needed later |
|---|---|---|---|
| `standing_delivery` | day 1, 07:00 | Deliveries come at 08:00 on day 2 and day 3. Nobody tells you | Information only. Not an M1 claim |
| `east_wing_gluten` | day 2, 07:30 | The east wing is now a coeliac ward: no gluten | Every box released from day 2, 10:00 to day 4, 12:00. That is 2.5 h to 52 h after the reveal. Hidden constraint `exclude_allergens: [gluten]` |

State that only sensing reveals:
- Items behind closed doors (`fridge_main`, `fridge_back`, `pantry`) are visible only after the robot opens the door.
- What lies on `pack_counter` or the `dock` is visible only when the robot stands there.

### Exogenous events (P3)

| When | Event | Observed | Effect on later work |
|---|---|---|---|
| Day 2, 08:00 | `delivery` chicken + cheese to `dock` | No (fact gives the time) | Chicken must reach a fridge within about 2 h, or day 3 has no hot lunch |
| Day 2, 09:50 | `relocate` `chicken_breast_006` from `fridge_main` to `pack_counter` | No | The only chicken for day 3 now warms on the pack counter. The next pack sweeps it into a box |
| Day 3, 08:00 | `delivery` chicken + bread to `dock` | No | Same as day 2, for the day-4 hot lunch |

The relocation is a no-op if the robot stored the chicken somewhere other than `fridge_main`. The objective tells the robot to keep raw chicken there.

### Failure modes (P4)

| Failure | Detected by | Recoverable? | Recovery |
|---|---|---|---|
| Chicken on the pack counter (relocation) | Detections when the robot stands at the counter to pack | Yes, if seen before packing and within about 1.5 h | Carry it back to `fridge_main` |
| That chicken packed into a box, or spoiled | — | No. An order arrives day 3 08:00, too late for an 8 h marinade before the day-3 deadline | None |
| Delivered chicken left on the dock | Detections at the dock | Yes within about 2 h; no after | Move it to `fridge_main` |
| Cook overrun (> 10 min after done) | Elapsed time | No for that piece and that day | None without a spare marinated piece |
| Marinade not started the evening before | — | No for that day | None |
| Gluten box packed (bread on the counter, or bread fetched) | Detections at the counter before packing | Yes before it goes on `pass`: bin it and repack. No after collection | Bin and repack |
| Misgrasp or blocked place | Gripper width, skill note | Yes | Retry. **Not exercised by S4**: the symbolic backend has no grasp failures unless `grasp_fail_p` is set, and the definition cannot set it |

## Difficulty claims (stage S3)

| Property (P1–P4) | Mechanism | Physical consequence |
|---|---|---|
| P1 | `lead_time` (marinate 8 h) with `hidden_state` | Chicken not placed in `fridge_back` and started the evening before cannot be cooked by the next day's deadline |
| P1 | `lead_time` (cook) with being in one place | Cooked chicken left on the stove more than 10 min is damaged. The robot must be at the stove then, not at the dock or the pass |
| P1 | `compounding` (pack combines the whole counter) | Every item on `pack_counter` goes into the box. The counter must hold only the filling |
| P2 | `facts` with `hidden_state` | After the fact, the robot must fetch cheese from the closed `fridge_main` instead of bread from the pantry. The ticket never repeats the rule |
| P3 | `drift` (`relocate`) with `compounding` | The only day-3 chicken appears on the pack counter. If the robot packs without looking, the chicken goes into a box and day 3 has no hot lunch |
| P3 | `resources` (scheduled delivery, spoilage) | Chicken that waits on the dock for more than about 2 h spoils. It is the only chicken for the next day |
| P4 | `compounding` (irreversible spoilage, damage, combining) | A packed, spoiled or overcooked chicken cannot be repaired. The supplier lead time is too long to replace it |
| P4 | Skills, sensor-only feedback | The robot learns about the counter and the dock only from detections at those fixtures. It never gets a success flag |

### Self-check against section 3

| Check | Result |
|---|---|
| Durations, power levels | Given in the objective (8 h, 20 min, 10 min). The robot still places, switches and unloads by hand |
| Quantities | Trivial: one hot lunch, one box per ticket, one filling per box |
| Schedule | Greedy rule works (see the day-by-day chain). Box tickets have 1.5 h or more of slack. Hot lunch tickets have 2.5 h or more |
| Stock | Chicken is scarce but needs no planning: one piece per day, freshest first. Chicken-only boxes are not a way out: 4 hot lunches use 4 of the 6 obtainable pieces, and boxes on days 2–4 need 6–9 fillings |
| Pricing, cost | Not used |
| Ticket text | Plain requests. No diet information |

## Horizon limits

Certification is per seed and horizon. This scenario needs at least 3 days:
- The diet fact comes on day 2. At 1 day, M1 has no fact.
- The pack-counter trap costs the day-3 hot lunch. At 2 days, the no-recovery control passes (seen in the runs below).

## Verification

The claims are also in `scenario.yaml`. `dsz verify scenarios/care_home_lunches` (2026-11-22):

- S1 and S2 pass.
- S3 fails: claim M1 hides the cheese in `fridge_main` or the bread in `pantry`, and the objective names both (CR6, MR3). This matches the spec's own example: "No gluten, then fetch cheese from the fridge that the objective names" does not count. P2 has no valid claim.
- S4 on its own (the scenario's `care_home_oracle`): passes for horizons 3 and 4.
- With the generic oracle instead, `never_recover` passes on seeds 0–4. The generic oracle carries the delivered chicken into `fridge_back` at once, so the 09:50 move finds nothing. Claim C1 depends on the robot waiting to marinate: a hedge (CR8).

Earlier hand run on the symbolic backend, before `dsz verify` existed (pilot, not a benchmark result):

| Horizon | Seeds | Oracle | `noop` | `care_home_ignore_facts` | `care_home_no_recovery` |
|---|---|---|---|---|---|
| 4 days | 0–19 | pass (20/20) | fail (20/20) | fail (20/20): gluten violations | fail (20/20): day-3 hot lunch expires |
| 3 days | 0–19 | pass (20/20) | fail (20/20) | fail (20/20) | fail (20/20) |
| 2 days | 0–2 | pass | fail | fail | **pass** |

- Oracle length L: 394–440 skill calls at 4 days (seeds 0–19). Graded score 0.93–0.97. The only waste is 1–2 bread loaves that spoil unused on day 4.
- Two runs of seeds 0–2 gave identical output.
- S5 (E1 gap) is not available.

## Capability requests

1. **Content predicate for work.** `deliver` cannot require a component (for example `contains: [cheese]`). The diet fact can only forbid. This scenario makes it bind because bread is the default filling and other gluten-free stock is scarce. A `contains` field would make facts bind directly.
2. **Sensing for spoilage in `tau_sym`.** Symbolic detections have only a type label. A robot cannot see that a chicken on the counter has started to warm, or that a fridge has failed. This removed the fridge-fault idea.
3. **Door left open warms a fridge.** `door_left_open` changes only visibility. `effective_zone()` ignores the door.
4. **Grasp failure from the definition.** `grasp_fail_p` and `break_on_fail_p` cannot be set from `scenario.yaml`. The misgrasp recovery branch is therefore not exercised.
5. **Per-template subjects.** The template draws subjects from one global list for all work templates. To pin a constrained resident per day, this scenario uses a single subject.
6. **Platform bug: delivery to a full fixture crashes the run.** `DeliveryEvent.apply` does not catch the `ValueError` from a full fixture. `RelocateEvent` does. This scenario avoids it by keeping the whole pool at the dock capacity.
7. **The pass assigns boxes by deadline.** `WorkTracker` gives a box on the pass to the released ticket with the earliest deadline, not to the resident it was packed for. With several residents and different diets, a correct box can complete the wrong ticket. One subject avoids this here.

## Notes

- The oracle and the controls read the world and the instance (they are evaluator-side). They act only through skills and pick by detection index.
- The `marinate` process starts on everything in `fridge_back`. Cheese placed there would also be "marinated" and would hold the process: removing it before the end aborts the chicken's marinade. The objective tells the robot to keep only chicken there.
