"""Redact phone-like digit runs from stored speech text (issue 28)."""

from __future__ import annotations

import re
from typing import Any

# Digit runs of this length or more are treated as sensitive, including
# values that are not a well-formed Indian mobile number.
MIN_DIGIT_RUN = 8
REDACTION_PLACEHOLDER = "[redacted]"

# Contiguous 8+ digit runs first, including an immediately attached
# + / +91 / 91 prefix, so a longer run is never partially masked by
# a 10-digit mobile match in the middle.
_DIGIT_RUN = re.compile(rf"(?:\+91|\+|91)?\d{{{MIN_DIGIT_RUN},}}")

# Optional +91 / 91 / 0 prefix and common spacing or dashes around a
# 10-digit Indian mobile starting with 6-9, for forms that are not one
# contiguous digit run (for example "+91 98765 43210").
_SEPARATED_MOBILE = re.compile(
    r"(?:(?:\+91|91)[\s-]*|0)?[6-9]\d(?:[\s-]?\d){8}"
)

# Only these fields are rewritten. Short order tokens live in event.order_id
# and are left alone by the length rule above.
_TEXT_KEYS = ("transcript", "sample_text")
_EVENT_TEXT_KEYS = ("transcript",)


def redact_text(value: str) -> str:
    """Replace long digit runs and remaining Indian mobile shapes."""
    redacted = _DIGIT_RUN.sub(REDACTION_PLACEHOLDER, value)
    return _SEPARATED_MOBILE.sub(REDACTION_PLACEHOLDER, redacted)


def redact_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``record`` with speech-text fields redacted."""
    copied = dict(record)
    for key in _TEXT_KEYS:
        raw = copied.get(key)
        if isinstance(raw, str):
            copied[key] = redact_text(raw)
    event = copied.get("event")
    if isinstance(event, dict):
        event_copy = dict(event)
        for key in _EVENT_TEXT_KEYS:
            raw = event_copy.get(key)
            if isinstance(raw, str):
                event_copy[key] = redact_text(raw)
        copied["event"] = event_copy
    return copied
