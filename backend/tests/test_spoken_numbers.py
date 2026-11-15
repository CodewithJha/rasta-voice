"""Number grammar regressions, independent of the frozen intent holdouts."""

import pytest

from rasta.extract import extract_event


@pytest.mark.parametrize("phrase,expected", [
    ("one eight", "18"),
    ("one zero two", "102"),
    ("four-zero-five", "405"),
    ("ek aath", "18"),
    ("ek shoonya do", "102"),
    ("one aath", "18"),
    ("one two three four five six", "123456"),
    ("twenty five", "25"),
    ("ninety-nine", "99"),
    ("one hundred two", "102"),
    ("one hundred and two", "102"),
    ("two thousand three hundred forty five", "2345"),
    ("one thousand and five", "1005"),
    ("nine hundred ninety nine thousand nine hundred ninety nine", "999999"),
])
def test_spoken_order_grammar(phrase, expected):
    result = extract_event(f"order number {phrase} pe customer phone nahi utha raha", "rules")
    assert result.order_id == expected
    assert result.intent.value == "customer_unreachable"


@pytest.mark.parametrize("phrase,expected", [
    ("gyarah", 11), ("barah", 12), ("terah", 13), ("chaudah", 14),
    ("pandrah", 15), ("solah", 16), ("satrah", 17), ("atharah", 18),
    ("unnees", 19), ("bees", 20), ("ikkees", 21), ("baees", 22),
    ("teis", 23), ("chaubees", 24), ("pachchees", 25), ("chhabbees", 26),
    ("sattais", 27), ("atthais", 28), ("untees", 29), ("tees", 30),
])
def test_hindi_number_literals_in_order_and_eta(phrase, expected):
    result = extract_event(f"order {phrase}, traffic mein {phrase} minute late", "rules")
    assert result.order_id == str(expected)
    assert result.eta_minutes == expected


@pytest.mark.parametrize("phrase", [
    "a teen", "twenty eighteen", "one two hundred", "hundred", "one thousand thousand",
    "twenty five five", "one million", "one billion", "one point five", "18.5", "1,234",
    "eighteen or nineteen", "eighteen ya nineteen", "18 or 19",
    "one two three four five six seven",
    "one two three four five six seven eight", "9876543210",
])
def test_invalid_or_phone_length_order_is_not_guessed_or_truncated(phrase):
    assert extract_event(f"order {phrase}, phone nahi utha raha", "rules").order_id is None


def test_unrelated_number_and_conjunction_do_not_change_order():
    result = extract_event(
        "order eighteen and customer phone nahi utha raha, room one eight", "rules",
    )
    assert result.order_id == "18"
    assert extract_event("room one eight, customer phone nahi utha raha", "rules").order_id is None


def test_digit_sequence_is_not_an_invented_eta():
    result = extract_event("order one eight, one two minutes late", "rules")
    assert result.order_id == "18"
    assert result.eta_minutes is None


@pytest.mark.parametrize("phrase", ["18.5", "18,5", "one point five"])
def test_fractional_eta_does_not_become_an_integer_suffix(phrase):
    assert extract_event(f"traffic, {phrase} minutes late", "rules").eta_minutes is None
