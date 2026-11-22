# authoring

The scenario loop. An author agent writes a scenario, `dsz verify` checks it, and a reviewer agent gives a verdict. Each agent works in a sandbox and sees only what it needs.

## Files

| File | Job | Reader |
|---|---|---|
| `loop.py` | Runs the loop through the Claude CLI | Person |
| `guard.py` | Hook that keeps each agent in its sandbox | Claude CLI |
| `author.md` | The author's instructions | Author agent |
| `reviewer.md` | The reviewer's instructions | Reviewer agent |
| `test_guard.py` | Tests for `guard.py` | Person |

## Sandbox

The loop makes a workspace in the system temp folder, outside the repository:

| Path | Source |
|---|---|
| `SPEC.md` | `LONG_HORIZON_TASK_SPEC.md` |
| `FORMAT.md` | `day_shift_zero/src/dsz/scenario/FORMAT.md` |
| `VOCABULARY.md` | `dsz vocab`, generated from the platform registries |
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
   python authoring/loop.py --rounds 3 --brief "optional idea"
   ```
3. Read the result line. On `passed`, the scenario is in `day_shift_zero/scenarios/<id>/`. Review it and commit it.

| Status | Meaning |
|---|---|
| `passed` | Verify passed, including S4 with the generic oracle, and the reviewer passed it |
| `rounds_exhausted` | No pass. The snapshots are in the run log |

The loop finds the CLI on `PATH`, in `$CLAUDE_BIN` or in the VS Code extension. Each round's author output, scenario snapshot, verify report and verdict go to `runs/scenario_loop/<UTC time>/`.

## Rules

- Keep one source per subject. Rules go in the task spec. Format and platform limits go in `FORMAT.md`. Do not repeat them in `author.md` or `reviewer.md`.
- Never give an agent a path into the repository.
- Run `python -m pytest authoring` after you change `guard.py`.
