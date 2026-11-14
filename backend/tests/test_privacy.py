"""Privacy: redaction, TTL, deletion, wipe, and no audio-on-disk (issue 28)."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.redact import MIN_DIGIT_RUN, REDACTION_PLACEHOLDER, redact_record, redact_text
from rasta.settings import (
    DEFAULT_EVENT_TTL_HOURS,
    MAX_EVENT_TTL_HOURS,
    SettingsError,
    clear_settings_cache,
    get_settings,
)
from rasta.store import ACCIDENT_SOS_INTENT, WIPE_CONFIRM, EventStore

PHONE = "9876543210"
TEST_DESK_PASSCODE = "desk-test-passphrase-9f3"
DESK_HEADERS = {"X-Dispatch-Passcode": TEST_DESK_PASSCODE}

# Speech modules that must not persist wav files.
_SPEECH_MODULES = (
    "backend/rasta/pipeline.py",
    "backend/rasta/simulate.py",
    "backend/rasta/routes_reply.py",
    "backend/rasta/routes_sim.py",
    "backend/rasta/main.py",
    "backend/rasta/stream_session.py",
)


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture(autouse=True)
def _desk_passcode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISPATCH_PASSCODE", TEST_DESK_PASSCODE)
    clear_settings_cache()
    yield
    clear_settings_cache()


def _payload(
    transcript: str,
    *,
    intent: str = "other",
    order_id: str | None = "18",
    **extra,
) -> dict:
    body = {
        "transcript": transcript,
        "stt": {"model": "prisma-v3.0", "request_id": "req-1"},
        "event": {
            "intent": intent,
            "order_id": order_id,
            "transcript": transcript,
        },
    }
    body.update(extra)
    return body


def test_redact_text_masks_digit_runs_and_indian_mobiles_but_keeps_order_tokens():
    assert MIN_DIGIT_RUN == 8
    line = f"order 18 mein call {PHONE} or +91 98765 43210 please"
    redacted = redact_text(line)
    assert PHONE not in redacted
    assert "98765 43210" not in redacted
    assert "+91" not in redacted
    assert "order 18" in redacted
    assert redacted.count(REDACTION_PLACEHOLDER) >= 2


def test_eight_digit_run_is_redacted_and_short_tokens_are_not():
    assert redact_text("pin 12345678 and order eighteen") == (
        f"pin {REDACTION_PLACEHOLDER} and order eighteen"
    )
    assert redact_text("order 18") == "order 18"


def test_contiguous_digit_runs_are_masked_as_a_whole():
    long_run = "123456789012345678"
    assert redact_text(f"id {long_run}") == f"id {REDACTION_PLACEHOLDER}"
    assert long_run not in redact_text(f"id {long_run}")
    assert "12345" not in redact_text(f"id {long_run}")
    assert redact_text(long_run) == REDACTION_PLACEHOLDER


def test_country_prefixes_are_consumed_with_the_digit_run():
    assert redact_text("+919876543210") == REDACTION_PLACEHOLDER
    assert redact_text("919876543210") == REDACTION_PLACEHOLDER
    assert redact_text("+91 98765 43210") == REDACTION_PLACEHOLDER
    assert redact_text("91-98765-43210") == REDACTION_PLACEHOLDER
    assert "+91" not in redact_text("reach me at +919876543210 today")
    assert "98765" not in redact_text("reach me at +91 98765 43210 today")


def test_redact_record_covers_transcript_fields_only():
    record = redact_record(
        {
            "transcript": f"call {PHONE}",
            "sample_text": f"+91{PHONE}",
            "event": {"intent": "other", "order_id": "18", "transcript": PHONE},
            "stt": {"request_id": "req-1"},
        }
    )
    assert record["transcript"] == f"call {REDACTION_PLACEHOLDER}"
    assert record["sample_text"] == REDACTION_PLACEHOLDER
    assert record["event"]["transcript"] == REDACTION_PLACEHOLDER
    assert record["event"]["order_id"] == "18"
    assert PHONE not in str(record)


def test_append_and_list_never_expose_a_phone_and_keep_order_18():
    store = EventStore(capacity=10, path=":memory:")
    try:
        stored = store.append(_payload(f"order 18, meri number {PHONE} hai"))
        assert stored["event"]["order_id"] == "18"
        assert PHONE not in stored["transcript"]
        assert PHONE not in stored["event"]["transcript"]
        listed = store.list_since(None)
        assert listed[0]["id"] == stored["id"]
        assert PHONE not in str(listed)
        assert listed[0]["event"]["order_id"] == "18"
    finally:
        store.close()


def test_zero_ttl_hides_a_row_and_purge_removes_it():
    store = EventStore(capacity=10, path=":memory:", ttl_hours=0)
    try:
        stored = store.append(_payload("order 18"))
        assert store.list_since(None) == []
        assert store.get(stored["id"]) is None
        assert store.purge_expired() == [stored["id"]]
        assert store.delete(stored["id"]) is False
    finally:
        store.close()


def test_patched_clock_expires_a_row_after_the_ttl():
    clock = {"now": datetime(2026, 11, 14, tzinfo=UTC)}

    def now() -> datetime:
        return clock["now"]

    store = EventStore(capacity=10, path=":memory:", clock=now, ttl_hours=24)
    try:
        stored = store.append(_payload("order 18"))
        assert store.list_since(None)[0]["id"] == stored["id"]
        clock["now"] = clock["now"] + timedelta(hours=24)
        assert store.list_since(None) == []
        assert store.purge_expired() == [stored["id"]]
    finally:
        store.close()


def test_export_omits_expired_rows_before_the_sweeper_runs(tmp_path):
    clock = {"now": datetime(2026, 11, 14, tzinfo=UTC)}

    def now() -> datetime:
        return clock["now"]

    store = EventStore(capacity=10, path=str(tmp_path / "live.sqlite"), clock=now, ttl_hours=1)
    try:
        stored = store.append(_payload(f"order 18, call {PHONE}"))
        clock["now"] = clock["now"] + timedelta(hours=2)
        assert store.list_since(None) == []
        assert store.get(stored["id"]) is None
        dest = tmp_path / "export.sqlite"
        store.export_copy(dest)
        # The sweeper has not run; the live file may still hold the row,
        # but the snapshot must not.
        with sqlite3.connect(dest) as connection:
            count = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
            payloads = [row[0] for row in connection.execute("SELECT payload FROM events")]
        assert count == 0
        assert payloads == []
        assert PHONE not in dest.read_bytes().decode("utf-8", errors="ignore")
    finally:
        store.close()


def test_delete_wipe_and_ttl_remove_audit_details(tmp_path):
    clock = {"now": datetime(2026, 11, 14, tzinfo=UTC)}

    def now() -> datetime:
        return clock["now"]

    store = EventStore(
        capacity=10, path=str(tmp_path / "desk.sqlite"), clock=now, ttl_hours=1
    )
    try:
        first = store.append(_payload("first"))
        second = store.append(_payload("second"))
        assert store.list_audit(first["id"])
        details = [str(item["detail"]) for item in store.list_audit(first["id"])]
        assert all("transcript" not in detail for detail in details)
        assert store.delete(first["id"]) is True
        assert store.list_audit(first["id"]) == []
        assert store.list_audit(second["id"])
        store.wipe()
        assert store.list_since(None) == []
        assert store.list_audit(second["id"]) == []

        again = store.append(_payload("ttl"))
        assert store.list_audit(again["id"])
        clock["now"] = clock["now"] + timedelta(hours=2)
        dest = tmp_path / "export.sqlite"
        store.export_copy(dest)
        with sqlite3.connect(dest) as connection:
            events = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
            audits = int(connection.execute("SELECT COUNT(*) FROM audit").fetchone()[0])
        assert events == 0 and audits == 0
        assert store.purge_expired() == [again["id"]]
        assert store.list_audit(again["id"]) == []
    finally:
        store.close()


def test_delete_removes_a_row_and_wipe_clears_the_desk():
    store = EventStore(capacity=10, path=":memory:")
    try:
        first = store.append(_payload("first"))
        second = store.append(_payload("second"))
        assert store.delete(first["id"]) is True
        ids = [row["id"] for row in store.list_since(None)]
        assert ids == [second["id"]]
        assert store.wipe() == 1
        assert store.list_since(None) == []
    finally:
        store.close()


def test_capacity_prefers_resolved_rows_and_logs_live_sos_eviction(caplog):
    store = EventStore(capacity=2, path=":memory:")
    try:
        sos = store.append(
            _payload("sos", intent=ACCIDENT_SOS_INTENT, state="new")
        )
        resolved = store.append(
            _payload("done", intent="other", state="resolved")
        )
        caplog.set_level(logging.INFO, logger="rasta")
        later = store.append(_payload("third"))
        ids = {row["id"] for row in store.list_since(None)}
        assert resolved["id"] not in ids
        assert sos["id"] in ids and later["id"] in ids
        tight = EventStore(capacity=1, path=":memory:")
        try:
            caplog.clear()
            tight.append(
                _payload(f"help {PHONE}", intent=ACCIDENT_SOS_INTENT, state="escalated")
            )
            tight.append(_payload("next"))
            text = caplog.text
            assert "action=evicted" in text
            assert PHONE not in text
            assert "help " not in text
        finally:
            tight.close()
    finally:
        store.close()


def test_historical_rows_are_redacted_on_open(tmp_path):
    path = str(tmp_path / "desk.sqlite")
    first = EventStore(capacity=10, path=path)
    try:
        stored = first.append(_payload("clean"))
        # Simulate a pre-redaction row still on disk.
        import json

        raw = {
            "id": stored["id"],
            "created_at": stored["created_at"],
            "transcript": f"old {PHONE}",
            "event": {"intent": "other", "order_id": "18", "transcript": PHONE},
        }
        with sqlite3.connect(path) as connection:
            connection.execute(
                "UPDATE events SET payload = ? WHERE id = ?",
                (json.dumps(raw), stored["id"]),
            )
            connection.commit()
    finally:
        first.close()
    again = EventStore(capacity=10, path=path)
    try:
        listed = again.list_since(None)
        assert PHONE not in str(listed)
        assert listed[0]["event"]["order_id"] == "18"
    finally:
        again.close()


def test_ttl_settings_default_and_reject_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RASTA_EVENT_TTL_HOURS", raising=False)
    clear_settings_cache()
    assert get_settings().event_ttl_hours == DEFAULT_EVENT_TTL_HOURS
    monkeypatch.setenv("RASTA_EVENT_TTL_HOURS", "0")
    clear_settings_cache()
    assert get_settings().event_ttl_hours == 0
    monkeypatch.setenv("RASTA_EVENT_TTL_HOURS", "-1")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="RASTA_EVENT_TTL_HOURS"):
        get_settings()
    monkeypatch.setenv("RASTA_EVENT_TTL_HOURS", str(MAX_EVENT_TTL_HOURS + 1))
    clear_settings_cache()
    with pytest.raises(SettingsError, match="RASTA_EVENT_TTL_HOURS"):
        get_settings()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, make_wav) -> dict:
    state = {"transcript": f"Order 18, call me on {PHONE}"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/tts/inference":
            return httpx.Response(200, content=make_wav(seconds=1.0, rate=16000))
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req-privacy",
                "transcript": state["transcript"],
                "model": "prisma-v3.0",
                "detected_language_code": "hi-IN",
                "processing_time": 0.2,
            },
        )

    transport = httpx.MockTransport(handler)
    for cls in (PrismaSTT, TimbreTTS):
        monkeypatch.setattr(
            cls, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
        )
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    return state


@pytest.fixture
def client(calls) -> TestClient:
    with TestClient(app, headers=DESK_HEADERS) as test_client:
        yield test_client


def test_ingest_redacts_phone_and_keeps_order_18(client: TestClient, make_wav):
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["order_id"] == "18"
    assert PHONE not in response.text
    listed = client.get("/api/events")
    assert listed.status_code == 200
    assert PHONE not in listed.text
    assert listed.json()["events"][0]["event"]["order_id"] == "18"


def test_delete_and_wipe_are_passcode_protected_and_wipe_needs_confirm(
    client: TestClient, make_wav
):
    created = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
    )
    event_id = created.json()["id"]
    bare = TestClient(app)
    denied = bare.delete(f"/api/events/{event_id}")
    assert denied.status_code in {401, 503}
    assert PHONE not in denied.text
    assert TEST_DESK_PASSCODE not in denied.text
    missing = client.delete("/api/events/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404
    deleted = client.delete(f"/api/events/{event_id}")
    assert deleted.status_code == 204
    assert event_id not in {row["id"] for row in client.get("/api/events").json()["events"]}

    client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
    )
    assert bare.post("/api/admin/wipe", json={"confirm": WIPE_CONFIRM}).status_code in {
        401,
        503,
    }
    bad = client.post("/api/admin/wipe", json={"confirm": "nope"})
    assert bad.status_code == 422
    assert "nope" not in bad.text
    empty = client.get("/api/events")
    assert empty.json()["events"]
    wiped = client.post("/api/admin/wipe", json={"confirm": WIPE_CONFIRM})
    assert wiped.status_code == 204
    assert client.get("/api/events").json()["events"] == []


def test_speech_paths_do_not_write_wav_files(tmp_path, monkeypatch, make_wav):
    root = Path(__file__).resolve().parents[2]
    forbidden = []
    for relative in _SPEECH_MODULES:
        text = (root / relative).read_text()
        if "benchmark/data" in text:
            forbidden.append(f"{relative} mentions benchmark/data")
        if 'open("' in text and ".wav" in text and "wb" in text:
            # Allow documented in-memory wave.open(buf, "wb") only.
            if "wave.open(buf, \"wb\")" not in text and "wave.open(buf, 'wb')" not in text:
                forbidden.append(f"{relative} looks like a wav write")
    assert forbidden == []

    monkeypatch.chdir(tmp_path)
    (tmp_path / "benchmark" / "data").mkdir(parents=True)
    from rasta.simulate import write_wav

    payload = write_wav([0] * 160, 8000)
    assert payload[:4] == b"RIFF"
    leftover = [path for path in tmp_path.rglob("*") if path.is_file() and path.suffix == ".wav"]
    assert leftover == []
