"""Browser WebSocket ``/api/stream``: admission, then one supervised session."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket

from gnani_client.env import api_key
from gnani_client.errors import GnaniError, MissingApiKeyError
from gnani_client.stt_stream import SttStream
from gnani_client.tts import TimbreTTS
from rasta.origins import origin_allowed
from rasta.pipeline import SAMPLE_LINE
from rasta.request_id import watch_gnani_call
from rasta.resilience import UPSTREAM_TTS, get_upstream_runtime
from rasta.settings import Settings, get_settings
from rasta.stream_runtime import AllowAllAdmission, attach_stream_runtime
from rasta.stream_session import (
    CLOSE_BUSY,
    CLOSE_ERROR,
    CLOSE_IDLE,
    CLOSE_NO_KEY,
    CLOSE_ORIGIN,
    CLOSE_POLICY,
    StreamSession,
    fail,
    parse_control,
    receive_message,
)

log = logging.getLogger("rasta.stream")

stream_router = APIRouter()


@stream_router.websocket("/api/stream")
async def stream_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    app = websocket.app
    attach_stream_runtime(app)
    settings = get_settings()

    origin = websocket.headers.get("origin")
    if not origin_allowed(origin, settings, websocket.scope):
        await fail(websocket, "Origin is not allowed", CLOSE_ORIGIN)
        return
    if not api_key():
        await fail(websocket, "GNANI_API_KEY is not set", CLOSE_NO_KEY)
        return

    from rasta.limits import admit_websocket

    budget = admit_websocket(app, websocket.scope)
    if budget is not None:
        await fail(websocket, budget.message, CLOSE_BUSY)
        return

    slots = app.state.stream_slots
    if not await slots.try_acquire():
        await fail(websocket, "Too many live streams. Try again in a moment.", CLOSE_BUSY)
        return
    try:
        admission = getattr(app.state, "stream_admission", None) or AllowAllAdmission()
        if not admission.allow():
            await fail(websocket, "Stream admission denied", CLOSE_BUSY)
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
    first = await receive_message(websocket, settings.stream_idle_seconds)
    if first is None:
        await fail(websocket, "Stream idle timeout", CLOSE_IDLE)
        return
    if first["kind"] == "disconnect":
        return
    if first["kind"] == "text":
        message = parse_control(first["data"])
        if message and message.get("type") == "sample":
            await _run_sample(websocket, app, settings)
            return
        if message and message.get("type") == "commit":
            commit = asyncio.Event()
            commit.set()
            await StreamSession(
                websocket,
                app,
                settings,
                queue=asyncio.Queue(maxsize=settings.stream_queue_max),
                commit=commit,
            ).run()
            return
        await fail(websocket, "Expected audio, a commit, or a sample request", CLOSE_POLICY)
        return
    queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=settings.stream_queue_max)
    queue.put_nowait(first["data"])
    await StreamSession(websocket, app, settings, queue=queue, commit=asyncio.Event()).run()


async def _run_sample(websocket: WebSocket, app: Any, settings: Settings) -> None:
    from rasta.limits import attach_speech_guard

    # Stream admit reserved one Prisma session. Sample also spends a Timbre call.
    extra = attach_speech_guard(app).reserve_budget(1)
    if extra is not None:
        await fail(websocket, extra.message, CLOSE_BUSY)
        return
    try:
        pcm = await _sample_pcm(app, settings)
    except MissingApiKeyError:
        await fail(websocket, "GNANI_API_KEY is not set", CLOSE_NO_KEY)
        return
    except GnaniError as exc:
        log.warning("Timbre sample failed: %s", exc)
        await fail(websocket, "Could not synthesize the sample line", CLOSE_ERROR)
        return
    except Exception:
        log.exception("Timbre sample failed")
        await fail(websocket, "Could not synthesize the sample line", CLOSE_ERROR)
        return
    if not pcm:
        await fail(websocket, "Sample line produced no audio", CLOSE_ERROR)
        return

    session_holder: list[StreamSession] = []

    async def produce(stream: SttStream) -> None:
        session = session_holder[0]
        size = settings.stream_frame_bytes
        pace = settings.frame_seconds()
        for offset in range(0, len(pcm), size):
            if session.outcome is not None:
                return
            await stream.send_audio(pcm[offset : offset + size])
            session.touch()
            await asyncio.sleep(pace)
        if session.outcome is None:
            await stream.commit()

    session = StreamSession(websocket, app, settings, produce=produce)
    session_holder.append(session)
    await session.run()


async def _sample_pcm(app: Any, settings: Settings) -> bytes:
    factory = getattr(app.state, "sample_pcm", None)
    if factory is not None:
        result = factory()
        if asyncio.iscoroutine(result):
            return await result
        return result
    def speak() -> bytes:
        runtime = get_upstream_runtime()
        client = None if runtime is None else runtime.client

        def work() -> bytes:
            return TimbreTTS(client=client).synthesize(
                SAMPLE_LINE,
                sample_rate=settings.stream_sample_rate,
                container="raw",
            )

        def watched():
            return watch_gnani_call("tts_inference", work)

        if runtime is None:
            return watched()
        return runtime.call_gnani(UPSTREAM_TTS, watched)

    return await asyncio.to_thread(speak)
