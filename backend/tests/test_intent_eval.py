"""Gold, tuning-holdout, and blind-holdout contracts, plus offline rules eval."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from rasta.intent_eval import (
    BLIND_HOLDOUT_PATH,
    BLIND_RULES_BASELINE,
    BLIND_RULES_BASELINE_CORRECT,
    BLIND_RULES_BASELINE_N,
    GOLD_PATH,
    TUNING_HOLDOUT_PATH,
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
    assert {row.intent for row in rows} == INTENTS
    assert all(row.text.strip() for row in rows)


def test_tuning_holdout_is_preserved_as_a_regression_set():
    gold = load_gold_rows(GOLD_PATH)
    tuning = load_gold_rows(TUNING_HOLDOUT_PATH)
    assert len(tuning) == 24
    assert {row.intent for row in tuning} == INTENTS
    assert {row.text for row in gold}.isdisjoint({row.text for row in tuning})
    assert {row.id for row in gold}.isdisjoint({row.id for row in tuning})
    # The required stacked gate/phone case stays in the development set.
    assert any(
        "gate band" in row.text
        and "nahi utha" in row.text
        and row.intent == "customer_unreachable"
        for row in gold
    )
    assert any(row.intent == "other" for row in tuning)
    number_words = ("eighteen", "chaar", "bees")
    assert any(any(word in row.text for word in number_words) for row in tuning)


def test_blind_holdout_shape_and_independence():
    gold = load_gold_rows(GOLD_PATH)
    tuning = load_gold_rows(TUNING_HOLDOUT_PATH)
    blind = load_gold_rows(BLIND_HOLDOUT_PATH)
    assert len(blind) >= 36
    counts = {intent: 0 for intent in INTENTS}
    for row in blind:
        counts[row.intent] += 1
    assert all(count >= 6 for count in counts.values())
    gold_texts = {row.text for row in gold}
    tuning_texts = {row.text for row in tuning}
    blind_texts = {row.text for row in blind}
    assert gold_texts.isdisjoint(blind_texts)
    assert tuning_texts.isdisjoint(blind_texts)
    assert {row.id for row in gold}.isdisjoint({row.id for row in blind})
    assert {row.id for row in tuning}.isdisjoint({row.id for row in blind})
    assert any(row.intent == "other" for row in blind)


def test_fixtures_have_no_eight_digit_runs():
    for path in (GOLD_PATH, TUNING_HOLDOUT_PATH, BLIND_HOLDOUT_PATH):
        text = Path(path).read_text(encoding="utf-8")
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


def test_rules_accuracy_on_gold_tuning_and_blind():
    gold = evaluate_rows(load_gold_rows(GOLD_PATH), name="dev", provider="rules")
    tuning = evaluate_rows(
        load_gold_rows(TUNING_HOLDOUT_PATH), name="tuning", provider="rules"
    )
    blind = evaluate_rows(
        load_gold_rows(BLIND_HOLDOUT_PATH), name="blind", provider="rules"
    )
    print(format_report(gold))
    print(format_report(tuning))
    print(format_report(blind))
    # Development set only: not an independent claim.
    assert gold.accuracy >= 0.8, format_report(gold)
    # The 0.8 issue target is not met on the blind set. This floor is the
    # first (and repeated) rules score of 6/36 measured on 12 Nov 2026.
    # Do not raise it by retuning rules or relabelling the frozen file.
    assert blind.n == BLIND_RULES_BASELINE_N
    assert blind.accuracy >= BLIND_RULES_BASELINE, format_report(blind)
    assert blind.intent_correct >= BLIND_RULES_BASELINE_CORRECT
    assert gold.rules_used == gold.n
    assert gold.llm_successes == 0
    assert tuning.rules_used == tuning.n
    assert blind.rules_used == blind.n
    for intent in INTENTS:
        _correct, total = blind.per_intent[intent]
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
    if not rows:
        pytest.skip("benchmark corpus is not in this checkout")
    assert len(rows) >= 40
    assert {row.intent for row in rows} == INTENTS
