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


def test_a_task_result_never_carries_the_raw_session_token():
    """The Solari session id is a signed bearer token, and results.json is the artifact
    the README invites people to publish. It has been stripped by hand twice; that is
    twice too many for something that only has to leak once.

    A short fingerprint still answers "did these tasks run on the same desktop" without
    being usable as a credential.
    """
    import asyncio

    from cubicle.desktop import CubicleDesktop
    from cubicle.fixtures.build_seed import seed_bytes
    from cubicle.harness import run_task
    from cubicle.types import Action
    from tests.fake_desktop import FakeDesktop
    from tests.test_harness import BOOK_COPY, PASS, ScriptedAgent, make_task

    token = (
        "REDACTED-SESSION-TOKEN"
        ".REDACTED-SIGNATURE"
    )
    d = FakeDesktop()
    d.sessionId = token
    d.fs.files[BOOK_COPY] = seed_bytes("base")

    loop = asyncio.new_event_loop()
    try:
        r = run_task(CubicleDesktop(d, loop),
                     ScriptedAgent([Action(kind="done")]), make_task(PASS))
    finally:
        loop.close()

    assert token not in r.session_id
    assert token[:20] not in r.session_id
    assert r.session_id                      # still identifies the desktop
    assert len(r.session_id) <= 24
