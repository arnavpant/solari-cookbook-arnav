"""results.json -> a single self-contained report.html.

No JS libraries, no CDN, no build step: inline SVG and a little CSS. A benchmark's
report should be as re-derivable as its scores.

Design notes, because they are deliberate rather than taste:
  - Horizontal bars. The job is magnitude across a handful of named entities whose
    labels are long; bars beat a pie or a radar, and the entity names sit inline.
  - ONE hue. Every bar encodes the same measure, so there is no categorical identity
    to encode and therefore no legend - the title names the series. Validated against
    both surfaces (contrast >= 3:1 light and dark).
  - Data-ends rounded 4px, baseline end square, 2px surface gap between bars.
  - Dark mode is declared under both the media query and the [data-theme] scope, so a
    viewer's explicit toggle wins in either direction.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

BAR_H = 26
BAR_GAP = 4  # >= 2px surface gap between adjacent fills
LABEL_W = 200
TRACK_W = 520
VALUE_W = 260  # room for the score AND its note, which used to clip

CSS = """
:root {
  color-scheme: light;
  --surface: #fcfcfb;
  --surface-sunk: #f2f1ee;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --text-muted: #7a7873;
  --rule: #e0dfda;
  --series: #2a78d6;
  --track: #eceae5;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface: #1a1a19;
    --surface-sunk: #232322;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted: #8f8e86;
    --rule: #35342f;
    --series: #3987e5;
    --track: #2a2a28;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface: #1a1a19;
  --surface-sunk: #232322;
  --text-primary: #ffffff;
  --text-secondary: #c3c2b7;
  --text-muted: #8f8e86;
  --rule: #35342f;
  --series: #3987e5;
  --track: #2a2a28;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 48px 24px 72px;
  background: var(--surface); color: var(--text-primary);
  font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 980px; margin: 0 auto; }
h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: -0.02em; }
.sub { color: var(--text-secondary); margin: 0 0 36px; font-size: 16px; }
h2 { font-size: 17px; margin: 40px 0 4px; letter-spacing: -0.01em; }
.note { color: var(--text-muted); font-size: 13px; margin: 0 0 18px; }
figure { margin: 0; }
.wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 7px 10px; text-align: left; border-bottom: 1px solid var(--rule); }
th { color: var(--text-secondary); font-weight: 600; font-size: 12px;
     text-transform: uppercase; letter-spacing: 0.04em; }
td.num { font-variant-numeric: tabular-nums; color: var(--text-secondary); }
.pill { display: inline-block; padding: 1px 8px; border-radius: 999px;
        font-size: 12px; font-weight: 600; border: 1px solid var(--rule); }
