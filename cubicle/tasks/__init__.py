"""Task registry. Order here is the order the benchmark runs in."""

from cubicle.tasks import (
    t01_create_account,
    t02_simple_expense,
    t03_rename_account,
    t04_split_transaction,
    t05_correct_amount,
    t06_reconcile_march,
    t07_reparent_account,
    t08_six_entries,
    t09_reconcile_statement,
    t10_month_end_close,
)

_MODULES = (
    t01_create_account,
    t02_simple_expense,
    t03_rename_account,
    t04_split_transaction,
    t05_correct_amount,
    t06_reconcile_march,
    t07_reparent_account,
    t08_six_entries,
    t09_reconcile_statement,
    t10_month_end_close,
)

TASKS = {m.TASK.task_id: m.TASK for m in _MODULES}

# Tasks whose scripted reference solution has not been recorded yet. Their seeds,
# prompts and graders are complete and tested offline; what is missing is a set of
# coordinates, and this suite does not guess coordinates - every one in it was read off
# a real screenshot. Until a live desktop is used to record them:
#   - the oracle agent skips these tasks rather than crashing (scripts/run.py)
#   - the 3x-oracle step-budget rule cannot be computed, so they are exempt
#     (tests/test_step_budget.py)
# Both places name this set rather than hardcoding ids, so emptying it is the only edit
# needed once the oracles exist.
ORACLE_PENDING = frozenset({"t08", "t09", "t10"})

SCORED = tuple(t for t in TASKS if t not in ORACLE_PENDING)

__all__ = ["TASKS", "ORACLE_PENDING", "SCORED"]
