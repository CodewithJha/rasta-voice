"""Demo simulate route: prepare the clip, then ingest it."""

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile

from rasta.pipeline import ingest, read_upload_clip, reject_oversize_clip
from rasta.simulate import CONDITION_HINT, CONDITIONS, envelope, prepare_for_ingest
from rasta.store import attach_event_store, bind_rider_header, reset_rider_header
from rasta.upload_security import AudioUploadRoute

sim_router = APIRouter(route_class=AudioUploadRoute, tags=["rider"])


@sim_router.post("/api/simulate")
async def simulate(
    audio_file: UploadFile = File(...),
    condition: str = Query("clean"),
    x_rider_id: str | None = Header(default=None, alias="X-Rider-Id"),
) -> dict:
    if condition not in CONDITIONS:
        raise HTTPException(status_code=400, detail=CONDITION_HINT)
    data = await read_upload_clip(audio_file)

    from rasta.main import _run_speech, app

    def run() -> dict:
        reject_oversize_clip(data)
        wav = prepare_for_ingest(data, condition)
        stamped = attach_event_store(app).append(ingest(wav, "clip.wav"))
        return envelope(condition, wav, stamped)

    token = bind_rider_header(x_rider_id)
    try:
        return await _run_speech(run)
    finally:
        reset_rider_header(token)
