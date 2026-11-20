"""Dynamics modules: continuous, agent-independent change, as registered plugins.

Importing this package registers the built-in modules (spoilage, wear).
"""

from dsz.dynamics import spoilage, wear  # noqa: F401  (registration side effect)
from dsz.dynamics.registry import MODULES, build_modules, register_module
from dsz.dynamics.runner import DynamicsRunner

__all__ = ["MODULES", "DynamicsRunner", "build_modules", "register_module"]
