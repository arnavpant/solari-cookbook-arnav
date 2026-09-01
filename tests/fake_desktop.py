"""In-memory stand-in for a Solari Desktop so the harness is testable with no network.

Mirrors the real handle: every method is a coroutine, because the real `Desktop` is
async even when obtained from `SyncDesktopClient`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExecResult:
    exitCode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeFs:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def write(self, path, data, mode=None) -> None:
        self.files[path] = data if isinstance(data, bytes) else str(data).encode()

    async def read(self, path) -> bytes:
        return self.files[path]

    async def read_text(self, path) -> str:
        return self.files[path].decode()


class FakeMouse:
    def __init__(self, log: list) -> None:
        self.log = log

    async def click(self, x, y, **kw) -> None:
        self.log.append(("click", x, y))

    async def double_click(self, x, y, **kw) -> None:
        self.log.append(("double_click", x, y))

    async def move(self, x, y, **kw) -> None:
        self.log.append(("move", x, y))

    async def scroll(self, x, y, *, button=None, humanize=None) -> None:
        # Real signature: no direction, no amount. Kept here so a test cannot pass
        # against a fake that is friendlier than the API.
        self.log.append(("scroll", x, y))

    async def drag(self, frm, to, button="left") -> None:
        self.log.append(("drag", frm["x"], frm["y"], to["x"], to["y"]))


class FakeKeyboard:
    def __init__(self, log: list) -> None:
        self.log = log

    async def type(self, text) -> None:
        self.log.append(("type", text))

    async def press(self, keys) -> None:
        self.log.append(("press", keys))

    async def hotkey(self, *keys) -> None:
        self.log.append(("hotkey", keys))


class FakeProcess:
    def __init__(self, names: list[str]) -> None:
        self._names = names

    async def list(self):
        return [type("P", (), {"name": n})() for n in self._names]


@dataclass
class FakeDesktop:
    sessionId: str = "fake-session"
    log: list = field(default_factory=list)
    frames: list = field(default_factory=lambda: [b"FRAME-A", b"FRAME-A"])
    exec_results: dict = field(default_factory=dict)
    processes: list = field(default_factory=lambda: ["gnucash"])
    _i: int = 0

    def __post_init__(self) -> None:
        self.fs = FakeFs()
        self.mouse = FakeMouse(self.log)
        self.keyboard = FakeKeyboard(self.log)
        self.process = FakeProcess(self.processes)

    async def screenshot(self, **kw) -> bytes:
        frame = self.frames[min(self._i, len(self.frames) - 1)]
        self._i += 1
        return frame

    async def open(self, name, args=None) -> int:
        self.log.append(("open", name, tuple(args or ())))
        return 1

    async def exec(self, cmd, args=None, **kw) -> ExecResult:
        script = (args or ["", ""])[-1] if args else cmd
        self.log.append(("exec", script))
        for needle, result in self.exec_results.items():
            if needle in script:
                return result
        return ExecResult()

    async def close(self) -> None:
        self.log.append(("close",))

    async def reconnect(self) -> None:
        pass

    async def health(self):
        return type("H", (), {"ready": True})()
