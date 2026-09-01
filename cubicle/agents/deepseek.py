"""DeepSeek V4 Flash Vision.

The API caps every image at 384 tokens. A 1280x720 screenshot arrives heavily
downsampled, so this model is genuinely short-sighted on GUI work. That is a finding to
report, not a defect to hide - see the README.

Uses the OpenAI-compatible endpoint, which is what DeepSeek publishes.
"""

from __future__ import annotations

import base64
import pathlib

from cubicle.agents._json_action import parse_action
from cubicle.harness import UnparseableResponse
from cubicle.types import Action, Observation

SYSTEM = (pathlib.Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8")

MODEL = "deepseek-v4-flash-vision-exp"
BASE_URL = "https://api.deepseek.com"
KEEP_FRAMES = 3


class DeepSeekAgent:
    name = MODEL

    def __init__(self, api_key: str, keep_frames: int = KEEP_FRAMES) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=BASE_URL)
        self.keep_frames = keep_frames
        self._frames: list = []

    def reset(self) -> None:
        self._frames = []

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
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Task: {obs.task_prompt}\n\n"
                                    f"This is step {obs.step + 1} of at most "
                                    f"{obs.max_steps}. The last image is the current "
                                    "screen."
                                ),
                            },
                            *self._frames,
                        ],
                    },
                ],
                temperature=0.0,
                max_tokens=300,
            )
        except Exception as exc:  # noqa: BLE001 - a provider error is a failed step
            raise UnparseableResponse(f"{type(exc).__name__}: {str(exc)[:200]}") from exc

        return parse_action(response.choices[0].message.content or "")
