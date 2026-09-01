import pytest

from cubicle.agents._json_action import parse_action
from cubicle.harness import UnparseableResponse


def test_parses_a_bare_object():
    a = parse_action('{"kind":"click","x":10,"y":20}')
    assert (a.kind, a.x, a.y) == ("click", 10, 20)


def test_parses_json_inside_a_fenced_block():
    a = parse_action('Sure!\n```json\n{"kind":"type","text":"hi"}\n```\nHope that helps.')
    assert a.kind == "type"
    assert a.text == "hi"


def test_parses_an_unlabelled_fence():
    a = parse_action('```\n{"kind":"done"}\n```')
    assert a.kind == "done"


def test_tolerates_extra_keys_models_like_to_add():
    a = parse_action('{"kind":"click","x":1,"y":2,"reason":"the OK button","thought":"..."}')
    assert (a.kind, a.x, a.y) == ("click", 1, 2)


def test_parses_a_scroll_with_direction():
    a = parse_action('{"kind":"scroll","x":5,"y":6,"scroll_direction":"up","scroll_amount":3}')
    assert a.scroll_direction == "up"
    assert a.scroll_amount == 3


def test_rejects_prose_with_no_json():
    with pytest.raises(UnparseableResponse, match="no JSON object"):
        parse_action("I would click the New Account button next.")


def test_rejects_empty_response():
    with pytest.raises(UnparseableResponse):
        parse_action("")


def test_rejects_malformed_json():
    with pytest.raises(UnparseableResponse, match="invalid JSON"):
        parse_action('{"kind":"click", "x":}')


def test_rejects_an_unknown_action_kind():
    with pytest.raises(UnparseableResponse):
        parse_action('{"kind":"teleport","x":1,"y":2}')


def test_rejects_click_without_coordinates():
    """Action.__post_init__ enforces this; the parser must surface it, not swallow it."""
    with pytest.raises(UnparseableResponse, match="requires x and y"):
        parse_action('{"kind":"click"}')


def test_rejects_type_without_text():
    with pytest.raises(UnparseableResponse, match="requires text"):
        parse_action('{"kind":"type"}')


def test_rejects_drag_without_a_destination():
    with pytest.raises(UnparseableResponse, match="requires to_x and to_y"):
        parse_action('{"kind":"drag","x":1,"y":2}')


def test_rejects_a_json_array():
    with pytest.raises(UnparseableResponse):
        parse_action('[{"kind":"done"}]')


def test_system_prompt_is_committed_and_lists_every_action_kind():
    """One fixed prompt for every model. Per-model prompt tuning would measure prompt
    engineering rather than agent capability."""
    import pathlib

    from cubicle.types import ACTION_KINDS

    prompt = pathlib.Path("cubicle/agents/system_prompt.txt").read_text(encoding="utf-8")
    for kind in ACTION_KINDS:
        assert f'"{kind}"' in prompt, f"system prompt never mentions {kind}"
    assert "1280x720" in prompt
    # The anti-cheat promise must be stated to the model, not merely enforced in code.
    assert "accessibility tree" in prompt
    assert "clipboard" in prompt
