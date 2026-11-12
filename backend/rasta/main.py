"""FastAPI shell. One ingest route, plus a sample clip for mock mode."""

import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from gnani_client.stt import PrismaSTT
from gnani_client.wav import tone_wav
from rasta.extract import extract_event
from rasta.pipeline import ClipTooLarge, EmptyClip, ingest

app = FastAPI(title="Rasta Voice", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    stt = PrismaSTT()
    return {
        "ok": True,
        "stt_mock": stt.mock,
        "llm_provider": os.environ.get("LLM_PROVIDER", "mock"),
    }


@app.post("/api/ingest")
async def ingest_upload(audio_file: UploadFile = File(...)) -> dict:
    data = await audio_file.read()
    return _run(data, audio_file.filename or "clip.wav")


@app.post("/api/ingest/sample")
def ingest_sample() -> dict:
    """Silence-free tone plus the canned transcript, only while STT is mocked.

    The tone is not speech. A live Prisma call would return an empty
    transcript, so this route refuses to burn a request on it.
    """
    if not PrismaSTT().mock:
        raise HTTPException(
            status_code=409,
            detail="Sample clip is a tone, not speech. Upload a clip, or set GNANI_MOCK=1.",
        )
    return _run(tone_wav(), "sample.wav")


def _run(audio: bytes, filename: str) -> dict:
    try:
        return ingest(audio, filename)
    except EmptyClip as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ClipTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


# Imported so a schema drift test and callers share one extractor entry.
__all__ = ["app", "extract_event"]
