"""Bounded, memory-only multipart audio parsing for public upload routes."""

from __future__ import annotations

import io
import json
import math
import re
import wave
from collections.abc import Callable, Coroutine
from contextlib import aclosing
from typing import Any

from fastapi.routing import APIRoute
from starlette.datastructures import FormData, UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from rasta.pipeline import MAX_CLIP_BYTES
from rasta.request_id import current_request_id

MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_REQUEST_BYTES = MAX_CLIP_BYTES + MULTIPART_OVERHEAD_BYTES
MAX_CLIP_SECONDS = 30.0
AUDIO_UPLOAD_PATHS = frozenset(
    {"/api/ingest", "/api/simulate", "/api/v1/ingest", "/api/v1/simulate"}
)


class UploadRejected(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def upload_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "request_id": current_request_id()}},
        status_code=status,
    )


class UploadBodyLimit:
    """Count real incoming bytes before multipart parsing, including chunked bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = RequestBodyLimitMiddleware(app, max_body_size=MAX_REQUEST_BYTES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        replacement: bytes | None = None
        emitted = False

        async def send_with_envelope(message: Message) -> None:
            nonlocal replacement, emitted
            if message["type"] == "http.response.start" and message["status"] == 413:
                replacement = json.dumps(
                    {
                        "error": {
                            "code": "payload_too_large",
                            "message": "Audio limit is 2 MB plus 64 KiB multipart overhead.",
                            "request_id": current_request_id(),
                        }
                    }
                ).encode()
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"content-length", b"content-type"}
                ]
                headers.extend(
                    [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(replacement)).encode()),
                    ]
                )
                message = {**message, "headers": headers}
            elif message["type"] == "http.response.body" and replacement is not None:
                if emitted:
                    return
                emitted = True
                message = {"type": "http.response.body", "body": replacement, "more_body": False}
            await send(message)

        await self.app(scope, receive, send_with_envelope)


class MemoryMultipartParser(MultiPartParser):
    # The outer body limiter rejects larger requests before this threshold.
    # Accepted UploadFile instances never roll their SpooledTemporaryFile to disk.
    spool_max_size = MAX_REQUEST_BYTES + 1


def _audio_kind(data: bytes) -> str:
    if data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if data.startswith(b"fLaC"):
        return "flac"
    if data.startswith(b"OggS"):
        return "ogg"
    if data[4:8] == b"ftyp":
        return "m4a"
    if data.startswith(b"ID3") or (len(data) > 1 and data[0] == 255 and data[1] & 224 == 224):
        return "mp3"
    raise UploadRejected(415, "unsupported_media_type", "Upload WAV, MP3, OGG, FLAC or M4A audio.")


def _duration(data: bytes, kind: str) -> float:
    if kind == "wav":
        with wave.open(io.BytesIO(data), "rb") as audio:
            # Count actual PCM bytes, including streaming WAV headers. Never
            # trust a client-supplied byte-rate or declared data length alone.
            frames = audio.readframes(audio.getnframes())
            return len(frames) / (
                audio.getsampwidth() * audio.getnchannels() * audio.getframerate()
            )
    if kind == "mp3":
        from mutagen.mp3 import MPEGInfo

        # Stream metadata only; do not decompress or interpret ID3 tag payloads.
        return float(MPEGInfo(io.BytesIO(data)).length)
    if kind == "flac":
        from mutagen.flac import FLAC

        info = FLAC(io.BytesIO(data)).info
        if info is None:
            raise ValueError("missing FLAC stream metadata")
        return float(info.length)
    if kind == "m4a":
        from mutagen.mp4 import MP4

        info = MP4(io.BytesIO(data)).info
        if info is None:
            raise ValueError("missing MP4 stream metadata")
        return float(info.length)
    from mutagen import File
    from mutagen.oggflac import OggFLAC
    from mutagen.oggopus import OggOpus
    from mutagen.oggvorbis import OggVorbis

    parsed = File(io.BytesIO(data))
    if not isinstance(parsed, (OggFLAC, OggOpus, OggVorbis)):
        raise ValueError("unsupported OGG stream")
    info = parsed.info
    if info is None:
        raise ValueError("missing OGG stream metadata")
    return float(info.length)


def validate_audio(data: bytes, filename: str | None) -> str:
    if not data:
        raise UploadRejected(400, "validation_error", "Empty audio upload.")
    if len(data) > MAX_CLIP_BYTES:
        raise UploadRejected(413, "payload_too_large", "Audio must be under 2 MB.")
    kind = _audio_kind(data)
    try:
        seconds = _duration(data, kind)
    except Exception:
        raise UploadRejected(415, "unsupported_media_type", "Audio container is invalid.") from None
    if not math.isfinite(seconds) or seconds <= 0:
        raise UploadRejected(
            415, "unsupported_media_type", "Audio container has no valid duration."
        )
    if seconds > MAX_CLIP_SECONDS:
        raise UploadRejected(413, "payload_too_large", "Audio must be at most 30 seconds.")
    basename = (filename or "clip").replace("\\", "/").rsplit("/", 1)[-1]
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", stem).strip("_") or "clip"
    return f"{stem[: 64 - len(kind) - 1]}.{kind}"


class AudioUploadRoute(APIRoute):
    """Preparse only upload routes, retaining their typed FastAPI/OpenAPI signature."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def guarded(request: Request) -> Response:
            if request.url.path not in AUDIO_UPLOAD_PATHS or request.method != "POST":
                return await original(request)
            if (
                not request.headers.get("content-type", "")
                .lower()
                .startswith("multipart/form-data")
            ):
                return await original(request)
            form: FormData | None = None
            parser: MemoryMultipartParser | None = None
            try:
                async with aclosing(request.stream()) as stream:
                    parser = MemoryMultipartParser(
                        request.headers, stream, max_files=1, max_fields=0
                    )
                    form = await parser.parse()
                for name, value in form.multi_items():
                    if isinstance(value, UploadFile) and name == "audio_file":
                        data = await value.read(MAX_CLIP_BYTES + 1)
                        value.filename = validate_audio(data, value.filename)
                        await value.seek(0)
                # FastAPI's typed body reader reuses Request's parsed form
                # cache. Keep parsing and cleanup owned by this route wrapper.
                request._form = form
                return await original(request)
            except UploadRejected as exc:
                return upload_error(exc.status, exc.code, exc.message)
            except MultiPartException:
                return upload_error(400, "validation_error", "Invalid multipart audio upload.")
            finally:
                if form is not None:
                    await form.close()
                elif parser is not None:
                    # Starlette closes these for MultiPartException; also close
                    # when the outer raw-body ceiling aborts midway through parsing.
                    for handle in parser._files_to_close_on_error:
                        handle.close()

        return guarded
