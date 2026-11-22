---
name: scenario-brief
description: Help a person brainstorm a Day Shift Zero scenario and write it down as a brief (brief.json) for the authoring loop. Use when someone wants to plan, shape or sharpen an idea for a long-horizon embodied kitchen scenario, decide its objective, or prepare a --brief for authoring/loop.py. It writes a brief only, never a scenario definition, and it certifies nothing.
---

# Scenario brief

You help a person turn an idea into a brief: the prior the Day Shift Zero authoring loop starts from. The loop's author agent then writes the scenario, and `dsz verify` and a reviewer check it. Your output is one file, `brief.json`.

## Files

| File | Use it for |
|---|---|
| `references/brief.md` | The brief format and the three modes |
| `references/SPEC.md` | What makes a scenario valid. Sections 2–5 matter most here |
| `references/FORMAT.md` | What a scenario can express, and the platform limits |
| `references/VOCABULARY.md` | The names the platform has: fixtures, items, processes, events |
| `references/vocabulary.json` | The same names as data, and the vocabulary stamp |
| `scripts/brief.py` | The checker. Standard library only |

## Steps

1. Ask what the person wants the scenario to test, and how much the loop may change it. Agree on a mode: `free`, `improve` or `strict` (`references/brief.md`).
2. Shape the idea against `references/SPEC.md`:
   - each difficulty has a physical consequence: find, tell apart, open, check, carry, unload or recover (section 3);
   - the difficulty is not a parameter: no timing puzzles, quantities, schedules, prices (section 3, excluded sources);
   - a memory is about where, which, what state or whether done, and the robot cannot just look again cheaply (section 4);
   - a change in the world happens out of sight, and no message announces its what, where and when (CR5).
3. Check the idea against the platform limits in `references/FORMAT.md` and the names in `references/VOCABULARY.md`. Say plainly when the platform cannot do something yet. Do not design around a limit by pretending it is not there.
4. Write `brief.json`:
   - `objective` and `notes` in plain words; put platform names in backticks, for example `` `fridge` ``;
   - `must` only for what the author may not drop, `avoid` for what it should not use;
   - `vocabulary` set to the `stamp` in `references/vocabulary.json`.
5. Run `python scripts/brief.py brief.json --vocabulary references/vocabulary.json`. Fix every problem it lists.
6. Give the person the file and the command: `python authoring/loop.py --brief brief.json`.

## Rules

- Write the brief only. Do not write `scenario.yaml`, `DESIGN.md`, claims or code.
- A passing check means the brief is well formed. It does not mean the scenario will pass. Only the loop's `dsz verify` and reviewer decide that.
- In `strict` mode, warn the person about any part of the brief that breaks `SPEC.md` or a platform limit. The loop stops on a strict brief that cannot work.
- Do not tune a scenario to a particular model.
