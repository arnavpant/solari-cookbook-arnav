"""Task 3 Step 5: prove GnuCash actually opens a piecash-written book.

This is the assumption that would be most expensive to discover late: piecash writes a
GnuCash 3.x schema (Gnucash version 3000000) and Ubuntu 22.04 ships GnuCash 4.x. If 4.x
refuses the book, or silently rewrites it into something our graders cannot read, the
whole grading design collapses.

Also doubles as the setup path the real harness will use.

  python scripts/verify_seed.py            # verify, then destroy the desktop
  python scripts/verify_seed.py --keep     # leave it running, print the session id
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sqlite3
import sys
import time

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402
from solari_desktop import DesktopClient  # noqa: E402

from cubicle.fixtures.build_seed import seed_bytes  # noqa: E402
from cubicle.grading import open_book, write_temp_book  # noqa: E402

BASE_URL = "https://api.getsolari.com"
BOOK = "/root/book.gnucash"


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


async def sh(d, cmd: str, timeout_ms: int = 600_000, check: bool = True):
    """Run a shell command. A 200 only means the HTTP call worked - check exitCode."""
    r = await d.exec("sh", args=["-c", cmd], timeout_ms=timeout_ms)
    if check and r.exitCode != 0:
        raise RuntimeError(
            f"`{cmd[:60]}` exited {r.exitCode}: {(r.stderr or r.stdout or '')[:300]}"
        )
    return r


async def install_gnucash(d) -> None:
    # pkg.install does NOT run apt-get update, and a fresh desktop has EMPTY package
    # lists, so every install fails with "Unable to locate package". Update first.
    log("apt-get update (package lists are empty on a fresh desktop)")
    t0 = time.time()
    await sh(d, "apt-get update -qq")
    log(f"  update done in {time.time() - t0:.0f}s")

    log("apt-get install gnucash - this is the slow part")
    t0 = time.time()
    await sh(d, "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq gnucash",
             timeout_ms=1_500_000)
    log(f"  install done in {time.time() - t0:.0f}s")

    ver = await sh(d, "gnucash --version 2>&1 | head -3", check=False)
    log(f"  version: {(ver.stdout or '').strip()!r}")


async def main() -> int:
    load_dotenv()
    keep = "--keep" in sys.argv
    client = DesktopClient(api_key=os.environ["SOLARI_API_KEY"], base_url=BASE_URL)
    d = await client.create(template="default", cpu=1, mem_mb=2048,
                            resolution="1280x720", record=True,
                            timeout_ms=60 * 60_000)
    log(f"SESSION_ID={d.sessionId}")
    log(f"watch: {getattr(d, 'streamUrl', '<none>')}")

    ok = False
    try:
        await d.connect()
        for _ in range(60):
            if getattr(await d.health(), "ready", False):
                break
            await asyncio.sleep(2)
        log("desktop ready")

        await install_gnucash(d)

        seed = seed_bytes("base")
        log(f"writing seed book ({len(seed)} bytes)")
        await d.fs.write(BOOK, seed)

        log("opening gnucash")
        await d.open("gnucash", [BOOK])

        # Settle: wait until two consecutive screenshots are identical.
        prev, settled = None, False
        for i in range(45):
            await asyncio.sleep(2)
            shot = await d.screenshot(format="png")
            if prev is not None and shot == prev:
                log(f"screen settled after ~{i * 2}s")
                settled = True
                break
            prev = shot
        if not settled:
            log("screen never settled - capturing anyway")

        shot = await d.screenshot(format="png")
        out = pathlib.Path("verify-seed.png")
        out.write_bytes(shot)
        log(f"screenshot -> {out} ({len(shot)} bytes)")

        # Did GnuCash leave the book readable, and is our data still there?
        log("copying the book out (GnuCash may hold a lock) and re-reading it")
        await sh(d, f"cp {BOOK} {BOOK}.copy")
        data = await d.fs.read(f"{BOOK}.copy")
        log(f"  read back {len(data)} bytes (seed was {len(seed)})")

        con = open_book(write_temp_book(data))
        try:
            n_txn = con.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
            n_acct = con.execute(
                "SELECT COUNT(*) c FROM accounts WHERE account_type != 'ROOT'"
            ).fetchone()["c"]
            ver = dict(con.execute("SELECT table_name, table_version FROM versions"))
            log(f"  transactions={n_txn} accounts={n_acct}")
            log(f"  Gnucash schema version now: {ver.get('Gnucash')}")
            ok = n_txn == 12 and n_acct >= 9
            log(f"  VERDICT: {'PASS' if ok else 'FAIL'}")
        except sqlite3.DatabaseError as exc:
            log(f"  VERDICT: FAIL - book is not readable sqlite: {exc}")

        if keep:
            log("")
            log("Desktop left running. To reuse it:")
            log(f"  export CUBICLE_SESSION_ID={d.sessionId}")
        return 0 if ok else 1
    finally:
        if not keep:
            log("cleaning up")
            try:
                await d.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                await client.destroy(d.sessionId)
            except Exception:  # noqa: BLE001
                pass
            log("destroyed")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
