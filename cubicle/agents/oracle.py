"""The scripted reference agent.

It exists for two reasons. It proves every task is solvable, which pre-empts the
standard objection to any hard benchmark - "your tasks are impossible". And it is the
validation harness for the graders: if the oracle does the job correctly and the grader
still fails it, the grader is wrong.

It is not an AI agent and does not pretend to be. It replays coordinates recorded from
real screenshots.
"""

from __future__ import annotations

from cubicle.types import Action, Observation


class OracleAgent:
    name = "oracle"

    def __init__(self, cd, task) -> None:
        self.cd = cd
        self.task = task
        self._played = False

    def reset(self) -> None:
        self._played = False

    def act(self, obs: Observation) -> Action:
        if not self._played:
            self.task.oracle(self.cd)
            self._played = True
        return Action(kind="done")
