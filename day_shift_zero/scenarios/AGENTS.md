# Writing a Day Shift Zero scenario

You are a scenario author. `LONG_HORIZON_TASK_SPEC.md` at the repository root defines a valid task. This file gives the procedure.

## 1. Output

One folder, `day_shift_zero/scenarios/<id>/`, with these files:

| File | Contents |
|---|---|
| `scenario.yaml` | The definition |
| `DESIGN.md` | The design (section 3) |
| `plugins.py` | Only if the built-ins cannot express a behaviour. Never an oracle or a control |

Do not create or change any other file.

## 2. Steps

1. Read `LONG_HORIZON_TASK_SPEC.md`.
2. Read `day_shift_zero/src/dsz/scenario/README.md` for the definition format and the `template` generator.
3. List the vocabulary that you can use:
   ```sh
   cd day_shift_zero && source .venv/bin/activate
   python -c "from dsz.scenario.compiler import platform_manifest as m; print(m())"
   ```
4. Choose an ID (section 5).
5. Write `DESIGN.md` (section 3).
6. Remove or rewrite each claim that breaks spec sections 3, 4 or 5.
7. Write `scenario.yaml`. Set the criterion parameters once (spec section 6).
8. Verify (section 4). Fix and verify again until it passes.

## 3. `DESIGN.md`

Write these five parts:

1. **Blueprint:** objective; h_min and h_max; fixtures, items and actors; dependency graph; messages; exogenous events; failures.
2. **Claims:** `| ID | Property | Mechanism | Physical consequence | Cue | Evidence for CR3, CR7, CR8 |`
3. **Memory:** `| x | Class | Acquired (when, how) | Needed (when, by which work) | κ vs. slack | Physical consequence |`
4. **Self-check:** one line for each of CR1–CR15.
5. **Capability requests:** what the platform cannot do yet (spec section 8, or a `MissingCapabilities` error).

## 4. Verify

`dsz verify` does not exist yet. Until it does, run parse and compile:

```sh
cd day_shift_zero && source .venv/bin/activate
python -c "from dsz.scenario.spec import load_spec; from dsz.scenario.compiler import compile_spec; \
compile_spec(load_spec('scenarios/<id>/scenario.yaml')); print('OK')"
```

- `SpecError` lists each structure or reference problem. Fix all of them.
- `MissingCapabilities` names what the platform does not have. Rewrite with the existing vocabulary. If you cannot, add it to the capability requests.

Stages S4 and S5 are not available yet. Say so in your report.

## 5. Rules

- **ID:** lowercase snake_case, the same as the folder name, and not used yet. `cloud_kitchen` and `wedding_cake` are reserved.
- Do not change `src/`, tests, other scenarios or any file outside your folder.
- Do not write an oracle or a control (spec section 6).
- Do not change a criterion parameter because a control passed (spec section 6).
- Write tickets as plain requests, with no hidden constraint.
- Do not tune the scenario to an evaluated model.
- Do not commit. A person reviews your folder.

## 6. Feedback

You can get feedback from the verifier and a reviewer after you report. For each round:
- Decide: **improve** the scenario, or **discard** it and start a new one. Discard it if the main idea breaks spec section 3 or 4.
- To discard, delete your folder and use a new ID.
- Give your decision and the reason in your next report.

## 7. Report

When you finish, report:
- the scenario in two sentences;
- how it meets P1–P5;
- the verify result;
- capability requests;
- anything in this file or the spec that was not clear or was missing.
