# dsz.scenario

`scenario` turns a declarative definition into a running world. A new scenario needs a definition (YAML or dict). It needs code only for behaviour that the built-in plugins do not cover.

## Pipeline

```
definition ──parse_spec──► ScenarioSpec ──compile_spec──► SpecScenario ──generate(seed, horizon)──► Instance ──materialize──► Run
```

| Step | Module | Checks or does |
|---|---|---|
| Parse | `spec.py` | Checks structure. Reports every problem at once (`SpecError`) |
| Compile | `compiler.py` | Imports `plugins:`. Resolves plugin names. Validates module and actor parameters. Checks capabilities (`MissingCapabilities`). Checks references in a 1-day probe instance |
| Generate | `template.py` or a plugin | Makes a reproducible `Instance`. Day *d* is the same for every horizon |
| Materialize | `materialize.py` | Builds the backend, items, events, actors, modules, processes, work tracker, success check, skills and observations |
| Run | `Run` | `observe()`, `act(call)`, `advance_to(t)`, `verdict()`, `brief()` |

## Definition

```yaml
id: deli
objective: "Pack and dispatch lunch boxes on time."
horizon: {type: continuous, days: 3}             # or deadline
fixtures: {fridge: fridge, counter: counter, dispatch: dispatch_shelf}
modules: {spoilage: {}}                          # dynamics modules
actors: [{role: supplier, name: acme, fixture: inbox, lead_time_days: [1, 2]}]
generator: {name: template, params: {...}}       # see template.py for the schema
success:
  criteria:
    work_completion: {params: {min_on_time: 0.9}}
    no_violations: {}
    waste: {required: false, weight: 0.5}
policies: {oracle: my_oracle, controls: [noop]}
plugins: [my_package.deli_plugins]               # modules that register scenario plugins
```

## Built-in plugins

| Kind | Name | Purpose |
|---|---|---|
| Generator | `template` | Pool, initial items, subjects, facts, work templates, event templates |
| Criterion | `work_completion` | On-time fraction of work. Passes at `min_on_time` |
| Criterion | `no_violations` | No delivery with a forbidden allergen or a bad condition |
| Criterion | `waste` | Graded penalty for spoiled, damaged or contaminated items |
| Policy | `noop` | Negative control: waits forever |

## Work and hidden constraints

- A work item has a `deliver` predicate: `item_type`, `at`, `stages`, `exclude_allergens`. It can also have `collect` and `grace`.
- `WorkTracker` completes work when a matching item is at the fixture. With `collect: true`, a courier removes the item.
- A fact with `subject` and `constraint` adds the constraint to later work for that subject. The ticket does not repeat it. This makes the M1 dependency.
- A delivery that breaks a constraint still completes the work. It also records a violation.

## Rules

- Generators use only the `RngStreams` they receive. Use `rng.indexed(name, day)` to keep the prefix property.
- Do not put hidden constraints in ticket text.
- `Run` is evaluator-side. Give a policy only `brief()` and `observe()` output.
- `full_state=True` is for the pi_sym ablation only.

## Extend

- **Generator:** subclass `InstanceGenerator`. Decorate with `@register_generator`.
- **Criterion:** subclass `Criterion`. Decorate with `@register_criterion`.
- **Oracle or control:** add a factory `(instance, world, params) -> Policy` to `POLICIES`.
- Put scenario-specific plugins in a module. List it under `plugins:`.
