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
from rasta.extract import extract_event
from rasta.pipeline import SAMPLE_LINE, ClipTooLarge, EmptyClip, ingest, speak_sample
from rasta.routes_events import events_router
from rasta.routes_stream import stream_router
from rasta.settings import get_settings
from rasta.store import attach_event_store
from rasta.stream_runtime import attach_stream_runtime

# Real env vars win over .env, so a deploy secret is never shadowed.
load_dotenv()
log = logging.getLogger("rasta")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not api_key():
        log.error("GNANI_API_KEY is not set. Every speech request will fail with 503.")
    attach_event_store(app, replace=True)
    attach_stream_runtime(app, replace=True)
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


app = FastAPI(title="Rasta Voice", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_allow_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(events_router)
app.include_router(stream_router)


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "gnani_key_set": bool(api_key()),
        "llm_provider": os.environ.get("LLM_PROVIDER", "rules"),
    }


@app.post("/api/ingest")
async def ingest_upload(audio_file: UploadFile = File(...)) -> dict:
    data = await audio_file.read()
    filename = audio_file.filename or "clip.wav"
    # The pipeline is still sync (Prisma and Timbre clients are sync). Run it
    # in a worker thread so an LLM or STT wait cannot block the event loop.
    return await asyncio.to_thread(
        _guard,
        lambda: attach_event_store(app).append(ingest(data, filename)),
    )


@app.post("/api/ingest/sample")
async def ingest_sample() -> dict:
    """Timbre speaks a synthetic rider line, then Prisma transcribes it.

    Two real Gnani calls, no uploaded file needed. The response carries the
    exact text Timbre was given so the transcript can be compared to it.
    """

    def run() -> dict:
        audio = speak_sample()
        stamped = attach_event_store(app).append(ingest(audio, "sample.wav"))
        stamped["sample_text"] = SAMPLE_LINE
        return stamped

    return await asyncio.to_thread(_guard, run)


def _guard(work):
    try:
        return work()
    except EmptyClip as exc:
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


# Imported so a schema drift test and callers share one extractor entry.
__all__ = ["app", "extract_event"]
