"""The bring-your-own-endpoint adapter, tested without a key or a network.

The README invites people to add their agent. Until now that meant writing a class.
Almost every hosted model worth testing - OpenRouter, Groq, GitHub Models, NVIDIA NIM,
Mistral, Together - and Ollama running locally all speak the same OpenAI-compatible
chat API, so one adapter configured by environment variables covers them all.
"""

from __future__ import annotations

import base64

import pytest

from cubicle.agents.openai_compat import OpenAICompatAgent, from_env
from cubicle.agents.openai_compat import SYSTEM as COMPAT_SYSTEM
from cubicle.types import Observation


def obs(step=0, png=b"\x89PNG-FAKE"):
    return Observation(screenshot_png=png, width=1280, height=720,
                       step=step, max_steps=15, task_prompt="do the thing")


@pytest.fixture
def agent():
    return OpenAICompatAgent(
        base_url="https://example.test/v1", model="some/vision-model", api_key="k"
    )


def test_payload_carries_the_byte_identical_shared_prompt(agent):
    """Fairness rule: every model in the suite gets the same committed prompt."""
    from cubicle.agents.deepseek import SYSTEM as DEEPSEEK_SYSTEM

    assert COMPAT_SYSTEM == DEEPSEEK_SYSTEM
    assert agent.build_payload(obs())["messages"][0]["content"] == COMPAT_SYSTEM


def test_payload_is_deterministic(agent):
    assert agent.build_payload(obs())["temperature"] == 0.0


def test_payload_includes_the_task_and_step_budget(agent):
    content = agent.build_payload(obs(step=4))["messages"][1]["content"]
    text = next(c["text"] for c in content if c["type"] == "text")
    assert "do the thing" in text
    assert "step 5 of at most 15" in text


def test_screenshot_is_sent_as_a_base64_data_uri(agent):
    agent._frames = [
        {"type": "image_url",
         "image_url": {"url": "data:image/png;base64," + base64.b64encode(b"PNGBYTES").decode()}}
    ]
    content = agent.build_payload(obs())["messages"][1]["content"]
    images = [c for c in content if c["type"] == "image_url"]
    assert len(images) == 1
    head, _, data = images[0]["image_url"]["url"].partition(",")
    assert head == "data:image/png;base64"
    assert base64.b64decode(data) == b"PNGBYTES"


def test_history_is_bounded_so_input_tokens_stay_flat():
    a = OpenAICompatAgent(base_url="https://example.test/v1", model="m", api_key="k",
                          keep_frames=2)
    for i in range(5):
        a._remember(obs(step=i, png=f"frame{i}".encode()))
    assert len(a._frames) == 2


def test_reset_clears_history(agent):
    agent._remember(obs())
    agent.reset()
    assert agent._frames == []


def test_endpoint_tolerates_a_trailing_slash():
    """Half the dashboards print the base URL with a slash and half without."""
    a = OpenAICompatAgent(base_url="https://example.test/v1/", model="m", api_key="k")
    b = OpenAICompatAgent(base_url="https://example.test/v1", model="m", api_key="k")
    assert a.endpoint == b.endpoint == "https://example.test/v1/chat/completions"


def test_name_defaults_to_the_model_so_the_leaderboard_says_what_ran(agent):
    assert agent.name == "some/vision-model"


def test_a_local_endpoint_needs_no_api_key():
    """Ollama serves an OpenAI-compatible API with no auth. Requiring a key would
    exclude the only genuinely free, unmetered option."""
    a = OpenAICompatAgent(base_url="http://localhost:11434/v1", model="qwen2.5vl:3b")
    assert "Authorization" not in a.headers


def test_a_hosted_endpoint_sends_a_bearer_token(agent):
    assert agent.headers["Authorization"] == "Bearer k"


# ------------------------------------------------------------------ from_env

ENV = {
    "CUBICLE_VISION_BASE_URL": "https://openrouter.ai/api/v1",
    "CUBICLE_VISION_MODEL": "qwen/qwen2.5-vl-72b-instruct:free",
    "CUBICLE_VISION_API_KEY": "sk-or-test",
}


def test_from_env_builds_the_configured_agent(monkeypatch):
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    a = from_env()
    assert a.model == ENV["CUBICLE_VISION_MODEL"]
    assert a.endpoint.startswith(ENV["CUBICLE_VISION_BASE_URL"])
    assert a.api_key == ENV["CUBICLE_VISION_API_KEY"]


def test_from_env_names_the_missing_variable(monkeypatch):
    """A benchmark someone else is meant to run must not fail with a bare KeyError."""
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("CUBICLE_VISION_MODEL")
    with pytest.raises(RuntimeError, match="CUBICLE_VISION_MODEL"):
        from_env()


def test_from_env_allows_a_keyless_local_endpoint(monkeypatch):
    monkeypatch.setenv("CUBICLE_VISION_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("CUBICLE_VISION_MODEL", "qwen2.5vl:3b")
    monkeypatch.delenv("CUBICLE_VISION_API_KEY", raising=False)
    assert from_env().api_key is None


def test_from_env_requires_a_key_for_a_remote_endpoint(monkeypatch):
    """Silently sending an unauthenticated request to a hosted provider produces a 401
    that reads like a broken adapter. Say what is actually wrong."""
    monkeypatch.setenv("CUBICLE_VISION_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("CUBICLE_VISION_MODEL", "m")
    monkeypatch.delenv("CUBICLE_VISION_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CUBICLE_VISION_API_KEY"):
        from_env()


def test_agent_satisfies_the_protocol(agent):
    from cubicle.agent import Agent

    assert isinstance(agent, Agent)


def test_a_rejected_key_stops_the_run_instead_of_scoring_zeros(agent, monkeypatch):
    """A 401 is a setup mistake, not an agent failure.

    Treated as a normal bad step it would burn the budget and publish a 0/7 that says
    nothing about the model - the same class of error the provider_error outcome exists
    to prevent. It has to be loud.
    """
    from cubicle.agents.openai_compat import ProviderAuthError

    class Rejected:
        status_code = 401
        text = "invalid api key"

    monkeypatch.setattr(agent._http, "post", lambda *a, **k: Rejected())
    with pytest.raises(ProviderAuthError, match="401"):
        agent.act(obs())


def test_throttling_is_still_a_provider_error_not_an_agent_failure(agent, monkeypatch):
    from cubicle.harness import ProviderUnavailable

    class Throttled:
        status_code = 429
        text = "slow down"

    monkeypatch.setattr(agent._http, "post", lambda *a, **k: Throttled())
    with pytest.raises(ProviderUnavailable):
        agent.act(obs())
