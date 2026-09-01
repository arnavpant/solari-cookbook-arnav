"""Explain WHY a run failed, from its trace.

A score tells you an agent failed. This tells you how. It is the difference between
"DeepSeek got 0/7" and "DeepSeek clicked empty space at y=333 twelve times and never
noticed the screen had not changed" - and only the second is worth publishing.

  python scripts/analyze_trace.py results/<run-id>
  python scripts/analyze_trace.py results/<run-id> --task t01
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load_steps(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def summarise(task_id: str, steps: list[dict]) -> None:
    if not steps:
        print(f"  {task_id}: no trace")
        return

    actions = [s["action"] for s in steps if "action" in s]
    errors = [s for s in steps if "error" in s]
    provider = [s for s in steps if "provider_error" in s]
    moved = sum(1 for s in steps if s.get("screen_changed_since_last"))

    kinds = Counter(a["kind"] for a in actions)
    clicks = [(a["x"], a["y"]) for a in actions if a.get("x") is not None]

    print(f"  {task_id}: {len(steps)} steps, "
          f"{len(actions)} actions, {len(errors)} unparseable, "
          f"{len(provider)} provider errors, screen moved {moved}x")
    if kinds:
        print(f"       kinds: {', '.join(f'{k}x{n}' for k, n in kinds.most_common())}")

    if clicks:
        ys = Counter(y // 10 * 10 for _, y in clicks)
        band, count = ys.most_common(1)[0]
        if count >= max(3, len(clicks) // 2):
            # The signature of a stuck agent: same band, over and over, no effect.
            print(f"       STUCK: {count}/{len(clicks)} clicks in the y={band}-{band + 9} "
                  f"band; the screen moved only {moved} time(s)")

    if len(actions) >= 4 and moved <= 1:
        print("       NOTE: the agent kept acting on a screen that never changed - "
              "it never detected its own no-ops")

    for s in provider[:1]:
        print(f"       provider: {s['provider_error'][:100]}")
    for s in errors[:2]:
        print(f"       parse err: {s['error'][:100]}")


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    only = None
    for a in argv[1:]:
        if a.startswith("--task"):
            only = a.split("=", 1)[1] if "=" in a else None
    if not args:
        runs = sorted(Path("results").glob("*/"))
        if not runs:
            print("usage: python scripts/analyze_trace.py results/<run-id>", file=sys.stderr)
            return 2
        run = runs[-1]
    else:
        run = Path(args[0])

    results_file = run / "results.json"
    if not results_file.exists():
        print(f"no results.json in {run}", file=sys.stderr)
        return 2

    results = json.loads(results_file.read_text(encoding="utf-8"))
    agent = results[0]["agent"] if results else "?"
    passed = sum(1 for r in results if r["outcome"] == "pass")
    unscored = sum(1 for r in results if r["outcome"] == "provider_error")
    scored = len(results) - unscored

    print(f"\n{run}  -  {agent}")
    print(f"score: {passed}/{scored}" + (f"  ({unscored} unscored)" if unscored else ""))
    print()

    for r in results:
        if only and r["task_id"] != only:
            continue
        # Traces are filed under the CLI agent name ("deepseek") while results record
        # the model id ("deepseek-v4-flash-vision-exp"). Find it either way.
        candidates = list((run / "traces").glob(f"*/{r['task_id']}/actions.jsonl"))
        trace = candidates[0] if candidates else run / "traces" / agent / r["task_id"] / "actions.jsonl"
        print(f"{r['task_id']}  {r['outcome'].upper()}  -  {r['reason'][:70]}")
        summarise(r["task_id"], load_steps(trace))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
