"""Placeholder extractor. Rules stand in until a free LLM is wired (issue 02).

The shape is the contract: transcript in, RiderEvent out. A non-mock
LLM_PROVIDER fails closed so a half-set key cannot pretend to be a model.
"""

import os
import re

from rasta.schema import Intent, RiderEvent, Urgency

_ORDER = re.compile(r"\border\s*#?\s*(\d{1,6})\b", re.IGNORECASE)
_ETA = re.compile(r"\b(\d{1,3})\s*(?:min|mins|minute|minutes|mint)\b", re.IGNORECASE)
_LONG_DIGITS = re.compile(r"\d{8,}")

# First match wins. accident and a missing item outrank a closed gate,
# because the canned line "gate band … phone nahi utha" is a contact problem.
_RULES: tuple[tuple[Intent, Urgency, tuple[str, ...], str], ...] = (
    (
        Intent.accident_sos,
        Urgency.high,
        ("accident", "hadsa", "gir gaya", "gir gayi", "sos"),
        "Stop the route and get a human on this rider. They may be hurt.",
    ),
    (
        Intent.item_missing,
        Urgency.medium,
        ("item missing", "missing item", "ek item", "item nahi"),
        "Hold the drop. Ask the hub to check the bag before the rider moves.",
    ),
    (
        Intent.customer_unreachable,
        Urgency.high,
        ("nahi utha", "phone nahi", "not picking", "unreachable"),
        "Call the customer once from dispatch, then log the attempt.",
    ),
    (
        Intent.address_issue,
        Urgency.medium,
        ("gate band", "galat address", "address galat", "location galat", "rasta band"),
        "Ask the customer for a landmark and hold the rider nearby.",
    ),
    (
        Intent.delay,
        Urgency.low,
        ("late", "delay", "traffic", "der ho", "der lag"),
        "Send the new ETA to the customer and leave the rider on this drop.",
    ),
)


def extract_event(transcript: str, provider: str | None = None) -> RiderEvent:
    name = provider if provider is not None else os.environ.get("LLM_PROVIDER", "mock")
    if name != "mock":
        raise NotImplementedError(
            f"LLM provider {name!r} is not in the skeleton. "
            "Keep LLM_PROVIDER=mock until issue 02."
        )
    return _by_rules(transcript)


def _by_rules(transcript: str) -> RiderEvent:
    haystack = transcript.lower()
    intent = Intent.other
    urgency = Urgency.low
    action = "Read the transcript. No rule matched, so a person should."
    confidence = 0.0
    for candidate, level, needles, instruction in _RULES:
        if any(needle in haystack for needle in needles):
            intent = candidate
            urgency = level
            action = instruction
            confidence = 0.5
            break
    return RiderEvent(
        intent=intent,
        order_id=_order_id(transcript),
        eta_minutes=_eta(transcript),
        urgency=urgency,
        dispatch_action=action,
        transcript=transcript,
        confidence=confidence,
    )


def _order_id(transcript: str) -> str | None:
    match = _ORDER.search(transcript)
    if not match:
        return None
    token = match.group(1)
    if _LONG_DIGITS.fullmatch(token):
        return None
    return token


def _eta(transcript: str) -> int | None:
    match = _ETA.search(transcript)
    if not match:
        return None
    return int(match.group(1))
