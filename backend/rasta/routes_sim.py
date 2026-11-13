"""Demo simulate route: prepare the clip, then ingest it."""

import asyncio

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from rasta.pipeline import ingest, read_upload_clip, reject_oversize_clip
from rasta.simulate import CONDITION_HINT, CONDITIONS, envelope, prepare_for_ingest
from rasta.store import attach_event_store

sim_router = APIRouter()


@sim_router.post("/api/simulate")
async def simulate(
    audio_file: UploadFile = File(...),
    condition: str = Query("clean"),
) -> dict:
    if condition not in CONDITIONS:
        raise HTTPException(status_code=400, detail=CONDITION_HINT)
    data = await read_upload_clip(audio_file)

    from rasta.main import _guard, app

    def run() -> dict:
        reject_oversize_clip(data)
        wav = prepare_for_ingest(data, condition)
        stamped = attach_event_store(app).append(ingest(wav, "clip.wav"))
        return envelope(condition, wav, stamped)

    return await asyncio.to_thread(_guard, run)
