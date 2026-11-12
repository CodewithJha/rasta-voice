"""Browser WebSocket ``/api/stream`` ↔ Prisma realtime pump."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from gnani_client.env import api_key
from gnani_client.errors import GnaniError, MissingApiKeyError
from gnani_client.stt import RIDER_KEYTERMS, RIDER_TOPIC
from gnani_client.stt_stream import (
    StreamHandshakeError,
    SttStream,
    handshake_status,
)
from gnani_client.tts import TimbreTTS
from rasta.extract import extract_event_with_source
from rasta.pipeline import SAMPLE_LINE, STT_FORMAT
from rasta.settings import Settings, get_settings
from rasta.store import attach_event_store
from rasta.stream_runtime import AllowAllAdmission, attach_stream_runtime

log = logging.getLogger("rasta.stream")

stream_router = APIRouter()

CLOSE_OK = 1000
CLOSE_IDLE = 1001
CLOSE_POLICY = 1008
CLOSE_ERROR = 1011
CLOSE_BUSY = 1013
CLOSE_NO_KEY = 4401
CLOSE_ORIGIN = 4403


@stream_router.websocket("/api/stream")
async def stream_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    app = websocket.app
    attach_stream_runtime(app)
    settings = get_settings()

    origin = websocket.headers.get("origin")
    if origin not in settings.cors_allow_origins:
        await _fail(websocket, "Origin is not allowed", CLOSE_ORIGIN)
        return
    if not api_key():
        await _fail(websocket, "GNANI_API_KEY is not set", CLOSE_NO_KEY)
        return

    slots = app.state.stream_slots
    if not await slots.try_acquire():
        await _fail(websocket, "Too many live streams. Try again in a moment.", CLOSE_BUSY)
        return
    try:
        admission = getattr(app.state, "stream_admission", None) or AllowAllAdmission()
        if not admission.allow():
            await _fail(websocket, "Stream admission denied", CLOSE_BUSY)
            return
        registry = app.state.stream_registry
        task = asyncio.current_task()
        if task is not None:
            registry.add(task)
        try:
            await _run_session(websocket, app, settings)
        finally:
            if task is not None:
                registry.discard(task)
    finally:
        await slots.release()


async def _run_session(websocket: WebSocket, app: Any, settings: Settings) -> None:
    first = await _receive(websocket, settings.stream_idle_seconds)
    if first is None:
        await _fail(websocket, "Stream idle timeout", CLOSE_IDLE)
        return
    if first["kind"] == "disconnect":
        return
    if first["kind"] == "text":
        message = _parse_control(first["data"])
        if message is None:
            await _fail(websocket, "Expected audio, a commit, or a sample request", CLOSE_POLICY)
            return
        if message.get("type") == "sample":
            await _run_sample(websocket, app, settings)
            return
        if message.get("type") == "commit":
            await _run_live(websocket, app, settings, first=None, commit_first=True)
            return
        await _fail(websocket, "Expected audio, a commit, or a sample request", CLOSE_POLICY)
        return
    await _run_live(websocket, app, settings, first=first["data"], commit_first=False)


async def _run_live(
    websocket: WebSocket,
    app: Any,
    settings: Settings,
    *,
    first: bytes | None,
    commit_first: bool,
) -> None:
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=settings.stream_queue_max)
    if first:
        queue.put_nowait(first)
    commit = asyncio.Event()
    if commit_first:
        commit.set()
    await _pump(websocket, app, settings, queue=queue, commit=commit, produce=None)


async def _run_sample(websocket: WebSocket, app: Any, settings: Settings) -> None:
    try:
        pcm = await _sample_pcm(app, settings)
    except MissingApiKeyError:
        await _fail(websocket, "GNANI_API_KEY is not set", CLOSE_NO_KEY)
        return
    except GnaniError as exc:
        log.warning("Timbre sample failed: %s", exc)
        await _fail(websocket, "Could not synthesize the sample line", CLOSE_ERROR)
        return
    except Exception:
        log.exception("Timbre sample failed")
        await _fail(websocket, "Could not synthesize the sample line", CLOSE_ERROR)
        return
    if not pcm:
        await _fail(websocket, "Sample line produced no audio", CLOSE_ERROR)
        return

    pace = settings.frame_seconds()
    size = settings.stream_frame_bytes

    async def produce(stream: SttStream) -> None:
        for offset in range(0, len(pcm), size):
            await stream.send_audio(pcm[offset : offset + size])
            await asyncio.sleep(pace)
        await stream.commit()

    await _pump(websocket, app, settings, queue=None, commit=None, produce=produce)


async def _pump(
    websocket: WebSocket,
    app: Any,
    settings: Settings,
    *,
    queue: asyncio.Queue[bytes | None] | None,
    commit: asyncio.Event | None,
    produce: Any,
) -> None:
    """Run uplink, downlink, browser reader, and the watchdog together."""
    texts: list[str] = []
    request_id: str | None = None
    last_activity = time.monotonic()
    stop = asyncio.Event()
    finished = False

    def touch() -> None:
        nonlocal last_activity
        last_activity = time.monotonic()

    try:
        async with _open_stream(app, settings) as stream:

            async def uplink() -> None:
                if produce is not None:
                    await produce(stream)
                    return
                assert queue is not None and commit is not None
                while True:
                    if commit.is_set():
                        while not queue.empty():
                            chunk = queue.get_nowait()
                            if chunk:
                                await stream.send_audio(chunk)
                        await stream.commit()
                        return
                    get_task = asyncio.create_task(queue.get())
                    wait_task = asyncio.create_task(commit.wait())
                    _done, pending = await asyncio.wait(
                        {get_task, wait_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    if get_task.done() and not get_task.cancelled():
                        chunk = get_task.result()
                        if chunk:
                            await stream.send_audio(chunk)

            last_transcript_at = time.monotonic()
            got_frame = asyncio.Event()

            async def downlink() -> None:
                nonlocal request_id, last_transcript_at
                async for frame in stream.frames():
                    kind = frame.get("type")
                    if kind == "connected":
                        request_id = _request_id(frame) or request_id
                    elif kind == "transcript":
                        text = frame.get("text")
                        if isinstance(text, str) and text.strip():
                            texts.append(text.strip())
                            last_transcript_at = time.monotonic()
                            got_frame.set()
                            await _send_json(
                                websocket, {"type": "transcript", "text": text.strip()}
                            )
                        request_id = request_id or _request_id(frame)
                    elif kind == "error":
                        message = frame.get("message")
                        await _send_error(
                            websocket,
                            message
                            if isinstance(message, str) and message
                            else "Prisma stream error",
                        )

            async def browser_in() -> None:
                if produce is not None or commit is None or queue is None:
                    return
                while not commit.is_set() and not stop.is_set():
                    message = await _receive(websocket, settings.stream_idle_seconds)
                    if message is None:
                        await _send_error(websocket, "Stream idle timeout")
                        raise _SessionTimeout("idle")
                    if message["kind"] == "disconnect":
                        stop.set()
                        return
                    touch()
                    if message["kind"] == "bytes":
                        await queue.put(message["data"])
                        continue
                    control = _parse_control(message["data"])
                    if control and control.get("type") == "commit":
                        commit.set()
                        return

            async def watchdog() -> None:
                deadline = time.monotonic() + settings.stream_session_seconds
                next_ping = time.monotonic() + settings.stream_heartbeat_seconds
                while not stop.is_set():
                    now = time.monotonic()
                    if now - last_activity >= settings.stream_idle_seconds:
                        await _send_error(websocket, "Stream idle timeout")
                        raise _SessionTimeout("idle")
                    if now >= deadline:
                        await _send_error(websocket, "Stream session expired")
                        raise _SessionTimeout("session")
                    if now >= next_ping:
                        await _send_json(websocket, {"type": "ping"})
                        next_ping = now + settings.stream_heartbeat_seconds
                    wait = min(
                        settings.stream_idle_seconds - (now - last_activity),
                        deadline - now,
                        next_ping - now,
                    )
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=max(0.0, wait))
                        return
                    except TimeoutError:
                        continue

            tasks = [
                asyncio.create_task(uplink(), name="stream-uplink"),
                asyncio.create_task(downlink(), name="stream-downlink"),
                asyncio.create_task(browser_in(), name="stream-browser"),
                asyncio.create_task(watchdog(), name="stream-watchdog"),
            ]
            uplink_task, down_task, _browser_task, watch_task = tasks
            # Wait for the uplink to commit (or the watchdog). Do not treat
            # browser_in finishing as done: it returns as soon as it sees
            # commit, while the uplink may still be draining the queue.
            try:
                stop_task = asyncio.create_task(stop.wait(), name="stream-stop")
                done, _pending = await asyncio.wait(
                    {uplink_task, watch_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                stop_task.cancel()
                for task in done:
                    if task is stop_task:
                        continue
                    exc = task.exception() if not task.cancelled() else None
                    if isinstance(exc, _SessionTimeout):
                        return
                    if exc is not None:
                        raise exc
                if uplink_task.done() and not uplink_task.cancelled():
                    committed_at = time.monotonic()
                    await _drain_transcripts(
                        down_task,
                        got_frame,
                        texts,
                        lambda: max(last_transcript_at, committed_at),
                        settings,
                    )
                    await _emit_event(websocket, app, texts, request_id)
                    finished = True
            finally:
                stop.set()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except StreamHandshakeError as exc:
        await _fail(websocket, _handshake_message(exc), CLOSE_ERROR)
        return
    except _SessionTimeout:
        await _close(websocket, CLOSE_IDLE)
        return
    except WebSocketDisconnect:
        return
    except Exception:
        log.exception("Stream session failed")
        if not finished:
            await _fail(websocket, "Stream failed", CLOSE_ERROR)



async def _drain_transcripts(
    down_task: asyncio.Task,
    got_frame: asyncio.Event,
    texts: list[str],
    last_transcript_at: Any,
    settings: Settings,
) -> None:
    """Wait for trailing Prisma transcripts after commit, then return.

    Prisma does not always close the socket after ``commit``; waiting for the
    iterator to end would sit until idle timeout. Once at least one
    transcript has arrived, a quiet gap is enough. A hard cap still applies
    when nothing comes back.
    """
    deadline = time.monotonic() + settings.stream_drain_seconds
    while not down_task.done() and time.monotonic() < deadline:
        if texts:
            remaining = last_transcript_at() + settings.stream_quiet_seconds - time.monotonic()
            if remaining <= 0:
                return
        else:
            remaining = deadline - time.monotonic()
        got_frame.clear()
        try:
            await asyncio.wait_for(got_frame.wait(), timeout=max(0.0, remaining))
        except TimeoutError:
            if texts or time.monotonic() >= deadline:
                return
    if down_task.done():
        exc = down_task.exception() if not down_task.cancelled() else None
        if exc is not None:
            raise exc


# Live Prisma stream rejects a comma-separated language list (REST still
# accepts hi-IN,en-IN). transliterate sessions default to indic-auto.
STREAM_LANGUAGE_CODE = "indic-auto"


def _open_stream(app: Any, settings: Settings) -> SttStream:
    connect = getattr(app.state, "stt_connect", None)
    return SttStream(
        sample_rate=settings.stream_sample_rate,
        output_format=STT_FORMAT,
        language_code=STREAM_LANGUAGE_CODE,
        keyterms=RIDER_KEYTERMS,
        topic=RIDER_TOPIC,
        idle_timeout_sec=settings.prisma_idle_timeout_sec(),
        frame_bytes=settings.stream_frame_bytes,
        connect=connect,
    )


async def _sample_pcm(app: Any, settings: Settings) -> bytes:
    factory = getattr(app.state, "sample_pcm", None)
    if factory is not None:
        result = factory()
        if asyncio.iscoroutine(result):
            return await result
        return result
    return await asyncio.to_thread(
        TimbreTTS().synthesize,
        SAMPLE_LINE,
        sample_rate=settings.stream_sample_rate,
        container="raw",
    )


async def _emit_event(
    websocket: WebSocket,
    app: Any,
    texts: list[str],
    request_id: str | None,
) -> None:
    transcript = " ".join(texts).strip()
    if not transcript:
        await _fail(websocket, "No transcript received", CLOSE_OK)
        return
    extracted = await asyncio.to_thread(extract_event_with_source, transcript)
    payload = {
        "transcript": transcript,
        "stt": {
            "model": "prisma-v3.0",
            "request_id": request_id,
            "detected_language_code": None,
            "processing_time": None,
            "audio_seconds": None,
        },
        "event": extracted.event.model_dump(mode="json"),
        "extractor_source": extracted.source,
        "fallback_reason": extracted.fallback_reason,
    }
    stamped = attach_event_store(app).append(payload)
    await _send_json(websocket, {"type": "event", **stamped})
    await _close(websocket, CLOSE_OK)
    log.info("stream event id=%s request_id=%s", stamped.get("id"), request_id)


def _request_id(frame: dict[str, Any]) -> str | None:
    value = frame.get("request_id")
    if isinstance(value, str) and value:
        return value
    segment = frame.get("segment_id")
    if isinstance(segment, str) and "-seg-" in segment:
        return segment.split("-seg-", 1)[0] or None
    return None


def _parse_control(raw: str) -> dict[str, Any] | None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


def _handshake_message(exc: StreamHandshakeError) -> str:
    status = exc.status or handshake_status(exc)
    if status == 401:
        return "Prisma refused the handshake (401)"
    if status == 402:
        return "Prisma refused the handshake (402)"
    if status == 429:
        return "Prisma refused the handshake (429)"
    return "Could not open a Prisma stream"


async def _receive(websocket: WebSocket, timeout: float) -> dict[str, Any] | None:
    try:
        message = await asyncio.wait_for(websocket.receive(), timeout=timeout)
    except TimeoutError:
        return None
    except WebSocketDisconnect:
        return {"kind": "disconnect"}
    typ = message.get("type")
    if typ == "websocket.disconnect":
        return {"kind": "disconnect"}
    if typ == "websocket.receive":
        data = message.get("bytes")
        if isinstance(data, (bytes, bytearray)):
            return {"kind": "bytes", "data": bytes(data)}
        text = message.get("text")
        if isinstance(text, str):
            return {"kind": "text", "data": text}
    return {"kind": "disconnect"}


async def _send_json(websocket: WebSocket, payload: dict[str, Any]) -> None:
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.send_json(payload)
    except Exception:
        return


async def _send_error(websocket: WebSocket, message: str) -> None:
    await _send_json(websocket, {"type": "error", "message": message})


async def _close(websocket: WebSocket, code: int) -> None:
    if websocket.client_state != WebSocketState.CONNECTED:
        return
    try:
        await websocket.close(code=code)
    except Exception:
        return


async def _fail(websocket: WebSocket, message: str, code: int) -> None:
    await _send_error(websocket, message)
    await _close(websocket, code)


class _SessionTimeout(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
