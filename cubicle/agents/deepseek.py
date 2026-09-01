"""DeepSeek V4 Flash Vision, over the REST API.

The API caps every image at 384 tokens. A 1280x720 screenshot arrives heavily
downsampled, so this model is genuinely short-sighted on GUI work. That is a finding to
report, not a defect to hide - see the README.

Deliberately no `openai` SDK, for the same reason Gemini does not use google-genai:
openai 1.39 passes `proxies=` to httpx, which newer httpx removed, so constructing the
client dies with `Client.__init__() got an unexpected keyword argument 'proxies'`. The
endpoint is OpenAI-compatible and the call is fifteen lines; pinning two more packages
to work around a transitive break is not worth it in a repo other people must install.
"""

from __future__ import annotations

import base64
import pathlib

import httpx

from cubicle.agents._json_action import parse_action
from cubicle.harness import ProviderUnavailable, UnparseableResponse
from cubicle.types import Action, Observation

SYSTEM = (pathlib.Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8")

MODEL = "deepseek-v4-flash-vision-exp"
BASE_URL = "https://api.deepseek.com"
ENDPOINT = f"{BASE_URL}/chat/completions"
KEEP_FRAMES = 3

# This is a REASONING model: it spends completion tokens on `reasoning_content` before
# writing anything to `content`. At max_tokens=300 it burned all 300 on reasoning and
# returned content='' with finish_reason='length' - which looks exactly like a broken
# model and is really a budget that is too small. It needs ~200-300 reasoning tokens
# before the answer, so give it real headroom.
MAX_TOKENS = 2000


class DeepSeekAgent:
    name = MODEL

    def __init__(self, api_key: str, keep_frames: int = KEEP_FRAMES) -> None:
        self.api_key = api_key
        self.keep_frames = keep_frames
        self._frames: list[dict] = []
        self._http = httpx.Client(timeout=120.0)

    def reset(self) -> None:
        self._frames = []

    def build_payload(self, obs: Observation) -> dict:
        """Split out from act() so it is testable with no key and no network."""
        return {
            "model": MODEL,
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
            "max_tokens": MAX_TOKENS,
        }

    def act(self, obs: Observation) -> Action:
        encoded = base64.b64encode(obs.screenshot_png).decode()
        self._frames.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded}"},
            }
        )
        self._frames = self._frames[-self.keep_frames :]

        try:
            response = self._http.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=self.build_payload(obs),
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
                # Name the real cause. "empty response" would send someone hunting for
                # a model bug when the budget is what ran out.
                reason = choice.get("finish_reason", "unknown")
                raise UnparseableResponse(
                    f"no content (finish_reason={reason}); the model spent its whole "
                    f"budget on reasoning - raise MAX_TOKENS"
                )
        except (UnparseableResponse, ProviderUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001 - a provider error is a failed step
            raise UnparseableResponse(f"{type(exc).__name__}: {str(exc)[:200]}") from exc

        return parse_action(text)
