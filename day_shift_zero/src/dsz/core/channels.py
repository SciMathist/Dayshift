"""Channel contract: how actors talk to the robot. Messages are policy-visible."""

from __future__ import annotations

from typing import Protocol, Sequence

from dsz.core.types import Message


class Channels(Protocol):
    """Post messages and read the ones the policy has not seen yet."""

    def post(self, message: Message) -> None:
        """Deliver `message` to the robot."""
        ...

    def drain(self) -> Sequence[Message]:
        """Return messages posted since the last drain, in posting order."""
        ...
