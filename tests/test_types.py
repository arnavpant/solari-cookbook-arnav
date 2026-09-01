import pytest

from cubicle.types import Action, Observation, Verdict


def test_click_action_requires_coordinates():
    with pytest.raises(ValueError, match="click requires x and y"):
        Action(kind="click")


def test_type_action_requires_text():
    with pytest.raises(ValueError, match="type requires text"):
        Action(kind="type")


def test_drag_requires_a_destination():
    with pytest.raises(ValueError, match="drag requires to_x and to_y"):
        Action(kind="drag", x=1, y=2)


def test_done_action_needs_nothing():
    assert Action(kind="done").kind == "done"


def test_action_is_frozen():
    a = Action(kind="click", x=1, y=2)
    with pytest.raises(Exception):
        a.x = 5  # type: ignore[misc]


def test_verdict_failure_requires_reason():
    with pytest.raises(ValueError, match="reason"):
        Verdict(passed=False, reason="")


def test_passing_verdict_needs_no_reason():
    assert Verdict(passed=True).passed


def test_observation_carries_prompt_and_step_budget():
    o = Observation(
        screenshot_png=b"\x89PNG",
        width=1280,
        height=720,
        step=0,
        max_steps=15,
        task_prompt="do the thing",
    )
    assert o.max_steps == 15
    assert o.task_prompt == "do the thing"
