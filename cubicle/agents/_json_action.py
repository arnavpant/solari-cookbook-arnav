"""Turn a model's reply into an Action, or refuse to.

Deliberately strict. An agent that cannot emit a valid action IS failing, and papering
over that with a lenient parser would flatter the model and corrupt the benchmark.
"""

from __future__ import annotations

import json
import re

from cubicle.harness import UnparseableResponse
from cubicle.types import Action

_FENCED = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)
_BARE = re.compile(r"\{.*\}", re.S)

_ALLOWED = {
    "kind",
    "x",
    "y",
    "text",
    "scroll_direction",
    "scroll_amount",
    "to_x",
    "to_y",
}


def parse_action(text: str) -> Action:
    raw = (text or "").strip()

    # A list of actions is a format violation even when its contents are valid: the
    # contract is exactly one object per step, and _BARE would happily pull the object
    # out of the array and hide the mistake.
    if raw.startswith("["):
        raise UnparseableResponse("expected a single JSON object, got an array")

    match = _FENCED.search(raw) or _BARE.search(raw)
    if not match:
        raise UnparseableResponse(f"no JSON object in response: {raw[:200]!r}")

    blob = match.group(1) if match.lastindex else match.group(0)
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise UnparseableResponse(f"invalid JSON: {exc}: {blob[:200]!r}") from exc

    if not isinstance(data, dict):
        raise UnparseableResponse(f"expected a JSON object, got {type(data).__name__}")

    unknown = set(data) - _ALLOWED
    if unknown:
        # Tolerated rather than fatal: models like to add "reason" or "thought".
        data = {k: v for k, v in data.items() if k in _ALLOWED}

    try:
        return Action(**data)
    except (TypeError, ValueError) as exc:
        raise UnparseableResponse(f"{exc}: {blob[:200]!r}") from exc
