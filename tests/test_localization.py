"""Turning a model's prose into a measured localization error.

The README's headline table was read off model output by hand. Three rows, two models,
one screenshot - and a hand-computed scale factor. That is an anecdote wearing a
number's clothes.

This module is the arithmetic that replaces it: parse what the model said, pair it with
known ground truth, and fit y_pred = scale * y_true + offset. A slope, an intercept and
an R2 are checkable; "about 1.1x" is not.
"""

from __future__ import annotations

import math

import pytest

from cubicle.localization import Ground, fit, parse_positions

# ------------------------------------------------------------------ parsing

def test_parses_the_plain_name_then_y_form():
    assert parse_positions("Assets y=217") == {"assets": 217.0}


def test_parses_prose_around_the_pair():
    text = "The Assets row is at y=230, and Expenses sits at y = 256."
    assert parse_positions(text) == {"assets": 230.0, "expenses": 256.0}


def test_parses_a_bulleted_list():
    text = """
    1. Assets - y coordinate 217
    2. Expenses - y coordinate 241
    3. Income - y coordinate 264
    """
    assert parse_positions(text) == {"assets": 217.0, "expenses": 241.0, "income": 264.0}


def test_parses_an_xy_pair_and_keeps_only_y():
    assert parse_positions("New button at (389, 115)") == {"new button": 115.0}


def test_ignores_a_number_with_no_name():
    assert parse_positions("y=217") == {}


def test_is_case_insensitive_and_trims():
    assert parse_positions("  ASSETS   y=217 ") == {"assets": 217.0}


def test_takes_the_first_answer_when_a_model_repeats_itself():
    """Models often restate the list in a summary. The first statement is the answer;
    silently averaging two different claims would invent a number nobody made."""
    assert parse_positions("Assets y=217\n...\nAssets y=999") == {"assets": 217.0}


def test_returns_nothing_for_a_refusal():
    assert parse_positions("I cannot determine the coordinates from this image.") == {}


# ------------------------------------------------------------------ fitting

TRUTH = Ground({"assets": 217, "expenses": 241, "income": 264}, row_height=24)


def test_a_perfect_answer_has_unit_scale_and_no_error():
    f = fit({"assets": 217, "expenses": 241, "income": 264}, TRUTH)
    assert f.scale == pytest.approx(1.0)
    assert f.offset == pytest.approx(0.0, abs=1e-9)
    assert f.mean_abs_error_px == pytest.approx(0.0, abs=1e-9)
    assert f.mean_abs_error_rows == pytest.approx(0.0, abs=1e-9)


def test_a_pure_offset_is_reported_as_offset_not_scale():
    """A constant shift is a different defect from a stretch - one is a mis-registered
    origin, the other is a broken coordinate space. The fit has to tell them apart."""
    f = fit({"assets": 237, "expenses": 261, "income": 284}, TRUTH)
    assert f.scale == pytest.approx(1.0)
    assert f.offset == pytest.approx(20.0)


def test_a_pure_stretch_is_reported_as_scale():
    stretched = {k: v * 1.25 for k, v in TRUTH.positions.items()}
    f = fit(stretched, TRUTH)
    assert f.scale == pytest.approx(1.25)
    assert f.offset == pytest.approx(0.0, abs=1e-9)


def test_error_is_also_reported_in_row_heights():
    """Pixels do not say whether a click lands. A 24px row does."""
    f = fit({"assets": 241, "expenses": 265, "income": 288}, TRUTH)
    assert f.mean_abs_error_px == pytest.approx(24.0)
    assert f.mean_abs_error_rows == pytest.approx(1.0)


def test_r_squared_is_one_for_a_perfectly_linear_error():
    stretched = {k: v * 1.3 + 5 for k, v in TRUTH.positions.items()}
    assert fit(stretched, TRUTH).r_squared == pytest.approx(1.0)


def test_r_squared_falls_when_the_error_is_not_linear():
    """This is the honesty check on the whole claim. If the residuals are not linear,
    'a vertical scale factor' is the wrong description and the number must not be
    presented as one."""
    noisy = {"assets": 217, "expenses": 400, "income": 264}
    assert fit(noisy, TRUTH).r_squared < 0.5


