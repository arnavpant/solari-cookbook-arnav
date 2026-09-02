"""Does a model point worse when it is asked to act than when it is asked to look?

MiniMax-M3 describes the GnuCash account tree accurately - it puts rows that are truly
at y=217/241/264 at 222/245/269 - and then, driving the same screen through the
benchmark, clicks at a mean y of 298. Something is lost between seeing and acting.

But those two numbers came from two different prompts, so "describe vs act" was
confounded with "different prompt". This is the control. Same model, same screenshot,
same request, in the same session; the only thing that varies is what the model is
asked to produce:

  DESCRIBE : "where is the Expenses row?" -> a number
  ACT      : the committed benchmark system prompt -> {"kind":"click","x":..,"y":..}

If the ACT coordinates sit lower than the DESCRIBE coordinates on the same image, the
deficit is not perception. The model knows where the row is and cannot aim at it.

  python scripts/describe_vs_act.py --repeat 6
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import statistics
import sys
import time

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from cubicle.agents._json_action import parse_action  # noqa: E402
from cubicle.harness import UnparseableResponse  # noqa: E402
from cubicle.localization import parse_positions  # noqa: E402

SYSTEM = (
    pathlib.Path("cubicle/agents/system_prompt.txt").read_text(encoding="utf-8")
)

# One row, named the same way in both conditions, so the two answers are comparable.
TARGET = "Expenses"
TRUE_Y = 241
ROW_H = 24

DESCRIBE = (
    "This is a screenshot of the GnuCash accounting application at 1280x720.\n"
    f"Give the y pixel coordinate of the centre of the '{TARGET}' row in the account "
    "tree.\n"
    f"Answer with exactly one line, in this form:  {TARGET} y=<number>"
)

# Deliberately phrased as a benchmark task, because that is the condition under test.
ACT_TASK = (
    f"In GnuCash, click on the '{TARGET}' account row in the account tree to select it.\n"
    "Respond with a single click action."
)


def call(client, base_url, key, model, messages, max_tokens):
    r = client.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}"} if key else {},
        json={
            "model": model,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "messages": messages,
        },
    )
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:110]}"
    try:
        text = (r.json()["choices"][0]["message"].get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001
        return None, f"unreadable: {exc}"
    return (text, None) if text else (None, "empty reply")


def image_part(b64):
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def describe_y(client, base_url, key, model, b64, max_tokens):
    text, err = call(client, base_url, key, model, [
        {"role": "user", "content": [{"type": "text", "text": DESCRIBE}, image_part(b64)]}
    ], max_tokens)
    if err:
        return None, err
    found = parse_positions(text)
    y = found.get(TARGET.lower())
    return (y, None) if y is not None else (None, f"no coordinate in: {text[:70]!r}")


def act_y(client, base_url, key, model, b64, max_tokens):
    """The benchmark's own condition: committed system prompt, one action expected."""
    text, err = call(client, base_url, key, model, [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": f"Task: {ACT_TASK}\n\nThis is step 1 of at most 15. "
                                     "The last image is the current screen."},
            image_part(b64),
        ]},
    ], max_tokens)
    if err:
        return None, err
    try:
        action = parse_action(text)
    except UnparseableResponse as exc:
        return None, f"unparseable: {str(exc)[:70]}"
    if action.y is None:
        return None, f"action has no y: {action.kind}"
    return float(action.y), None


def main(argv):
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("screenshot", nargs="?", default="setup-verify.png")
    ap.add_argument("--model", default=os.environ.get("CUBICLE_VISION_MODEL"))
    ap.add_argument("--repeat", type=int, default=6)
    ap.add_argument("--pause", type=float, default=6.0)
    ap.add_argument("--max-tokens", type=int, default=800)
    args = ap.parse_args(argv[1:])

    shot = pathlib.Path(args.screenshot)
    if not shot.exists():
        print(f"no such screenshot: {shot}", file=sys.stderr)
        return 2

    base_url = os.environ.get("CUBICLE_VISION_BASE_URL", "https://openrouter.ai/api/v1")
    key = os.environ.get("CUBICLE_VISION_API_KEY")
    b64 = base64.b64encode(shot.read_bytes()).decode()

    print(f"model      : {args.model}")
    print(f"screenshot : {shot}")
    print(f"target     : {TARGET} row, true y={TRUE_Y}, row height {ROW_H}px")
    print(f"conditions : DESCRIBE (asked for a number) vs ACT (benchmark system prompt)\n")

    desc, act, errs = [], [], []
    with httpx.Client(timeout=180.0) as client:
        for i in range(args.repeat):
            dy, derr = describe_y(client, base_url, key, args.model, b64, args.max_tokens)
            time.sleep(args.pause)
            ay, aerr = act_y(client, base_url, key, args.model, b64, args.max_tokens)
            time.sleep(args.pause)

            if dy is not None:
                desc.append(dy)
            else:
                errs.append(f"describe: {derr}")
            if ay is not None:
                act.append(ay)
            else:
                errs.append(f"act: {aerr}")

            d = f"{dy:.0f}" if dy is not None else "--"
            a = f"{ay:.0f}" if ay is not None else "--"
            print(f"  round {i + 1}:  describe y={d:>5}   act y={a:>5}")

    print()
    out = {"model": args.model, "screenshot": str(shot), "target": TARGET,
           "true_y": TRUE_Y, "row_height": ROW_H,
           "describe": desc, "act": act, "errors": errs}

    for label, vals in (("DESCRIBE", desc), ("ACT", act)):
        if not vals:
            print(f"{label:9s} no usable answers")
            continue
        mean = statistics.fmean(vals)
        err_rows = abs(mean - TRUE_Y) / ROW_H
        spread = f"{min(vals):.0f}-{max(vals):.0f}" if len(vals) > 1 else f"{vals[0]:.0f}"
        print(f"{label:9s} n={len(vals)}  mean y={mean:6.1f}  [{spread}]  "
              f"error {mean - TRUE_Y:+.0f}px ({err_rows:.1f} rows)")
        out[f"{label.lower()}_mean"] = mean

    if desc and act:
        gap = statistics.fmean(act) - statistics.fmean(desc)
        out["gap_px"] = gap
        print(f"\ngap       ACT - DESCRIBE = {gap:+.0f}px ({gap / ROW_H:+.1f} rows)")
        if abs(gap) < ROW_H:
            print("          under one row: the two conditions agree. The deficit is")
            print("          perception, not the transition into an action.")
        else:
            print("          more than one row apart: the model states a better")
            print("          coordinate than it acts on. Knowing where the row is and")
            print("          aiming at it are separate failures.")

    if errs:
        print(f"\n{len(errs)} failed call(s): " + "; ".join(errs[:4]))

    d = pathlib.Path("results/localization")
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"describe-vs-act-{time.strftime('%Y%m%d-%H%M%S')}.json"
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\n-> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
