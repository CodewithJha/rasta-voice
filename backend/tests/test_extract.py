from rasta.extract import extract_event


def test_unreachable_beats_the_closed_gate():
    event = extract_event(
        "bhaiya gate band hai, customer phone nahi utha raha, order 18",
        provider="mock",
    )
    assert event.intent.value == "customer_unreachable"
    assert event.order_id == "18"
    assert event.urgency.value == "high"
    assert event.confidence == 0.5


def test_missing_item_and_order():
    event = extract_event("order 4 mein ek item missing", provider="mock")
    assert event.intent.value == "item_missing"
    assert event.order_id == "4"
    assert event.urgency.value == "medium"


def test_delay_picks_up_eta_not_the_order_number():
    event = extract_event("bhaiya 20 min late hoon, traffic mein, order 7", provider="mock")
    assert event.intent.value == "delay"
    assert event.eta_minutes == 20
    assert event.order_id == "7"
    assert event.urgency.value == "low"


def test_accident_is_high():
    event = extract_event("bhaiya accident ho gaya, main gir gaya", provider="mock")
    assert event.intent.value == "accident_sos"
    assert event.urgency.value == "high"
    assert event.order_id is None


def test_phone_shaped_digits_are_not_an_order_id():
    event = extract_event("customer 9876543210 nahi utha, order 4", provider="mock")
    dumped = event.model_dump(mode="json")
    assert dumped["order_id"] == "4"
    assert "9876543210" not in dumped["dispatch_action"]
    assert dumped["order_id"] != "9876543210"


def test_unknown_line():
    event = extract_event("bas theek hoon, paani pi ke nikalta hoon", provider="mock")
    assert event.intent.value == "other"
    assert event.confidence == 0.0


def test_live_provider_is_not_wired():
    try:
        extract_event("order 1", provider="groq")
    except NotImplementedError as exc:
        assert "issue 02" in str(exc)
    else:
        raise AssertionError("expected NotImplementedError")
