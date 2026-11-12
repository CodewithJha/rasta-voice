import json
import re
import socket
from collections import Counter
from pathlib import Path

import pytest

from rasta_bench.corpus import INTENTS, load_utterances

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "benchmark/data/utterances.jsonl"
VALID_ROW = {
    "id": "u01",
    "intent": "customer_unreachable",
    "order_id": "18",
    "eta_minutes": None,
    "text": "bhaiya gate band hai, customer phone nahi utha raha, order 18",
}


def test_committed_corpus_contract(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)

    def no_network(*args, **kwargs):
        raise AssertionError("corpus loading must be offline")

    monkeypatch.setattr(socket, "socket", no_network)
    rows = load_utterances(CORPUS)
    schema = json.loads((ROOT / "shared/rider_event.schema.json").read_text())
    intents = set(schema["properties"]["intent"]["enum"])
    assert INTENTS == intents
    assert len(rows) >= 40
    assert set(counts := Counter(row["intent"] for row in rows)) == intents
    assert all(counts[intent] >= 6 for intent in intents)
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({row["text"] for row in rows}) == len(rows)
    assert not re.search(r"\d{8,}", CORPUS.read_text(encoding="utf-8"))
    assert VALID_ROW in rows
    assert any(
        row["text"] == "order 4 mein ek item missing"
        and row["intent"] == "item_missing"
        and row["order_id"] == "4"
        for row in rows
    )
    assert {None, "4", "18", "102"} <= {row["order_id"] for row in rows}
    assert any(re.search(r"[\u0900-\u097f]", row["text"]) for row in rows)
    assert all(row["eta_minutes"] is None for row in rows if row["intent"] != "delay")
    delays = [row for row in rows if row["intent"] == "delay"]
    assert any(row["eta_minutes"] is None for row in delays)
    assert any(row["eta_minutes"] is not None for row in delays)


def test_loader_preserves_reference_and_accepts_small_subset(tmp_path):
    path = tmp_path / "subset.jsonl"
    rows = [VALID_ROW, {**VALID_ROW, "id": "u02", "text": "  भैया, gate band hai!  "}]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
    )
    assert load_utterances(str(path)) == rows


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"id": 1}, "id"),
        ({"id": "u1"}, "id"),
        ({"id": "u001"}, "id"),
        ({"id": "u०१"}, "id"),
        ({"intent": "unknown"}, "intent"),
        ({"intent": []}, "intent"),
        ({"order_id": 18}, "order_id"),
        ({"order_id": " "}, "order_id"),
        ({"order_id": "12345678"}, "digit runs"),
        ({"eta_minutes": -1}, "eta_minutes"),
        ({"eta_minutes": 1.5}, "eta_minutes"),
        ({"eta_minutes": True}, "eta_minutes"),
        ({"eta_minutes": "20"}, "eta_minutes"),
        ({"text": None}, "text"),
        ({"text": "  "}, "text"),
        ({"text": "<whispers> bhaiya"}, "tags"),
        ({"text": "bhaiya <pauses> gate band"}, "tags"),
        ({"text": "phone 12345678"}, "digit runs"),
        ({"text": "फोन १२३४५६७८"}, "digit runs"),
    ],
)
def test_bad_row_reports_physical_line(tmp_path, change, reason):
    bad_row = {**VALID_ROW, "id": "u02", **change}
    path = tmp_path / "bad.jsonl"
    # ensure_ascii exercises escaped Unicode digits as well as literal digits.
    path.write_text(json.dumps(VALID_ROW) + "\n" + json.dumps(bad_row), encoding="utf-8")
    with pytest.raises(ValueError, match=rf"line 2: .*{reason}"):
        load_utterances(path)


@pytest.mark.parametrize(
    "bad_line, reason",
    [
        ("{", "Expecting"),
        ("", "Expecting"),
        ("null", "expected an object"),
        ("[]", "expected an object"),
        (json.dumps({key: value for key, value in VALID_ROW.items() if key != "order_id"}),
         "expected an object"),
        (json.dumps({**VALID_ROW, "speaker_name": "not allowed"}), "expected an object"),
        (json.dumps(VALID_ROW), "duplicate id"),
        ('{"id":"u02","id":"u03"}', "duplicate field"),
    ],
)
def test_invalid_json_shape_and_duplicate_ids(tmp_path, bad_line, reason):
    path = tmp_path / "invalid.jsonl"
    path.write_text(json.dumps(VALID_ROW) + "\n" + bad_line + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=rf"line 2: .*{reason}"):
        load_utterances(path)


def test_invalid_utf8_reports_line(tmp_path):
    path = tmp_path / "encoding.jsonl"
    path.write_bytes(json.dumps(VALID_ROW).encode() + b"\n\xff\n")
    with pytest.raises(ValueError, match="line 2:"):
        load_utterances(path)


def test_zero_eta_and_null_fields_are_valid(tmp_path):
    row = {**VALID_ROW, "intent": "delay", "order_id": None, "eta_minutes": 0}
    path = tmp_path / "zero.jsonl"
    path.write_text(json.dumps(row), encoding="utf-8")
    assert load_utterances(path) == [row]
