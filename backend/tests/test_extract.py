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
# wins when a success signal and a failure phrase both appear. A rider
# saying they are busy is never a failed call.
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
            "pehle phone nahi uthaya, ab baat ho gayi",
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

