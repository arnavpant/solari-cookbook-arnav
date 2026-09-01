"""Second probe. The first one killed two assumptions; this one finds out why.

A: What OS/apt sources does the default template have, and can we get GnuCash at all?
B: What GUI apps are already installed that could host the benchmark instead?
C: Why is revert() "Not revertable" - does it need a pause, or a settled snapshot?
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402
from solari_desktop import DesktopClient  # noqa: E402

BASE_URL = "https://api.getsolari.com"


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


async def sh(d, cmd: str, timeout_ms: int = 180_000) -> str:
    r = await d.exec("sh", args=["-c", cmd], timeout_ms=timeout_ms)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return f"(exit {r.exitCode}) {out}"


async def section_a(d) -> None:
    log("=== A: base image and apt ===")
    for cmd in (
        "cat /etc/os-release | head -4",
        "apt-cache policy | head -20",
        "ls /etc/apt/sources.list.d/ 2>/dev/null; cat /etc/apt/sources.list 2>/dev/null | grep -v '^#' | grep . | head",
        "apt-cache search gnucash | head",
        "apt-cache search gnumeric | head -3",
    ):
        log(f"$ {cmd}\n    {await sh(d, cmd)}")

    log("--- trying to enable universe and install gnucash ---")
    log(await sh(d, "apt-get install -y -qq software-properties-common >/dev/null 2>&1; "
                    "add-apt-repository -y universe >/dev/null 2>&1; "
                    "apt-get update -qq 2>&1 | tail -2; "
                    "apt-cache search gnucash | head -3", timeout_ms=600_000))


async def section_b(d) -> None:
    log("=== B: what GUI apps already exist ===")
    for cmd in (
        "for b in gnucash gnumeric libreoffice soffice localc lobase sqlitebrowser "
        "mousepad thunar code google-chrome xterm; do "
        "printf '%-16s %s\\n' \"$b\" \"$(command -v $b || echo -)\"; done",
        "ls /usr/share/applications/ 2>/dev/null | head -30",
    ):
        log(f"$ {cmd}\n{await sh(d, cmd)}")


async def section_c(d, client) -> None:
    log("=== C: why is revert refused? ===")
    await d.fs.write("/root/canary.txt", "before\n")
    snap = await d.snapshot("probe2-snap")
    log(f"snapshot: {snap}")

    log("waiting 25s in case the snapshot settles asynchronously")
    await asyncio.sleep(25)
    await d.fs.write("/root/canary.txt", "after\n")

    try:
        await d.revert(snap)
        await asyncio.sleep(3)
        await d.reconnect()
        val = (await d.fs.read_text("/root/canary.txt")).strip()
        log(f"C1 revert-after-wait: OK, canary={val!r}")
        return
    except Exception as exc:  # noqa: BLE001
        log(f"C1 revert-after-wait FAILED: {type(exc).__name__}: {str(exc)[:200]}")

    try:
        log("C2: pausing, then reverting, then resuming")
        await client.pause(d.sessionId)
        await asyncio.sleep(5)
        await d.revert(snap)
        log("C2: revert accepted while paused")
        d2 = await client.resume(d.sessionId)
        await d2.connect()
        val = (await d2.fs.read_text("/root/canary.txt")).strip()
        log(f"C2 result: canary={val!r} -> {'PASS' if val == 'before' else 'FAIL'}")
        return
    except Exception as exc:  # noqa: BLE001
        log(f"C2 pause-revert FAILED: {type(exc).__name__}: {str(exc)[:200]}")

    log("C3: can we create a NEW desktop from the snapshot? (docs mention fromSnapshot)")
    for kw in ("fromSnapshot", "from_snapshot", "snapshot", "snapshotId"):
        try:
            n = await client.create(template="default", cpu=1, mem_mb=2048,
                                    timeout_ms=120_000, **{kw: snap})
            log(f"C3: ACCEPTED kwarg {kw!r} -> session {n.sessionId}")
            await client.destroy(n.sessionId)
            return
        except TypeError as exc:
            log(f"C3: SDK rejects kwarg {kw!r}: {str(exc)[:120]}")
        except Exception as exc:  # noqa: BLE001
            log(f"C3: server rejected {kw!r}: {type(exc).__name__}: {str(exc)[:160]}")


async def main() -> int:
    load_dotenv()
    client = DesktopClient(api_key=os.environ["SOLARI_API_KEY"], base_url=BASE_URL)
    d = await client.create(template="default", cpu=1, mem_mb=2048,
                            resolution="1280x720", timeout_ms=30 * 60_000)
    log(f"session: {d.sessionId[:60]}...")
    try:
        await d.connect()
        for _ in range(60):
            if getattr(await d.health(), "ready", False):
                break
            await asyncio.sleep(2)
        log("ready")
        await section_a(d)
        await section_b(d)
        await section_c(d, client)
        return 0
    finally:
        log("cleaning up")
        try:
            await d.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            await client.destroy(d.sessionId)
        except Exception:  # noqa: BLE001
            pass
        log("done")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
