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
import re
import time

import httpx

from cubicle.agents._json_action import parse_action
from cubicle.harness import ProviderUnavailable, UnparseableResponse
from cubicle.types import Action, Observation

SYSTEM = (pathlib.Path(__file__).parent / "system_prompt.txt").read_text(encoding="utf-8")

# gemini-2.5-flash and -flash-lite return "no longer available to new users" on keys
# issued now, even though they still appear in models.list. gemini-3.7-flash answers but
# is a thinking model that blew a 90s timeout on a one-pixel image, which is unusable in
# a per-step loop. gemini-3-flash-preview responds fast and takes inline images.
MODEL = "gemini-3-flash-preview"
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
# Measured, not assumed: at 6.5s between calls the free tier still returned 429 on 11
# of 15 steps. The published "10 RPM" is not what this preview model actually allows,
# so pace conservatively and back off hard rather than burning the step budget.
MIN_INTERVAL_S = 15.0
FIRST_BACKOFF_S = 20.0
MAX_BACKOFF_S = 90.0
MAX_ATTEMPTS = 4
KEEP_FRAMES = 3       # bounded history keeps input tokens flat across a long task


def _redact(text: str, secret: str) -> str:
    """Never let a key reach a trace file.

    Gemini accepts the key as a `?key=` query parameter, and httpx puts the full URL
    into HTTPStatusError. That message goes straight into actions.jsonl - which the
    README invites people to publish as evidence. We send the key as a header instead,
    and scrub it here as a second line of defence.
    """
    if secret and secret in text:
        text = text.replace(secret, "<redacted>")
    return re.sub(r"key=[\w.\-]+", "key=<redacted>", text)


def _quota_message(response) -> str:
    """Turn a 429 into something that names the actual limit.

    The free tier's real constraint is a DAILY per-model cap, not a per-minute one, so
    "rate limited" would send someone tuning a throttle that cannot help.
    """
    try:
        for detail in response.json().get("error", {}).get("details", []):
            for violation in detail.get("violations", []):
                qid = violation.get("quotaId", "?")
                val = violation.get("quotaValue", "?")
                return f"provider quota exhausted: {qid}={val}"
    except Exception:  # noqa: BLE001
        pass
    return "provider rate limited (HTTP 429)"


def _extract_text(body: dict) -> str:
    """Some Gemini models return a candidate with no `parts` at all - a thinking model
    that spent its whole budget, or a safety stop. Fail loudly rather than KeyError."""
    candidates = body.get("candidates") or []
    if not candidates:
        raise UnparseableResponse(f"no candidates in response: {str(body)[:160]}")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    if not text.strip():
        reason = candidates[0].get("finishReason", "unknown")
        raise UnparseableResponse(f"empty response (finishReason={reason})")
    return text


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
            response = self._post(obs)
            if response.status_code == 429:
                raise ProviderUnavailable(_quota_message(response))
            response.raise_for_status()
            body = response.json()
            text = _extract_text(body)
        except (UnparseableResponse, ProviderUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001 - a provider error is a failed step
            raise UnparseableResponse(
                _redact(f"{type(exc).__name__}: {str(exc)[:200]}", self.api_key)
            ) from exc

        return parse_action(text)

    def _post(self, obs: Observation):
        """POST with backoff on 429. Google's 429 IS retryable, unlike Solari's."""
        delay = FIRST_BACKOFF_S
        last = None
        for attempt in range(MAX_ATTEMPTS):
            last = self._http.post(
                ENDPOINT,
                headers={"x-goog-api-key": self.api_key},
                json=self.build_payload(obs),
            )
            if last.status_code != 429:
                return last
            # Honour Retry-After when the server sends one; it knows the real quota.
            wait = float(last.headers.get("retry-after") or delay)
            if attempt < MAX_ATTEMPTS - 1:
                time.sleep(min(wait, MAX_BACKOFF_S))
                delay = min(delay * 2, MAX_BACKOFF_S)
        return last
