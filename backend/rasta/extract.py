"""Transcript -> RiderEvent.

``LLM_PROVIDER=rules`` (the default) is a deterministic keyword extractor.
It is the real fallback when no free LLM key is set, and issue 02 keeps it
behind the Groq/Gemini path. Any other provider fails closed until issue 02
wires it, so a half-set key cannot pretend to be a model.

The pipeline asks Prisma for ``format=transliterate``, so transcripts arrive
in Latin script with numbers spoken as words ("order eighteen", "das
minute"). Both digits and number words are parsed.
"""

import os
import re

from rasta.schema import Intent, RiderEvent, Urgency

_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
    # Romanised Hindi, the way riders say minutes.
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "pandrah": 15, "pandra": 15, "bees": 20, "pachchis": 25, "pachees": 25,
    "tees": 30, "chalis": 40, "chaalis": 40, "paintalis": 45, "pachas": 50,
    "pachaas": 50, "saath": 60,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_WORD = "|".join(sorted([*_ONES, *_TENS], key=len, reverse=True))
_NUMBER = rf"(\d{{1,6}}|(?:{_NUMBER_WORD})(?:[\s-]+(?:{_NUMBER_WORD}))?)"
_ORDER = re.compile(rf"\border\s*(?:no\.?|number|#)?\s*{_NUMBER}\b", re.IGNORECASE)
_ETA = re.compile(
    rf"\b{_NUMBER}\s*(?:min|mins|minute|minutes|mint|minat)\b", re.IGNORECASE
)
_LONG_DIGITS = re.compile(r"\d{8,}")

# First match wins. accident and a missing item outrank a closed gate,
# because "gate band … phone nahi utha" is a contact problem first.
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
    name = provider if provider is not None else os.environ.get("LLM_PROVIDER", "rules")
    if name != "rules":
        raise NotImplementedError(
            f"LLM provider {name!r} is not wired yet. "
            "Use LLM_PROVIDER=rules until issue 02."
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
    value = _to_int(token)
    return None if value is None else str(value)


def _eta(transcript: str) -> int | None:
    match = _ETA.search(transcript)
    if not match:
        return None
    return _to_int(match.group(1))


def _to_int(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    total = 0
    for word in re.split(r"[\s-]+", token.lower()):
        if word in _TENS:
            total += _TENS[word]
        elif word in _ONES:
            total += _ONES[word]
        else:
            return None
    return total
