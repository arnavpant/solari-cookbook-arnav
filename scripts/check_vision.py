"""Does the configured vision endpoint actually work?

One image request against whatever CUBICLE_VISION_* points at. Run it before run.py: a
full benchmark costs Solari desktop time, and discovering a 401 or a text-only model
four minutes in wastes it.

Never prints the key.

  python scripts/check_vision.py
"""

from __future__ import annotations

import base64
import os
import pathlib
import sys

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402

# A 2x2 red PNG. Tiny, valid, and enough to prove the endpoint accepts images at all -
# which is the failure this script exists to catch, since a text-only model connects
# happily and then fails every step of a real run.
_PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVQI12P8z8Dwn4"
    "EIwESMolGFxCkEAJifAwEP0Xu0AAAAAElFTkSuQmCC"
)


def redact(key: str | None) -> str:
    if not key:
        return "(none - local endpoint)"
    return f"{key[:4]}...{key[-2:]} ({len(key)} chars)"


def main() -> int:
    load_dotenv()

    from cubicle.agents.openai_compat import ProviderAuthError, from_env

    try:
        agent = from_env()
    except RuntimeError as exc:
        print(f"not configured: {exc}", file=sys.stderr)
        return 2

    print(f"endpoint : {agent.endpoint}")
    print(f"model    : {agent.model}")
    print(f"key      : {redact(agent.api_key)}")
    print()

    shot = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    png = shot.read_bytes() if shot and shot.exists() else _PIXEL
    print(f"sending  : {shot if shot and shot.exists() else 'a 2x2 test image'}")

    payload = {
        "model": agent.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Reply with the single word: ok"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64," + base64.b64encode(png).decode()
                        },
                    },
                ],
            }
        ],
        "max_tokens": 20,
        "temperature": 0.0,
    }

    try:
        r = agent._http.post(agent.endpoint, headers=agent.headers, json=payload)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED   : could not reach the endpoint - {type(exc).__name__}: {exc}")
        return 1

    print(f"status   : HTTP {r.status_code}")
    if r.status_code in (401, 403):
        print("FAILED   : credentials rejected. Check CUBICLE_VISION_API_KEY.")
        return 1
    if r.status_code == 429:
        print("THROTTLED: the endpoint is rate limiting. The key works; wait and retry.")
        return 1
    if r.status_code != 200:
        body = r.text[:300]
        print(f"FAILED   : {body}")
        if "image" in body.lower() or "modal" in body.lower():
            print("           ^ this usually means the model is text-only. Pick a "
                  "vision model.")
        return 1

    try:
        choice = r.json()["choices"][0]
        answered = r.json().get("model", agent.model)
        text = (choice["message"].get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED   : unreadable response - {exc}: {r.text[:200]}")
        return 1

    print(f"answered : {answered}")
    print(f"reply    : {text.splitlines()[0][:120] if text else '(empty)'}")
    print()
    if not text:
        print("WARNING  : empty reply. If this is a reasoning model, raise "
              "CUBICLE_VISION_MAX_TOKENS.")
        return 1

    print("OK - this endpoint accepts images and answers. Next:")
    print("  python scripts/vision_probe.py setup-verify.png   # can it point?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
