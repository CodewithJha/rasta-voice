"""Offline verification of real, consented Rasta Voice field-audio results.

Never sends speech or reads raw recordings. Input contains only anonymized
reference/transcript text and provenance from *actual* Prisma responses.
An empty result file is valid as a pending work record, not as an achievement.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path

from rasta.extract import extract_event
from rasta_bench.run import normalize
from rasta_bench.score import cer, wer

RESULTS_PATH = Path(__file__).resolve().parents[1] / "results" / "field_validation.json"
INTENTS = (
    "customer_unreachable",
    "address_issue",
    "item_missing",
    "delay",
    "accident_sos",
    "other",
)
SOURCES = ("phone", "mic")
CONDITIONS = ("quiet", "noisy")
SETTINGS = {"language_code", "keyterms", "with_denoise", "output_format"}
ROW_FIELDS = {
    "id", "source", "condition", "recorded_at", "speaker_id",
    "consent_confirmed", "capture_method", "sample_rate_hz", "codec",
    "resampled", "g711_processed", "reference", "transcript", "model",
    "request_id", "request_id_unavailable_reason", "gold_intent",
    "predicted_intent", "intent_provider", "wer", "cer",
    "normalized_wer", "normalized_cer", "intent_correct",
    "latency_ms", "settings",
}
REQUIRED = ROW_FIELDS - {"request_id_unavailable_reason", "latency_ms"}
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{1,24}$")
LONG_DIGITS = re.compile(r"\d{8,}")


class FieldValidationError(ValueError):
    """Invalid or misleading field evidence."""


def _ensure(condition: bool, message: str) -> None:
    if not condition:
        raise FieldValidationError(message)


def _valid_row(row: dict, seen: set[str]) -> None:
    _ensure(isinstance(row, dict), "result must be an object")
    _ensure(REQUIRED <= row.keys(), "field result missing required keys")
    _ensure(not (row.keys() - ROW_FIELDS), "field result has unreviewed keys")
    identifier = row["id"]
    _ensure(
        isinstance(identifier, str)
        and bool(SAFE_ID.fullmatch(identifier))
        and identifier not in seen,
        "invalid or duplicate anonymized field id",
    )
    seen.add(identifier)
    _ensure(row["source"] in SOURCES, "source must be phone or mic")
    _ensure(row["condition"] in CONDITIONS, "condition must be quiet or noisy")
    _ensure(
        row["capture_method"] in ("microphone", "telephone_network"),
        "capture method must identify the real channel",
    )
    _ensure(
        (row["source"] == "phone") == (row["capture_method"] == "telephone_network"),
        "resampled microphone audio cannot be labelled a phone capture",
    )
    _ensure(row["consent_confirmed"] is True, "explicit consent must be confirmed")
    _ensure(
        isinstance(row["speaker_id"], str) and bool(re.fullmatch(r"s\d{1,3}", row["speaker_id"])),
        "speaker id must be anonymous, e.g. s1",
    )
    _ensure(isinstance(row["recorded_at"], str), "recorded_at must be a date")
    try:
        recorded = date.fromisoformat(row["recorded_at"])
        _ensure(recorded.isoformat() == row["recorded_at"], "recorded_at must be YYYY-MM-DD")
        _ensure(recorded <= date.today(), "recorded_at cannot be in the future")
    except ValueError as exc:
        raise FieldValidationError("recorded_at must be an ISO date") from exc
    _ensure(
        type(row["sample_rate_hz"]) is int and row["sample_rate_hz"] >= 8000,
        "sample rate must be an integer >= 8000",
    )
    _ensure(
        isinstance(row["codec"], str) and 0 < len(row["codec"]) <= 30,
        "recording codec is required",
    )
    for flag in ("resampled", "g711_processed"):
        _ensure(type(row[flag]) is bool, f"{flag} must be boolean")
    for field in ("reference", "transcript"):
        value = row[field]
        _ensure(isinstance(value, str) and 0 < len(value.strip()) <= 500, f"{field} invalid")
        _ensure(not LONG_DIGITS.search(value), "possible personal numeric data in text")
    _ensure(
        isinstance(row["model"], str) and row["model"].startswith("prisma-"),
        "model must identify the actual Prisma version",
    )
    _ensure(row["gold_intent"] in INTENTS and row["predicted_intent"] in INTENTS, "invalid intent")
    _ensure(row["intent_provider"] == "rules", "field accuracy must use frozen rules mode")
    _ensure(
        extract_event(row["transcript"], provider="rules").intent.value == row["predicted_intent"],
        "predicted intent does not match rule extractor on recorded transcript",
    )
    _ensure(
        type(row["intent_correct"]) is bool
        and row["intent_correct"] == (row["gold_intent"] == row["predicted_intent"]),
        "intent_correct does not match reference and predicted intent",
    )
    request_id = row["request_id"]
    _ensure(
        request_id is None
        or (isinstance(request_id, str) and 0 < len(request_id.strip()) <= 128),
        "invalid Gnani request_id",
    )
    if request_id is None:
        _ensure(
            isinstance(row.get("request_id_unavailable_reason"), str)
            and bool(row["request_id_unavailable_reason"].strip()),
            "missing request ID must be explained, never invented",
        )
    else:
        _ensure(
            row.get("request_id_unavailable_reason") in (None, ""),
            "do not claim a missing request ID when one was provided",
        )
    _ensure(isinstance(row["settings"], dict), "settings must be an object")
    _ensure(not (row["settings"].keys() - SETTINGS), "unknown settings can leak secrets")
    for name, value in row["settings"].items():
        if name in {"keyterms", "output_format"} and value is None:
            continue
        if name == "with_denoise":
            _ensure(type(value) is bool, "with_denoise must be boolean")
        elif name == "keyterms":
            _ensure(
                isinstance(value, list)
                and len(value) <= 20
                and all(
                    isinstance(item, str)
                    and 0 < len(item.strip()) < 80
                    and not LONG_DIGITS.search(item)
                    for item in value
                ),
                "settings contain an unsafe keyterms list",
            )
        else:
            _ensure(
                isinstance(value, str) and 0 < len(value.strip()) <= 80
                and not LONG_DIGITS.search(value),
                f"{name} must be a short sanitized string",
            )

    expected = {
        "wer": wer(row["reference"], row["transcript"]),
        "cer": cer(row["reference"], row["transcript"]),
        "normalized_wer": wer(normalize(row["reference"]), normalize(row["transcript"])),
        "normalized_cer": cer(normalize(row["reference"]), normalize(row["transcript"])),
    }
    for key, target in expected.items():
        score = row[key]
        _ensure(
            type(score) in {float, int}
            and math.isfinite(score)
            and math.isclose(score, target, rel_tol=1e-8, abs_tol=1e-8),
            f"{key} differs from recalculation for {identifier}",
        )
    latency = row.get("latency_ms")
    _ensure(
        latency is None
        or (type(latency) in {float, int} and math.isfinite(latency) and latency >= 0),
        "latency must be nonnegative when present",
    )


def validate_document(document: dict) -> dict:
    """Return inspectable aggregate results; do not invent missing observations."""
    _ensure(isinstance(document, dict), "field validation must be a JSON object")
    _ensure(
        set(document) <= {"status", "normalization", "results", "limitation"},
        "unexpected top-level fields",
    )
    _ensure(
        document.get("normalization") == "rasta_bench.run.normalize",
        "normalization method must match the synthetic benchmark",
    )
    rows = document.get("results")
    if not isinstance(rows, list):
        raise FieldValidationError("results must be an array")
    seen: set[str] = set()
    for row in rows:
        _valid_row(row, seen)
    if not rows:
        _ensure(document.get("status") == "not_collected", "empty results cannot be measured")
        _ensure(
            isinstance(document.get("limitation"), str) and bool(document["limitation"].strip()),
            "empty evidence needs an honest limitation",
        )
        return {"status": "not_collected", "n": 0, "phone": 0, "mic": 0}
    _ensure(document.get("status") == "measured", "nonempty results must be labelled measured")
    if len(rows) < 4:
        _ensure(
            isinstance(document.get("limitation"), str) and bool(document["limitation"].strip()),
            "fewer than 4 field clips requires an explicit limitation",
        )
    def aggregate(group: list[dict]) -> dict:
        return {
            "n": len(group),
            "raw_wer": sum(row["wer"] for row in group) / len(group),
            "raw_cer": sum(row["cer"] for row in group) / len(group),
            "normalized_wer": sum(row["normalized_wer"] for row in group) / len(group),
            "normalized_cer": sum(row["normalized_cer"] for row in group) / len(group),
            "intent_accuracy": sum(row["intent_correct"] for row in group) / len(group),
        }

    return {
        "status": "measured",
        **aggregate(rows),
        "phone": sum(row["source"] == "phone" for row in rows),
        "mic": sum(row["source"] == "mic" for row in rows),
        "by_source": {
            source: aggregate([row for row in rows if row["source"] == source])
            for source in sorted({row["source"] for row in rows})
        },
        "by_condition": {
            condition: aggregate([row for row in rows if row["condition"] == condition])
            for condition in sorted({row["condition"] for row in rows})
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    parser.add_argument(
        "--require-measured",
        action="store_true",
        help="fail until real field measurements have been recorded",
    )
    args = parser.parse_args(argv)
    try:
        summary = validate_document(json.loads(args.results.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"field evidence invalid: {exc}\n")
    print(json.dumps(summary, sort_keys=True))
    if args.require_measured and summary["n"] == 0:
        print("field audio still not measured; award claim is not verified")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
