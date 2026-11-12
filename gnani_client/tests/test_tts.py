import json

import httpx
import pytest

from gnani_client.errors import GnaniError, MissingApiKeyError
from gnani_client.tts import AUDIO_TAGS, TimbreTTS
from gnani_client.wav import wav_duration_seconds


def test_tag_catalog_matches_the_docs():
    assert "clears throat" in AUDIO_TAGS
    assert "whispers" in AUDIO_TAGS
    assert "pauses" in AUDIO_TAGS
    assert len(AUDIO_TAGS) == 13


def test_missing_key_fails_loudly(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        TimbreTTS()


def test_tts_error_is_raised_with_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"success": False, "message": "Model 'x' is not supported", "status_code": 400},
        )

    client = TimbreTTS(key="k", client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(GnaniError, match="400: Model 'x' is not supported") as info:
        client.synthesize("order aa gaya")
    assert info.value.status == 400


def test_duration_survives_a_streaming_header(make_wav):
    audio = bytearray(make_wav(seconds=1.0, rate=16000))
    assert wav_duration_seconds(bytes(audio)) == 1.0
    audio[4:8] = b"\xff\xff\xff\xff"
    data_at = audio.index(b"data")
    audio[data_at + 4 : data_at + 8] = b"\xff\xff\xff\xff"
    assert wav_duration_seconds(bytes(audio)) == 1.0
    assert wav_duration_seconds(b"not a wav") is None


def test_live_body_matches_the_docs(make_wav):
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["X-API-Key-ID"]
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, content=make_wav(), headers={"content-type": "audio/wav"})

    client = TimbreTTS(
        key="test-key",
        base="https://api.vachana.ai",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    audio = client.synthesize("order aa gaya <excited> bahut badhiya")
    assert audio.startswith(b"RIFF")
    assert seen["url"] == "https://api.vachana.ai/api/v1/tts/inference"
    assert seen["key"] == "test-key"
    body = seen["json"]
    assert isinstance(body, dict)
    assert body["model"] == "timbre-v3.0"
    assert body["voice"] == "Shivani"
    assert body["language"] == "hi-en"
    assert body["text"] == "order aa gaya <excited> bahut badhiya"
    assert body["audio_config"]["container"] == "wav"


def test_empty_text_rejected():
    with pytest.raises(ValueError):
        TimbreTTS(key="k").synthesize("   ")
