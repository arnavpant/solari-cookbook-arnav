"""Run the benchmark.

Needs a desktop prepared by scripts/setup_desktop.py (GnuCash + libdbd-sqlite3 +
xdotool installed, Chrome closed, Tip Of The Day disabled). Point CUBICLE_SESSION_ID at
it; every task resets that machine in software rather than reverting a snapshot.

  python scripts/run.py --agent oracle --tasks t01
  python scripts/run.py --agent oracle --tasks all
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import os
import sys
import time
from pathlib import Path

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402
from solari_desktop import DesktopClient  # noqa: E402

from cubicle.desktop import CubicleDesktop  # noqa: E402
from cubicle.harness import run_task  # noqa: E402
from cubicle.tasks import ORACLE_PENDING, SCORED, TASKS  # noqa: E402

BASE_URL = "https://api.getsolari.com"


def build_agent(name: str, cd, task):
    if name == "oracle":
        from cubicle.agents.oracle import OracleAgent

        return OracleAgent(cd, task)
    if name == "gemini":
        from cubicle.agents.gemini import GeminiAgent

        return GeminiAgent(os.environ["GEMINI_API_KEY"])
    if name == "deepseek":
        from cubicle.agents.deepseek import DeepSeekAgent

        return DeepSeekAgent(os.environ["DEEPSEEK_API_KEY"])
    raise SystemExit(f"unknown agent: {name}")


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, choices=["oracle", "gemini", "deepseek"])
    ap.add_argument("--tasks", default="all",
                    help="comma-separated task ids, or 'all' (the scored suite)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--no-trace", action="store_true")
    args = ap.parse_args()

    # "all" is the SCORED suite: the tasks with a recorded oracle, and so the only ones
    # proven solvable. A task in ORACLE_PENDING has a finished seed, prompt and grader,
    # but nobody has yet shown a machine can complete it - scoring a model against it
    # would put an unproven task in the denominator. Name it explicitly to run it.
    ids = list(SCORED) if args.tasks == "all" else args.tasks.split(",")
    for tid in ids:
        if tid not in TASKS:
            raise SystemExit(f"unknown task {tid!r}; known: {', '.join(TASKS)}")

    if args.agent == "oracle":
        pending = [t for t in ids if t in ORACLE_PENDING]
        if pending:
            raise SystemExit(
                f"no recorded oracle for {', '.join(pending)}. Their graders are complete "
                "and tested offline; what is missing is coordinates read off a live "
                "desktop. This suite does not guess coordinates."
            )

    run_id = args.run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{args.agent}"
    out = Path("results") / run_id
    out.mkdir(parents=True, exist_ok=True)

    # One owned loop for the whole process. The Desktop handle is async even when it
    # comes from SyncDesktopClient, and its httpx/websocket clients bind to the loop
    # they were created on - a second loop fails in confusing ways.
    loop = asyncio.new_event_loop()
    client = DesktopClient(api_key=os.environ["SOLARI_API_KEY"], base_url=BASE_URL)
    sid = os.environ["CUBICLE_SESSION_ID"]
    d = loop.run_until_complete(client.connect(sid))
    loop.run_until_complete(d.connect())  # client.connect() alone does NOT do this
    cd = CubicleDesktop(d, loop)

    if not cd.gnucash_installed():
        raise SystemExit("gnucash is not installed - run scripts/setup_desktop.py first")

    results = []
    try:
        for tid in ids:
            task = TASKS[tid]
            agent = build_agent(args.agent, cd, task)
            print(f"[{args.agent}] {tid} ({task.tier}, cap {task.max_steps}) ...", flush=True)
            t0 = time.monotonic()
            trace = None if args.no_trace else out / "traces" / args.agent / tid
            r = run_task(cd, agent, task, trace_dir=trace)
            mark = "PASS" if r.outcome == "pass" else r.outcome.upper()
            print(
                f"  -> {mark}  steps {r.steps_used}/{r.max_steps}  "
                f"{time.monotonic() - t0:.0f}s  {r.reason[:90]}"
            )
            results.append(dataclasses.asdict(r))
            (out / "results.json").write_text(json.dumps(results, indent=2))
    finally:
        try:
            loop.run_until_complete(d.close())
        except Exception:  # noqa: BLE001
            pass

    passed = sum(1 for r in results if r["outcome"] == "pass")
    print(f"\n{args.agent}: {passed}/{len(results)}   -> {out / 'results.json'}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
