# authoring

The scenario loop. An author agent writes a scenario from a brief, `dsz verify` checks it, and a reviewer agent gives a verdict. Each agent works in a sandbox and sees only what it needs. The `scenario-brief` skill helps a person write the brief with any agent.

## Files

| File | Job | Reader |
|---|---|---|
| `loop.py` | Runs the loop through the Claude CLI | Person |
| `guard.py` | Hook that keeps each agent in its sandbox | Claude CLI |
| `author.md` | The author's instructions | Author agent |
| `reviewer.md` | The reviewer's instructions | Reviewer agent |
| `brief.md` | The brief format and modes | Person, brief skill |
| `brief.py` | Parses and checks a brief. Standard library only; the skill ships it | `loop.py`, person |
| `skill/SKILL.md` | The `scenario-brief` skill's instructions (source) | Any agent, through the built skill |
| `build_skill.py` | Builds the skill package into `dist/` | Person |
| `test_*.py` | Tests for the guard, the brief and the skill build | Person |

## Sandbox

The loop makes a workspace in the system temp folder, outside the repository:

| Path | Source |
|---|---|
| `SPEC.md` | `LONG_HORIZON_TASK_SPEC.md` |
| `FORMAT.md` | `day_shift_zero/src/dsz/scenario/FORMAT.md` |
| `VOCABULARY.md` | `dsz vocab`, generated from the platform registries |
| `BRIEF.md` | The brief and its mode, from `--brief` |
| `scenario/` | Empty. The author writes here |

Each agent runs with `--restricted --strict-mcp-config`. This ignores user and project settings and MCP servers, and limits the file tools to the workspace. `guard.py` then allows only these calls:

| Tool | Author | Reviewer |
|---|---|---|
| Read, Glob, Grep | Inside the workspace | Inside the workspace |
| Write, Edit | `scenario/*.yaml`, `scenario/*.md` | No |
| Bash | `dsz verify scenario [--seeds N]` | No |
| StructuredOutput | Yes | Yes: it returns the verdict |

## Run

1. Install the platform in `day_shift_zero/.venv` (see `CLAUDE.md`).
2. From the repository root, run:
   ```sh
   python authoring/loop.py --rounds 3 --brief brief.json
   ```
3. Read the result line. On `passed`, the scenario is in `day_shift_zero/scenarios/<id>/`. Review it and commit it.

| Status | Meaning |
|---|---|
| `passed` | Verify passed, including S4 with the generic oracle, and the reviewer passed it |
| `brief_infeasible` | A `strict` brief cannot meet the task spec. The author's reason is in the summary |
| `rounds_exhausted` | No pass. The snapshots are in the run log |

The loop finds the CLI on `PATH`, in `$CLAUDE_BIN` or in the VS Code extension. Each round's author output, scenario snapshot, verify report and verdict go to `runs/scenario_loop/<UTC time>/`.

## Brief skill

1. From the repository root, run `python authoring/build_skill.py`.
2. Give `dist/scenario-brief.skill` to any agent that takes skills, for example Claude on the web.
3. Brainstorm with it. It writes `brief.json` and checks it with its own copy of `brief.py`.
4. Run the loop with `--brief brief.json`.

The skill is a snapshot: `SKILL.md` records the commit and the vocabulary stamp. Rebuild it after the task spec, `FORMAT.md` or the vocabulary changes. The loop warns when a brief names an older stamp.

## Rules

- Keep one source per subject. Rules go in the task spec. Format and platform limits go in `FORMAT.md`. Do not repeat them in `author.md` or `reviewer.md`.
- Never give an agent a path into the repository.
- Keep one definition of a brief: `brief.py`. The loop imports it and the skill ships it, so it uses only the standard library.
- Run `python -m pytest authoring` after you change anything here.
