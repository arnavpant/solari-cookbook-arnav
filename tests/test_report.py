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
