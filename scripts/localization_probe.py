"""Ask several models where things are, and measure how wrong they were.

The benchmark answers "can it do the job". This answers "why not", and it does so
without a desktop: one request per model against a screenshot already on disk.

Ground truth is read off that screenshot, never guessed. Every model gets the identical
question. Output is a table of scale, offset, error in row heights, and R2 - the
arithmetic lives in cubicle/localization.py and is unit tested.

  python scripts/localization_probe.py                       # default screenshot
  python scripts/localization_probe.py shot.png --models a,b

Raw replies are written to results/localization/<timestamp>.json so a number in the
README can be traced back to the sentence a model actually wrote.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import sys
import time

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from cubicle.localization import Ground, aggregate, fit, parse_positions  # noqa: E402

# Read off setup-verify.png at 1280x720, maximized. The account rows are 24px apart:
# 217, 241, 264. Anything added here must come from looking at the image.
TRUTH = Ground({"Assets": 217, "Expenses": 241, "Income": 264}, row_height=24)

QUESTION = (
    "This is a screenshot of the GnuCash accounting application at 1280x720.\n\n"
    "List every account name in the account tree, and for each one give the y pixel\n"
    "coordinate of the centre of its row.\n\n"
    "Answer with one line per account, in exactly this form:\n"
    "  <account name> y=<number>\n"
    "If you cannot read something, say so rather than guessing."
)

# Free, image-in / text-out, verified against openrouter.ai/api/v1/models on 2026-09-02.
# inkling and inkling-small are excluded: they answer 403 "only available on agentic
# harnesses" and never see the image at all.
DEFAULT_MODELS = (
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "minimax/minimax-m3:free",
    "dots-studio/dots-3-note-preview:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
)


def ask(client, base_url, key, model, b64, max_tokens):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    r = client.post(
        f"{base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json={
            "model": model,
            "temperature": 0.0,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": QUESTION},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        },
    )
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:120]}"
    try:
        choice = r.json()["choices"][0]
        text = (choice["message"].get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001
        return None, f"unreadable response: {exc}"
    if not text:
        return None, f"empty (finish_reason={choice.get('finish_reason')})"
    return text, None


def main(argv: list[str]) -> int:
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("screenshot", nargs="?", default="setup-verify.png")
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--max-tokens", type=int, default=1200)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--repeat", type=int, default=1,
                    help="runs per model. One run is not a measurement - these "
                         "models are not deterministic even at temperature 0.")
    ap.add_argument("--pause", type=float, default=8.0,
                    help="seconds between calls; free tiers throttle fast")
    args = ap.parse_args(argv[1:])

    shot = pathlib.Path(args.screenshot)
    if not shot.exists():
        print(f"no such screenshot: {shot}", file=sys.stderr)
        return 2

    base_url = os.environ.get("CUBICLE_VISION_BASE_URL", "https://openrouter.ai/api/v1")
    key = os.environ.get("CUBICLE_VISION_API_KEY")
    b64 = base64.b64encode(shot.read_bytes()).decode()
    models = [m.strip() for m in args.models.split(",") if m.strip()]

    print(f"screenshot : {shot}")
    print(f"endpoint   : {base_url}")
    print(f"truth      : " + ", ".join(f"{k} y={v}" for k, v in TRUTH.positions.items()))
    print(f"row height : {TRUTH.row_height}px\n")

    records = []
    with httpx.Client(timeout=180.0) as client:
        for model in models:
            fits = []
            for run in range(args.repeat):
                text = err = None
                for attempt in range(args.retries):
                    text, err = ask(client, base_url, key, model, b64, args.max_tokens)
                    if text or not err.startswith("HTTP 429"):
                        break
                    time.sleep(20 * (attempt + 1))

                if not text:
                    print(f"  {model:52s} run {run + 1} -- {err}")
                    records.append({"model": model, "run": run, "error": err})
                else:
                    claimed = parse_positions(text)
                    f = fit(claimed, TRUTH)
                    fits.append(f)
                    if args.repeat == 1:
                        print(f"  {f.summary(model)}")
                    else:
                        print(f"    run {run + 1}: {f.summary(model)}")
                    records.append(
                        {
                            "model": model,
                            "run": run,
                            "raw": text,
                            "parsed": claimed,
                            "n": f.n,
                            "named_correctly": f.named_correctly,
                            "total_names": f.total_names,
                            "scale": f.scale,
                            "offset": f.offset,
                            "r_squared": f.r_squared,
                            "mean_abs_error_px": f.mean_abs_error_px,
                            "mean_abs_error_rows": f.mean_abs_error_rows,
                            "residuals": f.residuals,
                        }
                    )
                if run + 1 < args.repeat:
                    time.sleep(args.pause)

            if args.repeat > 1 and fits:
                agg = aggregate(fits)
                print(f"  => {agg.summary(model)}")
                records.append({"model": model, "aggregate": {
                    "runs": agg.runs, "unmeasurable": agg.unmeasurable,
                    "mean_scale": agg.mean_scale, "scale_stdev": agg.scale_stdev,
                    "min_scale": agg.min_scale, "max_scale": agg.max_scale,
                    "mean_error_rows": agg.mean_error_rows,
                    "min_error_rows": agg.min_error_rows,
                    "max_error_rows": agg.max_error_rows}})
            time.sleep(args.pause)

    out = pathlib.Path("results/localization")
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(
        json.dumps(
            {
                "screenshot": str(shot),
                "truth": TRUTH.positions,
                "row_height": TRUTH.row_height,
                "question": QUESTION,
                "results": records,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nraw replies -> {path}")

    # Count MODELS, not runs. With --repeat this previously counted four runs of one
    # model and printed "4/5 models", which overstates the coverage of every table
    # built from this output.
    answered = {r["model"] for r in records if r.get("n", 0) >= 3}
    runs_ok = sum(1 for r in records if r.get("n", 0) >= 3)
    print(f"{len(answered)}/{len(models)} models produced a measurable answer "
          f"({runs_ok} usable runs of {args.repeat * len(models)} attempted)")
    if len(answered) < len(models):
        missing = [m for m in models if m not in answered]
        print("no answer from: " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
