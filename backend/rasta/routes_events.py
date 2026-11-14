"""Dispatch event list for the desk slate."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from rasta.dispatch_auth import (
    COOKIE_UNLOCK_CSRF,
    UNLOCK_CSRF_SECONDS,
    UnlockLimiter,
    client_address,
    cookie_secure,
    get_unlock_limiter,
    mint_actor,
    mint_unlock_csrf,
    require_desk_read,
    require_desk_write,
    require_dispatch_passcode,
    set_unlock_cookies,
)
from rasta.settings import get_settings
from rasta.store import (
    EventNotFound,
    EventStore,
    IllegalTransition,
    InvalidSince,
    VersionConflict,
    attach_event_store,
    normalize_actor,
    parse_if_match,
)

events_router = APIRouter()


def get_event_store(request: Request) -> EventStore:
    return attach_event_store(request.app)


@events_router.get("/api/events")
def list_events(
    since: str | None = None,
    updated_since: str | None = None,
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_read),
) -> dict:
    store.escalate_overdue(get_settings().sos_ack_seconds)
    try:
        if updated_since:
            events = store.list_updated_since(updated_since)
        else:
            events = store.list_since(since)
    except InvalidSince as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"events": events}


@events_router.get("/api/events/{event_id}")
def get_event(
    event_id: str,
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_read),
) -> dict:
    store.escalate_overdue(get_settings().sos_ack_seconds)
    record = store.get(event_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return record


@events_router.get("/api/dispatch/csrf")
def unlock_csrf(request: Request) -> JSONResponse:
    token = mint_unlock_csrf(require_dispatch_passcode())
    response = JSONResponse({"csrf_token": token}, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        COOKIE_UNLOCK_CSRF,
        token,
        httponly=True,
        secure=cookie_secure(request),
        samesite="strict",
        path="/",
        max_age=UNLOCK_CSRF_SECONDS,
    )
    return response


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
        raise HTTPException(status_code=429, detail="Too many unlock attempts. Try again later.")
    if outcome == "mismatch":
        raise HTTPException(status_code=401, detail="Unlock the desk to keep polling.")
    actor = mint_actor()
    response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(
        COOKIE_UNLOCK_CSRF,
        path="/",
        secure=cookie_secure(request),
        httponly=True,
        samesite="strict",
    )
    set_unlock_cookies(
        response,
        request,
        secret=secret,
        actor=actor,
    )
    return response


def _workflow_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EventNotFound):
        return HTTPException(status_code=404, detail="Event not found.")
    if isinstance(exc, VersionConflict):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc), "version": exc.version},
        )
    if isinstance(exc, IllegalTransition):
        return HTTPException(
            status_code=409,
            detail={"code": exc.code, "message": str(exc), "state": exc.state},
        )
    raise exc


def _resolve_actor(
    request: Request,
    body_actor: str | None,
    session_actor: str,
    secret: str,
) -> tuple[str, bool]:
    """Return (actor, minted). A minted actor should be written to the desk cookie."""
    requested = normalize_actor(body_actor)
    if requested:
        return requested, False
    if session_actor and session_actor != "d_header":
        return session_actor, False
    return mint_actor(), True


async def _read_actor_body(request: Request) -> dict:
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        return {}
    try:
        raw = await request.body()
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        import json

        body = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid workflow body.") from None
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Invalid workflow body.")
    return body


def _apply_workflow(
    request: Request,
    store: EventStore,
    event_id: str,
    action: str,
    actor: str,
    if_match_header: str | None,
    also_ack: bool,
) -> dict:
    matched = parse_if_match(if_match_header)
    if matched is None:
        raise HTTPException(status_code=428, detail="If-Match is required.")
    try:
        return store.transition(
            event_id,
            action=action,
            actor=actor,
            if_match=matched,
            also_ack=also_ack,
        )
    except (EventNotFound, VersionConflict, IllegalTransition) as exc:
        raise _workflow_error(exc) from exc


@events_router.post("/api/events/{event_id}/ack")
async def ack_event(
    event_id: str,
    request: Request,
    store: EventStore = Depends(get_event_store),
    actor: str = Depends(require_desk_write),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    body = await _read_actor_body(request)
    secret = require_dispatch_passcode()
    raw_actor = body.get("actor") if isinstance(body.get("actor"), str) else None
    resolved, minted = _resolve_actor(request, raw_actor, actor, secret)
    record = _apply_workflow(request, store, event_id, "ack", resolved, if_match, False)
    response = JSONResponse(record)
    if minted:
        set_unlock_cookies(
            response,
            request,
            secret=secret,
            actor=resolved,
        )
    return response


@events_router.post("/api/events/{event_id}/escalate")
async def escalate_event(
    event_id: str,
    request: Request,
    store: EventStore = Depends(get_event_store),
    actor: str = Depends(require_desk_write),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    body = await _read_actor_body(request)
    secret = require_dispatch_passcode()
    raw_actor = body.get("actor") if isinstance(body.get("actor"), str) else None
    resolved, minted = _resolve_actor(request, raw_actor, actor, secret)
    record = _apply_workflow(request, store, event_id, "escalate", resolved, if_match, False)
    response = JSONResponse(record)
    if minted:
        set_unlock_cookies(
            response,
            request,
            secret=secret,
            actor=resolved,
        )
    return response


@events_router.post("/api/events/{event_id}/resolve")
async def resolve_event(
    event_id: str,
    request: Request,
    store: EventStore = Depends(get_event_store),
    actor: str = Depends(require_desk_write),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> JSONResponse:
    body = await _read_actor_body(request)
    secret = require_dispatch_passcode()
    raw_actor = body.get("actor") if isinstance(body.get("actor"), str) else None
    resolved, minted = _resolve_actor(request, raw_actor, actor, secret)
    also_ack = bool(body.get("ack"))
    record = _apply_workflow(request, store, event_id, "resolve", resolved, if_match, also_ack)
    response = JSONResponse(record)
    if minted:
        set_unlock_cookies(
            response,
            request,
            secret=secret,
            actor=resolved,
        )
    return response


@events_router.get("/api/events/{event_id}/audit")
def event_audit(
    event_id: str,
    store: EventStore = Depends(get_event_store),
    _actor: str = Depends(require_desk_read),
) -> dict:
    if store.get(event_id) is None and not store.list_audit(event_id):
        raise HTTPException(status_code=404, detail="Event not found.")
    return {"audit": store.list_audit(event_id)}
