"""Drive GnuCash by hand, one step at a time, screenshotting as you go.

This is how oracle coordinates get recorded. Every coordinate in a task's oracle() must
come from a screenshot someone actually looked at - never from a guess.

  # fresh book, then click the New toolbar button
  python scripts/drive.py --fresh '[{"kind":"click","x":389,"y":115}]'

  # keep going from where you left off
  python scripts/drive.py '[{"kind":"type","text":"Software Subscriptions"}]'

  # just look
  python scripts/drive.py --shot

  # what does the database say right now?
  python scripts/drive.py --db
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402
from solari_desktop import DesktopClient  # noqa: E402

from cubicle.desktop import BOOK_COPY, BOOK_PATH, CubicleDesktop  # noqa: E402
from cubicle.fixtures.build_seed import seed_bytes  # noqa: E402
from cubicle.grading import open_book, write_temp_book  # noqa: E402
from cubicle.types import Action  # noqa: E402

BASE_URL = "https://api.getsolari.com"
SHOTS = pathlib.Path("drive")


def describe_db(data: bytes) -> str:
    con = open_book(write_temp_book(data))
    accts = con.execute(
        "SELECT name, account_type FROM accounts WHERE account_type != 'ROOT' ORDER BY name"
    ).fetchall()
    n_txn = con.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"]
    try:
        locks = con.execute("SELECT COUNT(*) c FROM gnclock").fetchone()["c"]
    except Exception:  # noqa: BLE001
        locks = "?"
    names = ", ".join(a["name"] for a in accts)
    return f"accounts({len(accts)}): {names}\ntransactions: {n_txn}\ngnclock: {locks}"


async def main() -> int:
    load_dotenv()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    variant = "base"
    for f in list(flags):
        if f.startswith("--variant="):
            variant = f.split("=", 1)[1]

    SHOTS.mkdir(exist_ok=True)
    client = DesktopClient(api_key=os.environ["SOLARI_API_KEY"], base_url=BASE_URL)
    d = await client.connect(os.environ["CUBICLE_SESSION_ID"])
    await d.connect()

    loop = asyncio.get_running_loop()

    # CubicleDesktop is sync and owns a loop; here we are already inside one, so drive
    # the handle directly rather than nesting run_until_complete.
    async def shot(label: str) -> None:
        png = await d.screenshot(format="png")
        out = SHOTS / f"{label}.png"
        out.write_bytes(png)
        print(f"  shot -> {out}")

    async def sh(cmd: str):
        return await d.exec("sh", args=["-c", cmd], timeout_ms=120_000)

    try:
        if "--fresh" in flags:
            print(f"resetting and opening a fresh '{variant}' book")
            await sh(
                "pkill -x gnucash 2>/dev/null; sleep 2; "
                f"rm -rf ~/.local/share/gnucash; rm -f {BOOK_PATH}* {BOOK_COPY}*"
            )
            await d.fs.write(BOOK_PATH, seed_bytes(variant))
            await d.open("gnucash", [BOOK_PATH])
            await asyncio.sleep(18)
            await sh('xdotool search --name "Tip Of The Day" windowclose 2>/dev/null; true')
            await asyncio.sleep(1)
            await shot("00-fresh")

        if args:
            actions = [Action(**a) for a in json.loads(args[0])]
            for i, act in enumerate(actions):
                print(f"[{i}] {act.kind} {act.x or ''},{act.y or ''} {act.text or ''}")
                if act.kind == "click":
                    await d.mouse.click(act.x, act.y, humanize=True)
                elif act.kind == "double_click":
                    await d.mouse.double_click(act.x, act.y)
                elif act.kind == "type":
                    await d.keyboard.type(act.text)
                elif act.kind == "key":
                    await d.keyboard.press(act.text)
                elif act.kind == "scroll":
                    await d.mouse.scroll(
                        act.x, act.y,
                        direction=act.scroll_direction or "down",
                        amount=act.scroll_amount or 3,
                    )
                await asyncio.sleep(2.0)
                await shot(f"{i:02d}-{act.kind}")

        if "--shot" in flags:
            await shot("now")

        if "--db" in flags:
            # Deliberately does NOT press Save. If GnuCash's SQLite backend really
            # commits on every edit, changes are here already.
            await sh(f"cp {BOOK_PATH} {BOOK_COPY}")
            print()
            print(describe_db(await d.fs.read(BOOK_COPY)))
        return 0
    finally:
        await d.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
