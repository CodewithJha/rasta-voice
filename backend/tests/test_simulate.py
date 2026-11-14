"""Clean/noisy simulate path. Prisma and Timbre transports are swapped as in
``test_ingest.py``; CI needs no Gnani key."""

from __future__ import annotations

import base64
import io
import struct
import wave
from contextlib import nullcontext

import httpx
import pytest
from fastapi.testclient import TestClient

from gnani_client.stt import PrismaSTT
from gnani_client.tts import TimbreTTS
from rasta.main import app
from rasta.pipeline import MAX_CLIP_BYTES, SAMPLE_LINE
from rasta.simulate import PHONE_RATE, prepare_for_ingest, read_pcm, write_wav

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


def _posted_wav(request: httpx.Request) -> bytes:
    start = request.content.find(b"RIFF")
    assert start != -1
    size = struct.unpack_from("<I", request.content, start + 4)[0]
    return request.content[start : start + 8 + size]


def _inspect(blob: bytes) -> tuple[int, int, int]:
    with wave.open(io.BytesIO(blob), "rb") as handle:
        return handle.getframerate(), handle.getnframes(), handle.getnchannels()


def test_noisy_simulate_sends_8khz_wav_to_prisma(client: TestClient, calls, make_wav):
    source = make_wav(seconds=0.4, rate=16000)
    response = client.post(
        "/api/simulate",
        params={"condition": "noisy"},
        files={"audio_file": ("clip.wav", source, "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["condition"] == "noisy"
    wav = base64.b64decode(body["audio_base64"])
    rate, frames, channels = _inspect(wav)
    assert rate == PHONE_RATE
    assert channels == 1
    assert frames == 3200  # 0.4s at 16 kHz, averaged in pairs
    assert [r.url.path for r in calls] == ["/stt/v3"]
    posted = _posted_wav(calls[0])
    assert posted == wav
    assert _inspect(posted)[0] == PHONE_RATE
    assert body["ingest"]["event"]["intent"] == "customer_unreachable"
    assert body["ingest"]["event"]["order_id"] == "18"


def test_clean_simulate_keeps_sample_count(client: TestClient, calls, make_wav):
    source = make_wav(seconds=0.4, rate=16000)
    source_samples, source_rate = read_pcm(source)
    response = client.post(
        "/api/simulate",
        params={"condition": "clean"},
        files={"audio_file": ("clip.wav", source, "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["condition"] == "clean"
    wav = base64.b64decode(body["audio_base64"])
    rate, frames, channels = _inspect(wav)
    assert rate == source_rate
    assert channels == 1
    assert frames == len(source_samples)
    assert _posted_wav(calls[0]) == wav


def test_noisy_is_deterministic(client: TestClient, make_wav):
    source = make_wav(seconds=0.3, rate=16000)
    first = client.post(
        "/api/simulate",
        params={"condition": "noisy"},
        files={"audio_file": ("clip.wav", source, "audio/wav")},
    ).json()["audio_base64"]
    second = client.post(
        "/api/simulate",
        params={"condition": "noisy"},
        files={"audio_file": ("clip.wav", source, "audio/wav")},
    ).json()["audio_base64"]
    assert first == second
    assert (
        first
        != client.post(
            "/api/simulate",
            params={"condition": "clean"},
            files={"audio_file": ("clip.wav", source, "audio/wav")},
        ).json()["audio_base64"]
    )


def test_bad_condition_is_400_and_skips_prisma(client: TestClient, calls, make_wav):
    response = client.post(
        "/api/simulate",
        params={"condition": "crushed"},
        files={"audio_file": ("clip.wav", make_wav(), "audio/wav")},
    )
    assert response.status_code == 400
    assert "clean or noisy" in response.json()["error"]["message"]
    assert calls == []


def test_bad_container_is_415_and_simulator_bad_rate_is_400(client: TestClient, calls, make_wav):
    mp3 = client.post(
        "/api/simulate",
        params={"condition": "clean"},
        files={"audio_file": ("clip.mp3", b"ID3fake", "audio/mpeg")},
    )
    assert mp3.status_code == 415
    assert mp3.json()["error"]["code"] == "unsupported_media_type"
    odd = client.post(
        "/api/simulate",
        params={"condition": "noisy"},
        files={"audio_file": ("clip.wav", make_wav(seconds=0.2, rate=44100), "audio/wav")},
    )
    assert odd.status_code == 400
    assert "8000" in odd.json()["error"]["message"]
    assert calls == []


def test_already_8khz_noisy_keeps_frame_count(client: TestClient, make_wav):
    source = make_wav(seconds=0.25, rate=8000)
    samples, _rate = read_pcm(source)
    body = client.post(
        "/api/simulate",
        params={"condition": "noisy"},
        files={"audio_file": ("clip.wav", source, "audio/wav")},
    ).json()
    wav = base64.b64decode(body["audio_base64"])
    rate, frames, _channels = _inspect(wav)
    assert rate == PHONE_RATE
    assert frames == len(samples)


def test_placeholder_header_clean_rewrites_wav(client: TestClient, make_wav):
    source = bytearray(make_wav(seconds=0.2, rate=16000))
    # Timbre-style streaming sizes: walk to the data chunk and stamp 0xFFFFFFFF.
    source[4:8] = struct.pack("<I", 0xFFFFFFFF)
    pos = 12
    while pos + 8 <= len(source):
        chunk = bytes(source[pos : pos + 4])
        size = struct.unpack_from("<I", source, pos + 4)[0]
        if chunk == b"data":
            source[pos + 4 : pos + 8] = struct.pack("<I", 0xFFFFFFFF)
            break
        pos = pos + 8 + size + (size & 1)
    body = client.post(
        "/api/simulate",
        params={"condition": "clean"},
        files={"audio_file": ("clip.wav", bytes(source), "audio/wav")},
    ).json()
    wav = base64.b64decode(body["audio_base64"])
    rate, frames, _channels = _inspect(wav)
    assert rate == 16000
    assert frames == 3200


def test_sample_noisy_dirties_before_prisma(client: TestClient, calls):
    response = client.post("/api/ingest/sample", params={"condition": "noisy"})
    assert response.status_code == 200
    body = response.json()
    assert body["condition"] == "noisy"
    assert body["ingest"]["sample_text"] == SAMPLE_LINE
    assert [r.url.path for r in calls] == ["/api/v1/tts/inference", "/stt/v3"]
    posted = _posted_wav(calls[1])
    assert posted == base64.b64decode(body["audio_base64"])
    assert _inspect(posted)[0] == PHONE_RATE
    # Duration is preserved: 1 s at 16 kHz becomes 1 s at 8 kHz.
    assert body["ingest"]["stt"]["audio_seconds"] == 1.0


def test_sample_bad_condition_skips_timbre(client: TestClient, calls):
    response = client.post("/api/ingest/sample", params={"condition": "muddy"})
    assert response.status_code == 400
    assert calls == []


def test_write_roundtrip_matches_read(make_wav):
    source = make_wav(seconds=0.15, rate=16000)
    samples, rate = read_pcm(source)
    again, rate_again = read_pcm(write_wav(samples, rate))
    assert again == samples
    assert rate_again == rate


def _wav_of_size(size: int, rate: int = 16000) -> bytes:
    """A valid mono 16-bit WAV whose exact file size is ``size`` bytes."""
    if size < 44 or size % 2:
        raise ValueError("size must be an even WAV length of at least one header")
    samples = [0] * ((size - 44) // 2)
    blob = write_wav(samples, rate)
    if len(blob) != size:
        raise AssertionError(f"expected {size} bytes, wrote {len(blob)}")
    return blob


def test_oversize_upload_skips_prepare_and_prisma(client: TestClient, calls, monkeypatch):
    seen: list[bytes] = []

    def spy(audio: bytes, condition: str) -> bytes:
        seen.append(audio)
        return prepare_for_ingest(audio, condition)

    monkeypatch.setattr("rasta.routes_sim.prepare_for_ingest", spy)
    oversized = _wav_of_size(MAX_CLIP_BYTES + 44)  # 2,000,044 bytes, valid header
    assert len(oversized) > MAX_CLIP_BYTES
    response = client.post(
        "/api/simulate",
        params={"condition": "noisy"},
        files={"audio_file": ("clip.wav", oversized, "audio/wav")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert seen == []
    assert calls == []


def test_clip_at_byte_limit_still_obeys_thirty_second_duration_limit(
    client: TestClient, calls, monkeypatch
):
    seen: list[int] = []
    monkeypatch.setattr(
        "rasta.routes_sim.prepare_for_ingest",
        lambda audio, condition: seen.append(len(audio)) or write_wav([0], 8000),
    )
    # ingest still runs after prepare; keep Prisma mocked via ``calls``.
    # Byte size alone is insufficient: this 16 kHz mono clip is over 30 seconds.
    at_limit = _wav_of_size(MAX_CLIP_BYTES)
    response = client.post(
        "/api/simulate",
        params={"condition": "clean"},
        files={"audio_file": ("clip.wav", at_limit, "audio/wav")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"
    assert seen == []
    assert calls == []
