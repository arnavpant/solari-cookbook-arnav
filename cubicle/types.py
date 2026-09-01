"""Core value types. This module imports nothing from the rest of cubicle.

Every other module imports it, so keeping it dependency-free stops import cycles
before they start.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

ActionKind = Literal["click", "double_click", "type", "key", "scroll", "drag", "done"]
ScrollDir = Literal["up", "down", "left", "right"]
Outcome = Literal["pass", "wrong_state", "timeout", "crash", "corrupt"]
Tier = Literal["easy", "medium", "hard"]


@dataclass(frozen=True)
class Observation:
    """Everything the agent is allowed to see. Pixels and the task, nothing else."""

    screenshot_png: bytes
    width: int
    height: int
    step: int
    max_steps: int
    task_prompt: str


@dataclass(frozen=True)
class Action:
    """One step of intent. Maps 1:1 onto the Solari mouse/keyboard surface."""

    kind: ActionKind
    x: int | None = None
    y: int | None = None
    text: str | None = None
    scroll_direction: ScrollDir | None = None
    scroll_amount: int | None = None
    to_x: int | None = None
    to_y: int | None = None

    def __post_init__(self) -> None:
        if self.kind in ("click", "double_click", "scroll", "drag"):
            if self.x is None or self.y is None:
                raise ValueError(f"{self.kind} requires x and y")
        if self.kind in ("type", "key") and not self.text:
            raise ValueError(f"{self.kind} requires text")
        if self.kind == "drag" and (self.to_x is None or self.to_y is None):
            raise ValueError("drag requires to_x and to_y")


@dataclass(frozen=True)
class Verdict:
    """A grader's answer. A failure must always say why."""

    passed: bool
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.passed and not self.reason:
            raise ValueError("a failing Verdict must carry a reason")


@dataclass
class TaskResult:
    """One (agent, task) outcome. Serialised straight into results.json."""

    task_id: str
    agent: str
    outcome: Outcome
    reason: str
    steps_used: int
    max_steps: int
    model_seconds: float
    desktop_seconds: float
    unparseable_responses: int
    session_id: str


@dataclass(frozen=True)
class Task:
    """A benchmark task: how to start it, how to score it, how to solve it."""

    task_id: str
    tier: Tier
    max_steps: int
    prompt: str
    seed: Callable[[], bytes]
    grade: Callable[[str], Verdict]
    oracle: Callable[[object], None]
