"""Passcode-protected operator exports. Not an off-site backup."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from rasta.dispatch_auth import require_desk_read
from rasta.routes_events import get_event_store
from rasta.store import EventStore

admin_router = APIRouter()


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
