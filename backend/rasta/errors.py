"""Stable JSON error envelope for every API 4xx/5xx (issue 26)."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gnani_client.errors import GnaniError, MissingApiKeyError
from rasta.request_id import current_request_id
from rasta.security import SecuredApp

SAFE_STATUS_CODES = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "idempotency_conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    428: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    501: "not_implemented",
    502: "upstream_error",
    503: "unavailable",
    504: "timeout",
}


def error_body(
    code: str,
    message: str,
    *,
    request_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the public ``{"error": {...}}`` object. Never include secrets."""
    rid = request_id if request_id is not None else (current_request_id() or "")
    payload: dict[str, Any] = {
        "code": str(code),
        "message": str(message),
        "request_id": rid,
    }
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return {"error": payload}


def error_json_response(status: int, code: str, message: str, **extra: Any):
    from starlette.responses import JSONResponse

    return JSONResponse(error_body(code, message, **extra), status_code=status)


def code_for_status(status: int, message: str = "", existing: str | None = None) -> str:
    if existing:
        return existing
    if status == 503 and _looks_like_missing_api_key(message):
        return "missing_api_key"
    return SAFE_STATUS_CODES.get(status, "internal_error")


def _looks_like_missing_api_key(message: str) -> bool:
    lower = message.lower()
    return "gnani_api_key" in lower or "api key is not set" in lower


def gnani_http_exception(exc: GnaniError) -> HTTPException:
    """Map a Gnani failure to the issue 26 statuses and codes."""
    status = exc.status
    if status == 429:
        return HTTPException(
            status_code=429,
            detail={
                "code": "upstream_rate_limited",
                "message": "The speech service is rate limited.",
                "upstream_status": status,
            },
        )
    if status == 402:
        return HTTPException(
            status_code=503,
            detail={
                "code": "upstream_out_of_credit",
                "message": "The speech service is out of credit.",
                "upstream_status": status,
            },
        )
    return HTTPException(
        status_code=502,
        detail={
            "code": "upstream_error",
            "message": "The speech service failed.",
            "upstream_status": status,
        },
    )


def missing_key_http_exception(exc: MissingApiKeyError) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={"code": "missing_api_key", "message": str(exc)},
    )


def envelope_from_detail(status: int, detail: Any) -> dict[str, Any]:
    """Turn a FastAPI/Starlette ``detail`` value into the public envelope."""
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        inner = dict(detail["error"])
        existing_message = str(inner.get("message") or "")
        code = str(inner.pop("code", "") or code_for_status(status, existing_message))
        message = str(inner.pop("message", "") or "Request failed.")
        inner.pop("request_id", None)
        return error_body(code, message, **inner)

    if isinstance(detail, dict):
        # Already-structured details from issue 25 / resilience, or the older
        # ``{"error": "…", "upstream_status": …}`` speech shape.
        existing = detail.get("code")
        if isinstance(existing, str) and existing:
            message = str(detail.get("message") or "Request failed.")
            extra = {
                key: value
                for key, value in detail.items()
                if key not in {"code", "message", "request_id"}
            }
            return error_body(existing, message, **extra)
        raw = detail.get("error")
        message = raw if isinstance(raw, str) and raw else "Request failed."
        extra = {
            key: value
            for key, value in detail.items()
            if key not in {"error", "code", "message", "request_id"}
        }
        return error_body(code_for_status(status, message), message, **extra)

    if isinstance(detail, str) and detail.strip():
        return error_body(code_for_status(status, detail), detail)

    if isinstance(detail, list):
        return error_body("validation_error", "Request validation failed.")

    return error_body(code_for_status(status), "Request failed.")


def _path_of(scope: Scope) -> str:
    return str(scope.get("path") or "")


def _is_readiness_document(path: str, payload: Any) -> bool:
    # Issue 22 readiness 503 is a probe document, not an API error envelope.
    if path in {"/api/ready", "/api/v1/ready"}:
        return True
    return (
        isinstance(payload, dict)
        and "db_writable" in payload
        and "schema_version" in payload
    )


