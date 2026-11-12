import json

import httpx

from gnani_client.tts import AUDIO_TAGS, TimbreTTS
from gnani_client.wav import tone_wav


def test_tag_catalog_matches_the_docs():
    assert "clears throat" in AUDIO_TAGS
    assert "whispers" in AUDIO_TAGS
    assert "pauses" in AUDIO_TAGS
    assert len(AUDIO_TAGS) == 13


def test_mock_returns_a_wav():
    audio = TimbreTTS(key="", mock=True).synthesize("gate band hai <whispers> order 18")
    assert audio.startswith(b"RIFF")
    assert b"WAVE" in audio[:16]


def test_live_body_matches_the_docs():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["X-API-Key-ID"]
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, content=tone_wav(), headers={"content-type": "audio/wav"})

    client = TimbreTTS(
        key="test-key",
        mock=False,
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
    try:
        TimbreTTS(key="", mock=True).synthesize("   ")
    except ValueError:
        return
    raise AssertionError("expected ValueError")
