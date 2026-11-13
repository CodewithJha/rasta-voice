"""Exercise actual multipart parsing, raw limits, media metadata and cleanup."""

import asyncio
import io
import wave
from pathlib import Path

import pytest
from fastapi import APIRouter, File, UploadFile
from fastapi.testclient import TestClient
from starlette import formparsers

from rasta.pipeline import MAX_CLIP_BYTES
from rasta.security import SecuredApp
from rasta.settings import clear_settings_cache
from rasta.upload_security import (
    MAX_REQUEST_BYTES,
    AudioUploadRoute,
    UploadBodyLimit,
    UploadRejected,
    validate_audio,
)

FIXTURES = Path(__file__).parent / "fixtures" / "upload-security"


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    monkeypatch.setenv("RASTA_ENV", "development")
    clear_settings_cache()
    yield
    clear_settings_cache()


def pcm(seconds=1.0, rate=16000, channels=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0" * int(seconds * rate * channels * 2))
    return buf.getvalue()


def probe_app():
    app = SecuredApp()
    app.add_middleware(UploadBodyLimit)
    app.router.route_class = AudioUploadRoute
    router = APIRouter(route_class=AudioUploadRoute)

    async def upload(audio_file: UploadFile = File(...)):
        return {
            "filename": audio_file.filename,
            "bytes": len(await audio_file.read()),
            "on_disk": audio_file.file._rolled,
        }

    app.post("/api/ingest")(upload)
    router.post("/api/simulate")(upload)
    app.include_router(router)
    return app


@pytest.mark.parametrize("path", ["/api/ingest", "/api/simulate"])
def test_large_valid_short_wav_stays_in_memory(path, monkeypatch):
    rolled = []
    real = formparsers.SpooledTemporaryFile

    class ObservedFile(real):
        def rollover(self):
            rolled.append(True)
            return super().rollover()

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", ObservedFile)
    audio = pcm(seconds=7, rate=44100, channels=2)
    assert 1024 * 1024 < len(audio) < MAX_CLIP_BYTES
    response = TestClient(probe_app()).post(path, files={"audio_file": ("clip.wav", audio)})
    assert response.status_code == 200
    assert response.json() == {"filename": "clip.wav", "bytes": len(audio), "on_disk": False}
    assert rolled == []


@pytest.mark.parametrize("ext", ["mp3", "ogg", "flac", "m4a"])
def test_real_compressed_container_is_accepted_and_extension_matches_magic(ext):
    audio = (FIXTURES / f"silence.{ext}").read_bytes()
    response = TestClient(probe_app()).post(
        "/api/ingest", files={"audio_file": ("wrong.wav", audio, "text/plain")}
    )
    assert response.status_code == 200
    assert response.json()["filename"] == f"wrong.{ext}"
    assert response.json()["on_disk"] is False


@pytest.mark.parametrize("path", ["/api/ingest", "/api/simulate"])
@pytest.mark.parametrize(
    "blob,status,code",
    [
        (b"pretending to be a wave", 415, "unsupported_media_type"),
        (b"", 400, "validation_error"),
        (b"ID3broken", 415, "unsupported_media_type"),
        (b"OggSbroken", 415, "unsupported_media_type"),
        (b"x" * (MAX_CLIP_BYTES + 1), 413, "payload_too_large"),
    ],
)
def test_invalid_audio_is_rejected_before_the_typed_handler(path, blob, status, code):
    response = TestClient(probe_app()).post(path, files={"audio_file": ("clip.wav", blob)})
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_pcm_over_thirty_seconds_is_rejected_but_exact_boundary_is_accepted():
    client = TestClient(probe_app())
    assert (
        client.post("/api/ingest", files={"audio_file": ("clip.wav", pcm(30))}).status_code == 200
    )
    response = client.post("/api/ingest", files={"audio_file": ("clip.wav", pcm(30.01))})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_filename_is_safe_basename_of_at_most_sixty_four_characters():
    name = "../../C:\\secret\\" + "x" * 100 + "\r\n.html"
    normalized = validate_audio(pcm(), name)
    assert len(normalized) == 64 and normalized.endswith(".wav")
    assert "/" not in normalized and "\\" not in normalized and "\n" not in normalized
    with pytest.raises(UploadRejected):
        validate_audio(b"not audio", "clip.wav")


def test_streaming_wav_declared_length_does_not_hide_actual_duration():
    blob = bytearray(pcm(30.01))
    blob[4:8] = (0xFFFFFFFF).to_bytes(4, "little")
    blob[40:44] = (0xFFFFFFFF).to_bytes(4, "little")
    with pytest.raises(UploadRejected) as failure:
        validate_audio(bytes(blob), "stream.wav")
    assert failure.value.status == 413


@pytest.mark.parametrize("declared", [None, str(MAX_REQUEST_BYTES + 1), "1"])
def test_raw_request_limit_counts_chunks_and_does_not_reach_parser(declared):
    received = []
    calls = 0
    chunks = [b"x" * (MAX_REQUEST_BYTES // 2), b"y" * (MAX_REQUEST_BYTES // 2 + 2)]

    async def receive():
        nonlocal calls
        calls += 1
        return {"type": "http.request", "body": chunks.pop(0), "more_body": bool(chunks)}

    async def send(message):
        received.append(message)

    headers = [(b"content-type", b"application/octet-stream")]
    if declared is not None:
        headers.append((b"content-length", declared.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/ingest",
        "root_path": "",
        "query_string": b"",
        "headers": headers,
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1),
    }
    # A tiny application consumes all chunks. The real raw limiter must reject
    # over-limit bodies even when Content-Length is absent or understated.
    from rasta.request_id import _run_with_request_id
    from rasta.upload_security import UploadBodyLimit

    async def consumer(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    asyncio.run(_run_with_request_id(scope, receive, send, UploadBodyLimit(consumer)))
    assert received[0]["status"] == 413
    import json

    body = json.loads(received[1]["body"])
    assert body["error"]["code"] == "payload_too_large"
    assert body["error"]["request_id"]
    if declared == str(MAX_REQUEST_BYTES + 1):
        assert calls == 0


def test_malformed_or_multiple_file_uploads_fail_closed_and_close_handles(monkeypatch):
    opened = []
    real = formparsers.SpooledTemporaryFile

    def observed(*args, **kwargs):
        handle = real(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", observed)
    client = TestClient(probe_app())
    response = client.post(
        "/api/ingest",
        files=[("audio_file", ("first.wav", pcm())), ("audio_file", ("second.wav", pcm()))],
    )
    assert response.status_code == 400
    assert opened and all(handle.closed for handle in opened)


def test_oversized_request_is_counted_and_rejected_before_parsing():
    from rasta.http_counts import attach_http_counts

    app = probe_app()
    # SecuredApp owns the outer counter, including early-limit responses.
    counts = attach_http_counts(app)
    response = TestClient(app).post(
        "/api/ingest",
        content=b"x" * (MAX_REQUEST_BYTES + 1),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413
    assert counts.snapshot() == {"4xx": 1, "5xx": 0}
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
