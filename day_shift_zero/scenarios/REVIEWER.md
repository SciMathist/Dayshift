# Reviewing a Day Shift Zero scenario

You are a scenario reviewer. `LONG_HORIZON_TASK_SPEC.md` at the repository root defines a valid task. `AGENTS.md` in this folder gives the author's procedure. This file gives your procedure.

## 1. Input

You get:

- the path of one scenario folder, `day_shift_zero/scenarios/<id>/`;
- the author's report;
- the verify output (stages S1 and S2).

You do not change any file. You read and you give a verdict.

## 2. Steps

1. Read `LONG_HORIZON_TASK_SPEC.md`.
2. Read `day_shift_zero/src/dsz/scenario/README.md` for the definition format.
3. Read `scenario.yaml`, `DESIGN.md` and, if it exists, `plugins.py`.
4. Check that the folder holds only the files in `AGENTS.md` section 1.
5. Check stage S3: apply CR1–CR15 and MR1–MR5 as far as the files show.
6. Check P1–P5 (spec section 2). For each, find the claim that supports it.
7. Check the excluded sources (spec section 3) and the platform limits (spec section 8).
8. Compare the report with the files. Each statement in the report must agree with the files.
9. Give the verdict (section 4).

## 3. What to check

| Area | Check |
|---|---|
| Claims | Each claim row meets every CR rule. A claim that fails a rule supports no predicate |
| Binding (CR3) | Removing the mechanism changes the oracle's physical actions. A fact that only forbids does not count |
| Hidden state (CR5, CR6) | No text names the hidden place. Each hidden state has ≥ 2 candidates |
| Memory (MR1–MR5) | At least one requirement is class S, D or I, or T under MR3. Its content is never a number |
| Recovery (P4) | One recoverable and one irrecoverable failure. The recoverable one has a cue before the point of no return |
| Hedges (CR8) | Name each hedge you can find. A claim fails if a hedge reaches the oracle's verdict |
| Every pair (CR7, CR14) | The claim holds for every seed and every h from h_min to h_max |
| Goal only (CR15) | No ticket, message or objective states a sequence of skills |
| Platform limits | No claim depends on a blocked capability (spec section 8) |
| Criteria | Criterion parameters are set once in the definition |
| Folder rules | No oracle, no control, no change outside the folder |

Stages S4 and S5 do not exist yet. Do not fail a scenario because they did not run. Mark each check that needs them "not verified".

## 4. Verdict

Give one decision:

| Decision | When |
|---|---|
| `pass` | Verify passed. No finding has severity `blocker` or `major` |
| `improve` | The main idea is valid. The author can fix each finding in the folder |
| `discard` | The main idea breaks spec section 3 or 4, or no change can satisfy P1–P5 |

For each finding, give:

- `rule`: one rule ID (P, MR, CR, OC or S). Use `AGENTS` for a procedure rule;
- `severity`: `blocker`, `major` or `minor`;
- `location`: the file and the claim ID, key or line;
- `problem`: what is wrong, in one or two sentences;
- `fix`: one concrete change, or "discard" if no change fixes it.

## 5. Rules

- Cite a rule ID in each finding.
- Report only problems that the files show. Do not guess.
- Do not ask for a change that breaks another rule.
- Do not tune the scenario to an evaluated model.
- Do not write the scenario for the author. Give the fix in one sentence.
- Keep the summary to at most three sentences.
