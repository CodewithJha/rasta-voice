"""Passcode-protected operator exports. Not an off-site backup."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from starlette.background import BackgroundTask

from rasta.dispatch_auth import require_desk_read, require_desk_write
from rasta.limits import attach_speech_guard
from rasta.routes_events import get_event_store
from rasta.settings import get_settings
from rasta.store import WIPE_CONFIRM, EventStore

admin_router = APIRouter(tags=["admin"])


@admin_router.get("/api/admin/export")
def export_events(
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_read),
) -> FileResponse:
    """Download a copy of the event database. This is not an off-site backup."""
    handle = tempfile.NamedTemporaryFile(prefix="rasta-export-", suffix=".sqlite", delete=False)
    path = Path(handle.name)
    handle.close()
    store.export_copy(path)
    return FileResponse(
        path,
        media_type="application/vnd.sqlite3",
        filename="rasta-events.sqlite",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@admin_router.post("/api/admin/wipe")
async def wipe_events(
    request: Request,
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_write),
):
    """Clear the desk event store. Usage counters stay."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid wipe body.") from None
    if not isinstance(body, dict) or body.get("confirm") != WIPE_CONFIRM:
        raise HTTPException(status_code=422, detail="Wipe requires an explicit confirm token.")
    store.wipe()
    return Response(status_code=204)



@admin_router.get("/api/admin/usage")
def admin_usage(
    request: Request,
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_read),
) -> dict:
    store.escalate_overdue(get_settings().sos_ack_seconds)
    guard = attach_speech_guard(request.app)
    remaining = guard.remaining()
    budget = get_settings().demo_speech_budget
    body: dict = {
        "events": store.counts_by_state(),
        "demo_credits_remaining": remaining,
        "gnani_calls": max(0, budget - remaining) if budget >= remaining else 0,
        "sos_unacked": store.sos_unacked(),
    }
    counts = getattr(request.app.state, "http_counts", None)
    if counts is not None:
        body["http_errors"] = counts.snapshot()
    breaker = getattr(request.app.state, "circuit_breaker", None)
    if breaker is not None:
        body["circuit_breaker"] = breaker
    return body
