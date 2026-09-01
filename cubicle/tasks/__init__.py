"""Task registry."""

from cubicle.tasks import t01_create_account

_MODULES = (t01_create_account,)

TASKS = {m.TASK.task_id: m.TASK for m in _MODULES}

__all__ = ["TASKS"]
