"""Wraps a Solari Desktop in a synchronous facade.

The agent never touches this; the harness does. Two things drive the design:

1. Everything on the Solari `Desktop` handle is a coroutine, including `screenshot`,
   `mouse.*`, `keyboard.*`, `fs.*` and `exec`. `SyncDesktopClient` does not help - it
   wraps the *client* calls only, and its own docstring says the handle it returns is
   async. So we own one event loop and wrap every call. `Agent.act()` stays sync.

2. Per-task isolation is done in software, not with snapshots. `revert()` fails with
   `Not revertable` and `create(fromSnapshot=...)` does not exist in the SDK. See
   `docs/research/04-probe-findings.md`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from cubicle.types import Action

BOOK_PATH = "/root/book.gnucash"
BOOK_COPY = "/root/book.copy.gnucash"

# GnuCash persists preferences, window geometry and a recent-files list. Without wiping
# these, a later task starts in a different UI state than an earlier one and the
# benchmark quietly stops being fair. It also drops .LCK / .log files beside the book,
# which make it refuse to reopen the file.
RESET_CMD = (
    "pkill -x gnucash 2>/dev/null; sleep 1; "
    "rm -rf ~/.config/gnucash ~/.local/share/gnucash ~/.gnucash; "
    f"rm -f {BOOK_PATH}* {BOOK_COPY}*; "
    "true"
)


class CubicleDesktop:
    """Synchronous facade over an async Solari Desktop handle."""

    def __init__(self, desktop: Any, loop: asyncio.AbstractEventLoop) -> None:
        self.d = desktop
        self.loop = loop

    # ---- plumbing -------------------------------------------------------

    def _run(self, coro):
        return self.loop.run_until_complete(coro)

    def _call(self, make_coro):
        """Run a Desktop coroutine, reconnecting once if the control channel dropped.

        A model agent spends 10-25s per step thinking and rate-limiting, and Solari's
        WebSocket control channel does not survive those gaps - it closes with 1006 and
        every later call fails. The oracle never hit this because it finishes a task in
        about 20 seconds. `make_coro` is a callable rather than a coroutine because a
        coroutine cannot be awaited twice.
        """
        try:
            return self._run(make_coro())
        except Exception as exc:  # noqa: BLE001 - narrowed by message below
            if "not connected" not in str(exc).lower() and "closed" not in str(exc).lower():
                raise
            time.sleep(1.0)
            self._run(self.d.reconnect())
            return self._run(make_coro())

    def exec(self, cmd: str, timeout_ms: int = 120_000, check: bool = True):
        """Run a shell command.

        A 200 from exec means only that the HTTP call succeeded; the command's real
        result is in exitCode. Never skip this check.
        """
        r = self._call(lambda: self.d.exec("sh", args=["-c", cmd], timeout_ms=timeout_ms))
        if check and getattr(r, "exitCode", 0) != 0:
            raise RuntimeError(
                f"`{cmd[:60]}` exited {r.exitCode}: "
                f"{(getattr(r, 'stderr', '') or getattr(r, 'stdout', '') or '')[:300]}"
            )
        return r

    # ---- setup ----------------------------------------------------------

    def install_gnucash(self) -> None:
        """Once per desktop. pkg.install does NOT run apt-get update, and a fresh
        desktop has empty package lists, so every install fails without this."""
        self.exec("apt-get update -qq", timeout_ms=600_000)
        self.exec(
            "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gnucash",
            timeout_ms=1_500_000,
        )

    def gnucash_installed(self) -> bool:
        return self.exec("command -v gnucash", check=False).exitCode == 0

    def gnucash_running(self) -> bool:
        """Ask the OS, not the SDK.

        `d.process.list()` returns 75 entries whose `name` is '' and whose `cmd` is
        None - ProcessInfo(pid=1, name='', cmd=None) - so you cannot find a process by
        name through it. pgrep works.
        """
        return self.exec("pgrep -x gnucash >/dev/null 2>&1", check=False).exitCode == 0

    # ---- per-task lifecycle ---------------------------------------------

    def reset(self) -> None:
        """Return the machine to a known state between tasks."""
        self.exec(RESET_CMD, timeout_ms=120_000)

    def start_task(self, seed: bytes) -> None:
        self.reset()
        self._call(lambda: self.d.fs.write(BOOK_PATH, seed))
        self._call(lambda: self.d.open("gnucash", [BOOK_PATH]))
        self.wait_for_gnucash_ready()
        self.dismiss_stray_dialogs()
        self.maximize_gnucash()

    def maximize_gnucash(self) -> None:
        """GnuCash opens at roughly 800x700 on a 1280x720 screen, which cuts the
        register's Withdrawal and Balance columns off the right edge entirely. An agent
        that cannot see the amount column is being tested on the wrong thing, so every
        task starts from a maximized window.
        """
        self.exec(
            'for w in $(xdotool search --onlyvisible --name "GnuCash" 2>/dev/null); do '
            "  xdotool windowmove $w 0 0 windowsize $w 100% 100% 2>/dev/null; "
            "done; true",
            timeout_ms=30_000,
            check=False,
        )
        time.sleep(1.5)

    def dismiss_stray_dialogs(self) -> None:
        """Close GnuCash's startup dialogs before the agent ever sees the screen.

        The gsettings fix in setup_desktop.py should stop 'Tip Of The Day' appearing at
        all; this is the belt-and-braces pass in case it survives. Closing by window
        NAME via xdotool rather than by pixel coordinates keeps it robust if the dialog
        moves. Any step spent dismissing chrome that the harness put there would be
        noise in the benchmark, not signal.
        """
        self.exec(
            'for w in "Tip Of The Day" "Tip of the Day"; do '
            '  xdotool search --name "$w" windowclose 2>/dev/null; '
            "done; true",
            timeout_ms=30_000,
            check=False,
        )

    def wait_for_gnucash_ready(
        self, timeout_seconds: int = 120, poll_seconds: float = 2.0
    ) -> None:
        """health().ready means X11 is up, NOT that GnuCash has finished drawing.

        Waits for the gnucash process to exist and then for the screen to stop
        repainting (two consecutive identical frames).
        """
        deadline = time.time() + timeout_seconds
        previous: bytes | None = None
        seen_process = False
        while time.time() < deadline:
            if not seen_process:
                seen_process = self.gnucash_running()
            if seen_process:
                current = self._call(lambda: self.d.screenshot(format="png"))
                if previous is not None and current == previous:
                    return
                previous = current
            if poll_seconds:
                time.sleep(poll_seconds)
        raise TimeoutError("GnuCash did not settle within the readiness timeout")

    # ---- the agent-facing surface ---------------------------------------

    def screenshot(self) -> bytes:
        return self._call(lambda: self.d.screenshot(format="png"))

    def apply(self, action: Action) -> None:
        """Mouse and keyboard only. Clipboard, exec, fs and process are deliberately
        unreachable from an Agent - that constraint is the benchmark."""
        k = action.kind
        if k == "done":
            return
        if k == "click":
            self._call(lambda: self.d.mouse.click(action.x, action.y, humanize=True))
        elif k == "double_click":
            self._call(lambda: self.d.mouse.double_click(action.x, action.y))
        elif k == "type":
            self._call(lambda: self.d.keyboard.type(action.text))
        elif k == "key":
            self._call(lambda: self.d.keyboard.press(action.text))
        elif k == "scroll":
            # The SDK cannot express scroll direction. mouse.scroll() takes only
            # (x, y, button, humanize), and MouseButton is Literal["left","right",
            # "middle"] mapped to X11 codes 1/2/3 - there is no wheel code (4/5), so
            # "scroll up" is unrepresentable.
            #
            # Rather than expose a one-directional scroll, move the pointer there and
            # send Page_Up/Page_Down, which GnuCash's register honours. The agent still
            # gets working directional scrolling; it just travels over the keyboard.
            self._call(lambda: self.d.mouse.move(action.x, action.y))
            key = "Page_Up" if action.scroll_direction == "up" else "Page_Down"
            for _ in range(max(1, min(action.scroll_amount or 1, 5))):
                self._call(lambda: self.d.keyboard.press(key))
        elif k == "drag":
            # drag(frm: dict, to: dict, button) - NOT four positional coordinates.
            self._call(
                lambda: self.d.mouse.drag(
                    {"x": action.x, "y": action.y},
                    {"x": action.to_x, "y": action.to_y},
                )
            )
        else:
            raise ValueError(f"unknown action kind {k!r}")

    # ---- grading --------------------------------------------------------

    def read_book(self) -> bytes:
        """GnuCash holds the SQLite file open; copy it inside the VM, then read the copy."""
        self.exec(f"cp {BOOK_PATH} {BOOK_COPY}")
        return self._call(lambda: self.d.fs.read(BOOK_COPY))
