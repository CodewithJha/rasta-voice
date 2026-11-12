"""Parse a free-tier model response into a frozen ``RiderEvent``."""

from __future__ import annotations

import json
import re
from typing import Any

from rasta.extractors.base import LlmError
from rasta.schema import RiderEvent

# Same policy as the rules extractor: an 8+ digit token is not an order id.
_LONG_DIGITS = re.compile(r"\d{8,}")
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _unwrap_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE.sub("", text).strip()
    # Some models wrap the object in a leading sentence. Prefer the first
    # JSON object if the whole string does not parse.
    return text


def _load_object(raw: str) -> dict[str, Any]:
    text = _unwrap_text(raw)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LlmError("model did not return JSON", reason="invalid_json") from None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LlmError("model did not return JSON", reason="invalid_json") from exc
    if not isinstance(payload, dict):
        raise LlmError("model JSON was not an object", reason="invalid_json")
    return payload


def event_from_model_text(raw: str, transcript: str) -> RiderEvent:
    """Validate model text against ``RiderEvent``.

    The stored transcript is always the caller's text, not whatever the
    model echoed, so a prompt-injection attempt cannot rewrite it. An
    8-digit ``order_id`` is rejected rather than silently copied.
    """
    payload = _load_object(raw)
    payload = dict(payload)
    payload["transcript"] = transcript
    order = payload.get("order_id")
    if isinstance(order, str) and _LONG_DIGITS.search(order):
        raise LlmError(
            "model copied a long digit run into order_id",
            reason="schema_invalid",
        )
    try:
        return RiderEvent.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError
        raise LlmError("model JSON failed RiderEvent validation", reason="schema_invalid") from exc
