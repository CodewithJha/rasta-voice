"""API tests. The app always calls Gnani; here the HTTP transport is swapped
for ``httpx.MockTransport`` so CI runs with a dummy key and no network."""

from contextlib import nullcontext

import httpx
import pytest
from fastapi.testclient import TestClient

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.pipeline import SAMPLE_LINE

LINE = (
    "Bhaiya, gate band hai aur customer phone nahi utha raha. "
    "Order eighteen pe main das minute se khada hoon."
)


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
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_PROVIDER", "rules")
    return seen


@pytest.fixture
def client(calls) -> TestClient:
    return TestClient(app)


def test_health(client: TestClient):
    body = client.get("/api/health").json()
    assert body == {"ok": True, "gnani_key_set": True, "llm_provider": "rules"}


def test_upload_goes_to_prisma(client: TestClient, calls, make_wav):
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", make_wav(seconds=2.0), "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert [r.url.path for r in calls] == ["/stt/v3"]
    assert calls[0].headers["X-API-Key-ID"] == "test-key"
    assert b"transliterate" in calls[0].content
    assert body["stt"]["model"] == "prisma-v3.0"
    assert body["stt"]["request_id"] == "req-1"
    assert body["stt"]["audio_seconds"] == 2.0
    assert "mock" not in body["stt"]
    assert body["event"]["intent"] == "customer_unreachable"
    assert body["event"]["order_id"] == "18"
    assert body["event"]["eta_minutes"] == 10
    assert body["extractor_source"] == "rules"
    assert body["fallback_reason"] is None
    assert "extractor_source" not in body["event"]
    assert "fallback_reason" not in body["event"]


def test_sample_is_timbre_then_prisma(client: TestClient, calls):
    response = client.post("/api/ingest/sample")
    assert response.status_code == 200
    body = response.json()
    assert [r.url.path for r in calls] == ["/api/v1/tts/inference", "/stt/v3"]
    assert SAMPLE_LINE in calls[0].content.decode()
    assert body["sample_text"] == SAMPLE_LINE
    assert body["stt"]["audio_seconds"] == 1.0
    assert body["event"]["urgency"] == "high"


def test_empty_upload(client: TestClient):
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400


def test_missing_key_is_a_loud_503(monkeypatch: pytest.MonkeyPatch, make_wav):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    client = TestClient(app)
    assert client.get("/api/health").json()["gnani_key_set"] is False
    response = client.post(
        "/api/ingest", files={"audio_file": ("clip.wav", make_wav(), "audio/wav")}
    )
    assert response.status_code == 503
    assert "GNANI_API_KEY is not set" in response.json()["detail"]
    assert client.post("/api/ingest/sample").status_code == 503


def test_upstream_error_is_a_502(monkeypatch: pytest.MonkeyPatch, make_wav):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            402, json={"detail": {"error_code": "INSUFFICIENT_CREDIT", "message": "No credit"}}
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        PrismaSTT, "_http", lambda self: nullcontext(httpx.Client(transport=transport))
    )
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    response = TestClient(app).post(
        "/api/ingest", files={"audio_file": ("clip.wav", make_wav(), "audio/wav")}
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["upstream_status"] == 402
    assert "No credit" in detail["error"]


def test_missing_llm_key_still_ingests_with_rules(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from rasta.settings import clear_settings_cache

    clear_settings_cache()
    response = client.post("/api/ingest/sample")
    assert response.status_code == 200
    body = response.json()
    assert body["extractor_source"] == "rules"
    assert body["fallback_reason"] == "missing_api_key"
    assert body["event"]["intent"] == "customer_unreachable"
    assert "extractor_source" not in body["event"]
