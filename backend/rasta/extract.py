"""Transcript -> RiderEvent.

``LLM_PROVIDER=rules`` (the default) is a deterministic keyword extractor.
It is the real fallback when no free LLM key is set, when the free tier
fails, and when the circuit breaker is open. Issue 02 keeps it behind the
Groq/Gemini path. CI always runs this path.

Prisma transcripts arrive with ``format=transliterate``: Latin script,
numbers often as words ("order eighteen", "das minute"). Both digits and
number words are parsed. The rules themselves stay generalisable Hinglish
patterns; they must not memorise a holdout line.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from rasta.extractors.base import ExtractResult, LlmError
from rasta.extractors.breaker import ensure_closed
from rasta.llm import get_llm_extractor
from rasta.schema import Intent, RiderEvent, Urgency
from rasta.settings import get_settings

log = logging.getLogger("rasta")

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

# First match wins. Accident outranks a missing item; a missing item
# outranks a closed gate or an unanswered phone; an unanswered phone
# outranks a closed gate. "gate band … phone nahi utha" is a contact
# problem first.
_ACTION = {
    Intent.accident_sos: (
        "Stop the route and get a human on this rider. They may be hurt."
    ),
    Intent.item_missing: (
        "Hold the drop. Ask the hub to check the bag before the rider moves."
    ),
    Intent.customer_unreachable: (
        "Call the customer once from dispatch, then log the attempt."
    ),
    Intent.address_issue: (
        "Ask the customer for a landmark and hold the rider nearby."
    ),
    Intent.delay: (
        "Send the new ETA to the customer and leave the rider on this drop."
    ),
    Intent.other: "Read the transcript. No rule matched, so a person should.",
}


@dataclass(frozen=True, slots=True)
class _Rule:
    """A keyword rule. ``any_of`` is a substring OR; ``all_groups`` is AND-of-ORs.

    ``detect`` replaces both when set. The customer-unreachable rule uses it
    so failure is bound to the phone channel instead of a bag of words.
    """

    intent: Intent
    urgency: Urgency
    any_of: tuple[str, ...] = ()
    all_groups: tuple[tuple[str, ...], ...] = ()
    detect: Callable[[str], bool] | None = None

    def matches(self, haystack: str) -> bool:
        if self.detect is not None:
            return self.detect(haystack)
        if self.any_of and any(needle in haystack for needle in self.any_of):
            return True
        if self.all_groups and all(
            any(needle in haystack for needle in group) for group in self.all_groups
        ):
            return True
        return False


# Failed contact is a phrase in which the failure term is bound to the
# phone / line / number / call channel, or an inherently contact-failure
# phrase. Success counts only as successful customer contact: the success
# verb is bound, in the same clause, to that channel and/or to the
# customer as actor. Clause boundaries are comma, semicolon, period, and
# the connectives aur, lekin, par (not "phone par"), but, ab, and phir.
# A bare "confirm kar di" (address, packing, entry, or an unspecified
# actor) is not contact success. A rider saying they themselves are busy
# is never a failed call. Latest-state comparison is only between a
# bound failure span and a bound success span.
_CHANNEL = r"(?:phone|mobile|call|line|number)"
# At most five tokens between the channel word and the failure term.
_GAP = r"(?:\W+\w+){0,5}"
_UTHA_FAIL = r"(?:nahi\s+utha\w*|utha(?:ya|ta|te)?\s+nahi)"

_FAILED_CONTACT: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("channel_busy", re.compile(rf"\b{_CHANNEL}{_GAP}\W+busy\b")),
    ("busy_channel", re.compile(rf"\bbusy{_GAP}\W+{_CHANNEL}\b")),
    ("switched_off", re.compile(r"\bswitch(?:ed)?\s+off\b")),
    ("channel_off", re.compile(rf"\b{_CHANNEL}{_GAP}\W+off\b")),
    (
        "channel_band",
        re.compile(r"\b(?:phone|mobile|number)(?:\W+\w+){0,3}\W+band\b"),
    ),
    ("line_not_found", re.compile(r"\bline\b(?:\W+\w+){0,3}\W+nahi\s+mil")),
    ("not_connecting", re.compile(rf"\b{_CHANNEL}{_GAP}\W+nahi\s+lag")),
    (
        "channel_not_picking_up",
        re.compile(
            rf"\b{_CHANNEL}{_GAP}\W+{_UTHA_FAIL}"
            rf"|\b{_UTHA_FAIL}{_GAP}\W+{_CHANNEL}\b"
            rf"|\bpickup\s+nahi(?:\W+\w+){{0,3}}\W+{_CHANNEL}"
            rf"|\b{_CHANNEL}(?:\W+\w+){{0,3}}\W+pickup\s+nahi"
        ),
    ),
    (
        "not_picking_up",
        re.compile(
            r"\b(?:nahi\s+utha\w*|utha(?:ya|ta|te)?\s+nahi|not\s+picking"
            r"|not\s+answering|no\s+answer|unreachable|not\s+reachable)\b"
        ),
    ),
    ("receive_failed", re.compile(r"\breceive\s+(?:hi\s+)?nahi\b|\breceive\s+ki\s+nahi\b")),
    (
        "ring_unanswered",
        re.compile(r"\bring\s+ja\s+rahi(?:\W+\w+){0,6}\W+utha\s+nahi"),
    ),
)

_SUCCESS_CONTACT: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("baat_ho_gayi", re.compile(r"\bbaat\s+ho\s+(?:gayi|gai|gaya|chuki|chuka)\b")),
    (
        "receive_ok",
        re.compile(r"\breceive\s+(?:kar\s+liya|kar\s+li|kiya|ki)\b(?!\s+nahi)"),
    ),
    ("utha_liya", re.compile(r"\butha\s+liya\b")),
    ("call_connected", re.compile(r"\b(?:call\s+)?connect(?:ed)?\s+ho\s+gaya\b")),
    ("confirm_kar_di", re.compile(r"\bconfirm\s+kar\s+d(?:i|iya|iye)\b")),
)

# First-person "I am busy", not a busy phone line.
_RIDER_BUSY = re.compile(
    r"\bmain\b(?:\W+\w+){0,8}\W+busy\s+(?:hoon|hun|hu)\b|\bbusy\s+(?:hoon|hun|hu)\b"
)
_CUSTOMER_ACTOR = re.compile(r"\bcustomer\b")
_CHANNEL_WORD = re.compile(rf"\b{_CHANNEL}\b")
# "par" is a contrastive connective, except in "phone par" / "call par".
_CLAUSE_BOUNDARY = re.compile(
    r",|;|\.(?:\s+|$)|\b(?:aur|lekin|but|ab|phir)\b|\bpar\b"
)


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _is_rider_self_busy(haystack: str, match: re.Match[str]) -> bool:
    return any(
        _spans_overlap(match.span(), rider.span()) for rider in _RIDER_BUSY.finditer(haystack)
    )


def _mask_channel_par(haystack: str) -> str:
    """Keep 'phone par' as one token so 'par' is not a clause boundary."""
    return re.sub(rf"\b({_CHANNEL}) par\b", lambda m: f"{m.group(1)}_par", haystack)


def _clause_spans(haystack: str) -> tuple[tuple[int, int], ...]:
    """Return inclusive-exclusive character spans for each clause."""
    masked = _mask_channel_par(haystack)
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _CLAUSE_BOUNDARY.finditer(masked):
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(haystack):
        spans.append((start, len(haystack)))
    return tuple(spans) if spans else ((0, len(haystack)),)


def _clause_at(haystack: str, index: int, spans: tuple[tuple[int, int], ...]) -> str:
    for start, end in spans:
        if start <= index < end:
            return haystack[start:end]
    return haystack


def _success_is_bound(name: str, clause: str) -> bool:
    """True when the clause itself binds the success verb to contact."""
    has_channel = _CHANNEL_WORD.search(clause) is not None
    has_customer = _CUSTOMER_ACTOR.search(clause) is not None
    if name == "confirm_kar_di":
        # Address/packing/entry confirms need both actor and channel.
        return has_channel and has_customer
    if name == "call_connected":
        return has_channel
    return has_channel or has_customer


def _contact_spans(haystack: str) -> tuple[list[int], list[int]]:
    """Return end indexes of bound failure and bound success contact matches."""
    failures: list[int] = []
    for name, pattern in _FAILED_CONTACT:
        for match in pattern.finditer(haystack):
            if name in {"channel_busy", "busy_channel"} and _is_rider_self_busy(
                haystack, match
            ):
                continue
            failures.append(match.end())
    clauses = _clause_spans(haystack)
    successes: list[int] = []
    for name, pattern in _SUCCESS_CONTACT:
        for match in pattern.finditer(haystack):
            clause = _clause_at(haystack, match.start(), clauses)
            if _success_is_bound(name, clause):
                successes.append(match.end())
    return failures, successes


def _is_failed_contact(haystack: str) -> bool:
    """True when the latest bound contact state is a failure."""
    failures, successes = _contact_spans(haystack)
    if not failures:
        return False
    if not successes:
        return True
    return max(failures) > max(successes)


# Needles are general Hinglish / transliterated English paraphrases a rider
# would actually say, not memorised evaluation lines.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        Intent.accident_sos,
        Urgency.high,
        any_of=(
            "accident",
            "hadsa",
            "gir gaya",
            "gir gayi",
            "sos",
            "takkar",
            "palat gayi",
            "palat gaya",
            "palat gaye",
            "chot lag",
            "chot lagi",
            "chot hai",
            "injured",
            "phisal gayi",
            "phisal gaya",
        ),
    ),
    _Rule(
        Intent.item_missing,
        Urgency.medium,
        any_of=(
            "item missing",
            "missing item",
            "ek item",
            "item nahi",
            "saman nahi",
            "saman hi nahi",
            "saman kam",
            "sku missing",
            "quantity short",
            "cheez kam",
            "item kam",
        ),
    ),
    _Rule(
        Intent.customer_unreachable,
        Urgency.high,
        detect=_is_failed_contact,
    ),
    _Rule(
        Intent.address_issue,
        Urgency.medium,
        any_of=(
            "gate band",
            "gate lock",
            "galat address",
            "address galat",
            "location galat",
            "rasta band",
            "rasta stuck",
            "entry closed",
            "entry close",
            "andar nahi ja",
            "nahi jaane de",
            "nahi jaa paa",
            "address clear nahi",
            "address nahi mil",
        ),
        all_groups=(
            ("galat", "wrong"),
            ("building", "society", "wing", "map", "pin", "gali"),
        ),
    ),
    _Rule(
        Intent.address_issue,
        Urgency.medium,
        all_groups=(
            ("rasta",),
            ("stuck",),
        ),
    ),
    _Rule(
        Intent.delay,
        Urgency.low,
        any_of=(
            "late",
            "delay",
            "traffic",
            "der ho",
            "der lag",
            "atak gaya",
            "atak gayi",
            "atka",
            "lamba queue",
            "lamba wait",
            "zyada lag",
            "extra lagenge",
            "minute extra",
        ),
        all_groups=(("eta",), ("min", "minute", "minutes", "mint")),
    ),
)


def extract_event(
    transcript: str,
    provider: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> RiderEvent:
    """Return a ``RiderEvent`` for ``transcript``.

    ``provider`` overrides ``LLM_PROVIDER``. Extra keyword arguments are
    allowed; the return type stays ``RiderEvent``. Failures on the LLM
    path fall back to the rules rather than raising to the rider.
    """
    return extract_event_with_source(transcript, provider, client=client).event


def extract_event_with_source(
    transcript: str,
    provider: str | None = None,
    *,
    client: httpx.Client | None = None,
) -> ExtractResult:
    """Return the event plus the envelope fields ``extractor_source`` and fallback reason.

    Those fields must stay off the frozen ``RiderEvent``.
    """
    name = _provider_name(provider)
    if name == "rules":
        return ExtractResult(_by_rules(transcript), "rules", None)
    try:
        event = _by_llm(transcript, name, client=client)
    except LlmError as exc:
        # Never log the transcript, the prompt, the raw model text, or the key.
        log.warning("llm extractor fell back to rules (%s)", exc.reason)
        return ExtractResult(_by_rules(transcript), "rules", exc.reason)
    return ExtractResult(event, "llm", None)


def _provider_name(provider: str | None) -> str:
    if provider is not None:
        return provider.strip().lower() or "rules"
    return get_settings().llm_provider or "rules"


def _by_llm(
    transcript: str,
    provider: str,
    *,
    client: httpx.Client | None,
) -> RiderEvent:
    ensure_closed(provider)
    extractor = get_llm_extractor(provider)
    return extractor.extract(transcript, client=client)


def _by_rules(transcript: str) -> RiderEvent:
    haystack = transcript.lower()
    intent = Intent.other
    urgency = Urgency.low
    confidence = 0.0
    for rule in _RULES:
        if rule.matches(haystack):
            intent = rule.intent
            urgency = rule.urgency
            confidence = 0.5
            break
    return RiderEvent(
        intent=intent,
        order_id=_order_id(transcript),
        eta_minutes=_eta(transcript),
        urgency=urgency,
        dispatch_action=_ACTION[intent],
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
