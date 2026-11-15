"""Offline field-validation contract, with synthetic test rows only."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from rasta.extract import extract_event
from rasta_bench.field_validation import FieldValidationError, main, validate_document
from rasta_bench.run import normalize
from rasta_bench.score import cer, wer

ROOT = Path(__file__).resolve().parents[1]


def _record() -> dict:
    ref = "bhaiya gate band hai customer phone nahi utha order 18"
    hyp = ref
    gold = "customer_unreachable"
    predicted = extract_event(hyp, provider="rules").intent.value
    return {
        "id": "f01",
        "source": "mic",
        "capture_method": "microphone",
        "condition": "noisy",
        "recorded_at": "2026-11-14",
        "speaker_id": "s1",
        "consent_confirmed": True,
        "sample_rate_hz": 16000,
        "codec": "wav-pcm16",
        "resampled": False,
        "g711_processed": False,
        "reference": ref,
        "transcript": hyp,
        "model": "prisma-v3.0",
        "request_id": "synthetic-request-for-offline-unit-test",
        "gold_intent": gold,
        "predicted_intent": predicted,
        "intent_provider": "rules",
        "wer": wer(ref, hyp),
        "cer": cer(ref, hyp),
        "normalized_wer": wer(normalize(ref), normalize(hyp)),
        "normalized_cer": cer(normalize(ref), normalize(hyp)),
        "intent_correct": gold == predicted,
        "settings": {
            "language_code": "hi-IN,en-IN",
            "keyterms": ["order", "gate", "item", "accident"],
            "output_format": "codemix",
            "with_denoise": True,
        },
        "latency_ms": 140,
    }


def _document(row: dict) -> dict:
    return {
        "status": "measured",
        "normalization": "rasta_bench.run.normalize",
        "limitation": "Only one invented sample in this test; no real recordings.",
        "results": [row],
    }


def test_committed_field_evidence_is_consistent():
    path = ROOT / "results" / "field_validation.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    summary = validate_document(document)
    assert summary["n"] == len(document["results"])
    assert summary["status"] == document["status"]


def test_strict_release_check_cannot_pass_without_actual_audio(tmp_path, capsys):
    empty = {
        "status": "not_collected",
        "normalization": "rasta_bench.run.normalize",
        "limitation": "No consented audio collected in this regression fixture.",
        "results": [],
    }
    path = tmp_path / "field.json"
    path.write_text(json.dumps(empty), encoding="utf-8")
    assert main(["--results", str(path), "--require-measured"]) == 1
    assert "not measured" in capsys.readouterr().out


def test_synthetic_test_fixture_scores_are_recalculated():
    result = validate_document(_document(_record()))
    assert result["n"] == 1
    assert result["mic"] == 1
    assert result["phone"] == 0
    assert result["raw_wer"] == 0.0
    assert result["normalized_cer"] == 0.0


@pytest.mark.parametrize(
    "field,bad",
    [
        ("wer", 0.5),
        ("normalized_wer", 0.5),
        ("cer", 0.5),
        ("normalized_cer", 0.5),
        ("intent_correct", "true"),
        ("predicted_intent", "accident_sos"),
        ("source", "phone"),
        ("consent_confirmed", False),
        ("speaker_id", "real-person"),
        ("request_id", None),
    ],
)
def test_invalid_field_evidence_is_rejected(field, bad):
    row = _record()
    row[field] = bad
    with pytest.raises(FieldValidationError):
        validate_document(_document(row))


def test_field_scorer_preserves_raw_vs_normalized_number_word_difference():
    row = _record()
    row["reference"] = row["reference"].replace("order 18", "order eighteen")
    row["wer"] = wer(row["reference"], row["transcript"])
    row["cer"] = cer(row["reference"], row["transcript"])
    row["normalized_wer"] = wer(normalize(row["reference"]), normalize(row["transcript"]))
    row["normalized_cer"] = cer(normalize(row["reference"]), normalize(row["transcript"]))
    report = validate_document(_document(row))
    assert report["raw_wer"] > 0
    assert report["normalized_wer"] == 0
    assert report["by_source"]["mic"]["n"] == 1
    assert report["by_condition"]["noisy"]["n"] == 1


def test_only_verified_phone_network_recordings_can_be_phone():
    row = _record()
    row["source"] = "phone"
    row["capture_method"] = "telephone_network"
    assert validate_document(_document(row))["phone"] == 1


def test_missing_request_id_can_only_be_recorded_with_explanation():
    row = _record()
    row["request_id"] = None
    row["request_id_unavailable_reason"] = "Provider response did not include an ID."
    assert validate_document(_document(row))["mic"] == 1


def test_wrong_transcript_label_and_pii_are_rejected():
    row = _record()
    row["transcript"] = "phone number 1234567890"
    with pytest.raises(FieldValidationError):
        validate_document(_document(row))


def test_duplicate_rows_and_hidden_metadata_fail():
    row = _record()
    document = _document(row)
    document["results"].append(deepcopy(row))
    with pytest.raises(FieldValidationError):
        validate_document(document)
    document["results"] = [row]
    row["raw_audio_path"] = "/tmp/private.wav"
    with pytest.raises(FieldValidationError):
        validate_document(document)


def test_measured_flag_is_not_allowed_on_empty_results():
    document = {
        "status": "measured",
        "normalization": "rasta_bench.run.normalize",
        "limitation": "No clips",
        "results": [],
    }
    with pytest.raises(FieldValidationError):
        validate_document(document)


@pytest.mark.parametrize("field", ["source", "condition", "capture_method", "gold_intent"])
def test_malformed_label_types_are_controlled_validation_errors(field):
    row = _record()
    row[field] = []
    with pytest.raises(FieldValidationError):
        validate_document(_document(row))


@pytest.mark.parametrize("value", [None, {}, "clips"])
def test_results_must_be_an_array(value):
    document = _document(_record())
    document["results"] = value
    with pytest.raises(FieldValidationError):
        validate_document(document)


@pytest.mark.parametrize("value", ["20261114", "2999-01-01", "2026-02-30"])
def test_capture_date_is_canonical_and_not_future(value):
    row = _record()
    row["recorded_at"] = value
    with pytest.raises(FieldValidationError):
        validate_document(_document(row))


@pytest.mark.parametrize("settings", [
    {"with_denoise": "true"},
    {"keyterms": "gate"},
    {"keyterms": ["1234567890"]},
    {"output_format": []},
    {"language_code": None},
    {"api_key": "not-a-real-key"},
])
def test_provider_settings_have_field_specific_types(settings):
    row = _record()
    row["settings"] = settings
    with pytest.raises(FieldValidationError):
        validate_document(_document(row))


def test_optional_prisma_settings_may_be_null():
    row = _record()
    row["settings"] = {"keyterms": None, "output_format": None, "with_denoise": False}
    assert validate_document(_document(row))["n"] == 1


def test_invalid_file_exits_with_one_readable_error_line(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text('{"results": null}', encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        main(["--results", str(path)])
    assert error.value.code == 1
    output = capsys.readouterr().err
    assert output.endswith("\n") and "\\n" not in output
