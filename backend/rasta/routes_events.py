"""Dispatch event list for the desk slate."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from rasta.dispatch_auth import (
    UnlockLimiter,
    client_address,
    get_unlock_limiter,
    mint_actor,
    passcodes_match,
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


@events_router.post("/api/dispatch/unlock")
async def unlock_desk(
    request: Request,
    limiter: UnlockLimiter = Depends(get_unlock_limiter),
) -> JSONResponse:
    secret = require_dispatch_passcode()
    settings = get_settings()
    address = client_address(request)
    if limiter.blocked(address, settings):
        raise HTTPException(
            status_code=429, detail="Too many unlock attempts. Try again later."
        )
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid unlock body.") from None
    if not isinstance(body, dict) or not isinstance(body.get("passcode"), str):
        raise HTTPException(status_code=422, detail="Invalid unlock body.")
    if not passcodes_match(body["passcode"], secret):
        limiter.record_failure(address, settings)
        raise HTTPException(
            status_code=401, detail="Unlock the desk to keep polling."
        )
    limiter.clear(address)
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
