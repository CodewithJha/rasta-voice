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
from rasta.limits import SpeechBudgetMiddleware, attach_speech_guard
from rasta.pipeline import (
    SAMPLE_LINE,
    ClipTooLarge,
    EmptyClip,
    ingest,
    read_upload_clip,
    speak_sample,
)
from rasta.request_id import RequestIdApp, configure_rasta_logging
from rasta.routes_events import events_router
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
    try:
        yield
    finally:
        # Cancel live /api/stream sessions first. Issue 29 will own a broader
        # inflight cap; this registry is the hook it can reuse.
        registry = getattr(app.state, "stream_registry", None)
        if registry is not None:
            await registry.aclose()
        # Issue 29 will own shutdown of the shared client; close it here until then
        # so a one-off LLM client cannot outlive the process.
        from rasta.llm import close_shared_client

        close_shared_client()


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
    return await _run_speech(lambda: attach_event_store(app).append(ingest(data, filename)))


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

    return await _run_speech(run)


async def _run_speech(work):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_guard, work),
            timeout=get_settings().max_speech_seconds,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="The speech request timed out.") from exc


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
