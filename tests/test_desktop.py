import asyncio

import pytest

from cubicle.desktop import BOOK_COPY, BOOK_PATH, CubicleDesktop
from cubicle.types import Action
from tests.fake_desktop import ExecResult, FakeDesktop


@pytest.fixture
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


@pytest.fixture
def cd(loop):
    return CubicleDesktop(FakeDesktop(), loop)


def _kinds(cd):
    return [e[0] for e in cd.d.log]


def test_start_task_resets_before_writing_the_seed(cd):
    cd.start_task(b"SEEDBYTES")
    kinds = _kinds(cd)
    assert kinds.index("exec") < kinds.index("open")
    assert cd.d.fs.files[BOOK_PATH] == b"SEEDBYTES"


def test_reset_wipes_gnucash_config_not_just_the_book(cd):
    cd.reset()
    script = next(e[1] for e in cd.d.log if e[0] == "exec")
    assert ".config/gnucash" in script
    assert ".local/share/gnucash" in script
    assert "pkill" in script
    assert BOOK_PATH in script


def test_exec_raises_on_nonzero_exit_code(cd):
    """A 200 only means the HTTP call worked; the real result is in exitCode."""
    cd.d.exec_results["boom"] = ExecResult(exitCode=3, stderr="it broke")
    with pytest.raises(RuntimeError, match="exited 3"):
        cd.exec("boom")


def test_exec_can_opt_out_of_the_check(cd):
    cd.d.exec_results["boom"] = ExecResult(exitCode=3)
    assert cd.exec("boom", check=False).exitCode == 3


def test_apply_click_forwards_coordinates(cd):
    cd.apply(Action(kind="click", x=10, y=20))
    assert ("click", 10, 20) in cd.d.log


def test_apply_double_click(cd):
    cd.apply(Action(kind="double_click", x=3, y=4))
    assert ("double_click", 3, 4) in cd.d.log


def test_apply_type_forwards_text(cd):
    cd.apply(Action(kind="type", text="hello"))
    assert ("type", "hello") in cd.d.log


def test_apply_key_uses_press_not_type(cd):
    cd.apply(Action(kind="key", text="ctrl+s"))
    assert ("press", "ctrl+s") in cd.d.log


def test_apply_scroll_passes_direction_and_amount(cd):
    cd.apply(Action(kind="scroll", x=1, y=2, scroll_direction="up", scroll_amount=5))
    assert ("scroll", 1, 2, "up", 5) in cd.d.log


def test_apply_drag_passes_destination(cd):
    cd.apply(Action(kind="drag", x=1, y=2, to_x=8, to_y=9))
    assert ("drag", 1, 2, 8, 9) in cd.d.log


def test_apply_done_is_a_noop(cd):
    cd.apply(Action(kind="done"))
    assert cd.d.log == []


def test_read_book_copies_inside_the_vm_first(cd):
    cd.d.fs.files[BOOK_COPY] = b"COPIED"
    assert cd.read_book() == b"COPIED"
    assert any(e[0] == "exec" and e[1].startswith("cp ") for e in cd.d.log)


def test_wait_for_ready_settles_on_two_identical_frames(cd):
    cd.d.frames = [b"A", b"B", b"C", b"C"]
    cd.wait_for_gnucash_ready(poll_seconds=0)
    assert cd.d._i >= 4


def test_wait_for_ready_times_out_if_the_screen_never_settles(cd):
    cd.d.frames = [bytes([i]) for i in range(200)]
    with pytest.raises(TimeoutError):
        cd.wait_for_gnucash_ready(timeout_seconds=0, poll_seconds=0)


def test_wait_for_ready_waits_for_the_gnucash_process(loop):
    d = FakeDesktop()
    d.exec_results["pgrep -x gnucash"] = ExecResult(exitCode=1)  # not running
    cd = CubicleDesktop(d, loop)
    with pytest.raises(TimeoutError):
        cd.wait_for_gnucash_ready(timeout_seconds=0, poll_seconds=0)


def test_readiness_uses_pgrep_not_the_sdk_process_list(cd):
    """Regression: d.process.list() returns 75 entries all with name='' and cmd=None,
    so a process cannot be found by name through the SDK. pgrep can."""
    cd.gnucash_running()
    assert any(e[0] == "exec" and "pgrep -x gnucash" in e[1] for e in cd.d.log)


def test_gnucash_installed_reports_false_when_absent(cd):
    cd.d.exec_results["command -v gnucash"] = ExecResult(exitCode=1)
    assert cd.gnucash_installed() is False


def test_install_runs_apt_update_before_install(cd):
    """pkg.install does not update, and a fresh desktop has empty package lists."""
    cd.install_gnucash()
    scripts = [e[1] for e in cd.d.log if e[0] == "exec"]
    assert any("apt-get update" in s for s in scripts)
    assert any("install -y -qq gnucash" in s for s in scripts)
    assert scripts.index(next(s for s in scripts if "apt-get update" in s)) < scripts.index(
        next(s for s in scripts if "install -y -qq gnucash" in s)
    )


def test_reset_does_not_pkill_by_full_commandline():
    """Regression: `pkill -f gnucash` matches the FULL command line, and the reset
    command line contains 'gnucash' (rm -f /root/book.gnucash*). The shell pkilled
    itself and the reset exited -1 with everything after it unrun. -x matches the
    process NAME, and the shell is 'sh', so it cannot self-match."""
    from cubicle.desktop import RESET_CMD

    assert "pkill -x gnucash" in RESET_CMD
    assert "pkill -f" not in RESET_CMD
