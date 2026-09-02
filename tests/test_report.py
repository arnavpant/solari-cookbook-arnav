import json
from pathlib import Path

from cubicle.report import _bar_path, leaderboard_svg, load, render


def _run(agent, outcomes):
    return [
        {"task_id": t, "agent": agent, "outcome": o, "reason": "" if o == "pass" else "nope",
         "steps_used": 3, "max_steps": 15, "model_seconds": 1.0, "desktop_seconds": 2.0,
         "unparseable_responses": 0, "session_id": "s"}
        for t, o in outcomes.items()
    ]


def test_bar_path_is_empty_for_a_zero_width_bar():
    assert _bar_path(0, 0, 0, 26) == ""


def test_bar_path_rounds_only_the_data_end():
    d = _bar_path(10, 0, 100, 26)
    assert d.startswith("M10,0")
    assert d.count("Q") == 2  # two corners, both at the far end


def test_leaderboard_renders_an_empty_dashed_track_for_the_untested_row():
    svg = leaderboard_svg([("oracle", 7, 7, ""), ("Pinetree-CUA", 0, 0, "untested")])
    assert "stroke-dasharray" in svg
    assert "untested" in svg


def test_leaderboard_marks_up_a_title_for_hover(): 
    svg = leaderboard_svg([("oracle", 7, 7, "")])
    assert "<title>oracle: 7 of 7 tasks passed</title>" in svg


def test_render_declares_dark_mode_under_both_scopes():
    """A viewer's explicit toggle must win in either direction."""
    out = render({"oracle": _run("oracle", {"t01": "pass"})})
    assert "@media (prefers-color-scheme: dark)" in out
    assert ':root[data-theme="dark"]' in out
    assert ':root:not([data-theme="light"])' in out


def test_render_has_no_external_resources():
    out = render({"oracle": _run("oracle", {"t01": "pass"})})
    for forbidden in ("http://", "https://cdn", "<script", "cdnjs", "unpkg"):
        assert forbidden not in out, f"report should be self-contained, found {forbidden}"


def test_render_sorts_agents_by_score_and_pins_pinetree_last():
    out = render({
        "weak": _run("weak", {"t01": "wrong_state", "t02": "wrong_state"}),
        "oracle": _run("oracle", {"t01": "pass", "t02": "pass"}),
    })
    assert out.index(">oracle<") < out.index(">weak<")
    assert out.index(">weak<") < out.index("Pinetree-CUA")


def test_render_escapes_grader_reasons():
    runs = {"x": _run("x", {"t01": "wrong_state"})}
    runs["x"][0]["reason"] = "<script>alert(1)</script>"
    assert "<script>alert(1)</script>" not in render(runs)


def test_load_groups_by_agent(tmp_path):
    p = tmp_path / "results.json"
    p.write_text(json.dumps(_run("oracle", {"t01": "pass"})))
    assert list(load([Path(p)])) == ["oracle"]


def test_provider_errors_are_excluded_from_the_denominator():
    """Scoring 1/3 when two tasks never ran would understate the model."""
    runs = {"m": _run("m", {"t01": "pass", "t02": "provider_error", "t03": "provider_error"})}
    out = render(runs)
    assert ">1/1<" in out
    assert "2 unscored (provider unavailable)" in out


def test_notes_fit_inside_the_viewbox():
    """The oracle's note used to clip to 'reference - pr...' at the right edge."""
    import re

    from cubicle.report import LABEL_W, TRACK_W, leaderboard_svg

    note = "reference - proves solvable"
    svg = leaderboard_svg([("oracle", 7, 7, note)])
    width = int(re.search(r'viewBox="0 0 (\d+)', svg).group(1))
    note_x = max(int(x) for x in re.findall(r'<text x="(\d+)"', svg))
    # ~6px per char at font-size 11 is a conservative advance width
    assert note_x + len(note) * 6 <= width, "note runs past the right edge of the viewBox"
    assert note_x > LABEL_W + TRACK_W


def test_the_leaderboard_scores_the_latest_run_not_the_sum_of_all_history():
    """The headline number must be one run, not thirteen added together.

    results/ accumulates every experiment, including early broken ones. Summing them
    put "oracle 23/25" on the front page - a reader sees the reference solution failing
    two tasks and concludes the suite is not reliably solvable. It is 7/7; the 2 came
    from debugging runs that crashed before GnuCash was even installed correctly.
    """
    runs = {
        "oracle": [
            {"run": "20260901-1000", **r} for r in _run("oracle", {"t01": "crash"})
        ] + [
            {"run": "20260901-2000", **r}
            for r in _run("oracle", {"t01": "pass", "t02": "pass"})
        ]
    }
    out = render(runs)
    assert ">2/2<" in out, "should score the latest run"
    assert ">2/3<" not in out, "must not sum across runs"


