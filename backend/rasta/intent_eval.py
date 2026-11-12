"""Offline intent evaluation for the gold and frozen holdout sets.

Labels were assigned before any rule or prompt change. This module never
rewrites them. Accuracy is intent-only; order_id and eta are reported as
secondary exact-match rates. A rules fallback on the LLM path is counted
as rules, never as an LLM success.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rasta.extract import extract_event_with_source
from rasta.schema import Intent

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
GOLD_PATH = FIXTURES_DIR / "intent_gold.jsonl"
HOLDOUT_PATH = FIXTURES_DIR / "intent_holdout.jsonl"
# Himanshu's corpus is read-only reference data; this module must not edit it.
BENCHMARK_CORPUS_PATH = (
    Path(__file__).resolve().parents[2] / "benchmark" / "data" / "utterances.jsonl"
)

_FIELDS = frozenset({"id", "intent", "order_id", "eta_minutes", "text"})
_LONG_DIGITS = re.compile(r"\d{8,}")
INTENTS = tuple(intent.value for intent in Intent)
HOLDOUT_ACCURACY_TARGET = 0.8


class FixtureError(ValueError):
    """A gold or holdout row is not usable."""


@dataclass(frozen=True, slots=True)
class GoldRow:
    """One labelled utterance."""

    id: str
    intent: str
    order_id: str | None
    eta_minutes: int | None
    text: str


@dataclass(slots=True)
class RowScore:
    """One prediction compared to a frozen label."""

    row: GoldRow
    predicted: str
    source: str
    fallback_reason: str | None
    order_id: str | None
    eta_minutes: int | None
    intent_ok: bool
    order_ok: bool
    eta_ok: bool


@dataclass(slots=True)
class EvalReport:
    """Accuracy, per-intent recall, and a confusion matrix for one split."""

    name: str
    n: int
    intent_correct: int
    order_correct: int
    eta_correct: int
    per_intent: dict[str, tuple[int, int]] = field(default_factory=dict)
    confusion: dict[tuple[str, str], int] = field(default_factory=dict)
    misses: list[RowScore] = field(default_factory=list)
    llm_calls: int = 0
    llm_successes: int = 0
    rules_used: int = 0

    @property
    def accuracy(self) -> float:
        return 0.0 if self.n == 0 else self.intent_correct / self.n

    def confusion_matrix(self) -> list[list[int]]:
        """Rows are gold labels, columns are predictions, both in schema order."""
        return [
            [self.confusion.get((gold, pred), 0) for pred in INTENTS]
            for gold in INTENTS
        ]


def load_gold_rows(path: str | Path) -> list[GoldRow]:
    """Load a JSONL gold or holdout file, or raise ``FixtureError``."""
    rows: list[GoldRow] = []
    seen: set[str] = set()
    texts: set[str] = set()
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            if _LONG_DIGITS.search(line):
                raise FixtureError(f"{path}:{line_number}: digit runs of 8 or more are not allowed")
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FixtureError(f"{path}:{line_number}: invalid JSON") from exc
            row = _parse_row(raw, path, line_number)
            if row.id in seen:
                raise FixtureError(f"{path}:{line_number}: duplicate id {row.id!r}")
            if row.text in texts:
                raise FixtureError(f"{path}:{line_number}: duplicate text")
            seen.add(row.id)
            texts.add(row.text)
            rows.append(row)
    return rows


def _parse_row(raw: Any, path: str | Path, line_number: int) -> GoldRow:
    if not isinstance(raw, dict) or not _FIELDS <= set(raw):
        raise FixtureError(
            f"{path}:{line_number}: expected id, intent, order_id, eta_minutes, text"
        )
    identifier = raw["id"]
    intent = raw["intent"]
    order = raw["order_id"]
    eta = raw["eta_minutes"]
    text = raw["text"]
    if not isinstance(identifier, str) or not identifier.strip():
        raise FixtureError(f"{path}:{line_number}: id must be a nonempty string")
    if intent not in INTENTS:
        raise FixtureError(f"{path}:{line_number}: intent is not a schema value")
    if order is not None and (not isinstance(order, str) or not order.strip()):
        raise FixtureError(f"{path}:{line_number}: order_id must be a nonempty string or null")
    if eta is not None and (type(eta) is not int or eta < 0):
        raise FixtureError(f"{path}:{line_number}: eta_minutes must be a nonnegative int or null")
    if not isinstance(text, str) or not text.strip():
        raise FixtureError(f"{path}:{line_number}: text must be a nonempty string")
    if _LONG_DIGITS.search(json.dumps(raw, ensure_ascii=False)):
        raise FixtureError(f"{path}:{line_number}: digit runs of 8 or more are not allowed")
    return GoldRow(identifier, intent, order, eta, text)


def evaluate_rows(
    rows: Iterable[GoldRow],
    *,
    name: str,
    provider: str = "rules",
    predict: Callable[[GoldRow], RowScore] | None = None,
) -> EvalReport:
    """Score ``rows`` with ``provider``, or with an injected ``predict`` function."""
    materialised = list(rows)
    report = EvalReport(
        name=name,
        n=len(materialised),
        intent_correct=0,
        order_correct=0,
        eta_correct=0,
        per_intent={intent: (0, 0) for intent in INTENTS},
    )
    scorer = predict or (lambda row: _predict_row(row, provider))
    for row in materialised:
        scored = scorer(row)
        correct, total = report.per_intent[row.intent]
        total += 1
        if scored.intent_ok:
            report.intent_correct += 1
            correct += 1
        else:
            report.misses.append(scored)
        if scored.order_ok:
            report.order_correct += 1
        if scored.eta_ok:
            report.eta_correct += 1
        report.per_intent[row.intent] = (correct, total)
        key = (row.intent, scored.predicted)
        report.confusion[key] = report.confusion.get(key, 0) + 1
        if scored.source == "llm":
            report.llm_calls += 1
            report.llm_successes += 1
        else:
            report.rules_used += 1
            if scored.fallback_reason:
                report.llm_calls += 1
    return report


def _predict_row(row: GoldRow, provider: str) -> RowScore:
    result = extract_event_with_source(row.text, provider=provider)
    predicted = result.event.intent.value
    return RowScore(
        row=row,
        predicted=predicted,
        source=result.source,
        fallback_reason=result.fallback_reason,
        order_id=result.event.order_id,
        eta_minutes=result.event.eta_minutes,
        intent_ok=predicted == row.intent,
        order_ok=result.event.order_id == row.order_id,
        eta_ok=result.event.eta_minutes == row.eta_minutes,
    )


def format_report(report: EvalReport) -> str:
    """Return a plain-text report with per-intent accuracy and a confusion matrix."""
    lines = [
        f"{report.name}: intent accuracy {report.intent_correct}/{report.n} "
        f"= {report.accuracy:.3f}",
        (
            f"  order_id exact {report.order_correct}/{report.n}, "
            f"eta_minutes exact {report.eta_correct}/{report.n}"
        ),
        f"  source counts: rules={report.rules_used} llm={report.llm_successes}"
        + (f" (llm attempts={report.llm_calls})" if report.llm_calls else ""),
        "  per-intent (correct/total):",
    ]
    for intent in INTENTS:
        correct, total = report.per_intent.get(intent, (0, 0))
        rate = "n/a" if total == 0 else f"{correct / total:.2f}"
        lines.append(f"    {intent:22} {correct}/{total} {rate}")
    lines.append("  confusion matrix (rows gold, columns predicted):")
    header = " ".join(f"{intent[:6]:>6}" for intent in INTENTS)
    lines.append(f"    {'gold':22} {header}")
    matrix = report.confusion_matrix()
    for intent, row in zip(INTENTS, matrix, strict=True):
        cells = " ".join(f"{count:6d}" for count in row)
        lines.append(f"    {intent:22} {cells}")
    if report.misses:
        lines.append("  misses:")
        for scored in report.misses:
            lines.append(
                f"    {scored.row.id}: gold={scored.row.intent} pred={scored.predicted} "
                f"source={scored.source}"
                + (f" reason={scored.fallback_reason}" if scored.fallback_reason else "")
            )
    return "\n".join(lines)


def load_benchmark_corpus(path: str | Path | None = None) -> list[GoldRow]:
    """Load Himanshu's utterance corpus as an extra reference split.

    The file is not opened for write. A missing file returns an empty list
    so the eval script still runs on a partial checkout.
    """
    target = Path(path) if path is not None else BENCHMARK_CORPUS_PATH
    if not target.is_file():
        return []
    # Import inside the function so backend tests do not require the
    # benchmark package to import rasta.intent_eval.
    from rasta_bench.corpus import load_utterances

    rows = []
    for raw in load_utterances(target):
        rows.append(
            GoldRow(
                id=raw["id"],
                intent=raw["intent"],
                order_id=raw["order_id"],
                eta_minutes=raw["eta_minutes"],
                text=raw["text"],
            )
        )
    return rows
