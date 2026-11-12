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


def test_answered_call_is_not_unreachable():
    event = extract_event(
        "customer ne phone receive kar liya, address clear hai",
        provider="rules",
    )
    assert event.intent.value == "other"
    assert event.urgency.value == "low"
    assert event.confidence == 0.0

    event = extract_event(
        "customer ne call receive ki aur location confirm kar di",
        provider="rules",
    )
    assert event.intent.value == "other"
    assert event.urgency.value == "low"
    assert event.confidence == 0.0


def test_failed_receive_and_busy_line_still_match():
    event = extract_event("call receive hi nahi kar raha, order 18", provider="rules")
    assert event.intent.value == "customer_unreachable"
    assert event.urgency.value == "high"
    assert event.order_id == "18"

    event = extract_event("customer ka phone receive nahi ho raha, order 4", provider="rules")
    assert event.intent.value == "customer_unreachable"
    assert event.order_id == "4"

    event = extract_event("customer ka mobile busy hai, order 102", provider="rules")
    assert event.intent.value == "customer_unreachable"
    assert event.order_id == "102"

