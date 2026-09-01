"""One-shot platform probe. Answers the three open questions in the spec, then exits.

Q1  Does GnuCash install from apt on the default desktop template, and what version?
Q2  Does revert() actually restore a dirtied filesystem?
Q3  What shape does create(lifecycle=...) accept?

Everything on the Desktop handle is a coroutine, so this script is async throughout.
See the plan's Global Constraints for why SyncDesktopClient does not help.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import time

# Some Pythons (MSYS2/mingw, and some minimal Linux images) ship an EMPTY OpenSSL
# CA store. httpx still works because it bundles certifi, but Solari's WebSocket
# control channel uses the `websockets` library and the stdlib default SSL context,
# so d.connect() dies with CERTIFICATE_VERIFY_FAILED while every HTTP call succeeds.
# Point OpenSSL at certifi BEFORE anything creates an SSL context.
import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402
from solari_desktop import ConcurrencyLimitError, DesktopClient  # noqa: E402

BASE_URL = "https://api.getsolari.com"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def wait_ready(d, timeout_s: int = 120) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if getattr(await d.health(), "ready", False):
                return True
        except Exception as exc:  # noqa: BLE001 - health can flap while booting
            log(f"    health not up yet: {type(exc).__name__}")
        await asyncio.sleep(2)
    return False


async def q1_gnucash(d) -> None:
    log("Q1: installing gnucash via pkg.install('apt', ['gnucash']) - this is slow")
    t0 = time.time()
    try:
        res = await d.pkg.install("apt", ["gnucash"])
        log(f"Q1: pkg.install returned {res!r} after {time.time() - t0:.0f}s")
    except Exception as exc:  # noqa: BLE001 - we want the failure mode recorded
        log(f"Q1: pkg.install FAILED {type(exc).__name__}: {str(exc)[:300]}")
        log("Q1: falling back to apt-get via exec")
        r = await d.exec("sh", args=["-c", "apt-get update -qq && apt-get install -y -qq gnucash"],
                         timeout_ms=900_000)
        log(f"Q1: apt-get exit={getattr(r, 'exitCode', '?')} err={(getattr(r, 'stderr', '') or '')[:300]}")

    which = await d.exec("command", args=["-v", "gnucash"], timeout_ms=60_000)
    log(f"Q1: which gnucash exit={which.exitCode} out={(which.stdout or '').strip()!r}")

    ver = await d.exec("gnucash", args=["--version"], timeout_ms=180_000)
    log(f"Q1: version exit={ver.exitCode} out={(ver.stdout or '').strip()[:200]!r} "
        f"err={(ver.stderr or '').strip()[:200]!r}")


async def q2_revert(d) -> None:
    log("Q2: writing canary, snapshotting, dirtying, reverting")
    await d.fs.write("/root/canary.txt", "before-snapshot\n")
    snap = await d.snapshot("probe-snap")
    log(f"Q2: snapshot id = {snap}")

    await d.fs.write("/root/canary.txt", "AFTER-snapshot\n")
    log(f"Q2: dirtied  -> {(await d.fs.read_text('/root/canary.txt')).strip()!r}")

    t0 = time.time()
    await d.revert(snap)
    log(f"Q2: revert() returned in {time.time() - t0:.2f}s")
    await asyncio.sleep(3)
    try:
        await d.reconnect()
    except Exception as exc:  # noqa: BLE001
        log(f"Q2: reconnect after revert raised {type(exc).__name__}: {str(exc)[:200]}")

    after = (await d.fs.read_text("/root/canary.txt")).strip()
    verdict = "PASS" if after == "before-snapshot" else "FAIL"
    log(f"Q2: canary after revert = {after!r} -> {verdict}")
    log(f"Q2: SNAPSHOT_ID={snap}")


async def q3_lifecycle(client) -> None:
    shapes = [
        {"onIdle": "pause"},
        {"on_idle": "pause"},
        {"idle": {"action": "pause"}},
        {"action": "pause"},
        {"onTimeout": "pause"},
    ]
    for shape in shapes:
        probe = None
        try:
            probe = await client.create(template="default", cpu=1, mem_mb=2048,
                                        lifecycle=shape, timeout_ms=120_000)
            log(f"Q3: ACCEPTED {shape}")
            return
        except ConcurrencyLimitError:
            log("Q3: hit the 2-desktop concurrency cap - cannot probe lifecycle now. "
                "Re-run Q3 alone. (429 is never retryable.)")
            return
        except Exception as exc:  # noqa: BLE001 - probing shapes on purpose
            log(f"Q3: rejected {shape} -> {type(exc).__name__}: {str(exc)[:180]}")
        finally:
            if probe is not None:
                try:
                    await client.destroy(probe.sessionId)
                except Exception:  # noqa: BLE001
                    pass
    log("Q3: no shape accepted - omit the lifecycle parameter entirely")


async def main() -> int:
    load_dotenv()
    key = os.environ.get("SOLARI_API_KEY")
    if not key:
        print("SOLARI_API_KEY is not set (put it in .env)", file=sys.stderr)
        return 2

    client = DesktopClient(api_key=key, base_url=BASE_URL)
    d = await client.create(template="default", cpu=1, mem_mb=2048,
                            resolution="1280x720", record=True,
                            timeout_ms=30 * 60_000)
    log(f"session: {d.sessionId}")
    log(f"watch  : {getattr(d, 'streamUrl', '<none>')}")

    try:
        await d.connect()
        if not await wait_ready(d):
            log("desktop never reported ready - aborting")
            return 1
        log("desktop ready")

        await q1_gnucash(d)
        await q2_revert(d)
        await q3_lifecycle(client)

        shot = await d.screenshot(format="png")
        out = pathlib.Path("probe-screen.png")
        out.write_bytes(shot)
        log(f"screenshot: {out} ({len(shot)} bytes)")
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
