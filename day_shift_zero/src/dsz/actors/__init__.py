"""Actors (suppliers, customers, couriers, co-workers) and the channel hub they talk through.

Importing this package registers the built-in actor roles.
"""

from dsz.actors import supplier  # noqa: F401  (registration side effect)
from dsz.actors.channels import ChannelHub
from dsz.actors.registry import ACTORS, build_actors, register_actor

__all__ = ["ACTORS", "ChannelHub", "build_actors", "register_actor"]
