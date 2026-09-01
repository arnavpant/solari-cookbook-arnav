"""Diagnose and fix 'No suitable backend was found for /root/book.gnucash'.

GnuCash reaches SQL backends through libdbi, whose SQLite driver ships in a SEPARATE
package (libdbd-sqlite3). Without it GnuCash sees a .gnucash file, fails to match a
backend, and refuses to open - which looks exactly like a corrupt book.

Reuses an existing desktop so we do not reinstall GnuCash:
    CUBICLE_SESSION_ID=... python scripts/fix_backend.py

The check here is programmatic, not visual: a GnuCash SQLite book that has been opened
successfully has a row in its `gnclock` table. Checking that the file still parses is
NOT evidence of anything - a book GnuCash never touched parses perfectly.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
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


async def sh(d, cmd: str, timeout_ms: int = 600_000, check: bool = False):
    r = await d.exec("sh", args=["-c", cmd], timeout_ms=timeout_ms)
    if check and r.exitCode != 0:
        raise RuntimeError(f"`{cmd[:60]}` exited {r.exitCode}: {(r.stderr or '')[:300]}")
    return r


async def open_and_check(d, target: str, label: str) -> bool:
    """Open `target` in GnuCash and decide, from the database, whether it worked."""
    log(f"--- attempt: {label} ---")
    await sh(d, "pkill -x gnucash 2>/dev/null; sleep 2; "
                f"rm -rf ~/.config/gnucash ~/.local/share/gnucash ~/.gnucash; rm -f {BOOK}*")
    await d.fs.write(BOOK, seed_bytes("base"))

    await d.open("gnucash", [target])
    await asyncio.sleep(20)

    shot = await d.screenshot(format="png")
    out = pathlib.Path(f"backend-{label}.png")
    out.write_bytes(shot)
    log(f"  screenshot -> {out}")

    await sh(d, f"cp {BOOK} {BOOK}.copy")
    con = open_book(write_temp_book(await d.fs.read(f"{BOOK}.copy")))
    try:
        locks = con.execute("SELECT COUNT(*) c FROM gnclock").fetchone()["c"]
    except Exception as exc:  # noqa: BLE001
        log(f"  gnclock unreadable: {exc}")
        return False
    log(f"  gnclock rows = {locks}  -> {'OPENED' if locks > 0 else 'NOT OPENED'}")
    return locks > 0


async def main() -> int:
    load_dotenv()
    sid = os.environ.get("CUBICLE_SESSION_ID")
    if not sid:
        print("set CUBICLE_SESSION_ID to an existing desktop", file=sys.stderr)
        return 2

    client = DesktopClient(api_key=os.environ["SOLARI_API_KEY"], base_url=BASE_URL)
    d = await client.connect(sid)
    # client.connect(id) re-attaches and returns the handle, but does NOT open the
    # control channel. You still need d.connect(). Two different connect() methods.
    await d.connect()
    try:
        log("connected to existing desktop")

        r = await sh(d, "dpkg -l | grep -c libdbd-sqlite3")
        log(f"libdbd-sqlite3 installed? {(r.stdout or '').strip()}")
        r = await sh(d, "ls /usr/lib/*/dbd/ 2>/dev/null; ls /usr/lib/dbd/ 2>/dev/null")
        log(f"libdbi drivers present: {(r.stdout or '').strip() or '<none>'}")

        log("installing libdbd-sqlite3")
        await sh(d, "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libdbd-sqlite3",
                 timeout_ms=600_000, check=True)
        r = await sh(d, "ls /usr/lib/*/dbd/ 2>/dev/null; ls /usr/lib/dbd/ 2>/dev/null")
        log(f"libdbi drivers now: {(r.stdout or '').strip() or '<none>'}")

        # Quieten the desktop: Chrome auto-starts on the default template and the
        # Tip Of The Day dialog steals focus on first run.
        log("closing Chrome and disabling Tip Of The Day")
        await sh(d, "pkill -x chrome 2>/dev/null; true")
        await sh(d, "mkdir -p ~/.config/gnucash && "
                    "printf '[general]\\ntip-of-the-day=false\\n' "
                    "> ~/.config/gnucash/gnucash.conf; true")

        if await open_and_check(d, BOOK, "plainpath"):
            log("RESULT: plain path works once libdbd-sqlite3 is installed")
            return 0
        if await open_and_check(d, f"sqlite3://{BOOK}", "sqlite3uri"):
            log("RESULT: needs the sqlite3:// URI form")
            return 0

        log("RESULT: still failing - inspect backend-*.png")
        return 1
    finally:
        try:
            await d.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
