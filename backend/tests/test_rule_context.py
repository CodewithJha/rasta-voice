"""Development regressions from rule inspection, never copied from the holdout."""

import pytest

from rasta.extract import extract_event


@pytest.mark.parametrize(
    "text",
    [
        "parcel ek plate mein hai, order 31",
        "chocolate ka packet mil gaya, order 31",
        "please translate this message",
        "accidentally button dab gaya",
        "ek item scan kar liya, sab theek hai",
        "item missing nahi hai, sab bag mein hain",
        "no accident hua, main theek hoon",
        "accident nahi hua, safe hoon",
        "chot lagi nahi hai",
        "gate band nahi hai, entry ho gayi",
        "address galat nahi hai, main sahi jagah hoon",
        "building wrong nahi hai",
        "no delay, time pe aaunga",
        "traffic nahi hai, main time pe hoon",
        "late nahi hoon, on time aaunga",
        "not late, delivery time pe hogi",
        "no item missing, sab complete hai",
        "phone busy nahi hai, customer ne receive kar liya",
        "customer unreachable nahi hai",
        "customer is not unreachable",
        "phone off nahi hai, baat ho gayi",
    ],
)
def test_non_problem_mentions_do_not_trigger_escalation(text):
    assert extract_event(text, provider="rules").intent.value == "other"


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("accident nahi hua lekin pair mein chot lagi hai", "accident_sos"),
        ("accident nahi rok paya, help bhejo", "accident_sos"),
        ("accident nahi tal saka", "accident_sos"),
        ("missing item nahi mila report mein", "item_missing"),
        ("no delay but bike gir gayi", "accident_sos"),
        ("no accident, item missing hai", "item_missing"),
        ("gate band nahi hai, customer phone nahi utha raha", "customer_unreachable"),
        ("traffic nahi hai lekin address galat hai", "address_issue"),
        ("address galat nahi hai lekin traffic hai", "delay"),
        ("late nahi hoon. Traffic jam aage hai", "delay"),
        ("item missing hai, customer nahi utha raha", "item_missing"),
        ("order 31 mein ek item kam hai", "item_missing"),
        ("phone nahi lag raha, order 31", "customer_unreachable"),
        ("customer not answering, order 31", "customer_unreachable"),
        ("phone busy nahi hai par customer nahi utha raha", "customer_unreachable"),
        ("chot lagne se pair dard kar raha", "accident_sos"),
        ("der lagne wali hai, order 31", "delay"),
    ],
)
def test_negation_does_not_suppress_an_independent_problem(text, intent):
    assert extract_event(text, provider="rules").intent.value == intent
