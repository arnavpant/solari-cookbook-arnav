"""The run loop: one (agent, task) pair in, one TaskResult out.

Grading never looks at a screenshot and never asks a model. It reads the book GnuCash
wrote and runs SQL over it.
"""

from __future__ import annotations

import time
from pathlib import Path

from cubicle.desktop import CubicleDesktop
from cubicle.grading import check_integrity, open_book, write_temp_book
from cubicle.types import Observation, Task, TaskResult, Verdict


class UnparseableResponse(Exception):
    """Raised by an agent when the model's reply is not a valid Action.

    The harness counts it as a wasted step rather than silently papering over it,
    because an agent that cannot emit a valid action IS failing.
    """


def run_task(
    cd: CubicleDesktop,
    agent,
    task: Task,
    trace_dir: Path | None = None,
) -> TaskResult:
    agent.reset()
    steps = 0
    unparseable = 0
    model_s = 0.0
    desktop_s = 0.0

    def result(outcome: str, reason: str) -> TaskResult:
        return TaskResult(
            task_id=task.task_id,
            agent=agent.name,
            outcome=outcome,  # type: ignore[arg-type]
            reason=reason,
            steps_used=steps,
            max_steps=task.max_steps,
            model_seconds=round(model_s, 2),
            desktop_seconds=round(desktop_s, 2),
            unparseable_responses=unparseable,
            session_id=getattr(cd.d, "sessionId", "unknown"),
        )

    def grade_now() -> Verdict:
        nonlocal desktop_s
        t0 = time.monotonic()
        book = cd.read_book()
        desktop_s += time.monotonic() - t0
        path = write_temp_book(book)
        integrity = check_integrity(open_book(path))
        if not integrity.passed:
            return integrity
        return task.grade(path)

    try:
        t0 = time.monotonic()
        cd.start_task(task.seed())
        desktop_s += time.monotonic() - t0

        hit_cap = True
        for step in range(task.max_steps):
            t0 = time.monotonic()
            shot = cd.screenshot()
            desktop_s += time.monotonic() - t0

            if trace_dir is not None:
                trace_dir.mkdir(parents=True, exist_ok=True)
                (trace_dir / f"step-{step:03d}.png").write_bytes(shot)

            obs = Observation(
                screenshot_png=shot,
                width=1280,
                height=720,
                step=step,
                max_steps=task.max_steps,
                task_prompt=task.prompt,
            )

            t0 = time.monotonic()
            try:
                action = agent.act(obs)
            except UnparseableResponse:
                unparseable += 1
                steps += 1
                model_s += time.monotonic() - t0
                continue
            model_s += time.monotonic() - t0

            steps += 1
            if action.kind == "done":
                hit_cap = False
                break

            t0 = time.monotonic()
            cd.apply(action)
            desktop_s += time.monotonic() - t0

        verdict = grade_now()
        if verdict.passed:
            # An agent that ran out of steps but still finished the job passes. The
            # step cap is a budget, not a correctness criterion.
            return result("pass", "")
        if "does not balance" in verdict.reason:
            return result("corrupt", verdict.reason)
        if hit_cap:
            return result("timeout", verdict.reason or "step cap reached")
        return result("wrong_state", verdict.reason)

    except Exception as exc:  # noqa: BLE001 - anything unhandled here is a crash
        message = str(exc)
        outcome = "corrupt" if "does not balance" in message else "crash"
        return result(outcome, message[:400])