.pass { color: #0a6b3d; border-color: #0a6b3d55; }
:root[data-theme="dark"] .pass, :root:not([data-theme="light"]) .pass { color: #45c08a; }
.reason { color: var(--text-muted); font-size: 13px; }
footer { margin-top: 46px; padding-top: 18px; border-top: 1px solid var(--rule);
         color: var(--text-muted); font-size: 13px; }
code { background: var(--surface-sunk); padding: 1px 5px; border-radius: 4px;
       font-size: 13px; }
"""


def _bar_path(x: float, y: float, w: float, h: float, r: float = 4.0) -> str:
    """Rounded at the data end only; square where it meets the baseline."""
    if w <= 0.5:
        return ""
    r = min(r, w, h / 2)
    return (
        f"M{x},{y} H{x + w - r} Q{x + w},{y} {x + w},{y + r} "
        f"V{y + h - r} Q{x + w},{y + h} {x + w - r},{y + h} H{x} Z"
    )


def leaderboard_svg(rows: list[tuple[str, int, int, str]]) -> str:
    """rows: (label, passed, total, note). A total of 0 renders as an empty track."""
    total = max((t for _, _, t, _ in rows if t), default=1)
    # Trailing gap only, not a whole row's worth - an unused band under the last bar
    # reads as a missing series.
    height = len(rows) * (BAR_H + BAR_GAP) - BAR_GAP + 2
    width = LABEL_W + TRACK_W + VALUE_W
    out = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'role="img" aria-label="Tasks passed by agent" font-family="inherit">'
    ]
    for i, (label, passed, tot, note) in enumerate(rows):
        y = i * (BAR_H + BAR_GAP)
        frac = (passed / total) if tot else 0.0
        out.append(
            f'<text x="{LABEL_W - 12}" y="{y + BAR_H / 2 + 5}" text-anchor="end" '
            f'font-size="14" fill="var(--text-primary)">{html.escape(label)}</text>'
        )
        if tot:
            out.append(
                f'<rect x="{LABEL_W}" y="{y}" width="{TRACK_W}" height="{BAR_H}" '
                f'rx="4" fill="var(--track)"/>'
            )
            path = _bar_path(LABEL_W, y, TRACK_W * frac, BAR_H)
            if path:
                out.append(
                    f'<path d="{path}" fill="var(--series)">'
                    f"<title>{html.escape(label)}: {passed} of {tot} tasks passed</title>"
                    f"</path>"
                )
            label_txt = f"{passed}/{tot}"
            out.append(
                f'<text x="{LABEL_W + TRACK_W + 12}" y="{y + BAR_H / 2 + 5}" '
                f'font-size="14" font-variant-numeric="tabular-nums" '
                f'fill="var(--text-primary)">{label_txt}</text>'
            )
            if note:
                out.append(
                    f'<text x="{LABEL_W + TRACK_W + 12 + 46}" y="{y + BAR_H / 2 + 5}" '
                    f'font-size="11" fill="var(--text-muted)">{html.escape(note)}</text>'
                )
        else:
            out.append(
                f'<rect x="{LABEL_W}" y="{y}" width="{TRACK_W}" height="{BAR_H}" rx="4" '
                f'fill="none" stroke="var(--text-muted)" stroke-width="1.5" '
                f'stroke-dasharray="5 4" opacity="0.75"/>'
            )
            out.append(
                f'<text x="{LABEL_W + TRACK_W + 12}" y="{y + BAR_H / 2 + 5}" '
                f'font-size="13" fill="var(--text-muted)">{html.escape(note)}</text>'
            )
    out.append("</svg>")
    return "".join(out)


def matrix_table(runs: dict[str, list[dict]], task_ids: list[str]) -> str:
    head = "".join(f"<th>{html.escape(t)}</th>" for t in task_ids)
    body = []
    for agent, results in runs.items():
        by_id = {r["task_id"]: r for r in results}
        cells = []
        for tid in task_ids:
            r = by_id.get(tid)
            if r is None:
                cells.append('<td class="reason">-</td>')
            elif r["outcome"] == "pass":
                cells.append('<td><span class="pill pass">pass</span></td>')
            else:
                cells.append(
                    f'<td><span class="pill">{html.escape(r["outcome"])}</span></td>'
                )
        body.append(f"<tr><td>{html.escape(agent)}</td>{''.join(cells)}</tr>")
    return (
        f'<div class="wrap"><table><thead><tr><th>Agent</th>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
    )


def detail_table(runs: dict[str, list[dict]]) -> str:
    rows = []
    for agent, results in runs.items():
        for r in results:
            rows.append(
                f"<tr><td>{html.escape(agent)}</td><td>{html.escape(r['task_id'])}</td>"
                f'<td><span class="pill{" pass" if r["outcome"] == "pass" else ""}">'
                f"{html.escape(r['outcome'])}</span></td>"
                f'<td class="num">{r["steps_used"]}/{r["max_steps"]}</td>'
                f'<td class="num">{r.get("model_seconds", 0):.0f}s</td>'
                f'<td class="reason">{html.escape(r["reason"][:110])}</td></tr>'
            )
    return (
        '<div class="wrap"><table><thead><tr><th>Agent</th><th>Task</th><th>Outcome</th>'
        "<th>Steps</th><th>Model time</th><th>Why it failed</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render(runs: dict[str, list[dict]]) -> str:
    task_ids = sorted({r["task_id"] for rs in runs.values() for r in rs})

    scored = []
    for agent, results in runs.items():
        # The headline is ONE run - the most recent - not every run ever done added
        # together. results/ keeps the whole history, including early runs that crashed
        # before the environment was right; summing those reported "oracle 23/25" and
        # made the reference solution look unreliable when it is 7/7. The full history
        # stays visible in the tables below.
        latest = max((r.get("run", "") for r in results), default="")
        current = [r for r in results if r.get("run", "") == latest] or results

        # A provider outage is not an agent failure. Excluding it from the denominator
        # keeps the score honest: a model is never punished for its vendor throttling us.
        attempted = [r for r in current if r["outcome"] != "provider_error"]
        skipped = len(current) - len(attempted)
        passed = sum(1 for r in attempted if r["outcome"] == "pass")

        runs_done = len({r.get("run", "") for r in results})
        if agent == "oracle":
            note = "reference - proves solvable"
        elif skipped:
            note = f"{skipped} unscored (provider unavailable)"
        elif runs_done > 1:
            note = f"latest of {runs_done} runs"
        else:
            note = ""
        scored.append((agent, passed, len(attempted), note))
    scored.sort(key=lambda row: (-row[1], row[0]))
    scored.append(("Pinetree-CUA", 0, 0, "untested"))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>cubicle results</title>
<style>{CSS}</style></head>
<body><main>
<h1>cubicle</h1>
<p class="sub">A computer-use benchmark for software that has no API.
GnuCash on a Solari cloud desktop, driven only through pixels, keyboard and mouse.</p>

<h2>Tasks passed</h2>
<p class="note">Out of {len(task_ids)} bookkeeping tasks. Every score is a SQL assertion
over the book GnuCash itself wrote - no model judged anything.</p>
<figure>{leaderboard_svg(scored)}</figure>

<h2>Per task</h2>
<p class="note">The oracle row is the proof the suite is solvable at all.</p>
{matrix_table(runs, task_ids)}

<h2>Every run</h2>
<p class="note">Failures name the assertion that failed, so a result is diagnosable
without watching a replay.</p>
{detail_table(runs)}

<footer>
Grading reads the GnuCash SQLite book with <code>sqlite3</code> and nothing else.
No LLM judge, no screenshot diffing, no human review. Agents receive pixels, mouse and
keyboard - the clipboard, shell and filesystem are deliberately outside the action space.
</footer>
</main></body></html>
"""


def load(paths: list[Path]) -> dict[str, list[dict]]:
    """Group results by agent, tagging each record with the run it came from.

    The run id matters: results/ accumulates every experiment ever done, and the
    headline score must be one run rather than the sum of all of them.
    """
    runs: dict[str, list[dict]] = {}
    for p in paths:
        results = json.loads(p.read_text(encoding="utf-8"))
        if not results:
            continue
        run_id = p.parent.name
        tagged = [{"run": run_id, **r} for r in results]
        runs.setdefault(results[0]["agent"], []).extend(tagged)
    return runs


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv[1:]] or sorted(Path("results").glob("*/results.json"))
    if not paths:
        print("no results.json files found", file=sys.stderr)
        return 2
    out = Path("report.html")
    out.write_text(render(load(paths)), encoding="utf-8")
    print(f"wrote {out} from {len(paths)} run(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
