"""The run loop: one (agent, task) pair in, one TaskResult out.

Grading never looks at a screenshot and never asks a model. It reads the book GnuCash
wrote and runs SQL over it.
"""

from __future__ import annotations

import dataclasses
import json
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


class ProviderUnavailable(Exception):
    """The provider refused to answer - rate limit, quota, or an outage.

    This is NOT an agent failure and must never be scored as one. Counting a 429 as a
    wasted step makes a model look worse because its vendor throttled us, which would
    make the whole leaderboard dishonest. A task that hits this is abandoned and
    reported as `provider_error`, and the report shows it as unscored rather than zero.
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
    trace_log: list[dict] = []
    previous_shot: bytes | None = None

    def flush_trace() -> None:
        """One JSON object per step: what the agent asked for, and whether the screen
        moved. Screenshots alone cannot separate "the model clicked empty space" from
        "the harness dropped the action".

        Rewritten after every step, not once at the end. A run that dies mid-task is
        exactly when the trace matters most, and a trace only written on the happy path
        is not there when you need it.
        """
        if trace_dir is not None and trace_log:
            trace_dir.mkdir(parents=True, exist_ok=True)
            lines = [json.dumps(entry) for entry in trace_log]
            (trace_dir / "actions.jsonl").write_text(
                "\n".join(lines) + "\n", encoding="utf-8"
            )

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
                # Screenshots alone cannot tell "the model clicked empty space" from
                # "the harness dropped the action". Record what was actually asked for.
                screen_changed = previous_shot is not None and shot != previous_shot
                trace_log.append({"step": step, "screen_changed_since_last": screen_changed})
            previous_shot = shot

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
            except ProviderUnavailable as exc:
                # Not the agent's fault. Abandon the task rather than burning the step
                # budget on retries and reporting the result as if the model failed.
                model_s += time.monotonic() - t0
                if trace_log:
                    trace_log[-1]["provider_error"] = str(exc)[:300]
                    flush_trace()
                return result("provider_error", str(exc)[:400])
            except UnparseableResponse as exc:
                unparseable += 1
                steps += 1
                model_s += time.monotonic() - t0
                if trace_log:
                    trace_log[-1]["error"] = str(exc)[:300]
                    flush_trace()
                continue
            model_s += time.monotonic() - t0

            steps += 1
            if trace_log:
                trace_log[-1]["action"] = {
                    k: v for k, v in dataclasses.asdict(action).items() if v is not None
                }
                # A coordinate outside the display is a distinct kind of wrong from a
                # coordinate that is merely in the wrong place, and worth separating in
                # the record. The action is still applied - the harness does not correct
                # the agent, it measures it.
                if action.x is not None and not (
                    0 <= action.x < 1280 and 0 <= action.y < 720
                ):
                    trace_log[-1]["off_screen"] = True
                flush_trace()
            if action.kind == "done":
                hit_cap = False
                break

            t0 = time.monotonic()
            cd.apply(action)
            desktop_s += time.monotonic() - t0

        flush_trace()
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
        flush_trace()
        message = str(exc)
        outcome = "corrupt" if "does not balance" in message else "crash"
        return result(outcome, message[:400])
