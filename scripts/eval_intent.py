#!/usr/bin/env python3
"""Report per-intent accuracy and a confusion matrix for the extractor.

Usage:
  python scripts/eval_intent.py
  python scripts/eval_intent.py --provider groq
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
import sys
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
    evaluate_rows,
    format_report,
    format_target_status,
    load_benchmark_corpus,
    load_gold_rows,
)
from rasta.settings import get_settings  # noqa: E402


def _run(name: str, path: Path, provider: str):
    rows = load_gold_rows(path)
    report = evaluate_rows(rows, name=name, provider=provider)
    print(format_report(report))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        default="rules",
        help="rules (default), groq, or gemini. LLM paths skip when the key is missing.",
    )
    parser.add_argument(
        "--enforce-target",
        action="store_true",
        help=(
            "exit 1 if the blind rules score is below HOLDOUT_ACCURACY_TARGET. "
            "CI does not pass this flag until issue 2 accuracy work lands."
        ),
    )
    args = parser.parse_args(argv)

    print("=== rules ===")
    _run("dev (gold)", GOLD_PATH, "rules")
    print()
    _run("tuning holdout (seen during rule expansion)", TUNING_HOLDOUT_PATH, "rules")
    print()
    blind = _run("blind holdout", BLIND_HOLDOUT_PATH, "rules")
    print(format_target_status(blind.accuracy, correct=blind.intent_correct, n=blind.n))
    corpus = load_benchmark_corpus()
    if corpus:
        print()
        report = evaluate_rows(
            corpus,
            name="benchmark corpus (reference, not used for tuning)",
            provider="rules",
        )
        print(format_report(report))

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
            _run("dev (gold)", GOLD_PATH, provider)
            print()
            _run("tuning holdout (seen during rule expansion)", TUNING_HOLDOUT_PATH, provider)
            print()
            _run("blind holdout", BLIND_HOLDOUT_PATH, provider)

    if args.enforce_target and blind.accuracy < HOLDOUT_ACCURACY_TARGET:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
