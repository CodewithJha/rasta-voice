import pytest

from rasta.extract import extract_event


def test_unreachable_beats_the_closed_gate():
    event = extract_event(
        "bhaiya gate band hai, customer phone nahi utha raha, order 18",
        provider="rules",
    )
    assert event.intent.value == "customer_unreachable"
    assert event.order_id == "18"
    assert event.urgency.value == "high"
    assert event.confidence == 0.5


def test_missing_item_and_order():
    event = extract_event("order 4 mein ek item missing", provider="rules")
    assert event.intent.value == "item_missing"
    assert event.order_id == "4"
    assert event.urgency.value == "medium"


def test_delay_picks_up_eta_not_the_order_number():
    event = extract_event("bhaiya 20 min late hoon, traffic mein, order 7", provider="rules")
    assert event.intent.value == "delay"
    assert event.eta_minutes == 20
    assert event.order_id == "7"
    assert event.urgency.value == "low"


def test_accident_is_high():
    event = extract_event("bhaiya accident ho gaya, main gir gaya", provider="rules")
    assert event.intent.value == "accident_sos"
    assert event.urgency.value == "high"
    assert event.order_id is None


def test_phone_shaped_digits_are_not_an_order_id():
    event = extract_event("customer 9876543210 nahi utha, order 4", provider="rules")
    dumped = event.model_dump(mode="json")
    assert dumped["order_id"] == "4"
    assert "9876543210" not in dumped["dispatch_action"]
    assert dumped["order_id"] != "9876543210"


def test_unknown_line():
    event = extract_event("bas theek hoon, paani pi ke nikalta hoon", provider="rules")
    assert event.intent.value == "other"
    assert event.confidence == 0.0


def test_transliterated_prisma_line():
    event = extract_event(
        "Bhaiya, gate band hai aur customer phone nahi utha raha. "
        "Order eighteen pe main das minute se khada hoon.",
        provider="rules",
    )
    assert event.intent.value == "customer_unreachable"
    assert event.order_id == "18"
    assert event.eta_minutes == 10


def test_number_words_compose():
    event = extract_event("order twenty five, pachchis minute late", provider="rules")
    assert event.order_id == "25"
    assert event.eta_minutes == 25


def test_rules_is_the_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert extract_event("order 4 mein ek item missing").intent.value == "item_missing"