def test_every_run_table_still_shows_the_whole_history():
    """Only the headline collapses to one run. The audit trail stays complete."""
    runs = {
        "oracle": [
            {"run": "20260901-1000", **r} for r in _run("oracle", {"t01": "crash"})
        ] + [
            {"run": "20260901-2000", **r} for r in _run("oracle", {"t01": "pass"})
        ]
    }
    out = render(runs)
    assert out.count("crash") >= 1, "the earlier failed run must remain visible"


def test_load_keeps_runs_apart(tmp_path):
    a = tmp_path / "20260901-1000-oracle"
    b = tmp_path / "20260901-2000-oracle"
    for d, outcome in ((a, "crash"), (b, "pass")):
        d.mkdir()
        (d / "results.json").write_text(json.dumps(_run("oracle", {"t01": outcome})))
    got = load([a / "results.json", b / "results.json"])
    assert {r["run"] for r in got["oracle"]} == {"20260901-1000-oracle", "20260901-2000-oracle"}


# ------------------------------------------------- localization + control charts

def test_localization_chart_places_marks_at_true_screen_scale():
    """The whole point is that you can SEE the stretch, so the drawing must be to
    scale: a model that says y=300 for a row at y=217 has to sit visibly lower."""
    from cubicle.charts import localization_svg

    svg = localization_svg(
        truth={"Assets": 217, "Expenses": 241, "Income": 264},
        models=[("truth-like", [217, 241, 264]), ("stretched", [300, 330, 360])],
        height_px=720,
    )
    ys = [float(v) for v in __import__("re").findall(r'data-y="([\d.]+)"', svg)]
    assert ys, "marks must record the screen y they represent"
    assert max(ys) == 360 and min(ys) == 217


def test_localization_chart_draws_the_truth_line_for_every_row():
    from cubicle.charts import localization_svg

    svg = localization_svg(
        truth={"Assets": 217, "Expenses": 241, "Income": 264},
        models=[("m", [300, 330, 360])],
        height_px=720,
    )
    assert svg.count('class="truth"') == 3


def test_localization_chart_escapes_model_names():
    from cubicle.charts import localization_svg

    svg = localization_svg(
        truth={"A": 217},
        models=[("<script>x</script>", [300])],
        height_px=720,
    )
    assert "<script>x</script>" not in svg


def test_control_chart_shows_two_distributions_and_the_truth():
    from cubicle.charts import control_svg

    svg = control_svg(describe=[267, 270, 264], act=[299, 297, 302], true_y=241)
    assert "describe" in svg and "act" in svg
    assert 'class="truth"' in svg


def test_control_chart_reports_that_the_ranges_do_not_overlap():
    """That is the claim the chart exists to support; it must be stated, not implied."""
    from cubicle.charts import control_svg

    svg = control_svg(describe=[239, 280], act=[291, 332], true_y=241)
    assert "no overlap" in svg.lower()


def test_control_chart_says_so_when_the_ranges_DO_overlap():
    from cubicle.charts import control_svg

    svg = control_svg(describe=[239, 300], act=[291, 332], true_y=241)
    assert "no overlap" not in svg.lower()


def test_load_localization_reads_the_probe_output(tmp_path):
    from cubicle.charts import load_localization

    d = tmp_path / "localization"
    d.mkdir()
    (d / "20260902-120000.json").write_text(json.dumps({
        "truth": {"Assets": 217, "Expenses": 241, "Income": 264},
        "row_height": 24,
        "results": [
            {"model": "m1", "parsed": {"assets": 300, "expenses": 330, "income": 360},
             "n": 3, "scale": 1.276, "mean_abs_error_rows": 3.7, "r_squared": 1.0},
            {"model": "m2", "error": "HTTP 429"},
        ],
    }))
    got = load_localization(d)
    assert [m for m, _ in got["models"]] == ["m1"], "a model that never answered is not plotted"
    assert got["truth"] == {"Assets": 217, "Expenses": 241, "Income": 264}


def test_load_localization_pools_every_probe_file(tmp_path):
    """Free tiers throttle, so no single probe file has every model in it.

    Reading only the newest file plotted one model and silently dropped four that had
    answered perfectly well an hour earlier - which reads as "only one model was
    measured" and understates the finding.
    """
    from cubicle.charts import load_localization

    d = tmp_path / "localization"
    d.mkdir()
    truth = {"Assets": 217, "Expenses": 241, "Income": 264}

    (d / "20260902-100000.json").write_text(json.dumps({
        "truth": truth, "row_height": 24,
        "results": [
            {"model": "early", "parsed": {"assets": 300, "expenses": 330, "income": 360},
             "n": 3, "scale": 1.276, "mean_abs_error_rows": 3.7, "r_squared": 1.0},
        ],
    }))
    (d / "20260902-200000.json").write_text(json.dumps({
        "truth": truth, "row_height": 24,
        "results": [
            {"model": "late", "parsed": {"assets": 222, "expenses": 245, "income": 269},
             "n": 3, "scale": 1.0, "mean_abs_error_rows": 0.2, "r_squared": 0.999},
            {"model": "early", "error": "HTTP 429"},
        ],
    }))

    got = load_localization(d)
    assert sorted(m for m, _ in got["models"]) == ["early", "late"]
