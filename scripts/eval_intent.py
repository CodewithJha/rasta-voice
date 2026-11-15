#!/usr/bin/env python3
"""Report per-intent accuracy and a confusion matrix for the extractor.

Usage:
  python scripts/eval_intent.py
  python scripts/eval_intent.py --provider groq
  python scripts/eval_intent.py --provider gemini --sets blind
  python scripts/eval_intent.py --enforce-target

The default exit is 0 even when the 0.8 blind-holdout target is unmet;
the script still prints TARGET MET or TARGET NOT MET. Pass
``--enforce-target`` to exit 1 when the target is unmet. CI does not
pass that flag until the issue 2 accuracy work lands.

Rules always run. An LLM provider is used only when its key is set; the
script then reports LLM accuracy without counting a rules fallback as an
LLM success. Without a key the LLM section is skipped cleanly.

The headline split is the blind holdout. The earlier 24-line file is a
tuning holdout: it was seen during rule expansion and is not an
independent test.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))
    sys.path.insert(0, str(ROOT / "benchmark"))

from rasta.intent_eval import (  # noqa: E402
    BLIND_HOLDOUT_PATH,
    GOLD_PATH,
    HOLDOUT_ACCURACY_TARGET,
    TUNING_HOLDOUT_PATH,
    EvalReport,
    evaluate_rows,
    format_report,
    format_target_status,
    load_benchmark_corpus,
    load_gold_rows,
)
from rasta.settings import get_settings  # noqa: E402

SET_CHOICES = ("gold", "tuning", "blind", "corpus")
_SET_PATHS = {
    "gold": ("dev (gold)", GOLD_PATH),
    "tuning": ("tuning holdout (seen during rule expansion)", TUNING_HOLDOUT_PATH),
    "blind": ("blind holdout", BLIND_HOLDOUT_PATH),
}


def _run(name: str, path: Path, provider: str) -> EvalReport:
    rows = load_gold_rows(path)
    report = evaluate_rows(rows, name=name, provider=provider)
    print(format_report(report))
    return report


def _wanted(sets: list[str] | None, name: str) -> bool:
    return sets is None or name in sets


def evidence_payload(
    report: EvalReport, *,
    provider: str,
    model: str,
    timeout_seconds: float,
) -> dict:
    """Structured scores only. Never include API keys or environment values."""
    latencies = [scored.latency_ms for scored in report.scores if scored.latency_ms is not None]
    reasons: dict[str, int] = {}
    for scored in report.scores:
        if scored.fallback_reason:
            reasons[scored.fallback_reason] = reasons.get(scored.fallback_reason, 0) + 1
    payload = {
        "run_at": datetime.now(UTC).isoformat(),
        "split": report.name,
        "provider": provider,
        "model": model,
        "timeout_seconds": timeout_seconds,
        "n": report.n,
        "intent_correct": report.intent_correct,
        "accuracy": report.accuracy,
        "order_correct": report.order_correct,
        "eta_correct": report.eta_correct,
        "rules_used": report.rules_used,
        "llm_successes": report.llm_successes,
        "llm_attempts": report.llm_calls,
        "fallback_reasons": reasons,
        "per_intent": {
            intent: {"correct": correct, "total": total}
            for intent, (correct, total) in report.per_intent.items()
        },
        "rows": [
            {
                "id": scored.row.id,
                "gold": scored.row.intent,
                "predicted": scored.predicted,
                "source": scored.source,
                "fallback_reason": scored.fallback_reason,
                "intent_ok": scored.intent_ok,
                "latency_ms": None if scored.latency_ms is None else round(scored.latency_ms, 1),
            }
            for scored in report.scores
        ],
    }
    if latencies:
        payload["latency_ms"] = {
            "n": len(latencies),
            "mean": round(statistics.fmean(latencies), 1),
            "p50": round(statistics.median(latencies), 1),
            "min": round(min(latencies), 1),
            "max": round(max(latencies), 1),
        }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default="rules",
        help="rules (default), groq, or gemini. LLM paths skip when the key is missing.",
    )
    parser.add_argument(
        "--sets",
        nargs="+",
        choices=SET_CHOICES,
        help=(
            "limit evaluation to these splits "
            "(default: gold, tuning, blind, and corpus for rules)."
        ),
    )
    parser.add_argument(
        "--write-evidence",
        type=Path,
        help="write JSON evidence for the last scored split of the selected provider.",
    )
    parser.add_argument(
        "--enforce-target",
        action="store_true",
        help=(
            "exit 1 if the blind rules score is below HOLDOUT_ACCURACY_TARGET. "
            "CI does not pass that flag until issue 2 accuracy work lands."
        ),
    )
    args = parser.parse_args(argv)
    sets = args.sets

    print("=== rules ===")
    last_report = None
    if _wanted(sets, "gold"):
        last_report = _run("dev (gold)", GOLD_PATH, "rules")
        print()
    if _wanted(sets, "tuning"):
        last_report = _run("tuning holdout (seen during rule expansion)", TUNING_HOLDOUT_PATH, "rules")
        print()
    blind = None
    if _wanted(sets, "blind"):
        blind = _run("blind holdout", BLIND_HOLDOUT_PATH, "rules")
        last_report = blind
        print(format_target_status(blind.accuracy, correct=blind.intent_correct, n=blind.n))
    if _wanted(sets, "corpus"):
        corpus = load_benchmark_corpus()
        if corpus:
            print()
            last_report = evaluate_rows(
                corpus,
                name="benchmark corpus (reference, not used for tuning)",
                provider="rules",
            )
            print(format_report(last_report))
    provider = args.provider.strip().lower()
    if provider != "rules":
        settings = get_settings()
        key = settings.key_for(provider)
        print()
        if not key:
            env_name = settings.key_env_name(provider)
            print(f"=== {provider} skipped ({env_name} is not set) ===")
        else:
            print(f"=== {provider} ===")
            last_report = None
            for name in ("gold", "tuning", "blind"):
                if not _wanted(sets, name):
                    continue
                if last_report is not None:
                    print()
                title, path = _SET_PATHS[name]
                last_report = _run(title, path, provider)

    if args.write_evidence:
        if last_report is None:
            print("No scored split available to write as evidence.", file=sys.stderr)
            return 1
        settings = get_settings()
        model = "rules"
        timeout = settings.llm_timeout_seconds
        written_provider = provider
        if provider != "rules" and settings.key_for(provider):
            model = settings.model_for(provider)
        else:
            written_provider = "rules"
        payload = evidence_payload(
            last_report,
            provider=written_provider,
            model=model,
            timeout_seconds=timeout,
        )
        path = args.write_evidence
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote evidence to {path}")

    if args.enforce_target:
        if blind is None:
            print("Cannot enforce the holdout target without the blind split.", file=sys.stderr)
            return 1
        if blind.accuracy < HOLDOUT_ACCURACY_TARGET:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
