"""Gemini 2.5 Flash, over the REST API.

Deliberately no google-genai SDK. It pulls in `cryptography`, which has no prebuilt
wheel on some Pythons and fails to build - and a benchmark other people are meant to run
should not need a compiler. The REST call is a dozen lines and `httpx` is already a
Solari dependency.

Free tier, so this throttles itself rather than relying on retries. The free tier also
lets Google train on prompts and responses; the README states that plainly.
"""

from __future__ import annotations

import base64
import pathlib
import time

import httpx

from cubicle.agents._json_action import parse_action
from cubicle.harness import UnparseableResponse
from cubicle.types import Action, Observation

SYSTEM = (pathlib.Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8")

MODEL = "gemini-2.5-flash"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MIN_INTERVAL_S = 6.5  # free tier is ~10 RPM; stay comfortably under it
KEEP_FRAMES = 3       # bounded history keeps input tokens flat across a long task


class GeminiAgent:
    name = MODEL

    def __init__(self, api_key: str, keep_frames: int = KEEP_FRAMES) -> None:
        self.api_key = api_key
        self.keep_frames = keep_frames
        self._frames: list[str] = []
        self._last_call = 0.0
        self._http = httpx.Client(timeout=120.0)

    def reset(self) -> None:
        self._frames = []

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - elapsed)
        self._last_call = time.monotonic()

    def build_payload(self, obs: Observation) -> dict:
        """Split out from act() so it can be tested without a key or a network."""
        parts: list[dict] = [
            {
                "text": (
                    f"Task: {obs.task_prompt}\n\n"
                    f"This is step {obs.step + 1} of at most {obs.max_steps}. "
                    "The last image is the current screen."
                )
            }
        ]
        for frame in self._frames:
            parts.append({"inline_data": {"mime_type": "image/png", "data": frame}})

        return {
            "system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 300},
        }

    def act(self, obs: Observation) -> Action:
        self._frames.append(base64.b64encode(obs.screenshot_png).decode())
        self._frames = self._frames[-self.keep_frames :]

        self._throttle()
        try:
            response = self._http.post(
                ENDPOINT,
                params={"key": self.api_key},
                json=self.build_payload(obs),
            )
            if response.status_code == 429:
                # Google's 429 IS retryable, unlike Solari's. Back off once and retry.
                time.sleep(20)
                response = self._http.post(
                    ENDPOINT,
                    params={"key": self.api_key},
                    json=self.build_payload(obs),
                )
            response.raise_for_status()
            body = response.json()
            text = body["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:  # noqa: BLE001 - a provider error is a failed step
            raise UnparseableResponse(f"{type(exc).__name__}: {str(exc)[:200]}") from exc

        return parse_action(text)
