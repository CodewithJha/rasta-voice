"""Short Hinglish confirmations from structured events, never rider-supplied text."""

from rasta.schema import Intent, RiderEvent

UNCERTAIN_REPLY = (
    "Baat saaf nahi hui, surakshit jagah rukiye aur dispatch se pushti kijiye."
)
ACCIDENT_REPLY = (
    "Kya aap theek hain, surakshit jagah rukiye aur turant dispatch se madad maangiye."
)
_HINDI = (
    "shoonya ek do teen chaar paanch chhah saat aath nau das gyarah barah terah "
    "chaudah pandrah solah satrah atharah unnees bees ikkees baees teis chaubees "
    "pachchees chhabbees sattais atthais untees tees"
).split()
_ENGLISH_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_ENGLISH_TENS = "zero ten twenty thirty forty fifty sixty seventy eighty ninety".split()


def _minutes(value: int | None) -> str | None:
    # An implausible/unbounded ETA is not safe to repeat as a dispatch promise.
    if value is None or not 0 <= value <= 180:
        return None
    if value < len(_HINDI):
        return _HINDI[value]
    if value >= 100:
        tail = value % 100
        return "one hundred" + (f" {_english_under_100(tail)}" if tail else "")
    return _english_under_100(value)


def _english_under_100(value: int) -> str:
    if value < 20:
        return _ENGLISH_ONES[value]
    return _ENGLISH_TENS[value // 10] + (
        f" {_ENGLISH_ONES[value % 10]}" if value % 10 else ""
    )


def reply_text(event: RiderEvent) -> str:
    """Use cautious wording until a human acknowledgement exists in the envelope.

    No transcript, order token or dispatch_action is spoken. Even an accident
    classified with low confidence gets the audible safety/human-review line.
    """
    if event.intent == Intent.accident_sos:
        return ACCIDENT_REPLY
    # Matched rules use 0.5; lower-confidence classifications request review.
    if event.intent == Intent.other or event.confidence < 0.5:
        return UNCERTAIN_REPLY
    if event.intent == Intent.customer_unreachable:
        return "Gate ke paas rukiye; <pauses> dispatch se customer ko ek baar call karne ko kahiye."
    if event.intent == Intent.address_issue:
        return "Paas ke landmark par surakshit jagah rukiye aur dispatch se baat kijiye."
    if event.intent == Intent.item_missing:
        return "Drop abhi rokiye aur bag check ke liye hub se baat kijiye."
    minutes = _minutes(event.eta_minutes)
    if minutes is not None:
        return f"Aapka {minutes} minute ka delay note hua hai."
    return "Traffic ka delay note hua hai, ETA ki pushti dispatch se kijiye."
