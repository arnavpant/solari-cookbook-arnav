"""No credential may ever reach a tracked file.

This exists because a real one nearly did: while writing the gotcha about not putting
API keys in URLs, the example quoted a fragment of the actual key. The verification pass
caught it one commit before the repo went public.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Prefixes of the credentials this project uses. Deliberately matched on shape, so a
# fragment is caught as well as a whole key.
PATTERNS = [
    re.compile(r"slr_live_[A-Za-z0-9_\-]{8,}"),      # Solari
    re.compile(r"AQ\.[A-Za-z0-9_\-]{8,}"),           # Google AI Studio
    re.compile(r"sk-[a-f0-9]{16,}"),                 # DeepSeek / OpenAI style
    re.compile(r"AIza[A-Za-z0-9_\-]{20,}"),          # Google API key
]

ALLOWED = {"tests/test_no_secrets.py"}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [Path(p) for p in out if p not in ALLOWED]


def test_no_credential_appears_in_any_tracked_file():
    offenders = []
    for path in tracked_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path}: matches {pattern.pattern}")
    assert not offenders, "credential-shaped strings in tracked files:\n" + "\n".join(offenders)


def test_env_is_never_tracked():
    assert Path(".env") not in tracked_files()
