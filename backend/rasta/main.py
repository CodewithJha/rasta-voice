"""FastAPI app. Every speech call goes to the real Gnani APIs."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from gnani_client.env import api_key
from gnani_client.errors import GnaniError, MissingApiKeyError
from rasta.dispatch_auth import attach_dispatch_auth
from rasta.extract import extract_event
from rasta.limits import SpeechBudgetMiddleware, attach_speech_guard, await_held_work
from rasta.pipeline import (
    SAMPLE_LINE,
    ClipTooLarge,
    EmptyClip,
    ingest,
    read_upload_clip,
    speak_sample,
)
from rasta.request_id import RequestIdApp, configure_rasta_logging
from rasta.resilience import (
    ResilienceError,
    attach_upstream_runtime,
    shutdown_upstream_runtime,
)
from rasta.routes_admin import admin_router
from rasta.routes_events import events_router
from rasta.routes_health import health_router
from rasta.routes_reply import reply_router
from rasta.routes_sim import sim_router
from rasta.routes_stream import stream_router
from rasta.settings import get_settings
from rasta.simulate import CONDITION_HINT, CONDITIONS, BadClip, envelope, prepare_for_ingest
from rasta.store import attach_event_store
from rasta.stream_runtime import attach_stream_runtime

# Real env vars win over .env, so a deploy secret is never shadowed.
load_dotenv()
configure_rasta_logging()
log = logging.getLogger("rasta")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not api_key():
        log.error("GNANI_API_KEY is not set. Every speech request will fail with 503.")
    attach_event_store(app, replace=True)
    attach_stream_runtime(app, replace=True)
    attach_dispatch_auth(app, replace=True)
    attach_speech_guard(app, replace=True)
    attach_upstream_runtime(app, replace=True)
    try:
        yield
    finally:
        # Stop new speech first, close live streams, drain inflight Gnani
        # work, then close the HTTP client and the SQLite store.
        await asyncio.to_thread(shutdown_upstream_runtime, app)
        registry = getattr(app.state, "stream_registry", None)
        if registry is not None:
            await registry.aclose()
        from rasta.llm import close_shared_client

        close_shared_client()
        store = getattr(app.state, "event_store", None)
        if store is not None:
            store.close()


app = RequestIdApp(title="Rasta Voice", version="0.1.0", lifespan=lifespan)


def _configure_production(application: FastAPI) -> None:
    """Fail closed on missing prod secrets and attach host / budget guards."""
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    settings = get_settings()
    settings.require_production_secrets()
    if settings.allowed_hosts:
        application.add_middleware(
            TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts)
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_allow_origins),
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(SpeechBudgetMiddleware)
_configure_production(app)
app.include_router(events_router)
app.include_router(admin_router)
app.include_router(health_router)
app.include_router(reply_router)
app.include_router(stream_router)
app.include_router(sim_router)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "gnani_key_set": bool(api_key()),
        "llm_provider": os.environ.get("LLM_PROVIDER", "rules"),
    }


@app.post("/api/ingest")
async def ingest_upload(audio_file: UploadFile = File(...)) -> dict:
    data = await read_upload_clip(audio_file)
    filename = audio_file.filename or "clip.wav"
    # The pipeline is still sync (Prisma and Timbre clients are sync). Run it
    # in a worker thread so an LLM or STT wait cannot block the event loop.
    return await _run_speech(
        lambda: attach_event_store(app).append(ingest(data, filename)),
        deadline=get_settings().ingest_deadline_seconds,
    )


@app.post("/api/ingest/sample")
async def ingest_sample(condition: str = "clean") -> dict:
    """Timbre speaks a synthetic rider line, then Prisma transcribes it.

    Two real Gnani calls, no uploaded file needed. The response carries the
    exact text Timbre was given so the transcript can be compared to it.
    ``condition`` shares the simulate envelope: clean re-wraps the spoken
    WAV, noisy dirties it to 8 kHz before Prisma hears it.
    """
    if condition not in CONDITIONS:
        raise HTTPException(status_code=400, detail=CONDITION_HINT)

    def run() -> dict:
        audio = speak_sample()
        wav = prepare_for_ingest(audio, condition)
        stamped = attach_event_store(app).append(ingest(wav, "sample.wav"))
        stamped["sample_text"] = SAMPLE_LINE
        return envelope(condition, wav, stamped)

    return await _run_speech(run, deadline=get_settings().ingest_deadline_seconds)


async def _run_speech(work, *, deadline: float | None = None):
    runtime = getattr(app.state, "upstream_runtime", None)
    if runtime is not None and not runtime.accepting:
        raise HTTPException(
            status_code=503,
            detail={"code": "shutting_down", "message": "The process is shutting down."},
        )
    limit = get_settings().max_speech_seconds if deadline is None else deadline

    def leased():
        if runtime is None:
            return _guard(work)
        with runtime.operation():
            return _guard(work)

    try:
        return await await_held_work(leased, limit)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "timeout", "message": "The speech request timed out."},
        ) from exc


def _guard(work):
    try:
        return work()
    except EmptyClip as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except BadClip as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ClipTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ResilienceError as exc:
        log.warning("upstream resilience: %s", exc)
        raise HTTPException(status_code=exc.status, detail=exc.as_detail()) from exc
    except MissingApiKeyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except GnaniError as exc:
        log.warning("Gnani call failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail={"error": str(exc), "upstream_status": exc.status},
        ) from exc


def _mount_static(application: FastAPI) -> None:
    """Serve the built UI at ``/`` when a dist directory is configured or present."""
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    settings = get_settings()
    candidates = []
    if settings.static_dir:
        candidates.append(Path(settings.static_dir))
    candidates.append(Path("frontend/dist"))
    for path in candidates:
        if path.is_dir() and (path / "index.html").is_file():
            application.mount("/", StaticFiles(directory=path, html=True), name="ui")
            return


_mount_static(app)

# Imported so a schema drift test and callers share one extractor entry.
__all__ = ["app", "extract_event"]
