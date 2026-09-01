"""The entire pluggable surface of cubicle.

To put your agent on the leaderboard, implement `act`. That is the whole contract.

Deliberately synchronous: a one-method sync interface is the reason a third party can
adopt this in a sitting. The harness owns the event loop; your agent never sees it.

Your agent receives pixels and the task text. It does not receive a DOM, an
accessibility tree, the clipboard, a shell, or the filesystem. That constraint is the
benchmark.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cubicle.types import Action, Observation


@runtime_checkable
class Agent(Protocol):
    name: str

    def reset(self) -> None:
        """Called once before each task. Drop any per-task history here."""
        ...

    def act(self, obs: Observation) -> Action:
        """Look at the screenshot, return the next action.

        Raise cubicle.harness.UnparseableResponse if the model's reply cannot be
        turned into an Action; the harness counts it and moves on.
        """
        ...
