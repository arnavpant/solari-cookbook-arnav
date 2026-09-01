import asyncio

import pytest

from cubicle.desktop import BOOK_COPY, CubicleDesktop
from cubicle.fixtures.build_seed import seed_bytes
from cubicle.harness import UnparseableResponse, run_task
from cubicle.types import Action, Task, Verdict
from tests.fake_desktop import FakeDesktop


class ScriptedAgent:
    def __init__(self, actions):
        self.name = "scripted"
        self._actions = list(actions)
        self.calls = 0

    def reset(self):
        self.calls = 0

    def act(self, obs):
        self.calls += 1
        return self._actions.pop(0) if self._actions else Action(kind="done")


class ExplodingAgent:
    name = "boom"

    def reset(self):
        pass

    def act(self, obs):
        raise RuntimeError("model died")


class BabblingAgent:
    """Never emits a parseable action."""

    name = "babbler"

    def reset(self):
        pass

    def act(self, obs):
        raise UnparseableResponse("not json")


@pytest.fixture
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


@pytest.fixture
def cd(loop):
    d = FakeDesktop()
    # The harness grades whatever read_book() returns, so the fake must hold a REAL
    # book - otherwise check_integrity throws and everything reports "crash".
    d.fs.files[BOOK_COPY] = seed_bytes("base")
    return CubicleDesktop(d, loop)


def make_task(grade, max_steps=5):
    return Task(
        task_id="t00",
        tier="easy",
        max_steps=max_steps,
        prompt="do the thing",
        seed=lambda: b"SEED",
        grade=grade,
        oracle=lambda d: None,
    )


PASS = lambda _p: Verdict(True)  # noqa: E731


def test_passing_task_reports_pass(cd):
    r = run_task(cd, ScriptedAgent([Action(kind="done")]), make_task(PASS))
    assert r.outcome == "pass"
    assert r.steps_used == 1
    assert r.reason == ""


def test_done_stops_the_loop_early(cd):
    agent = ScriptedAgent([Action(kind="click", x=1, y=1), Action(kind="done")])
    r = run_task(cd, agent, make_task(PASS))
    assert r.steps_used == 2
    assert agent.calls == 2


def test_step_cap_with_failing_grade_reports_timeout(cd):
    agent = ScriptedAgent([Action(kind="click", x=1, y=1)] * 20)
    r = run_task(cd, agent, make_task(lambda _p: Verdict(False, "nope"), max_steps=3))
    assert r.outcome == "timeout"
    assert r.steps_used == 3


def test_step_cap_but_job_done_still_passes(cd):
    """The cap is a budget, not a correctness criterion."""
    agent = ScriptedAgent([Action(kind="click", x=1, y=1)] * 20)
    r = run_task(cd, agent, make_task(PASS, max_steps=3))
    assert r.outcome == "pass"


def test_wrong_state_reports_the_grader_reason(cd):
    r = run_task(
        cd,
        ScriptedAgent([Action(kind="done")]),
        make_task(lambda _p: Verdict(False, "account missing")),
    )
    assert r.outcome == "wrong_state"
    assert r.reason == "account missing"


def test_agent_exception_reports_crash(cd):
    r = run_task(cd, ExplodingAgent(), make_task(PASS))
    assert r.outcome == "crash"
    assert "model died" in r.reason


def test_corrupt_beats_wrong_state(cd):
    r = run_task(
        cd,
        ScriptedAgent([Action(kind="done")]),
        make_task(lambda _p: Verdict(False, "transaction abc does not balance (sum=5.0)")),
    )
    assert r.outcome == "corrupt"


def test_unparseable_responses_are_counted_and_cost_a_step(cd):
    r = run_task(cd, BabblingAgent(), make_task(PASS, max_steps=4))
    assert r.unparseable_responses == 4
    assert r.steps_used == 4


def test_result_records_session_and_timing(cd):
    r = run_task(cd, ScriptedAgent([Action(kind="done")]), make_task(PASS))
    assert r.session_id == "fake-session"
    assert r.model_seconds >= 0
    assert r.desktop_seconds >= 0
    assert r.max_steps == 5
    assert r.agent == "scripted"
    assert r.task_id == "t00"


def test_agent_reset_is_called_before_the_run(cd):
    agent = ScriptedAgent([Action(kind="done")])
    agent.calls = 99
    run_task(cd, agent, make_task(PASS))
    assert agent.calls == 1  # reset zeroed it, then one act()


def test_seed_is_written_to_the_desktop(cd):
    from cubicle.desktop import BOOK_PATH

    run_task(cd, ScriptedAgent([Action(kind="done")]), make_task(PASS))
    assert cd.d.fs.files[BOOK_PATH] == b"SEED"


def test_traces_are_written_when_requested(cd, tmp_path):
    agent = ScriptedAgent([Action(kind="click", x=1, y=1), Action(kind="done")])
    run_task(cd, agent, make_task(PASS), trace_dir=tmp_path / "t00")
    shots = sorted((tmp_path / "t00").glob("step-*.png"))
    assert len(shots) == 2
    assert shots[0].name == "step-000.png"
