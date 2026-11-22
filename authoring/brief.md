# Scenario brief

A brief is the prior you give the authoring loop: what the scenario should be about, and how closely the author must follow it. It is a JSON file. `brief.py` checks it.

## Format

```json
{
  "version": 1,
  "vocabulary": "9bf80e285023",
  "mode": "strict",
  "objective": "A canteen where a co-worker sometimes moves prepared food out of the `fridge`, and the robot must notice before lunch.",
  "notes": "The memory should be about where things are, not about allergens.",
  "must": ["P3 through an unseen `relocate`"],
  "avoid": ["supplier orders"]
}
```

| Key | Required | Meaning |
|---|---|---|
| `version` | Yes | `1` |
| `mode` | Yes | `free`, `improve` or `strict` (below) |
| `objective` | For `improve` and `strict` | What the scenario is about, in plain words |
| `notes` | No | Explanation, preferences, things to try |
| `must` | No | What the author may not drop. Not allowed in `free` |
| `avoid` | No | What the author should not use |
| `vocabulary` | No | The vocabulary stamp the brief was written against (in `VOCABULARY.md` and `vocabulary.json`). The loop warns if the platform has changed since |

Put platform names in backticks, for example `` `fridge` `` or `` `relocate` ``. The checker reports a name in backticks that is not in the vocabulary. Rule IDs such as `P3` or `CR8` are also allowed in backticks.

## Modes

| Mode | The author |
|---|---|
| `free` | Chooses everything, including the objective. Same as giving no brief |
| `improve` | Starts from the brief and may change anything to meet the task spec. It reports each change and why |
| `strict` | Keeps the objective and every `must` item. It only fills gaps and writes the format. If the brief cannot meet the task spec or the platform limits, it writes no scenario and reports `BRIEF INFEASIBLE:` with the rule IDs. The loop then stops with status `brief_infeasible` |

The reviewer checks that the scenario follows the brief in its mode (finding rule `BRIEF`).

## Use

| Where | How |
|---|---|
| Authoring loop | `python authoring/loop.py --brief brief.json`. Text instead of a path is an `improve` brief with that objective. No `--brief` is `free` |
| Check a brief | `python brief.py brief.json --vocabulary vocabulary.json` |

A brief is not a scenario. It never contains `scenario.yaml` content, and a passing check certifies nothing. Only `dsz verify` in the loop does that.
