import pytest
from fastapi.testclient import TestClient

from gnani_client.wav import tone_wav
from rasta.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("GNANI_MOCK", "1")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    return TestClient(app)


def test_health(client: TestClient):
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["stt_mock"] is True
    assert body["llm_provider"] == "mock"


def test_upload_returns_an_event(client: TestClient):
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", tone_wav(), "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["stt"]["mock"] is True
    assert body["stt"]["model"] == "prisma-v3.0"
    assert body["event"]["intent"] == "customer_unreachable"
    assert body["event"]["order_id"] == "18"


def test_sample_clip(client: TestClient):
    response = client.post("/api/ingest/sample")
    assert response.status_code == 200
    assert response.json()["event"]["urgency"] == "high"


def test_empty_upload(client: TestClient):
    response = client.post(
        "/api/ingest",
        files={"audio_file": ("clip.wav", b"", "audio/wav")},
    )
    assert response.status_code == 400


def test_sample_refuses_live_mode(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GNANI_MOCK", "0")
    monkeypatch.setenv("GNANI_API_KEY", "not-used")
    response = TestClient(app).post("/api/ingest/sample")
    assert response.status_code == 409


def test_unwired_llm_is_501(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GNANI_MOCK", "1")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    response = TestClient(app).post("/api/ingest/sample")
    assert response.status_code == 501
