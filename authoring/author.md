# Scenario author

You write one Day Shift Zero scenario. Your working folder holds everything you can use:

| File | Contents |
|---|---|
| `SPEC.md` | What a valid scenario is. The rules (P, MR, CR, OC) |
| `FORMAT.md` | How to write `scenario.yaml`, and the platform limits |
| `VOCABULARY.md` | Every fixture, item, process, event, module, actor, criterion and skill |
| `scenario/` | Your output. You can write only here |

## Output

| File | Contents |
|---|---|
| `scenario/scenario.yaml` | The definition, with its `claims` (`FORMAT.md`) |
| `scenario/DESIGN.md` | The design (below) |

Write no other file. You cannot write code. If the platform lacks something, use what exists, or add a capability request.

## Steps

1. Read `SPEC.md`, `FORMAT.md` and `VOCABULARY.md`.
2. Choose an idea. Check it against `SPEC.md` sections 3 and 4 and the platform limits before you write.
3. Write `DESIGN.md`. Remove each claim that breaks a rule in `SPEC.md`.
4. Write `scenario.yaml` with its `claims`. Set the criterion parameters once.
5. Run `dsz verify scenario`. Fix each problem and run it again until it passes. This is the only command you can run. S4 runs the platform's generic oracle and its controls. If the oracle fails, the scenario needs scheduling or search: change it. If a control passes, a claimed difficulty is missing: change the scenario, not the criteria.
6. Give the report (below).

## DESIGN.md

Write three sections:

1. **Blueprint.** Objective; horizon (`min_days` to `days`); fixtures, items and actors; dependency graph; messages; exogenous events; failure modes, with one recoverable and one irrecoverable.
2. **Claims.** One short paragraph per claim ID in `scenario.yaml`: the cue, why the claim holds on every seed and horizon, and the hedges you considered (CR8). Do not repeat the claim's fields.
3. **Capability requests.** What you needed that the platform does not have.

## Rules

- Use a lowercase snake_case `id` that is not taken. The first prompt lists the taken IDs.
- Write tickets and messages as plain requests. Give no hidden constraint and no sequence of skills (CR15).
- Do not change a criterion parameter to make a run pass (`SPEC.md` section 6).
- Do not write an oracle, a recipe or a control.

## Feedback

After each report you can get the verify output and a reviewer verdict. Decide one:

- **improve:** fix the findings in place;
- **discard:** the main idea breaks `SPEC.md` section 3 or 4. Replace the folder contents with a new scenario and a new `id`.

## Report

- the scenario in two sentences;
- the claim IDs that support each of P1–P5;
- the last `dsz verify` result;
- capability requests;
- anything in `SPEC.md`, `FORMAT.md` or `VOCABULARY.md` that was unclear or missing;
- after feedback: improve or discard, and why.
