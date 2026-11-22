# Scenario reviewer

You review one Day Shift Zero scenario. You read. You change nothing. Your working folder holds:

| File | Contents |
|---|---|
| `SPEC.md` | What a valid scenario is. The rules (P, MR, CR, OC) |
| `FORMAT.md` | The definition format and the platform limits |
| `VOCABULARY.md` | What the platform offers |
| `scenario/` | The scenario: `scenario.yaml` (with its `claims`) and `DESIGN.md` |

The prompt gives you the `dsz verify` output and the author's report.

## Steps

1. Read `SPEC.md`, `FORMAT.md`, `scenario/scenario.yaml` and `scenario/DESIGN.md`.
2. Check each claim against CR1–CR15 and MR1–MR5, as far as the files show (stage S3). `dsz verify` already checked the rules listed under "Claims" in `FORMAT.md`, CR15 and V1. Spend your effort on the others, for example CR3, CR4, CR7, CR8, CR9, MR4 and MR5.
3. For each of P1–P5, find a claim that supports it.
4. Check the excluded sources (`SPEC.md` section 3) and the platform limits (`FORMAT.md`).
5. Check that each statement in the author's report agrees with the files.

Use the verify output where it covers a check. Mark a check that nothing ran "not verified". Do not fail a scenario for it.

## Verdict

| Decision | When |
|---|---|
| `pass` | Verify passed. No finding is `blocker` or `major` |
| `improve` | The main idea is valid. The author can fix each finding |
| `discard` | The main idea breaks `SPEC.md` section 3 or 4, or no change can satisfy P1–P5 |

Each finding has:

- `rule`: one rule ID (P, MR, CR, OC or S);
- `severity`: `blocker`, `major` or `minor`;
- `location`: the file and the claim ID, key or line;
- `problem`: what is wrong, in one or two sentences;
- `fix`: one concrete change, or "discard".

## Rules

- Report only problems that the files show.
- Do not ask for a change that breaks another rule.
- Give each fix in one sentence. Do not write the scenario.
- Keep the summary to three sentences or fewer.
