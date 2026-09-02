"""Bring your own endpoint.

The README invites people to put their agent on the leaderboard. Until now that meant
writing a class, which is a strange thing to ask of someone who just wants to see how
their model does.

Almost every model worth pointing at this benchmark is reachable over the same
OpenAI-compatible chat API - OpenRouter, Groq, GitHub Models, NVIDIA NIM, Mistral,
Together, DeepSeek - and so is Ollama running on your own machine. One adapter,
configured by three environment variables, covers all of them:

    CUBICLE_VISION_BASE_URL=https://openrouter.ai/api/v1
    CUBICLE_VISION_MODEL=qwen/qwen2.5-vl-72b-instruct:free
    CUBICLE_VISION_API_KEY=sk-or-...

    python scripts/run.py --agent vision --tasks all

The API key is optional only for a loopback address, because Ollama serves this API
with no auth and is the one genuinely unmetered option. Requiring a key would exclude it.

Deliberately no `openai` SDK, for the same reason the other adapters avoid it: openai
1.39 passes `proxies=` to httpx, which newer httpx removed, so constructing the client
dies with `Client.__init__() got an unexpected keyword argument 'proxies'`. The call is
twenty lines of httpx and this repo has to install cleanly for strangers.
"""

from __future__ import annotations

import base64
import os
import pathlib
from urllib.parse import urlparse

import httpx

from cubicle.agents._json_action import parse_action
from cubicle.harness import ProviderUnavailable, UnparseableResponse
from cubicle.types import Action, Observation

# The same committed prompt every other model in the suite receives, byte for byte.
# Per-model prompt tuning would measure prompt engineering rather than capability.
SYSTEM = (pathlib.Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8")

KEEP_FRAMES = 3
MAX_TOKENS = 2000

_LOOPBACK = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class ProviderAuthError(RuntimeError):
    """The endpoint refused the credentials.

    Not a ProviderUnavailable and emphatically not a failed step: a rejected key would
    otherwise burn the whole budget and publish a zero that says nothing about the
    model. It stops the run.
    """


def _is_loopback(base_url: str) -> bool:
    return (urlparse(base_url).hostname or "").lower() in _LOOPBACK


class OpenAICompatAgent:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        keep_frames: int = KEEP_FRAMES,
        max_tokens: int = MAX_TOKENS,
        name: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.keep_frames = keep_frames
        self.max_tokens = max_tokens
        # Default the leaderboard label to the model id, so a row always says exactly
        # what ran rather than a friendly name nobody can trace back to a checkpoint.
        self.name = name or model
        self._frames: list[dict] = []
        self._http = httpx.Client(timeout=180.0)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    @property
    def headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def reset(self) -> None:
        self._frames = []

    def _remember(self, obs: Observation) -> None:
        encoded = base64.b64encode(obs.screenshot_png).decode()
        self._frames.append(
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}}
        )
        self._frames = self._frames[-self.keep_frames :]

    def build_payload(self, obs: Observation) -> dict:
        """Split out from act() so it is testable with no key and no network."""
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Task: {obs.task_prompt}\n\n"
                                f"This is step {obs.step + 1} of at most "
                                f"{obs.max_steps}. The last image is the current screen."
                            ),
                        },
                        *self._frames,
                    ],
                },
            ],
            "temperature": 0.0,
            "max_tokens": self.max_tokens,
        }

    def act(self, obs: Observation) -> Action:
        self._remember(obs)
        try:
            response = self._http.post(
                self.endpoint, headers=self.headers, json=self.build_payload(obs)
            )
            if response.status_code in (401, 403):
                raise ProviderAuthError(
                    f"{self.base_url} rejected the credentials (HTTP "
                    f"{response.status_code}): {response.text[:160]}. Check "
                    "CUBICLE_VISION_API_KEY - this is a setup error, not a model result."
                )
            if response.status_code in (429, 402, 503):
                raise ProviderUnavailable(
                    f"provider unavailable (HTTP {response.status_code}): "
                    f"{response.text[:160]}"
                )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            text = choice["message"].get("content") or ""
            if not text.strip():
                reason = choice.get("finish_reason", "unknown")
                raise UnparseableResponse(
                    f"no content (finish_reason={reason}); a reasoning model may have "
                    f"spent its whole budget before answering - raise "
                    f"CUBICLE_VISION_MAX_TOKENS (currently {self.max_tokens})"
                )
        except (UnparseableResponse, ProviderUnavailable, ProviderAuthError):
            raise
        except Exception as exc:  # noqa: BLE001 - a provider error is a failed step
            raise UnparseableResponse(f"{type(exc).__name__}: {str(exc)[:200]}") from exc

        return parse_action(text)


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. The generic vision agent needs "
            "CUBICLE_VISION_BASE_URL and CUBICLE_VISION_MODEL (and "
            "CUBICLE_VISION_API_KEY unless the endpoint is local). See "
            "docs/free-models.md."
        )
    return value


def from_env() -> OpenAICompatAgent:
    base_url = _require("CUBICLE_VISION_BASE_URL")
    model = _require("CUBICLE_VISION_MODEL")

    api_key = os.environ.get("CUBICLE_VISION_API_KEY") or None
    if api_key is None and not _is_loopback(base_url):
        raise RuntimeError(
            f"CUBICLE_VISION_API_KEY is not set and {base_url} is not a local endpoint. "
            "Sending an unauthenticated request would come back 401 and look like a "
            "broken adapter."
        )

    return OpenAICompatAgent(
        base_url=base_url,
        model=model,
        api_key=api_key,
        max_tokens=int(os.environ.get("CUBICLE_VISION_MAX_TOKENS", MAX_TOKENS)),
        name=os.environ.get("CUBICLE_VISION_NAME") or None,
    )
