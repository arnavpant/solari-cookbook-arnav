"""Measure how badly a model points, rather than eyeballing it.

The finding this benchmark leads with - models read a GUI correctly and then click
somewhere else - was originally three numbers copied out of model output by hand, with
a scale factor computed on the side. That is an anecdote with a decimal point in it.

This module makes it arithmetic. Parse the positions a model claims, pair them with
ground truth read off a real screenshot, and fit

    y_predicted = scale * y_true + offset

A slope near 1.0 with a large offset is a mis-registered origin. A slope away from 1.0
is a stretched coordinate space, and the error grows the further down the screen you
look - those are different defects and the fit distinguishes them.

R2 is the honesty check. If the residuals are not linear then "a vertical scale factor"
is simply the wrong description, and the number must not be published as one. With two
points R2 is meaningless - any two points fit a line exactly - so it is withheld rather
than reported as a flattering 1.0.

Reading and pointing are scored separately, because the entire claim is that one works
and the other does not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "Assets y=217", "Assets - y coordinate 217", "New button at (389, 115)", and the
# markdown shape models actually emit: "*   **Assets** - y=230".
# The name is required: a bare number has nothing to pair with ground truth.
#
# The separator class has to admit the punctuation models really use - em and en dashes,
# asterisks, backticks, quotes - or the most common output format silently parses as
# "named nothing", which reads as a capability result and is not one.
_NAME = r"([A-Za-z][A-Za-z /:'’-]{0,40}?)"
_SEP = r"[\s*`\"'‘’“”:,–—-]*"
_PATTERNS = (
    re.compile(_NAME + _SEP + r"\(\s*\d+(?:\.\d+)?\s*,\s*(\d+(?:\.\d+)?)\s*\)"),
    re.compile(
        _NAME + _SEP + r"(?:y|vertical)\s*(?:coordinate|coord|position|px|pixel)?"
        r"\s*(?:=|:|is|at)?\s*(\d+(?:\.\d+)?)",
        re.I,
    ),
)

# Leading list markers and filler that would otherwise be captured as part of the name.
_STRIP = re.compile(
    r"^(?:\d+[.)]\s*|[-*•–—]\s*|the\s+|and\s+|row\s+|at\s+|is\s+)+", re.I
)
# Trailing verbs and nouns a model puts between the name and the number.
_TRAIL = re.compile(
    r"(?:\s+|^)(?:row|rows|is|are|sits|sit|at|located|found|appears|appear|shown|"
    r"displayed|label|labelled|labeled|entry|item|line)\s*$",
    re.I,
)


def _clean(name: str) -> str:
    name = _STRIP.sub("", name.strip())
    # Applied repeatedly: "Income row appears" needs two passes.
    while True:
        stripped = _TRAIL.sub("", name.strip())
        if stripped == name.strip():
            break
        name = stripped
    name = name.strip(" -:,*`\"'‘’“”–—")
    return " ".join(name.split()).lower()


def parse_positions(text: str) -> dict[str, float]:
    """Every (name, y) a model asserted, first mention wins.

    Models routinely restate the list in a closing summary. Averaging two different
    claims would report a number the model never made, so the first one stands.
    """
    found: dict[str, float] = {}
    for pattern in _PATTERNS:
        for match in pattern.finditer(text or ""):
            name = _clean(match.group(1))
            if not name or name in found:
                continue
            found[name] = float(match.group(2))
    return found


@dataclass(frozen=True)
class Ground:
    """Known-correct positions, read off a real screenshot. Never guessed."""

    positions: dict[str, float]
    row_height: float = 24.0

    def normalised(self) -> dict[str, float]:
        return {k.lower(): float(v) for k, v in self.positions.items()}


@dataclass(frozen=True)
class Fit:
    n: int
    total_names: int
    named_correctly: int
    scale: float | None = None
    offset: float | None = None
    r_squared: float | None = None
    mean_abs_error_px: float = float("nan")
    mean_abs_error_rows: float = float("nan")
    row_height: float = 24.0
    residuals: dict[str, float] = field(default_factory=dict)

    def summary(self, label: str) -> str:
        if self.n == 0:
            return f"{label}: named nothing measurable - not scored"
        scale = "n/a" if self.scale is None else f"{self.scale:.3f}"
        r2 = "n/a" if self.r_squared is None else f"{self.r_squared:.3f}"
        return (
            f"{label}: read {self.named_correctly}/{self.total_names}  "
            f"scale {scale}  offset {self.offset:+.1f}px  "
            f"err {self.mean_abs_error_px:.1f}px "
            f"({self.mean_abs_error_rows:.1f} rows)  R2 {r2}  n={self.n}"
        )


def fit(claimed: dict[str, float], truth: Ground) -> Fit:
    """Least squares of claimed against true y, over the names present in both."""
    true_pos = truth.normalised()
    shared = [k for k in claimed if k in true_pos]
    total = len(true_pos)
    named = len(shared)

    if not shared:
        return Fit(n=0, total_names=total, named_correctly=0, row_height=truth.row_height)

    xs = [true_pos[k] for k in shared]
    ys = [float(claimed[k]) for k in shared]
    n = len(shared)

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)

    if sxx == 0:
        # Every reference point sits at the same y; a slope is not defined.
        scale = offset = r2 = None
    else:
        scale = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sxx
        offset = mean_y - scale * mean_x
        if n < 3:
            # Two points always fit a line exactly. Reporting R2=1.0 would be a lie of
            # presentation, not a measurement.
            r2 = None
        else:
            ss_res = sum((y - (scale * x + offset)) ** 2 for x, y in zip(xs, ys))
            ss_tot = sum((y - mean_y) ** 2 for y in ys)
            r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot

    residuals = {k: float(claimed[k]) - true_pos[k] for k in shared}
    mae = sum(abs(v) for v in residuals.values()) / n

    return Fit(
        n=n,
        total_names=total,
        named_correctly=named,
        scale=scale,
        offset=offset,
        r_squared=r2,
        mean_abs_error_px=mae,
        mean_abs_error_rows=mae / truth.row_height,
        row_height=truth.row_height,
        residuals=residuals,
    )


@dataclass(frozen=True)
class Aggregate:
    """Several runs of one model on one screenshot.

    One run is not a measurement. Six runs of MiniMax-M3 at temperature 0 produced
    scales from 0.893 to 1.106 and errors from 0.08 to 2.08 row heights - a single run
    would have published either "points perfectly" or "two rows out", and both would
    have been wrong. The spread is reported alongside the mean so a reader can see
    which claims a single number could support.
    """

    runs: int
    unmeasurable: int
    mean_scale: float | None = None
    scale_stdev: float | None = None
    min_scale: float | None = None
    max_scale: float | None = None
    mean_error_rows: float = float("nan")
    min_error_rows: float = float("nan")
    max_error_rows: float = float("nan")

    def summary(self, label: str) -> str:
        if self.runs == 0:
            return f"{label}: no measurable run out of {self.unmeasurable}"
        scale = "n/a" if self.mean_scale is None else f"{self.mean_scale:.3f}"
        spread = (
            ""
            if self.min_scale is None or self.runs < 2
            else f" [{self.min_scale:.3f}-{self.max_scale:.3f}]"
        )
        return (
            f"{label}: n={self.runs}  scale {scale}{spread}  "
            f"err {self.mean_error_rows:.2f} rows "
            f"[{self.min_error_rows:.2f}-{self.max_error_rows:.2f}]"
        )


def aggregate(fits: "list[Fit]") -> Aggregate:
    """Collapse repeated runs, keeping the spread visible."""
    import statistics

    good = [f for f in fits if f.n >= 2 and f.scale is not None]
    unmeasurable = len(fits) - len(good)
    if not good:
        return Aggregate(runs=0, unmeasurable=unmeasurable)

    scales = [f.scale for f in good]
    errs = [f.mean_abs_error_rows for f in good]
    return Aggregate(
        runs=len(good),
        unmeasurable=unmeasurable,
        mean_scale=statistics.fmean(scales),
        scale_stdev=statistics.stdev(scales) if len(scales) > 1 else 0.0,
        min_scale=min(scales),
        max_scale=max(scales),
        mean_error_rows=statistics.fmean(errs),
        min_error_rows=min(errs),
        max_error_rows=max(errs),
    )
