"""Can the model SEE the screen, or only fail to act on it?

A 0/7 is not a finding until you know which. This asks the model to read a real cubicle
screenshot and report where the account rows are. Ground truth is known exactly:

    Assets    y=217
    Expenses  y=241
    Income    y=264

If it names the accounts but misplaces them, the deficit is localization. If it cannot
name them, the deficit is resolution - which for DeepSeek would be the documented
384-token image cap doing exactly what you would expect.

  python scripts/vision_probe.py <screenshot.png>
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

QUESTION = (
    "This is a screenshot of the GnuCash accounting application at 1280x720.\n\n"
    "1. List every account name you can read in the account tree.\n"
    "2. For each one, give the y pixel coordinate of its row.\n"
    "3. Give the x,y of the 'New' button in the toolbar.\n\n"
    "Answer plainly. If you cannot read something, say so rather than guessing."
)

TRUTH = "Assets y=217, Expenses y=241, Income y=264, New button ~(389, 115)"


def ask_deepseek(b64: str, key: str) -> str:
    from cubicle.agents.deepseek import ENDPOINT, MAX_TOKENS, MODEL

    r = httpx.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": QUESTION},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ]}],
            "temperature": 0.0,
            "max_tokens": MAX_TOKENS,
        },
        timeout=180,
    )
    if r.status_code != 200:
        return f"[HTTP {r.status_code}] {r.text[:200]}"
    return (r.json()["choices"][0]["message"].get("content") or "").strip() or "[empty]"


def ask_gemini(b64: str, key: str, model: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = httpx.post(
        url,
        headers={"x-goog-api-key": key},
        json={
            "contents": [{"role": "user", "parts": [
                {"text": QUESTION},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 600},
        },
        timeout=180,
    )
    if r.status_code != 200:
        return f"[HTTP {r.status_code}] {r.text[:160]}"
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip() or "[empty]"
    except Exception as exc:  # noqa: BLE001
        return f"[unreadable response: {exc}]"


def main(argv: list[str]) -> int:
    load_dotenv()
    if len(argv) < 2:
        print("usage: python scripts/vision_probe.py <screenshot.png>", file=sys.stderr)
        return 2

    b64 = base64.b64encode(Path(argv[1]).read_bytes()).decode()
    print(f"screenshot: {argv[1]}")
    print(f"ground truth: {TRUTH}\n")

    if key := os.environ.get("DEEPSEEK_API_KEY"):
        print("=" * 72)
        print("DeepSeek V4 Flash Vision  (API caps every image at 384 tokens)")
        print("=" * 72)
        print(ask_deepseek(b64, key), "\n")

    if key := os.environ.get("GEMINI_API_KEY"):
        # gemini-2.5-computer-use is the one that matters: a model post-trained to
        # ground clicks in a GUI, rather than a general vision model asked to guess.
        # If it stretches the y axis the way the flash models do, the finding is about
        # computer-use models and not about model size. It has free-tier quota, but a
        # small daily one - a 429 here usually means "tomorrow", not "pay".
        for model in ("gemini-2.5-computer-use-preview-10-2025",
                      "gemini-3.5-flash",
                      "gemini-flash-lite-latest"):
            print("=" * 72)
            print(f"Gemini {model}")
            print("=" * 72)
            out = ask_gemini(b64, key, model)
            if out.startswith("[HTTP 429]"):
                out = ("[HTTP 429] free-tier daily cap for this model is spent. "
                       "It resets at midnight Pacific; this costs nothing to retry.")
            print(out, "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
