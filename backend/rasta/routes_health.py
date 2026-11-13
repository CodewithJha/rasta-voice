"""Readiness probe. Liveness stays on GET /api/health in main.py."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gnani_client.env import api_key
from rasta import readiness

health_router = APIRouter()


@health_router.get("/api/ready")
def ready(request: Request) -> JSONResponse:
    """Report whether this process should stay in the host's rotation.

    A missing Gnani key or a spent / not-yet-deployed credit budget stays
    HTTP 200 so a misconfigured Space does not flap. HTTP 503 only when a
    configured durable store exists and cannot be written.
    """
    db_writable = readiness.check_db_writable()
    remaining, exhausted, rate_limit = readiness.limiter_fields(request.app)
    ok = db_writable is not False
    body = {
        "ok": ok,
        "gnani_key_set": bool(api_key()),
        "db_writable": db_writable,
        "rate_limit": rate_limit,
        "demo_credits_remaining": remaining,
        "demo_credits_exhausted": exhausted,
        "schema_version": readiness.schema_version(),
        "circuit_breaker": readiness.circuit_breaker(request.app),
        "events_in_store": readiness.events_in_store(request.app),
    }
    return JSONResponse(body, status_code=200 if ok else 503)
