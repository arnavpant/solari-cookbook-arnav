"""Agent adapters, tested without a key or a network."""

import base64

import pytest

from cubicle.agents.gemini import SYSTEM as GEMINI_SYSTEM
from cubicle.agents.gemini import GeminiAgent
from cubicle.types import Observation


def obs(step=0, png=b"\x89PNG-FAKE"):
    return Observation(screenshot_png=png, width=1280, height=720,
                       step=step, max_steps=15, task_prompt="do the thing")


@pytest.fixture
def agent():
    return GeminiAgent(api_key="not-a-real-key")


def test_payload_carries_the_shared_system_prompt(agent):
    agent._frames = ["AAAA"]
    payload = agent.build_payload(obs())
    assert payload["system_instruction"]["parts"][0]["text"] == GEMINI_SYSTEM


def test_payload_is_deterministic(agent):
    assert agent.build_payload(obs())["generationConfig"]["temperature"] == 0.0


def test_payload_includes_the_task_and_step_budget(agent):
    text = agent.build_payload(obs(step=4))["contents"][0]["parts"][0]["text"]
    assert "do the thing" in text
    assert "step 5 of at most 15" in text


def test_screenshot_is_sent_as_inline_base64_png(agent):
    agent._frames = [base64.b64encode(b"PNGBYTES").decode()]
    parts = agent.build_payload(obs())["contents"][0]["parts"]
    images = [p for p in parts if "inline_data" in p]
    assert len(images) == 1
    assert images[0]["inline_data"]["mime_type"] == "image/png"
    assert base64.b64decode(images[0]["inline_data"]["data"]) == b"PNGBYTES"


def test_history_is_bounded_so_input_tokens_stay_flat():
    a = GeminiAgent(api_key="x", keep_frames=3)
    for i in range(10):
        a._frames.append(str(i))
        a._frames = a._frames[-a.keep_frames:]
    assert a._frames == ["7", "8", "9"]


def test_reset_clears_history(agent):
    agent._frames = ["a", "b"]
    agent.reset()
    assert agent._frames == []


def test_agent_satisfies_the_protocol(agent):
    from cubicle.agent import Agent
    from cubicle.agents.gemini import MODEL

    assert isinstance(agent, Agent)
    # Reference the constant, not a literal - the model id has already had to change
    # once (2.5-flash was retired for new keys) and a hardcoded name silently rots.
    assert agent.name == MODEL


def test_deepseek_shares_the_identical_prompt():
    """Per-model prompt tuning would measure prompt engineering, not agents."""
    from cubicle.agents.deepseek import SYSTEM as DEEPSEEK_SYSTEM
    assert DEEPSEEK_SYSTEM == GEMINI_SYSTEM


def test_deepseek_budget_leaves_room_for_reasoning():
    """Regression: at max_tokens=300 this model spent all 300 on reasoning_content and
    returned content='' with finish_reason='length', which is indistinguishable from a
    broken model. It needs ~200-300 reasoning tokens before it writes an answer."""
    from cubicle.agents.deepseek import MAX_TOKENS

    assert MAX_TOKENS >= 1000


def test_deepseek_payload_carries_the_shared_prompt_and_image():
    import base64

    from cubicle.agents.deepseek import DeepSeekAgent

    a = DeepSeekAgent(api_key="x")
    a._frames = [{"type": "image_url",
                  "image_url": {"url": "data:image/png;base64," + base64.b64encode(b"P").decode()}}]
    payload = a.build_payload(obs())
    assert payload["messages"][0]["content"] == GEMINI_SYSTEM
    assert payload["temperature"] == 0.0
    parts = payload["messages"][1]["content"]
    assert any(p.get("type") == "image_url" for p in parts)