def _rewrite_error_bytes(status: int, body: bytes) -> bytes | None:
    if not body:
        payload = error_body(code_for_status(status), _default_message(status))
        return json.dumps(payload).encode("utf-8")
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = error_body(code_for_status(status), _default_message(status))
        return json.dumps(payload).encode("utf-8")
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        inner = parsed["error"]
        if "request_id" not in inner or not inner.get("request_id"):
            inner = {**inner, "request_id": current_request_id() or ""}
            parsed = {"error": inner}
        return json.dumps(parsed).encode("utf-8")
    if isinstance(parsed, dict) and "detail" in parsed:
        return json.dumps(envelope_from_detail(status, parsed["detail"])).encode("utf-8")
    if isinstance(parsed, dict) and "code" in parsed and "message" in parsed:
        extra = {
            key: value
            for key, value in parsed.items()
            if key not in {"code", "message", "request_id"}
        }
        return json.dumps(
            error_body(str(parsed["code"]), str(parsed["message"]), **extra)
        ).encode("utf-8")
    return json.dumps(envelope_from_detail(status, parsed)).encode("utf-8")


def _default_message(status: int) -> str:
    if status == 404:
        return "Not found."
    if status == 500:
        return "Internal server error."
    return "Request failed."


class V1Alias:
    """Expose /api/v1/... as the same handlers as /api/..."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            path = str(scope.get("path") or "")
            if path == "/api/v1" or path.startswith("/api/v1/"):
                new_path = "/api" + path[len("/api/v1") :]
                scope = dict(scope)
                scope["path"] = new_path
                raw = scope.get("raw_path")
                if isinstance(raw, (bytes, bytearray)):
                    prefix = b"/api/v1"
                    if raw == prefix or raw.startswith(prefix + b"/"):
                        suffix = raw[len(prefix) :]
                        scope["raw_path"] = b"/api" + suffix
        await self.app(scope, receive, send)


class ErrorEnvelope:
    """Rewrite JSON (and empty) 4xx/5xx bodies into the public envelope."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = _path_of(scope)
        start: dict[str, Any] | None = None
        chunks = bytearray()

        async def send_filtered(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = {**message, "headers": list(message.get("headers") or [])}
                return
            if message["type"] != "http.response.body":
                await send(message)
                return
            chunks.extend(message.get("body") or b"")
            if message.get("more_body"):
                return
            assert start is not None
            status = int(start.get("status") or 200)
            payload: Any = None
            if status >= 400 and chunks:
                try:
                    payload = json.loads(bytes(chunks))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = None
            if status < 400 or _is_readiness_document(path, payload):
                await send(start)
                await send(
                    {"type": "http.response.body", "body": bytes(chunks), "more_body": False}
                )
                return
            rewritten = _rewrite_error_bytes(status, bytes(chunks))
            assert rewritten is not None
            headers = [
                (name, value)
                for name, value in start["headers"]
                if name.lower() not in {b"content-length", b"content-type"}
            ]
            headers.append((b"content-type", b"application/json"))
            headers.append((b"content-length", str(len(rewritten)).encode("ascii")))
            await send({**start, "headers": headers})
            await send({"type": "http.response.body", "body": rewritten, "more_body": False})

        await self.app(scope, receive, send_filtered)


class ContractApp(SecuredApp):
    """Request IDs and security headers enclose the error envelope and FastAPI."""

    def build_middleware_stack(self) -> ASGIApp:
        from rasta.idempotency import IdempotencyMiddleware

        return V1Alias(
            IdempotencyMiddleware(ErrorEnvelope(super().build_middleware_stack()))
        )


def install_validation_handler(application: ContractApp) -> None:
    """Keep FastAPI 422s going through the same detail-to-envelope path."""

    @application.exception_handler(RequestValidationError)
    async def _validation(_request, exc: RequestValidationError):
        from starlette.responses import JSONResponse

        return JSONResponse(
            error_body("validation_error", "Request validation failed."),
            status_code=422,
        )
