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
_NUMBER_WORD = "(?:" + "|".join(sorted([*_ONES, *_TENS], key=len, reverse=True)) + ")"
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


# Only these original Hindi needles intentionally end in a verb stem.
# Other needles need whole words: "late" must not match "plate" and "sos"
# must not match an unrelated word. Negation is local to one matched status,
# never borrowed from a later phone failure or another clause.
_STEM_NEEDLES = frozenset(
    {
        "chot lag",
        "der ho",
        "der lag",
        "zyada lag",
        "andar nahi ja",
        "nahi jaa paa",
        "address nahi mil",
        "chot aay",
        "takra",
    }
)
_NEGATIVE_PREFIX = re.compile(r"\b(?:no|not|without)\s+(?:any\s+)?$")
_NEGATIVE_SUFFIX = re.compile(
    r"^\s+(?:(?:hai|hain|hua|hui|ho|is|was)\s+)?(?:nahi|nahin|not)\b"
    r"(?=\s*(?:$|[,.!?;]|(?:hai|hain|hua|hui|tha|thi|hoga|hogi|hoon|hun|hu|"
    r"hoonga|hongi|ho|hota|hoti|hue)\b))"
)


def _affirmed_keyword(text: str, needle: str) -> bool:
    suffix = r"\w*" if needle in _STEM_NEEDLES else ""
    pattern = re.compile(r"(?<!\w)" + re.escape(needle) + suffix + r"(?!\w)")
    for match in pattern.finditer(text):
        if _NEGATIVE_PREFIX.search(text[: match.start()]) is not None:
            continue
        if _NEGATIVE_SUFFIX.match(text[match.end() :]) is not None:
            continue
        return True
    return False


