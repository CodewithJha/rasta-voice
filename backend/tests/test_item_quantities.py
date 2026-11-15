"""Invented item-count regressions, separate from frozen intent datasets."""

import pytest

from rasta.extract import extract_event


@pytest.mark.parametrize("text", [
    "bill mein only twenty five items hain, order 9 complete hai",
    "invoice pe only three items hain, order 9, four minutes late",
    "bill mein only three items hain, order 9, sab mil gaya",
    "invoice pe only three items hain, order 9 complete hai",
    "bag mein char items hain aur teen extra chutney sachets bhi hain, sab complete hai",
    "bill pe five items hain, bag mein only five items mile, order 7",
    "bill pe three items hain, bag mein only four items mile, order 7",
    "bill pe twenty five items hain, twenty minutes late, order nine",
    "only twenty five items, order one eight, das minute late",
    "bill pe three items hain, phone number nine eight seven six five four three two one zero",
    "bill pe twenty eighteen items hain, bag mein only four mile",
    "bill pe 3.5 items hain, bag mein only two mile",
    "bill pe three items hain, bag mein only 1.5 mile",
    "bill pe five items hain, only three hours late, order 9",
    "invoice lists five pieces, only three customers are waiting, order 9",
    "bill pe three items hain, only two extra chutney sachets bhi mile",
    "bill pe five items hain, teen mile door hai, order 9",
    "bill pe five items hain, only three mile away, order 9",
    "bill pe only five items hain, invoice mein only three items hain, order 9",
    "invoice mein sirf five items hain, bill pe sirf three items hain, order 9",
])
def test_unrelated_or_non_shortage_quantities_are_not_missing(text):
    assert extract_event(text, "rules").intent.value != "item_missing"


@pytest.mark.parametrize("text", [
    "bill pe char items likhe hain, bag mein sirf teen nikle, order 9",
    "bill pe twenty five items hain, bag mein only twenty three items mile, order 9",
    "invoice lists thirty two pieces, only thirty pieces mila, order 9",
    "four items hone the, only three items mile, order eighteen",
    "three items honi thi, bag mein only two items mile, four minutes late",
    "bill pe three items hain, bag mein only zero items nikle, order 9",
    "bag mein only three items mile, bill pe five items hain, order 9",
    "bill pe four items hain, bag mein only three",
    "bill pe only five items hain, bag mein only three items mile, order 9",
])
def test_explicit_expected_and_received_shortage(text):
    event = extract_event(text, "rules")
    assert event.intent.value == "item_missing"
    assert event.urgency.value == "medium"


def test_eta_retains_its_intent_without_a_shortage():
    event = extract_event("invoice pe only three items hain, order 9, four minutes late", "rules")
    assert event.intent.value == "delay"
    assert event.order_id == "9"
    assert event.eta_minutes == 4


def test_quantity_shortage_does_not_override_sos():
    event = extract_event("bill pe five items hain, only three mile, accident hua", "rules")
    assert event.intent.value == "accident_sos"
    assert event.urgency.value == "high"
