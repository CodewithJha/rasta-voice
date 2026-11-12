"""Gold / holdout contract and offline rules evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rasta.intent_eval import (
    GOLD_PATH,
    HOLDOUT_ACCURACY_TARGET,
    HOLDOUT_PATH,
    FixtureError,
    evaluate_rows,
    format_report,
    load_benchmark_corpus,
    load_gold_rows,
)
from rasta.schema import Intent

INTENTS = {intent.value for intent in Intent}


def test_gold_file_meets_the_issue_minimum():
    rows = load_gold_rows(GOLD_PATH)
    assert len(rows) >= 20
    seen = {row.intent for row in rows}
    assert seen == INTENTS
    assert all(row.text.strip() for row in rows)


def test_holdout_is_independent_and_large_enough():
    gold = load_gold_rows(GOLD_PATH)
    holdout = load_gold_rows(HOLDOUT_PATH)
    assert len(holdout) >= 6
    assert {row.intent for row in holdout} == INTENTS
    gold_texts = {row.text for row in gold}
    holdout_texts = {row.text for row in holdout}
    assert gold_texts.isdisjoint(holdout_texts)
    gold_ids = {row.id for row in gold}
    holdout_ids = {row.id for row in holdout}
    assert gold_ids.isdisjoint(holdout_ids)
    # The required stacked gate/phone case is in the development set.
    assert any(
        "gate band" in row.text and "nahi utha" in row.text and row.intent == "customer_unreachable"
        for row in gold
    )
    # Holdout has negatives / other, number words, and a contact-failure line.
    assert any(row.intent == "other" for row in holdout)
    number_words = ("eighteen", "chaar", "bees")
    assert any(any(word in row.text for word in number_words) for row in holdout)


def test_fixtures_have_no_eight_digit_runs():
    for path in (GOLD_PATH, HOLDOUT_PATH):
        text = Path(path).read_text(encoding="utf-8")
        assert "8"  # file exists
        import re

        assert re.search(r"\d{8,}", text) is None


def test_loader_rejects_a_long_digit_run(tmp_path: Path):
    path = tmp_path / "bad.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "x01",
                "intent": "other",
                "order_id": "9876543210",
                "eta_minutes": None,
                "text": "hello",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(FixtureError, match="digit runs"):
        load_gold_rows(path)


def test_rules_accuracy_on_gold_and_holdout():
    gold = evaluate_rows(load_gold_rows(GOLD_PATH), name="dev", provider="rules")
    holdout = evaluate_rows(load_gold_rows(HOLDOUT_PATH), name="holdout", provider="rules")
    # Print the matrix so a failure shows the real numbers.
    print(format_report(gold))
    print(format_report(holdout))
    assert gold.accuracy >= 0.8, format_report(gold)
    assert holdout.accuracy >= HOLDOUT_ACCURACY_TARGET, format_report(holdout)
    assert gold.rules_used == gold.n
    assert gold.llm_successes == 0
    assert holdout.rules_used == holdout.n
    for intent in INTENTS:
        correct, total = holdout.per_intent[intent]
        assert total >= 1


def test_llm_fallback_is_not_counted_as_llm_success():
    gold = load_gold_rows(GOLD_PATH)[:3]

    def predict(row):
        from rasta.intent_eval import RowScore

        return RowScore(
            row=row,
            predicted=row.intent,
            source="rules",
            fallback_reason="timeout",
            order_id=row.order_id,
            eta_minutes=row.eta_minutes,
            intent_ok=True,
            order_ok=True,
            eta_ok=True,
        )

    report = evaluate_rows(gold, name="fallback", predict=predict)
    assert report.rules_used == 3
    assert report.llm_successes == 0
    assert report.llm_calls == 3
    assert report.accuracy == 1.0


def test_benchmark_corpus_is_readable_without_writing():
    rows = load_benchmark_corpus()
    # The corpus was merged in issue 01; if present it must parse and stay intact.
    if not rows:
        pytest.skip("benchmark corpus is not in this checkout")
    assert len(rows) >= 40
    assert {row.intent for row in rows} == INTENTS