@dataclass(frozen=True, slots=True)
class _Rule:
    """A keyword rule. ``any_of`` is an affirmed whole-word OR; ``all_groups`` is AND-of-ORs.

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
        if self.any_of and any(_affirmed_keyword(haystack, needle) for needle in self.any_of):
            return True
        if self.all_groups and all(
            any(_affirmed_keyword(haystack, needle) for needle in group)
            for group in self.all_groups
        ):
            return True
        return False


# Contact state for the rules fallback is fail-safe: a missed
# customer_unreachable escalation is worse than a false one that a
# dispatcher can glance at and dismiss. The LLM path handles nuance.
#
# A channel-bound (or inherently contact) failure span makes the event
# customer_unreachable unless a later, non-overlapping SUCCESS CONSTRUCT
# starts after that failure ends. A success construct is one contiguous
# pattern: either the customer actor is grammatically linked to a
# contact-success verb by only a small, fixed filler set (case markers
# se/ne/ka/ki/ko/ke, an optional channel word, and optional pe/par), or
# the phrase is explicitly about the call connecting (call connect ho
# gaya, call lag gaya). Bare "confirm kar di", bare "baat ho gayi", and
# talk with a restaurant, guard, rider, shop, or "maine" are not
# customer contact. There is no clause splitting and no bag-of-words
# check. Punctuation is normalised to spaces before matching, so a
# comma must not change the result.
_CHANNEL = r"(?:phone|mobile|call|line|number|intercom|whatsapp|sms)"
# Auxiliaries that may sit between a channel word and a failure verb.
# This is a closed set, not an arbitrary token window, so a later phrase
# cannot donate its channel word to an earlier failure.
_AUX = r"(?:hai|hain|ho|aa|raha|rahi|rahe|kar|tha|thi|the)"
# Frequency or manner words that may sit between a channel and a status.
# English adverbs are the -ly class; the list is otherwise closed.
_FREQ = r"(?:baar(?:\s+baar)?|phir|again|still|always|[a-z]+ly)"
_CASE_MARK = r"(?:se|ne|ka|ki|ko|ke|pe|par)"
_FILLED = rf"(?:\s+(?:{_AUX}|{_FREQ}|{_CASE_MARK})){{0,3}}"
_UTHA_FAIL = r"(?:nahi\s+utha\w*|utha(?:ya|ta|te)?\s+nahi)"

_FAILED_CONTACT: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("channel_busy", re.compile(rf"\b{_CHANNEL}{_FILLED}\s+busy\b")),
    ("busy_channel", re.compile(rf"\bbusy{_FILLED}\s+{_CHANNEL}\b")),
    ("channel_engaged", re.compile(rf"\b{_CHANNEL}{_FILLED}\s+engaged\b")),
    ("engaged_channel", re.compile(rf"\bengaged{_FILLED}\s+{_CHANNEL}\b")),
    (
        "call_cut",
        re.compile(
            rf"\b(?:call|phone|mobile){_FILLED}\s+"
            rf"(?:cut|disconnect(?:ed)?|dropped)\b"
        ),
    ),
    (
        "bell_no_response",
        re.compile(
            r"\b(?:doorbell|door\s*bell|bell|intercom)"
            r"(?:\s+\w+){0,8}\s+(?:response|jawab)\s+nahi"
            r"|\b(?:response|jawab)\s+nahi(?:\s+\w+){0,8}\s+"
            r"(?:doorbell|door\s*bell|bell|intercom)\b"
        ),
    ),
    (
        "message_no_reply",
        re.compile(
            rf"\b(?:whatsapp|sms|message|msg){_FILLED}\s+"
            rf"(?:reply|jawab|respond)\s+nahi"
        ),
    ),
    ("switched_off", re.compile(r"\bswi(?:tch|ch)(?:ed)?\s+off\b")),
    ("channel_off", re.compile(rf"\b{_CHANNEL}{_FILLED}\s+off\b")),
    (
        "channel_band",
        re.compile(rf"\b(?:phone|mobile|number){_FILLED}\s+band\b"),
    ),
    ("line_not_found", re.compile(rf"\bline{_FILLED}\s+nahi\s+mil")),
    ("not_connecting", re.compile(rf"\b{_CHANNEL}{_FILLED}\s+nahi\s+lag")),
    (
        "channel_not_picking_up",
        re.compile(
            rf"\b{_CHANNEL}{_FILLED}\s+{_UTHA_FAIL}"
            rf"|\bpickup\s+nahi{_FILLED}\s+{_CHANNEL}\b"
            rf"|\b{_CHANNEL}{_FILLED}\s+pickup\s+nahi"
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
        re.compile(r"\bring\s+ja\s+rahi(?:\s+hai)?\s+utha\s+nahi"),
    ),
)

# Fixed fillers that may appear between the customer and the verb.
_CASE = r"(?:se|ne|ka|ki|ko|ke)"
_ON = r"(?:pe|par(?:\s+se)?)"
_CUSTOMER_LINK = rf"customer(?:\s+{_CASE})?(?:\s+{_CHANNEL})?(?:\s+{_ON})?"
_BAAT_OK = r"(?:baat\s+ho\s+(?:gayi|gai|gaya|chuki|chuka)|baat\s+hui)"
_RECEIVE_OK = r"receive\s+(?:kar\s+liya|kar\s+li|kiya|ki)(?!\s+nahi)"
_UTHA_OK = rf"(?:{_CHANNEL}\s+)?utha\s+liya"
_PICK_OK = r"pick(?:\s+up|\s+kar)?\s+liya"
_CONNECT_OK = r"connect(?:ed)?\s+ho\s+gaya"
_CONFIRM_OK = r"confirm\s+kar\s+d(?:i|iya|iye)"

_CUSTOMER_SUCCESS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("customer_baat", re.compile(rf"\b{_CUSTOMER_LINK}\s+{_BAAT_OK}\b")),
    (
        "customer_receive",
        re.compile(rf"\b{_CUSTOMER_LINK}\s+(?:{_CHANNEL}\s+)?{_RECEIVE_OK}\b"),
    ),
    ("customer_utha_liya", re.compile(rf"\b{_CUSTOMER_LINK}\s+{_UTHA_OK}\b")),
    ("customer_pick", re.compile(rf"\b{_CUSTOMER_LINK}\s+{_PICK_OK}\b")),
    ("customer_connect", re.compile(rf"\b{_CUSTOMER_LINK}\s+{_CONNECT_OK}\b")),
    (
        "customer_confirm",
        re.compile(
            rf"\bcustomer\s+ne(?:\s+{_CHANNEL}\s+{_ON})?"
            rf"(?:\s+(?:location|address))?\s+{_CONFIRM_OK}\b"
        ),
    ),
)
_CHANNEL_SUCCESS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "call_connected",
        re.compile(rf"\b(?:call|phone|mobile)\s+(?:{_CONNECT_OK}|lag\s+gaya)\b"),
    ),
)

# First-person "I am busy", not a busy phone line.
_RIDER_BUSY = re.compile(
    r"\bmain\b(?:\W+\w+){0,8}\W+busy\s+(?:hoon|hun|hu)\b|\bbusy\s+(?:hoon|hun|hu)\b"
)
_NON_CUSTOMER_LEAD = re.compile(
    r"(?:restaurant|guard|maine|rider|shop|store|merchant|security|\bmain\b)"
    rf"(?:\s+{_CASE})?(?:\s+{_CHANNEL})?(?:\s+{_ON})?\s+$"
)


def _normalize_contact_text(text: str) -> str:
    """Strip punctuation so commas cannot change contact matching."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]+", " ", text)).strip()


