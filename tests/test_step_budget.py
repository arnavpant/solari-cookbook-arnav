"""The step budget must not be what fails an agent.

The oracle solves each task with perfect foreknowledge: exact coordinates, no looking,
no mistakes. Its action count is therefore the floor - the fewest moves the task can
possibly take. An agent has to observe, decide, and recover, so it gets three times
that floor.

Without this, a 0/7 is ambiguous: you cannot tell a model that cannot point from a model
that simply ran out of moves. t02 previously allowed 15 steps against an oracle that
needs 12, which is 3 spare moves for an entire GnuCash register entry.
"""

from __future__ import annotations

import inspect
import re

from cubicle.tasks import TASKS

MULTIPLIER = 3


def oracle_action_count(task) -> int:
    """How many Actions the scripted reference solution applies."""
    src = inspect.getsource(task.oracle)
    return len(re.findall(r"Action\(kind=", src))


def test_every_task_gets_at_least_three_times_the_oracle():
    tight = []
    for task_id, task in sorted(TASKS.items()):
        floor = oracle_action_count(task)
        assert floor > 0, f"{task_id}: could not count the oracle's actions"
        if task.max_steps < MULTIPLIER * floor:
            tight.append(
                f"{task_id}: cap {task.max_steps} < {MULTIPLIER}x oracle {floor} "
                f"(needs {MULTIPLIER * floor})"
            )
    assert not tight, "step budget too tight:\n  " + "\n  ".join(tight)


def test_the_floors_are_what_we_documented():
    """Pin the counts, so an oracle that grows silently trips the test above."""
    assert {t: oracle_action_count(k) for t, k in sorted(TASKS.items())} == {
        "t01": 5, "t02": 12, "t03": 7, "t04": 21,
        "t05": 6, "t06": 4, "t07": 9,
    }
