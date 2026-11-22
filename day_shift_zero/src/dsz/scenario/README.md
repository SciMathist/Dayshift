# dsz.scenario

`scenario` turns a declarative definition into a running world. A new scenario is a folder with a definition. It needs code only for behaviour that the built-in plugins do not cover.

The definition format, for authors, is in [FORMAT.md](FORMAT.md). This file is for platform developers.

## Pipeline

```
folder ──load_scenario──► ScenarioSpec ──compile_spec──► SpecScenario ──generate(seed, horizon)──► Instance ──materialize──► Run
```

| Step | Module | Checks or does |
|---|---|---|
| Load | `compiler.py` | Reads `scenario.yaml`. Imports `oracle.py` from the folder by file path, if present |
| Parse | `spec.py` | Checks structure. Reports every problem at once (`SpecError`) |
| Compile | `compiler.py` | Imports `plugins:`. Resolves plugin names. Validates module and actor parameters. Checks capabilities (`MissingCapabilities`). Checks references in a 1-day probe instance |
| Generate | `template.py` or a plugin | Makes a reproducible `Instance`. Day *d* is the same for every horizon |
| Materialize | `materialize.py` | Builds the backend, items, events, actors, modules, processes, work tracker, success check, skills and observations |
| Run | `Run` | `observe()`, `act(call)`, `advance_to(t)`, `verdict()`, `brief()` |

`dsz verify <folder>` (`dsz.certify.verify`) runs this pipeline and the acceptance stages. `dsz vocab` (`vocabulary_doc.py`) renders the vocabulary from the registries.

## Scenario folder

| File | Written by |
|---|---|
| `scenario.yaml` | The scenario author |
| `DESIGN.md` | The scenario author |
| `oracle.py` | Optional. Registers a scenario-specific oracle and controls, only where the generic oracle (`dsz.certify.oracle`) cannot do the scenario (task spec section 6). Never written by the author |

## Built-in plugins

| Kind | Name | Purpose |
|---|---|---|
| Generator | `template` | Pool, initial items, subjects, facts, work templates, event templates |
| Criterion | `work_completion` | On-time fraction of work. Passes at `min_on_time` |
| Criterion | `no_violations` | No delivery with a forbidden allergen or a bad condition |
| Criterion | `waste` | Graded penalty for spoiled, damaged or contaminated items |
| Policy | `noop` | Negative control: waits forever |

## Rules

- Generators use only the `RngStreams` they receive. Use `rng.indexed(name, day)` to keep the prefix property.
- Do not put hidden constraints in ticket text.
- `Run` is evaluator-side. Give a policy only `brief()` and `observe()` output.
- `full_state=True` is for the pi_sym ablation only.
- When a platform limit in FORMAT.md is lifted, remove its row.

## Extend

- **Generator:** subclass `InstanceGenerator`. Decorate with `@register_generator`.
- **Criterion:** subclass `Criterion`. Decorate with `@register_criterion`.
- **Oracle or control:** add a factory `(instance, world, params) -> Policy` to `POLICIES`, in the scenario's `oracle.py`.
- Platform plugins live in `src/dsz/`. A package outside it can be listed under `plugins:`.