def _spans_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _is_rider_self_busy(haystack: str, match: re.Match[str]) -> bool:
    return any(
        _spans_overlap(match.span(), rider.span()) for rider in _RIDER_BUSY.finditer(haystack)
    )


def _failure_spans(text: str) -> list[tuple[int, int]]:
    """Return character spans of channel-bound or contact-failure phrases."""
    spans: list[tuple[int, int]] = []
    for name, pattern in _FAILED_CONTACT:
        for match in pattern.finditer(text):
            if _NEGATIVE_PREFIX.search(text[:match.start()]) is not None:
                continue
            if _NEGATIVE_SUFFIX.match(text[match.end():]) is not None:
                continue
            if name in {"channel_busy", "busy_channel"} and _is_rider_self_busy(text, match):
                continue
            spans.append(match.span())
    return spans


def _success_spans(text: str) -> list[tuple[int, int]]:
    """Return spans of contiguous customer- or call-connect success constructs."""
    spans: list[tuple[int, int]] = []
    for _, pattern in _CUSTOMER_SUCCESS:
        for match in pattern.finditer(text):
            spans.append(match.span())
    for _, pattern in _CHANNEL_SUCCESS:
        for match in pattern.finditer(text):
            if _NON_CUSTOMER_LEAD.search(text[: match.start()]) is not None:
                continue
            spans.append(match.span())
    return spans


def _is_failed_contact(haystack: str) -> bool:
    """True unless a later, non-overlapping success construct overrides a failure.

    Once a failure span exists, the rules fallback stays on
    customer_unreachable unless an explicit success construct starts after
    that failure ends and does not overlap it.
    """
    text = _normalize_contact_text(haystack)
    failures = _failure_spans(text)
    if not failures:
        return False
    latest_failure_end = max(end for _start, end in failures)
    for start, end in _success_spans(text):
        if start < latest_failure_end:
            continue
        if any(_spans_overlap((start, end), failure) for failure in failures):
            continue
        return False
    return True