def test_only_names_present_in_both_are_used():
    f = fit({"assets": 217, "expenses": 241, "income": 264, "toolbar": 9999}, TRUTH)
    assert f.n == 3
    assert f.mean_abs_error_px == pytest.approx(0.0, abs=1e-9)


def test_a_model_that_named_nothing_measurable_is_not_scored():
    f = fit({}, TRUTH)
    assert f.n == 0
    assert f.scale is None and f.r_squared is None


def test_two_points_give_a_line_but_no_meaningful_r_squared():
    """Two points always fit a line exactly. Reporting R2=1.0 there would be a lie of
    presentation, so it is withheld."""
    f = fit({"assets": 217, "expenses": 241}, TRUTH)
    assert f.n == 2
    assert f.scale is not None
    assert f.r_squared is None


def test_reading_is_scored_separately_from_pointing():
    """The headline finding is that reading works and pointing does not. That is only
    sayable if the two are measured apart."""
    f = fit({"assets": 300, "expenses": 340, "income": 380}, TRUTH)
    assert f.named_correctly == 3
    assert f.total_names == 3
    partial = fit({"assets": 217}, TRUTH)
    assert partial.named_correctly == 1 and partial.total_names == 3


def test_summary_line_is_one_row_of_the_published_table():
    f = fit({"assets": 230, "expenses": 256, "income": 282}, TRUTH)
    row = f.summary("deepseek")
    assert "deepseek" in row
    assert "1.1" in row  # the scale, to one decimal at least
    assert not math.isnan(f.mean_abs_error_px)


def test_parses_a_markdown_bullet_with_bold_and_an_em_dash():
    """The single most common shape of real model output. Missing it would silently
    score a model as having named nothing."""
    text = "*   **Assets** — y=230\n*   **Expenses** — y=256\n*   **Income** — y=282"
    assert parse_positions(text) == {"assets": 230.0, "expenses": 256.0, "income": 282.0}


def test_strips_a_trailing_verb_from_the_name():
    """'Income appears at y=282' must key on 'income', or it never pairs with truth."""
    assert parse_positions("Income appears at y=282") == {"income": 282.0}


def test_names_in_quotes_or_backticks_are_matched_bare():
    assert parse_positions('"Assets" y=217') == {"assets": 217.0}


# ------------------------------------------------------------------ aggregate

def test_aggregate_reports_the_spread_not_just_the_mean():
    """One run is not a measurement.

    Six runs of the same model at temperature 0 gave scales from 0.893 to 1.106. A
    single run would have published either 'this model points perfectly' or 'this model
    is two rows out', and both would have been wrong.
    """
    from cubicle.localization import aggregate

    fits = [fit({"assets": 217 + d, "expenses": 241 + d, "income": 264 + d}, TRUTH)
            for d in (0, 12, 24)]
    agg = aggregate(fits)
    assert agg.runs == 3
    assert agg.mean_error_rows == pytest.approx(0.5)
    assert agg.min_error_rows == pytest.approx(0.0)
    assert agg.max_error_rows == pytest.approx(1.0)


def test_aggregate_ignores_runs_that_produced_no_answer():
    from cubicle.localization import aggregate

    fits = [fit({"assets": 217, "expenses": 241, "income": 264}, TRUTH), fit({}, TRUTH)]
    agg = aggregate(fits)
    assert agg.runs == 1
    assert agg.unmeasurable == 1


def test_aggregate_of_nothing_is_not_an_error():
    from cubicle.localization import aggregate

    agg = aggregate([fit({}, TRUTH)])
    assert agg.runs == 0 and agg.mean_scale is None


def test_a_reproducible_model_reports_zero_spread():
    """nemotron returned byte-identical coordinates on every run. That is a real
    property and has to be visible, not averaged away."""
    from cubicle.localization import aggregate

    same = fit({"assets": 300, "expenses": 330, "income": 360}, TRUTH)
    agg = aggregate([same, same, same])
    assert agg.scale_stdev == pytest.approx(0.0)
    assert agg.min_error_rows == agg.max_error_rows
