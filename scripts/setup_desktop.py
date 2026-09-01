"""Prepare a Solari desktop to run cubicle. Idempotent - safe to re-run.

Everything here was learned the hard way; see docs/research/04-probe-findings.md.

  python scripts/setup_desktop.py                 # new desktop, print its id
  CUBICLE_SESSION_ID=... python scripts/setup_desktop.py   # fix up an existing one
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

# GnuCash 4.x stores preferences in GSettings/dconf, not a config file. Writing
# ~/.config/gnucash/gnucash.conf does nothing. Without this, "Tip Of The Day" opens on
# every launch and every agent wastes steps dismissing it - noise, not signal.
# `export $(dbus-launch)` does NOT work - dbus-launch emits semicolon-separated
# statements, so the export mangles them. dbus-run-session is the reliable form, and it
# still writes to the same ~/.config/dconf/user the real X session reads.
# The key is NOT under .general and is NOT called show-tip-of-the-day. Found by
# listing the schema on a live desktop:
#   schema org.gnucash.GnuCash.dialogs.totd, key show-at-startup
DISABLE_TIPS = (
    "dbus-run-session -- gsettings set org.gnucash.GnuCash.dialogs.totd "
    "show-at-startup false 2>/dev/null "
    "|| dbus-run-session -- gsettings set org.gnucash.dialogs.totd "
    "show-at-startup false 2>/dev/null; "
    "dbus-run-session -- gsettings get org.gnucash.GnuCash.dialogs.totd "
    "show-at-startup 2>/dev/null"
)


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


async def sh(d, cmd: str, timeout_ms: int = 600_000, check: bool = False):
    r = await d.exec("sh", args=["-c", cmd], timeout_ms=timeout_ms)
    if check and r.exitCode != 0:
        raise RuntimeError(f"`{cmd[:60]}` exited {r.exitCode}: {(r.stderr or '')[:300]}")
    return r


async def prepare(d) -> None:
    log("apt-get update (a fresh desktop has EMPTY package lists)")
    await sh(d, "apt-get update -qq", check=True)

    log("installing gnucash + libdbd-sqlite3")
    # libdbd-sqlite3 is the libdbi SQLite driver. Without it GnuCash cannot open a
    # SQLite book at all and reports "No suitable backend was found" - which reads
    # exactly like a corrupt file and is not.
    # xdotool lets the harness close stray dialogs by window NAME rather than by
    # hardcoded pixel coordinates.
    await sh(
        d,
        "DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "
        "gnucash libdbd-sqlite3 xdotool",
        timeout_ms=1_500_000,
        check=True,
    )

    r = await sh(d, "ls /usr/lib/*/dbd/ 2>/dev/null | head")
    log(f"  libdbi drivers: {(r.stdout or '').strip() or '<NONE - broken>'}")
    r = await sh(d, "gnucash --version 2>/dev/null | tail -1")
    log(f"  {(r.stdout or '').strip()}")

    log("closing Chrome (the default template auto-starts it over the screen)")
    await sh(d, "pkill -f chrome 2>/dev/null; true")

    log("disabling Tip Of The Day")
    r = await sh(d, DISABLE_TIPS)
    log(f"  gsettings says: {(r.stdout or r.stderr or '').strip()[:200]!r}")


async def verify(d) -> bool:
    """Open the seed and prove from the database that GnuCash really took it.

    Checking that the file still parses proves NOTHING - a book GnuCash never opened
    parses perfectly. The evidence is a row in gnclock.
    """
    log("verifying: opening the seed book")
    await sh(d, "pkill -f gnucash 2>/dev/null; sleep 2; "
                f"rm -rf ~/.local/share/gnucash; rm -f {BOOK}*")
    await d.fs.write(BOOK, seed_bytes("base"))
    await d.open("gnucash", [BOOK])
    await asyncio.sleep(20)

    shot = await d.screenshot(format="png")
    out = pathlib.Path("setup-verify.png")
    out.write_bytes(shot)
    log(f"  screenshot -> {out}  (LOOK AT THIS - automated checks have lied before)")

    await sh(d, f"cp {BOOK} {BOOK}.copy")
    con = open_book(write_temp_book(await d.fs.read(f"{BOOK}.copy")))
    try:
        locks = con.execute("SELECT COUNT(*) c FROM gnclock").fetchone()["c"]
    except Exception as exc:  # noqa: BLE001
        log(f"  gnclock unreadable: {exc}")
        return False
    log(f"  gnclock rows = {locks} -> {'OPENED' if locks else 'NOT OPENED'}")
    return locks > 0


async def main() -> int:
    load_dotenv()
    client = DesktopClient(api_key=os.environ["SOLARI_API_KEY"], base_url=BASE_URL)
    existing = os.environ.get("CUBICLE_SESSION_ID")

    if existing:
        d = await client.connect(existing)
        # client.connect(id) re-attaches but does NOT open the control channel.
        await d.connect()
        log("reusing existing desktop")
    else:
        d = await client.create(template="default", cpu=1, mem_mb=2048,
                                resolution="1280x720", record=True,
                                timeout_ms=60 * 60_000)
        await d.connect()
        for _ in range(60):
            if getattr(await d.health(), "ready", False):
                break
            await asyncio.sleep(2)
        log("created a new desktop")

    log(f"watch: {getattr(d, 'streamUrl', '<none>')}")

    try:
        await prepare(d)
        ok = await verify(d)
        print()
        print("=" * 70)
        print(f"SETUP {'OK' if ok else 'FAILED'}")
        print(f"CUBICLE_SESSION_ID={d.sessionId}")
        print("=" * 70)
        return 0 if ok else 1
    finally:
        try:
            await d.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
