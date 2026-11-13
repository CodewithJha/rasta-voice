"""Dispatch event list for the desk slate."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from rasta.dispatch_auth import (
    UnlockLimiter,
    client_address,
    get_unlock_limiter,
    mint_actor,
    require_desk_read,
    require_dispatch_passcode,
    set_unlock_cookies,
)
from rasta.settings import get_settings
from rasta.store import EventStore, InvalidSince, attach_event_store

events_router = APIRouter()


def get_event_store(request: Request) -> EventStore:
    return attach_event_store(request.app)


@events_router.get("/api/events")
def list_events(
    since: str | None = None,
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_read),
) -> dict:
    try:
        events = store.list_since(since)
    except InvalidSince as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"events": events}


@events_router.delete("/api/events/{event_id}")
def delete_event(
    event_id: str,
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_read),
):
    if not store.delete(event_id):
        raise HTTPException(status_code=404, detail="Event not found.")
    return Response(status_code=204)


@events_router.post("/api/dispatch/unlock")
async def unlock_desk(
    request: Request,
    limiter: UnlockLimiter = Depends(get_unlock_limiter),
) -> JSONResponse:
    secret = require_dispatch_passcode()
    settings = get_settings()
    address = client_address(request)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid unlock body.") from None
    if not isinstance(body, dict) or not isinstance(body.get("passcode"), str):
        raise HTTPException(status_code=422, detail="Invalid unlock body.")
    outcome = limiter.verify_presented(address, settings, body["passcode"], secret)
    if outcome == "locked":
        raise HTTPException(
            status_code=429, detail="Too many unlock attempts. Try again later."
        )
    if outcome == "mismatch":
        raise HTTPException(
            status_code=401, detail="Unlock the desk to keep polling."
        )
    actor = mint_actor()
    response = JSONResponse({"ok": True})
    set_unlock_cookies(
        response,
        request,
        secret=secret,
        actor=actor,
        csrf=secrets.token_urlsafe(32),
    )
    return response
