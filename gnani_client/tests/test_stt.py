import json

import httpx
import pytest

from gnani_client.errors import GnaniError, MissingApiKeyError
from gnani_client.stt import PrismaSTT, stream_headers


def test_missing_key_fails_loudly(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError, match="GNANI_API_KEY is not set"):
        PrismaSTT()
    with pytest.raises(MissingApiKeyError):
        PrismaSTT(key="   ")


def test_key_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GNANI_API_KEY", " env-key ")
    assert PrismaSTT().api_key == "env-key"


def test_rest_request_matches_the_docs():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["X-API-Key-ID"]
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req-1",
                "transcript": "order 4 mein ek item missing",
                "model": "prisma-v3.0",
                "detected_language_code": "hi-IN",
                "processing_time": 0.2,
            },
        )

    client = PrismaSTT(
        key="test-key",
        base="https://api.vachana.ai",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = client.transcribe(
        b"RIFFfake",
        filename="clip.wav",
        keyterms=["order", "item"],
        topic="delivery rider",
    )
    assert seen["url"] == "https://api.vachana.ai/stt/v3"
    assert seen["key"] == "test-key"
    body = seen["body"]
    assert isinstance(body, bytes)
    assert b"prisma-v3.0" in body
    assert b"hi-IN,en-IN" in body
    assert b"codemix" in body
    assert b"order" in body
    assert result.transcript == "order 4 mein ek item missing"
    assert result.request_id == "req-1"


def test_rest_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"success": False, "error": {"type": "INVALID_CONTEXT", "message": "too long"}},
        )

    client = PrismaSTT(
        key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(GnaniError, match="INVALID_CONTEXT: too long") as info:
        client.transcribe(b"RIFFfake")
    assert info.value.status == 400


def test_auth_error_shape_is_readable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"detail": {"error_code": "INVALID_API_KEY", "message": "Unauthorized"}},
        )

    client = PrismaSTT(key="bad", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(GnaniError, match="401: INVALID_API_KEY: Unauthorized") as info:
        client.transcribe(b"RIFFfake")
    assert info.value.status == 401


def test_telephony_stream_headers():
    headers = stream_headers(api_key="k", keyterms=["gate"], preset="telephony")
    assert headers["x-api-key-id"] == "k"
    assert headers["model"] == "prisma-v3.0"
    assert headers["x-sample-rate"] == "8000"
    assert headers["x-vad-threshold"] == "0.7"
    assert json.loads(headers["keyterms"]) == ["gate"]
    assert headers["format"] == "codemix"


def test_stream_url():
    client = PrismaSTT(key="k", base="https://api.vachana.ai")
    assert client.stream_url == "wss://api.vachana.ai/stt/v3/stream"
