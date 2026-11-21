# Orchestrating the scenario loop in one Claude Code session

You are the orchestrator. You run the scenario loop from `project.md` section 5 inside an interactive Claude Code session. You spawn an author agent and reviewer agents with the Agent tool.

This is the fallback for the headless loop in `spike/scenario_loop/loop.py`. Use it when the Claude CLI cannot run headless, or when a person wants to watch each round.

## 1. Roles

| Role | Agent | Instructions | Lifetime |
|---|---|---|---|
| Author | `general-purpose` | `scenarios/AGENTS.md` | One agent for the whole run. Continue it with SendMessage |
| Reviewer | `general-purpose` | `scenarios/REVIEWER.md` | A new agent in each round |
| Orchestrator | You | This file | The whole run |

You do not write or fix the scenario. You do not review it. You run the checks, pass the outputs on and keep the log.

## 2. Before you start

1. Read `CLAUDE.md`, `scenarios/AGENTS.md` and `scenarios/REVIEWER.md`.
2. List the existing scenario folders. These are protected. The author must not change them.
3. Record the output of `git status --porcelain -uall`. This is the baseline.
4. Create the log folder `runs/scenario_loop/<UTC time>-interactive/`.
5. Set the round limit. Use 3 if the person gives no limit (`project.md` section 5).

## 3. The loop

For each round:

1. **Author.** In round 1, spawn the author with the prompt in section 4.1. In later rounds, send the feedback in section 4.3 to the same agent with SendMessage.
2. **Find the folder.** Find the new scenario folder that has a `scenario.yaml`. If there are two or more, use the newest. If there is none, the verify step fails.
3. **Verify.** Run the parse and compile check yourself, from `day_shift_zero/` with `.venv` active:
   ```sh
   python -c "from dsz.scenario.spec import load_spec; from dsz.scenario.compiler import compile_spec; \
   compile_spec(load_spec('scenarios/<id>/scenario.yaml')); print('OK')"
   ```
   Do not use the author's own verify result.
4. **Check for stray changes.** Run `git status --porcelain -uall`. Compare it with the baseline. A change outside `scenarios/<id>/`, or in a protected folder, is a stray change.
5. **Review.** Do this step only if verify passed and there are no stray changes. Spawn a new reviewer with the prompt in section 4.2.
6. **Log.** Write the author's report, the verify output and the verdict to the log folder. Use one file for each, with the round number in the name.
7. **Decide.**
   - Verify passed and the verdict is `pass`: stop. Go to section 5.
   - Last round: stop. Go to section 5.
   - Otherwise: go to the next round.

If the author deletes its folder and starts a new one (a discard), continue the loop with the new folder.

## 4. Prompts

Send the outputs word for word. Do not summarize, soften or add advice.

### 4.1 Author, round 1

```
You are the scenario author. Read day_shift_zero/scenarios/AGENTS.md and follow it exactly.
Write one new Day Shift Zero scenario, including the verify step and the report in section 7.
Write only inside your own folder day_shift_zero/scenarios/<id>/.
Do not change git state. Do not spawn other agents.
<If the person gave an idea: "Idea from the person who runs this loop: ...">
```

### 4.2 Reviewer

```
You are the scenario reviewer. Read day_shift_zero/scenarios/REVIEWER.md and follow it exactly.
Review the scenario in day_shift_zero/scenarios/<id>/.
Do not change any file. Do not run commands that write files. Do not spawn other agents.

## Verify output (S1, S2): PASSED
<verify output>

## Author's report
<the author's last report, word for word>

End your answer with the verdict as one JSON object:
{"decision": "pass|improve|discard", "summary": "...",
 "findings": [{"rule": "...", "severity": "blocker|major|minor",
               "location": "...", "problem": "...", "fix": "..."}]}
```

### 4.3 Author, later rounds

```
## Verify output (S1, S2): <PASSED or FAILED>
<verify output>

## Changes outside your folder (not allowed, revert them)
<stray paths, only if there are any>

## Reviewer verdict
<the reviewer's JSON, only if a review ran>

Follow AGENTS.md section 6: decide to improve or discard, act on it, verify again,
and give the report in section 7 with your decision and reason.
```

## 5. Report to the person

Give:

- the status: `passed` or `rounds exhausted`;
- the scenario folder;
- a table with one row for each round: verify result, stray changes, verdict;
- the open findings from the last verdict;
- the author's capability requests;
- the log folder.

Then follow `CLAUDE.md`: suggest a commit and wait for approval.

## 6. Rules

- Do not edit any file in the scenario folder. Only the author does.
- Do not revert a stray change yourself. Tell the author. If it stays, stop and tell the person.
- Do not let a reviewer see an earlier verdict. Each reviewer starts fresh.
- Do not change a criterion parameter, `AGENTS.md` or `REVIEWER.md` during a run.
- Do not commit. Ask the person first.
- Report honestly. If a step did not run, say so.
