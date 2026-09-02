"""The two charts that carry the finding, as inline SVG.

Kept beside report.py rather than inside it because these encode an argument, not a
table, and the reasoning is worth stating:

  - The localization chart is drawn to SCREEN SCALE. A table of numbers makes the
    reader do the arithmetic; drawing claims against the real y axis makes the stretch
    visible, because the marks fan out as they go down the screen. That fanning IS the
    finding - a constant offset would keep them parallel.

  - Every model shares one colour. There is no categorical identity to encode: the only
    distinction that matters is truth versus claim, so that is the only one drawn. A
    per-model legend would be decoration.

  - The control chart states in words whether the two ranges overlap. That is the whole
    claim, and leaving it to the eye would be the kind of thing this project keeps
    trying not to do.
"""

from __future__ import annotations

import html
import json
from pathlib import Path


def short_label(model: str) -> str:
    """A compact but identifiable column label.

    Full ids are 30-50 characters and, rotated, ran off the left edge of the SVG and
    were clipped mid-word. The table directly beneath the chart lists every full id.

    Shortening must never merge two models. gemini-3.5-flash and gemini-3.5-flash-lite
    are different checkpoints, and a naive truncation gave both the same label - so the
    variant marker is preserved even when the rest is dropped.
    """
    name = str(model).split("/")[-1].replace(":free", "")
    for suffix in ("-instruct", "-reasoning", "-preview", "-exp", "-it"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]

    parts = name.split("-")
    markers = ("lite", "nano", "mini", "small", "pro", "max", "thinking")
    variant = next((p for p in parts[2:] if p in markers), None)

    keep = parts[:2]
    if variant:
        keep = keep + [variant]
    elif len(parts) > 2 and len("-".join(parts[:3])) <= 16:
        keep = parts[:3]

    out = "-".join(keep)
    return out if len(out) <= 16 else out[:16]


LOC_W = 900
LOC_H = 330
LOC_PAD_L = 150
LOC_PAD_R = 40
LOC_TOP = 44
LOC_BOT = 62


def localization_svg(truth: dict, models: list, height_px: float = 720) -> str:
    """Where the rows are, and where each model says they are."""
    true_ys = [float(v) for v in truth.values()]
    all_ys = true_ys + [float(y) for _, ys in models for y in ys]
    # Frame the data, not the whole screen. Anchoring at y=0 spent half the chart on
    # empty space above the first row and squashed the thing the chart is FOR - the
    # gap between truth and claim - into a few pixels. The axis is labelled with real
    # y values at both ends, so nothing is hidden by not starting at zero.
    span = max(all_ys) - min(all_ys)
    pad = max(span * 0.18, 12.0)
    lo = min(all_ys) - pad
    hi = max(all_ys) + pad

    plot_h = LOC_H - LOC_TOP - LOC_BOT
    inner_w = LOC_W - LOC_PAD_L - LOC_PAD_R

    def sy(y):
        return LOC_TOP + (float(y) - lo) / (hi - lo) * plot_h

    out = [
        '<svg viewBox="0 0 %d %d" width="100%%" style="max-width:%dpx" role="img" '
        'aria-label="Claimed row positions against ground truth" font-family="inherit">'
        % (LOC_W, LOC_H, LOC_W)
    ]

    for name, y in truth.items():
        yy = sy(y)
        out.append(
            '<line class="truth" x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="var(--ok)" '
            'stroke-width="1.5" stroke-dasharray="3 3"/>'
            % (LOC_PAD_L, yy, LOC_W - LOC_PAD_R, yy)
        )
        out.append(
            '<text x="%d" y="%.1f" text-anchor="end" font-size="11" fill="var(--ok)">'
            "%s y=%.0f</text>" % (LOC_PAD_L - 8, yy + 3.5, html.escape(str(name)), y)
        )

    n = max(len(models), 1)
    col_w = inner_w / n
    for i, (label, ys) in enumerate(models):
        cx = LOC_PAD_L + col_w * (i + 0.5)
        if len(ys) > 1:
            pts = " ".join("%.1f,%.1f" % (cx, sy(y)) for y in ys)
            out.append(
                '<polyline points="%s" fill="none" stroke="var(--series)" '
                'stroke-width="1" opacity="0.45"/>' % pts
            )
        for y in ys:
            out.append(
                '<circle class="claim" data-y="%g" cx="%.1f" cy="%.1f" r="4" '
                'fill="var(--series)"/>' % (float(y), cx, sy(y))
            )
        short = html.escape(short_label(label))
        # Level labels collide once columns are narrow. Rotating them was the first
        # attempt and it clipped - rotated text left the SVG box and lost its leading
        # characters, so "gemma-4-31b" rendered as "ma-4-31b". Two staggered rows give
        # each label twice the width, need no transform, and cannot clip.
        row = (i % 2) if col_w < 90 else 0
        ly = LOC_H - 34 + row * 15
        out.append(
            '<text class="collabel" x="%.1f" y="%d" text-anchor="middle" font-size="10" '
            'fill="var(--text-muted)">%s</text>' % (cx, ly, short)
        )

    out.append(
        '<text x="%d" y="20" font-size="12" fill="var(--text-primary)">dashed = where the rows '
        "actually are &#183; dots = where the model says they are</text>" % LOC_PAD_L
    )
    # Label the axis at both ends so "not starting at zero" is visible, not implied.
    for value, yy in ((lo, LOC_TOP), (hi, LOC_TOP + plot_h)):
        out.append(
            '<text x="%d" y="%.1f" text-anchor="end" font-size="9" '
            'fill="var(--text-muted)">y=%.0f</text>' % (LOC_PAD_L - 66, yy + 3, value)
        )
    out.append("</svg>")
    return "".join(out)


