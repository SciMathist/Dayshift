"""The generic oracle and its derived controls (task spec section 6).

| Part | Module |
|---|---|
| Recipe | `recipe.py`: work item -> processes and fixtures |
| Belief | `belief.py`: where items are believed to be |
| Executor | `executor.py`: greedy scheduler (latest start first) and monitor |
| Skill compiler | `compiler.py`: steps -> skill calls |

Importing this package registers these policies:

| Policy | The one change from the oracle |
|---|---|
| `generic_oracle` | - |
| `hidden_state_blind` | Believes only what the robot saw (P2, P3) |
| `never_recover` | Monitor off: no clearing or rescue, and items stay where it put them (P4) |
| `memoryless` | Keeps only the current view, and forgets a fact after `k` newer messages (P2) |

`stale_after_event` (params: `event`) is not a control. It is the C1 (c) probe: the oracle,
except that it misses the moves of one claimed event until the robot looks.
"""

from typing import Any, Mapping

from dsz.certify.oracle.belief import GroundTruthBelief, ObservedBelief, PlacedBelief, StaleAfterEventBelief
from dsz.certify.oracle.compiler import SkillCompiler, Step, call, pick
from dsz.certify.oracle.executor import GenericOracle, OracleConfig
from dsz.certify.oracle.recipe import KitchenPlan, RecipeError, recipe_for
from dsz.core.policy import Policy
from dsz.core.scenario import Instance
from dsz.scenario.registries import POLICIES
from dsz.world.state import WorldState

GENERIC_ORACLE = "generic_oracle"
DERIVED_CONTROLS = ("hidden_state_blind", "never_recover", "memoryless")
STALE_PROBE = "stale_after_event"
MEMORYLESS_K = 5  # pilot value, not a benchmark threshold


def _oracle(instance: Instance, world: WorldState, params: Mapping[str, Any]) -> Policy:
    """Build the generic oracle."""
    return GenericOracle(instance, world, GroundTruthBelief(world), OracleConfig())


def _blind(instance: Instance, world: WorldState, params: Mapping[str, Any]) -> Policy:
    """Build the hidden_state_blind control."""
    return GenericOracle(instance, world, ObservedBelief(instance, remember=True), OracleConfig())


def _never_recover(instance: Instance, world: WorldState, params: Mapping[str, Any]) -> Policy:
    """Build the never_recover control."""
    return GenericOracle(instance, world, PlacedBelief(world), OracleConfig(recover=False))


def _stale_after_event(instance: Instance, world: WorldState, params: Mapping[str, Any]) -> Policy:
    """Build the C1 (c) probe; params: event (the definition id of the claimed event)."""
    belief = StaleAfterEventBelief(world, instance, str(params["event"]))
    return GenericOracle(instance, world, belief, OracleConfig())


def _memoryless(instance: Instance, world: WorldState, params: Mapping[str, Any]) -> Policy:
    """Build the memoryless control; params: k (default MEMORYLESS_K)."""
    k = int(params.get("k", MEMORYLESS_K))
    return GenericOracle(instance, world, ObservedBelief(instance, remember=False), OracleConfig(forget_after=k))


for _name, _factory in {GENERIC_ORACLE: _oracle, "hidden_state_blind": _blind,
                        "never_recover": _never_recover, "memoryless": _memoryless,
                        STALE_PROBE: _stale_after_event}.items():
    if _name not in POLICIES:
        POLICIES.add(_name, _factory)

__all__ = ["DERIVED_CONTROLS", "GENERIC_ORACLE", "STALE_PROBE", "GenericOracle", "GroundTruthBelief", "KitchenPlan",
           "ObservedBelief", "OracleConfig", "PlacedBelief", "RecipeError", "SkillCompiler", "StaleAfterEventBelief",
           "Step", "call", "pick", "recipe_for"]
