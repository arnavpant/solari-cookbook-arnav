"""Check every credential cubicle needs, without printing any of them.

Each check is a real minimal API call - a key that is present but rejected is worse
than one that is missing, because it fails an hour into a benchmark run instead of
immediately.

  python scripts/check_keys.py
"""

from __future__ import annotations

import os
import sys

import certifi

os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from dotenv import load_dotenv  # noqa: E402

CHECKS: list[tuple[str, str]] = [
    ("SOLARI_API_KEY", "Solari      "),
    ("GEMINI_API_KEY", "Gemini      "),
    ("DEEPSEEK_API_KEY", "DeepSeek    "),
]


def mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-2:]} ({len(value)} chars)"


def check_solari(key: str) -> tuple[bool, str]:
    import httpx

    try:
        r = httpx.get(
            "https://api.getsolari.com/desktops",
            headers={"Authorization": f"Bearer {key}"},
            timeout=30,
        )
        if r.status_code in (401, 403):
            return False, f"rejected ({r.status_code})"
        return True, f"accepted ({r.status_code})"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:70]}"


def check_gemini(key: str) -> tuple[bool, str]:
    import httpx

    from cubicle.agents.gemini import MODEL

    try:
        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
            params={"key": key},
            json={"contents": [{"role": "user", "parts": [{"text": "Reply with: ok"}]}]},
            timeout=60,
        )
        if r.status_code != 200:
            detail = r.json().get("error", {}).get("message", r.text)[:90]
            return False, f"HTTP {r.status_code}: {detail}"
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        return True, f"replied {text[:30]!r}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:70]}"


def check_deepseek(key: str) -> tuple[bool, str]:
    import httpx

    from cubicle.agents.deepseek import ENDPOINT, MODEL

    try:
        r = httpx.post(
            ENDPOINT,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": "Reply with: ok"}],
                "max_tokens": 10,
            },
            timeout=60,
        )
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}: {r.text[:90]}"
        return True, f"replied {r.json()['choices'][0]['message']['content'].strip()[:30]!r}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {str(exc)[:70]}"


CHECKERS = {
    "SOLARI_API_KEY": check_solari,
    "GEMINI_API_KEY": check_gemini,
    "DEEPSEEK_API_KEY": check_deepseek,
}


def main() -> int:
    load_dotenv()
    print("Checking credentials. Values are never printed.\n")

    missing = []
    failed = []
    for env_name, label in CHECKS:
        value = (os.environ.get(env_name) or "").strip()
        if not value:
            print(f"  {label}  MISSING   {env_name} is empty in .env")
            missing.append(env_name)
            continue

        ok, detail = CHECKERS[env_name](value)
        status = "OK      " if ok else "REJECTED"
        print(f"  {label}  {status}  {mask(value)}  -  {detail}")
        if not ok:
            failed.append(env_name)

    print()
    if missing:
        print("Missing:", ", ".join(missing))
        print("  Gemini keys are free at https://aistudio.google.com/apikey")
    if failed:
        print("Rejected:", ", ".join(failed))
    if not missing and not failed:
        print("All credentials working.")
    return 1 if (missing or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
