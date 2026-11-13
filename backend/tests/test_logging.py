"""Request IDs and JSON Gnani logs (issue 21)."""

from __future__ import annotations

import json
import logging
from contextlib import nullcontext

import httpx
import pytest
from fastapi.testclient import TestClient

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.pipeline import SAMPLE_LINE
from rasta.request_id import (
    REQUEST_ID_HEADER,
    JsonLogFormatter,
    current_request_id,
    log_gnani_call,
    resolve_request_id,
)
from rasta.settings import SettingsError, clear_settings_cache, get_settings
from rasta.store import attach_event_store

LINE = (
    "Bhaiya, gate band hai aur customer phone nahi utha raha. "
    "Order eighteen pe main das minute se khada hoon."
)
TEST_KEY = "test-key"


@pytest.fixture(autouse=True)
def _reset_settings():
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, make_wav) -> list[httpx.Request]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/api/v1/tts/inference":
            return httpx.Response(200, content=make_wav(seconds=1.0, rate=16000))
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req-1",
                "transcript": LINE,
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
    monkeypatch.setenv("GNANI_API_KEY", TEST_KEY)
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    return seen


@pytest.fixture
def client(calls) -> TestClient:
    return TestClient(app)


def _header(response, name: str = REQUEST_ID_HEADER) -> str:
    return response.headers[name]


def test_safe_incoming_request_id_is_kept():
    assert resolve_request_id("demo-42_ok.ID") == "demo-42_ok.ID"
    assert resolve_request_id("  abc  ") == "abc"


@pytest.mark.parametrize(
    "raw",
    ["", "has a space", "bad\nid", "not/slash", "x" * 129, "id with\r"],
)
def test_unsafe_request_id_is_replaced(raw: str):
    minted = resolve_request_id(raw)
    assert minted != raw.strip()
    assert resolve_request_id(minted) == minted


def test_health_returns_request_id(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert _header(response)
    echoed = client.get("/api/health", headers={REQUEST_ID_HEADER: "judge-ticket-1"})
    assert echoed.status_code == 200
    assert _header(echoed) == "judge-ticket-1"
    unsafe = client.get("/api/health", headers={REQUEST_ID_HEADER: "bad id\n"})
    assert unsafe.status_code == 200
    assert _header(unsafe) != "bad id\n"
    assert "\n" not in _header(unsafe)


def test_ingest_success_and_errors_echo_request_id(
    client: TestClient, make_wav, monkeypatch: pytest.MonkeyPatch
):
    ok = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=2.0), "audio/wav")},
        headers={REQUEST_ID_HEADER: "ingest-ok-1"},
    )
    assert ok.status_code == 200
    assert _header(ok) == "ingest-ok-1"

    empty = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", b"", "audio/wav")},
        headers={REQUEST_ID_HEADER: "ingest-empty-1"},
    )
    assert empty.status_code == 400
    assert _header(empty) == "ingest-empty-1"

    huge = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=2.0) + b"x" * 2_000_001, "audio/wav")},
        headers={REQUEST_ID_HEADER: "ingest-huge-1"},
    )
    assert huge.status_code == 413
    assert _header(huge) == "ingest-huge-1"

    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    missing = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=2.0), "audio/wav")},
        headers={REQUEST_ID_HEADER: "ingest-nokey-1"},
    )
    assert missing.status_code == 503
    assert _header(missing) == "ingest-nokey-1"


def test_upstream_error_still_has_request_id(monkeypatch: pytest.MonkeyPatch, make_wav):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402, json={"detail": {"error_code": "INSUFFICIENT_CREDIT", "message": "No credit"}}
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        PrismaSTT, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
    )
    monkeypatch.setenv("GNANI_API_KEY", TEST_KEY)
    with TestClient(app) as client:
        attach_event_store(app, replace=True)
        response = client.post(
            "/api/ingest",
            files={"audio_file": ("clip.wav", make_wav(seconds=1.0), "audio/wav")},
            headers={REQUEST_ID_HEADER: "ingest-402-1"},
        )
        assert response.status_code == 502
        assert _header(response) == "ingest-402-1"