CTL_W = 900
CTL_H = 170


def control_svg(describe: list, act: list, true_y: float) -> str:
    """Two conditions on one axis, with the overlap verdict written out."""
    vals = [float(v) for v in list(describe) + list(act) + [true_y]]
    lo, hi = min(vals) - 15, max(vals) + 15
    pad_l, pad_r = 110, 30
    inner = CTL_W - pad_l - pad_r

    def sx(v):
        return pad_l + (float(v) - lo) / (hi - lo) * inner

    out = [
        '<svg viewBox="0 0 %d %d" width="100%%" style="max-width:%dpx" role="img" '
        'aria-label="Describe versus act coordinates" font-family="inherit">'
        % (CTL_W, CTL_H, CTL_W)
    ]

    tx = sx(true_y)
    out.append(
        '<line class="truth" x1="%.1f" y1="40" x2="%.1f" y2="120" stroke="var(--ok)" '
        'stroke-width="2"/>' % (tx, tx)
    )
    out.append(
        '<text x="%.1f" y="32" text-anchor="middle" font-size="11" fill="var(--ok)">'
        "true y=%.0f</text>" % (tx, true_y)
    )

    for label, vals_, y in (("describe", list(describe), 62), ("act", list(act), 104)):
        if not vals_:
            continue
        a, b = min(vals_), max(vals_)
        out.append(
            '<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="var(--series)" '
            'stroke-width="2" opacity="0.4"/>' % (sx(a), y, sx(b), y)
        )
        for v in vals_:
            out.append(
                '<circle cx="%.1f" cy="%d" r="3.5" fill="var(--series)"/>' % (sx(v), y)
            )
        out.append(
            '<text x="%d" y="%d" text-anchor="end" font-size="12" fill="var(--text-primary)">'
            "%s</text>" % (pad_l - 12, y + 4, html.escape(label))
        )
        out.append(
            '<text x="%.1f" y="%d" font-size="11" fill="var(--text-muted)">n=%d mean %.0f'
            "</text>" % (sx(b) + 8, y + 4, len(vals_), sum(vals_) / len(vals_))
        )

    disjoint = describe and act and max(describe) < min(act)
    verdict = (
        "no overlap: highest describe %.0f, lowest act %.0f"
        % (max(describe), min(act))
        if disjoint
        else "ranges overlap"
    )
    out.append(
        '<text x="%d" y="%d" font-size="12" fill="var(--text-primary)">%s</text>'
        % (pad_l, CTL_H - 18, html.escape(verdict))
    )
    out.append("</svg>")
    return "".join(out)


def load_localization(directory) -> dict:
    """Every localization probe, pooled, one measurable answer per model.

    Pooling rather than taking the newest file is not tidiness: free tiers throttle, so
    no single probe run contains every model. Reading only the latest file plotted one
    model and silently dropped four that had answered perfectly well an hour earlier,
    which reads as "only one model was measured" and understates the result.
    """
    files = [
        f
        for f in sorted(Path(directory).glob("*.json"))
        if not f.name.startswith("describe-vs-act")
    ]
    if not files:
        return {}

    by_model: dict = {}
    stats: dict = {}
    truth: dict = {}
    row_height = 24
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        truth = data.get("truth", truth) or truth
        row_height = data.get("row_height", row_height)
        truth_keys = [k.lower() for k in truth]
        for r in data.get("results", []):
            if r.get("n", 0) < 3 or not r.get("parsed") or r["model"] in by_model:
                continue  # a model that never answered is not plotted as a zero
            ys = [r["parsed"][k] for k in truth_keys if k in r["parsed"]]
            if len(ys) >= 3:
                by_model[r["model"]] = ys
                stats[r["model"]] = {
                    "scale": r.get("scale"),
                    "err_rows": r.get("mean_abs_error_rows"),
                    "r2": r.get("r_squared"),
                }
    return {
        "truth": truth,
        "row_height": row_height,
        # Worst first: the reader should meet the finding before the exception to it.
        "models": sorted(by_model.items(), key=lambda kv: -kv[1][0]),
        "stats": stats,
    }


def load_control(directory) -> dict:
    """Pool every describe-vs-act batch."""
    describe: list = []
    act: list = []
    true_y = None
    model = None
    for f in sorted(Path(directory).glob("describe-vs-act-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        describe += [float(v) for v in d.get("describe", [])]
        act += [float(v) for v in d.get("act", [])]
        true_y = d.get("true_y", true_y)
        model = d.get("model", model)
    if not describe or not act:
        return {}
    return {"describe": describe, "act": act, "true_y": true_y, "model": model}