_TRAINING_CONTEXT = re.compile(
    r"\b(?:video|training|tutorial|chapter|course|clip|movie|lecture|module)\b"
)
_SOS_MENTION = (
    "accident",
    "hadsa",
    "sos",
)
_SOS_HARM = (
    "gir gaya",
    "gir gayi",
    "takkar",
    "takra",
    "takrai",
    "takraya",
    "takrayi",
    "palat gayi",
    "palat gaya",
    "palat gaye",
    "chot lag",
    "chot lagi",
    "chot hai",
    "chot aayi",
    "chot aaya",
    "injured",
    "phisal gayi",
    "phisal gaya",
    "slide",
    "skid",
    "bleeding",
    "khoon",
    "ambulance",
    "dard",
)
_HOSPITAL = re.compile(r"\bhospital\b")
_HOSPITAL_CUE = re.compile(
    r"\b(?:dard|chot|khoon|bleeding|madad|help|le jaana|le jana|ambulance)\b"
)
_ITEM_CONTEXT = re.compile(
    r"\b(?:bill|invoice|package|packing|bag|items?|pieces?|cheezein|cheez|saman|sku)\b"
)
_COUNT_TOKEN = re.compile(
    r"\b(?:\d{1,6}|" + "|".join(sorted([*_ONES, *_TENS], key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)
_RAIN = ("barish", "barsaat", "rain")
_SLOW = ("dheere", "slow", "atak")


def _normalize_rules_text(text: str) -> str:
    """Fold common romanisation variants before keyword matching."""
    lowered = text.lower()
    return re.sub(r"\bnahin\b", "nahi", lowered)


def _is_accident(haystack: str) -> bool:
    """True for rider harm or an unqualified accident mention.

    A mention of accident, hadsa, or sos inside a video/training context is
    not enough; a harm keyword still wins.
    """
    if any(_affirmed_keyword(haystack, needle) for needle in _SOS_HARM):
        return True
    if _HOSPITAL.search(haystack) and _HOSPITAL_CUE.search(haystack):
        return True
    if not any(_affirmed_keyword(haystack, needle) for needle in _SOS_MENTION):
        return False
    return _TRAINING_CONTEXT.search(haystack) is None


def _is_item_count_short(haystack: str) -> bool:
    """True when a bill or pack line states two different item counts."""
    if _ITEM_CONTEXT.search(haystack) is None:
        return False
    if re.search(
        r"\b(?:bill|invoice|sirf|only|honi thi|hone the|nikle|nikla)\b"
        r"|\bhi\s+(?:hain|hai|mil|nikle)\b",
        haystack,
    ) is None:
        return False
    values: set[int] = set()
    for token in _COUNT_TOKEN.findall(haystack):
        parsed = _to_int(token)
        if parsed is not None:
            values.add(parsed)
    return len(values) >= 2


def _is_item_missing(haystack: str) -> bool:
    keywords = (
        "item missing",
        "missing item",
        "item nahi",
        "saman nahi",
        "saman hi nahi",
        "saman kam",
        "sku missing",
        "quantity short",
        "cheez kam",
        "item kam",
        "chhoot gaya",
        "chhoot gayi",
        "chhut gaya",
        "chhut gayi",
        "replace nahi mila",
        "bag mein nahi mila",
        "packing mein nahi mila",
        "khali pack",
        "khali packet",
        "khali bag",
        "khali box",
        "empty pack",
        "empty packet",
        "empty bag",
    )
    if any(_affirmed_keyword(haystack, needle) for needle in keywords):
        return True
    return _is_item_count_short(haystack)


def _is_rain_delay(haystack: str) -> bool:
    return any(_affirmed_keyword(haystack, rain) for rain in _RAIN) and any(
        _affirmed_keyword(haystack, slow) for slow in _SLOW
    )


# Needles are general Hinglish / transliterated English paraphrases a rider
# would actually say, not memorised evaluation lines.
_RULES: tuple[_Rule, ...] = (
    _Rule(
        Intent.accident_sos,
        Urgency.high,
        detect=_is_accident,
    ),
    _Rule(
        Intent.item_missing,
        Urgency.medium,
        detect=_is_item_missing,
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
            "rasta close",
            "rasta closed",
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
            (
                "galat",
                "wrong",
                "alag",
                "dusra",
                "dusre",
                "match nahi",
                "le aaya",
                "le gaya",
                "le gayi",
            ),
            (
                "building",
                "society",
                "wing",
                "map",
                "pin",
                "gali",
                "tower",
                "sector",
                "block",
                "plot",
                "house",
                "flat",
                "landmark",
            ),
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
            "bumper to bumper",
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
        all_groups=(
            ("eta",),
            ("min", "minute", "minutes", "mint"),
        ),
    ),
    _Rule(
        Intent.delay,
        Urgency.low,
        detect=_is_rain_delay,
    ),
    _Rule(
        Intent.delay,
        Urgency.low,
        all_groups=(
            ("lamba",),
            ("wait", "queue", "minute lag", "min lag"),
        ),
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


# Reasons that may try the other free provider before rules. A missing
# key, 401/403, invalid JSON, or an open breaker stays on this hop.
_RETRYABLE_PROVIDER_REASONS = frozenset(
    {"timeout", "connection_error", "http_429", *{f"http_{code}" for code in range(500, 600)}}
)


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
    last_error: LlmError | None = None
    for hop in _provider_hops(name):
        try:
            event = _by_llm(transcript, hop, client=client)
        except LlmError as exc:
            # Never log the transcript, the prompt, the raw model text, or the key.
            last_error = exc
            if hop == name and exc.reason == "missing_api_key":
                break
            if exc.reason in _RETRYABLE_PROVIDER_REASONS:
                continue
            break
        else:
            return ExtractResult(event, "llm", None)
    reason = last_error.reason if last_error is not None else "unknown_provider"
    log.warning("llm extractor fell back to rules (%s)", reason)
    return ExtractResult(_by_rules(transcript), "rules", reason)


def _provider_hops(name: str) -> tuple[str, ...]:
    """Selected provider first, then the other free provider if its key is set."""
    if name not in {"groq", "gemini"}:
        return (name,)
    other = "gemini" if name == "groq" else "groq"
    settings = get_settings()
    if settings.key_for(other):
        return (name, other)
    return (name,)


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
    haystack = _normalize_rules_text(transcript)
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
