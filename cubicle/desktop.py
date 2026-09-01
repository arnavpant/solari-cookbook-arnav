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
    "pkill -f gnucash 2>/dev/null; sleep 1; "
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

    def exec(self, cmd: str, timeout_ms: int = 120_000, check: bool = True):
        """Run a shell command.

        A 200 from exec means only that the HTTP call succeeded; the command's real
        result is in exitCode. Never skip this check.
        """
        r = self._run(self.d.exec("sh", args=["-c", cmd], timeout_ms=timeout_ms))
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

    # ---- per-task lifecycle ---------------------------------------------

    def reset(self) -> None:
        """Return the machine to a known state between tasks."""
        self.exec(RESET_CMD, timeout_ms=120_000)

    def start_task(self, seed: bytes) -> None:
        self.reset()
        self._run(self.d.fs.write(BOOK_PATH, seed))
        self._run(self.d.open("gnucash", [BOOK_PATH]))
        self.wait_for_gnucash_ready()

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
                procs = self._run(self.d.process.list())
                seen_process = any(
                    "gnucash" in (getattr(p, "name", "") or "") for p in procs
                )
            if seen_process:
                current = self._run(self.d.screenshot(format="png"))
                if previous is not None and current == previous:
                    return
                previous = current
            if poll_seconds:
                time.sleep(poll_seconds)
        raise TimeoutError("GnuCash did not settle within the readiness timeout")

    # ---- the agent-facing surface ---------------------------------------

    def screenshot(self) -> bytes:
        return self._run(self.d.screenshot(format="png"))

    def apply(self, action: Action) -> None:
        """Mouse and keyboard only. Clipboard, exec, fs and process are deliberately
        unreachable from an Agent - that constraint is the benchmark."""
        k = action.kind
        if k == "done":
            return
        if k == "click":
            self._run(self.d.mouse.click(action.x, action.y, humanize=True))
        elif k == "double_click":
            self._run(self.d.mouse.double_click(action.x, action.y))
        elif k == "type":
            self._run(self.d.keyboard.type(action.text))
        elif k == "key":
            self._run(self.d.keyboard.press(action.text))
        elif k == "scroll":
            self._run(
                self.d.mouse.scroll(
                    action.x,
                    action.y,
                    direction=action.scroll_direction or "down",
                    amount=action.scroll_amount or 3,
                )
            )
        elif k == "drag":
            self._run(self.d.mouse.drag(action.x, action.y, action.to_x, action.to_y))
        else:
            raise ValueError(f"unknown action kind {k!r}")

    # ---- grading --------------------------------------------------------

    def read_book(self) -> bytes:
        """GnuCash holds the SQLite file open; copy it inside the VM, then read the copy."""
        self.exec(f"cp {BOOK_PATH} {BOOK_COPY}")
        return self._run(self.d.fs.read(BOOK_COPY))
