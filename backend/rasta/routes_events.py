"""Dispatch event list for the desk slate."""

from fastapi import APIRouter, Depends, HTTPException, Request

from rasta.store import EventStore, InvalidSince, attach_event_store

events_router = APIRouter()


def get_event_store(request: Request) -> EventStore:
    return attach_event_store(request.app)


@events_router.get("/api/events")
def list_events(
    since: str | None = None,
    store: EventStore = Depends(get_event_store),
) -> dict:
    try:
        events = store.list_since(since)
    except InvalidSince as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"events": events}