def test_sample_ingest_logs_one_line_per_gnani_call(client: TestClient, caplog):
    caplog.set_level(logging.INFO, logger="rasta")
    response = client.post(
        "/api/ingest/sample", headers={REQUEST_ID_HEADER: "sample-log-1"}
    )
    assert response.status_code == 200
    assert _header(response) == "sample-log-1"
    body = response.json()
    records = [record for record in caplog.records if record.getMessage() == "gnani_call"]
    by_endpoint = {record.endpoint: record for record in records}
    assert set(by_endpoint) == {"tts_inference", "stt_rest"}
    tts = by_endpoint["tts_inference"]
    stt = by_endpoint["stt_rest"]
    assert tts.request_id == "sample-log-1"
    assert stt.request_id == "sample-log-1"
    assert tts.status == 200
    assert stt.status == 200
    assert stt.gnani_request_id == "req-1"
    assert body["ingest"]["stt"]["request_id"] == "req-1"
    assert stt.audio_seconds is not None
    assert tts.audio_seconds is not None
    assert tts.latency_ms >= 0
    assert stt.latency_ms >= 0
    formatter = JsonLogFormatter()
    for record in (tts, stt):
        line = formatter.format(record)
        payload = json.loads(line)
        assert payload["request_id"] == "sample-log-1"
        assert payload["endpoint"] in {"tts_inference", "stt_rest"}
        assert TEST_KEY not in line
        assert "GNANI_API_KEY" not in line
        assert SAMPLE_LINE not in line
        assert LINE not in line
        assert "RIFF" not in line
        assert body["audio_base64"] not in line


def test_formatter_keeps_unknown_extra_keys():
    record = logging.LogRecord(
        name="rasta",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="gnani_call",
        args=(),
        exc_info=None,
    )
    record.request_id = "same-id"
    record.endpoint = "stt_rest"
    record.attempt = 2
    record.gnani_request_id = None
    record.latency_ms = 10
    record.status = 200
    record.audio_seconds = None
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["attempt"] == 2
    assert payload["request_id"] == "same-id"
    assert payload["endpoint"] == "stt_rest"


def test_formatter_bounds_line_size_and_stays_json(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_LOG_LINE_MAX_BYTES", "200")
    clear_settings_cache()
    assert get_settings().log_line_max_bytes == 200
    record = logging.LogRecord(
        name="rasta",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="gnani_call",
        args=(),
        exc_info=None,
    )
    record.request_id = "bound-1"
    record.note = "n" * 400
    line = JsonLogFormatter().format(record)
    assert len(line.encode("utf-8")) <= 200
    payload = json.loads(line)
    assert payload["truncated"] is True
    assert payload["request_id"] == "bound-1"
    assert "n" * 400 not in line


def test_log_gnani_call_does_not_store_redacted_extras(caplog):
    caplog.set_level(logging.INFO, logger="rasta")
    log_gnani_call(
        endpoint="stt_rest",
        latency_ms=1,
        status=200,
        transcript=LINE,
        api_key=TEST_KEY,
        attempt=1,
    )
    record = [item for item in caplog.records if item.getMessage() == "gnani_call"][-1]
    line = JsonLogFormatter().format(record)
    assert LINE not in line
    assert TEST_KEY not in line
    payload = json.loads(line)
    assert payload["attempt"] == 1
    assert "transcript" not in payload
    assert "api_key" not in payload


def test_log_line_cap_rejects_invalid(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RASTA_LOG_LINE_MAX_BYTES", "0")
    clear_settings_cache()
    with pytest.raises(SettingsError, match="RASTA_LOG_LINE_MAX_BYTES"):
        get_settings()


def test_current_request_id_is_unbound_outside_a_request():
    assert current_request_id() is None