def test_missing_llm_key_falls_back_to_rules(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from rasta.settings import clear_settings_cache

    clear_settings_cache()
    event = extract_event("order 4 mein ek item missing", provider="groq")
    assert event.intent.value == "item_missing"
    assert event.confidence == 0.5


# Contact-state classes for the customer_unreachable rule. Latest state
# is only between a bound failure and a bound success. A success verb
# counts only in the same clause as the customer and/or the phone
# channel. A rider saying they are busy is never a failed call. A bare
# address, packing, or entry confirmation is not customer contact.
@pytest.mark.parametrize(
    ("text", "intent", "urgency"),
    [
        (
            "customer ka call receive kar liya, ab main packing mein busy hoon",
            "other",
            "low",
        ),
        (
            "customer se phone par baat ho gayi, main parcel sort karne mein busy hoon",
            "other",
            "low",
        ),
        (
            "customer ne phone receive kar liya, address clear hai",
            "other",
            "low",
        ),
        (
            "customer ne call receive ki aur location confirm kar di",
            "other",
            "low",
        ),
        (
            "customer se call connect ho gaya, order 4",
            "other",
            "low",
        ),
        (
            "pehle phone nahi uthaya, ab customer se baat ho gayi",
            "other",
            "low",
        ),
        (
            "customer ka mobile busy hai, order 102",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka phone busy aa raha hai, order 18",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ki line busy hai, order 4",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka mobile switch off hai, order chaar pe do baar try ho chuka",
            "customer_unreachable",
            "high",
        ),
        (
            "phone switched off hai, order 18",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka phone off hai, order 4",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka mobile band hai, order 18",
            "customer_unreachable",
            "high",
        ),
        (
            "order eighteen ke customer ko call kiya, not picking up",
            "customer_unreachable",
            "high",
        ),
        (
            "phone nahi utha raha, order 18",
            "customer_unreachable",
            "high",
        ),
        (
            "andar gate lock hai aur koi pickup nahi kar raha phone, order 18",
            "customer_unreachable",
            "high",
        ),
        (
            "call receive hi nahi kar raha, order 18",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka phone receive nahi ho raha, order 4",
            "customer_unreachable",
            "high",
        ),
        (
            "dispatch, is bande ko line nahi mil rahi mujhe, order eighteen",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ki ring ja rahi hai, utha nahi raha, order 18",
            "customer_unreachable",
            "high",
        ),
        (
            "pehle baat ho gayi thi, ab phone nahi utha raha",
            "customer_unreachable",
            "high",
        ),
        (
            "customer phone nahi utha raha, address confirm kar diya hai",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka phone switch off hai, restaurant ne packing confirm kar di",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka number band hai, guard ne entry confirm kar di",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ne phone nahi uthaya, maine address confirm kar liya",
            "customer_unreachable",
            "high",
        ),
        (
            "customer phone nahi utha raha tha, ab customer se baat ho gayi, "
            "address confirm hai",
            "other",
            "low",
        ),
        (
            "pehle switch off tha, phir customer ne call utha liya",
            "other",
            "low",
        ),
        (
            "customer ne phone pe location confirm kar di",
            "other",
            "low",
        ),
    ],
    ids=[
        "answered_call_rider_busy_packing",
        "answered_call_rider_busy_sorting",
        "answered_call_receive_kar_liya",
        "answered_call_receive_ki_confirm",
        "answered_call_connect_ho_gaya",
        "latest_state_now_connected",
        "phone_busy",
        "phone_busy_aa_raha",
        "line_busy",
        "switched_off_mobile",
        "switched_off_phone",
        "phone_off",
        "mobile_band",
        "not_picking_up",
        "phone_nahi_utha",
        "pickup_nahi_phone",
        "receive_hi_nahi",
        "phone_receive_nahi",
        "line_nahi_mil",
        "ring_unanswered",
        "latest_state_now_unreachable",
        "confirm_address_after_no_answer",
        "confirm_packing_after_switch_off",
        "confirm_entry_after_number_band",
        "confirm_address_by_rider_after_no_answer",
        "latest_state_baat_then_address_confirm",
        "latest_state_then_customer_utha_liya",
        "customer_phone_location_confirm",
    ],
)
def test_contact_state_classes(text, intent, urgency):
    event = extract_event(text, provider="rules")
    assert event.intent.value == intent
    assert event.urgency.value == urgency
    if intent == "customer_unreachable":
        assert event.confidence == 0.5
    else:
        assert event.confidence == 0.0


# Every reproduction from the four reviews of this pull request.
@pytest.mark.parametrize(
    ("text", "intent", "urgency"),
    [
        (
            "customer ne phone receive kar liya, address clear hai",
            "other",
            "low",
        ),
        (
            "customer ne call receive ki aur location confirm kar di",
            "other",
            "low",
        ),
        (
            "customer ka call receive kar liya, ab main packing mein busy hoon",
            "other",
            "low",
        ),
        (
            "customer se phone par baat ho gayi, main parcel sort karne mein busy hoon",
            "other",
            "low",
        ),
        (
            "customer phone nahi utha raha, address confirm kar diya hai",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka phone switch off hai, restaurant ne packing confirm kar di",
            "customer_unreachable",
            "high",
        ),
        (
            "customer phone nahi utha raha address confirm kar diya hai",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka phone switch off hai restaurant ne packing confirm kar di",
            "customer_unreachable",
            "high",
        ),
        (
            "customer phone nahi utha raha maine address confirm kar diya hai",
            "customer_unreachable",
            "high",
        ),
        (
            "customer ka phone switch off hai restaurant se baat ho gayi",
            "customer_unreachable",
            "high",
        ),
    ],
    ids=[
        "review1_receive_kar_liya",
        "review1_receive_ki_confirm",
        "review2_receive_then_rider_busy_packing",
        "review2_baat_ho_gayi_then_rider_busy_sorting",
        "review3_no_answer_then_address_confirm",
        "review3_switch_off_then_packing_confirm",
        "review4_no_comma_address_confirm",
        "review4_no_comma_packing_confirm",
        "review4_no_comma_rider_confirm",
        "review4_no_comma_restaurant_baat",
    ],
)
def test_himanshu_review_repros(text, intent, urgency):
    event = extract_event(text, provider="rules")
    assert event.intent.value == intent
    assert event.urgency.value == urgency


# Generated contact-state matrix. Extend these lists to add coverage;
# do not add one-off repros without also adding the class here.
CONTACT_FAILURE_PHRASES = (
    "phone nahi utha raha",
    "customer phone nahi utha raha",
    "phone switch off hai",
    "customer ka phone switch off hai",
    "number band hai",
    "customer ka number band hai",
    "phone busy aa raha",
    "customer ka phone busy aa raha",
    "call receive nahi kiya",
    "customer ka call receive nahi kiya",
)
NON_CONTACT_FOLLOWUPS = (
    "address confirm kar diya hai",
    "restaurant ne packing confirm kar di",
    "maine address confirm kar diya hai",
    "guard ne entry confirm kar di",
    "restaurant se baat ho gayi",
    "main packing mein busy hoon",
)
CUSTOMER_SUCCESS_FOLLOWUPS = (
    "ab customer se baat ho gayi",
    "phir customer ne call utha liya",
    "customer ne phone pe location confirm kar di",
    "ab call connect ho gaya",
)
CONTACT_JOINERS = ("", ", ", " aur ", " ab ", " phir ", ". ")


def _joined(left: str, joiner: str, right: str) -> str:
    # An empty joiner means no punctuation, not a glued token. Speech
    # transcripts still have a space between the two phrases.
    if not joiner.strip():
        joiner = " "
    return " ".join(f"{left}{joiner}{right}".split())


def _failure_then_non_contact_cases():
    for failure in CONTACT_FAILURE_PHRASES:
        for follow in NON_CONTACT_FOLLOWUPS:
            for joiner in CONTACT_JOINERS:
                yield _joined(failure, joiner, follow), "customer_unreachable", "high"


def _failure_then_success_cases():
    for failure in CONTACT_FAILURE_PHRASES:
        for follow in CUSTOMER_SUCCESS_FOLLOWUPS:
            for joiner in CONTACT_JOINERS:
                yield _joined(failure, joiner, follow), "other", "low"


def _success_then_failure_cases():
    successes = (
        "customer se baat hui thi",
        "customer ne call receive kar liya",
    )
    failures = (
        "phone switch off hai",
        "phone nahi utha raha",
    )
    for success in successes:
        for failure in failures:
            for joiner in CONTACT_JOINERS:
                yield _joined(success, joiner, failure), "customer_unreachable", "high"


def _success_only_cases():
    for follow in CUSTOMER_SUCCESS_FOLLOWUPS:
        yield follow, "other", "low"
    yield "customer se call connect ho gaya", "other", "low"
    yield "customer ne phone receive kar liya", "other", "low"


def _matrix_id(prefix: str, text: str) -> str:
    return prefix + "_" + "_".join(text.split())[:80]


CONTACT_MATRIX_CASES = (
    list(_failure_then_non_contact_cases())
    + list(_failure_then_success_cases())
    + list(_success_then_failure_cases())
    + list(_success_only_cases())
)


@pytest.mark.parametrize(
    ("text", "intent", "urgency"),
    CONTACT_MATRIX_CASES,
    ids=[_matrix_id("matrix", text) for text, _intent, _urgency in CONTACT_MATRIX_CASES],
)
def test_contact_state_matrix(text, intent, urgency):
    event = extract_event(text, provider="rules")
    assert event.intent.value == intent
    assert event.urgency.value == urgency


# Variants tried in self-review of the fail-safe policy, including
# missing punctuation, spelling variants, and a customer token in the
# wrong place. Unrecognised success spellings must not clear a failure.
ADVERSARIAL_CONTACT_CASES = (
    (
        "customer phone nahi utha raha address confirm kar diya hai",
        "customer_unreachable",
        "high",
    ),
    (
        "customer ka phone switch off hai restaurant ne packing confirm kar di",
        "customer_unreachable",
        "high",
    ),
    (
        "customer phone nahi utha raha maine address confirm kar diya hai",
        "customer_unreachable",
        "high",
    ),
    (
        "customer ka phone switch off hai restaurant se baat ho gayi",
        "customer_unreachable",
        "high",
    ),
    (
        "phone nahi uthaa raha address confirm kar diya hai",
        "customer_unreachable",
        "high",
    ),
    (
        "customer ka phone swich off hai address confirm kar diya hai",
        "customer_unreachable",
        "high",
    ),
    (
        "customer phone nahi utha raha ab baat hogyi",
        "customer_unreachable",
        "high",
    ),
    (
        "phone nahi utha raha baat ho gayi customer se",
        "customer_unreachable",
        "high",
    ),
    (
        "baat ho gayi customer se phone nahi utha raha",
        "customer_unreachable",
        "high",
    ),
    (
        "customer se baat ho gayi phone nahi utha raha",
        "customer_unreachable",
        "high",
    ),
    (
        "phone switch off hai security ne entry confirm kar di",
        "customer_unreachable",
        "high",
    ),
    (
        "shop ne packing confirm kar di customer phone nahi utha raha",
        "customer_unreachable",
        "high",
    ),
    (
        "customer phone nahi utha raha rider ne address confirm kar diya",
        "customer_unreachable",
        "high",
    ),
    (
        "customer phone nahi utha raha store se baat ho gayi",
        "customer_unreachable",
        "high",
    ),
    (
        "customer phone nahi utha raha,, address confirm kar diya hai",
        "customer_unreachable",
        "high",
    ),
    (
        "merchant se baat ho gayi phone busy aa raha",
        "customer_unreachable",
        "high",
    ),
    (
        "customer phone nahi utha raha ab customer se baat ho gayi",
        "other",
        "low",
    ),
    (
        "customer ne phone pe location confirm kar di",
        "other",
        "low",
    ),
    (
        "phone nahi utha raha customer address confirm kar diya",
        "customer_unreachable",
        "high",
    ),
    (
        "customer phone pe location confirm kar di phone nahi utha raha",
        "customer_unreachable",
        "high",
    ),
)


@pytest.mark.parametrize(
    ("text", "intent", "urgency"),
    ADVERSARIAL_CONTACT_CASES,
    ids=[_matrix_id("adv", text) for text, _intent, _urgency in ADVERSARIAL_CONTACT_CASES],
)
def test_contact_adversarial_variants(text, intent, urgency):
    event = extract_event(text, provider="rules")
    assert event.intent.value == intent
    assert event.urgency.value == urgency
