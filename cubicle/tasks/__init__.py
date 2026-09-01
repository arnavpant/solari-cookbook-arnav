"""Task registry. Order here is the order the benchmark runs in."""

from cubicle.tasks import (
    t01_create_account,
    t02_simple_expense,
    t03_rename_account,
    t04_split_transaction,
    t05_correct_amount,
    t06_reconcile_march,
    t07_reparent_account,
)

_MODULES = (
    t01_create_account,
    t02_simple_expense,
    t03_rename_account,
    t04_split_transaction,
    t05_correct_amount,
    t06_reconcile_march,
    t07_reparent_account,
)

TASKS = {m.TASK.task_id: m.TASK for m in _MODULES}

__all__ = ["TASKS"]
