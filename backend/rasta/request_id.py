"""Request IDs and JSON Gnani call logs (issue 21)."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from gnani_client.errors import GnaniError, MissingApiKeyError
from gnani_client.wav import wav_duration_seconds
from rasta.settings import get_settings

REQUEST_ID_HEADER = "X-Request-ID"
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
GNANI_LOGGER = "rasta"

_request_id: ContextVar[str | None] = ContextVar("rasta_request_id", default=None)

_RESERVED_LOG_KEYS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "message",
        "taskName",
    }
)

# Never copy these extras into a log line, even if a caller passes them.
_REDACT_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "passcode",
        "api_key",
        "api-key",
        "gnani_api_key",
        "groq_api_key",
        "gemini_api_key",
        "dispatch_passcode",
        "csrf",
        "body",
        "audio",
        "audio_base64",
        "transcript",
        "wav",
    }
)

def resolve_request_id(raw: str | None) -> str:
    """Return a safe incoming id, or mint a uuid4 if it is missing or unsafe."""
    if raw is None:
        return str(uuid.uuid4())
    candidate = raw.strip()
    if SAFE_REQUEST_ID.fullmatch(candidate):
        return candidate
    return str(uuid.uuid4())


def current_request_id() -> str | None:
    return _request_id.get()


def bind_request_id(value: str):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def request_id_from_headers(headers: list[tuple[bytes, bytes]]) -> str:
    for name, value in headers:
        if name.lower() == b"x-request-id":
            try:
                return resolve_request_id(value.decode("ascii"))
            except UnicodeDecodeError:
                return resolve_request_id(None)
    return resolve_request_id(None)


class RequestIdMiddleware:
    """Bind and echo ``X-Request-ID`` on HTTP responses and WebSocket accepts."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        rid = request_id_from_headers(scope.get("headers") or [])
        token = bind_request_id(rid)
        header = (b"x-request-id", rid.encode("ascii"))

        async def send_with_id(message: dict) -> None:
            if message["type"] in {"http.response.start", "websocket.accept"}:
                headers = list(message.get("headers") or [])
                headers = [pair for pair in headers if pair[0].lower() != b"x-request-id"]
                headers.append(header)
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            reset_request_id(token)


class JsonLogFormatter(logging.Formatter):
    """Format a log record as one JSON object. Unknown extras are kept."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_KEYS or key in payload:
                continue
            if key.lower() in _REDACT_KEYS:
                continue
            if isinstance(value, (bytes, bytearray, memoryview)):
                continue
            payload[key] = value
        return _bounded_json(payload)


def _bounded_json(payload: dict[str, Any]) -> str:
    try:
        limit = get_settings().log_line_max_bytes
    except Exception:
        limit = 4096
    line = json.dumps(payload, default=str, ensure_ascii=True, separators=(",", ":"))
    if len(line.encode("utf-8")) <= limit:
        return line
    stub = {
        "level": payload.get("level"),
        "logger": payload.get("logger"),
        "message": "log line truncated",
        "request_id": payload.get("request_id"),
        "truncated": True,
    }
    stub_line = json.dumps(stub, default=str, ensure_ascii=True, separators=(",", ":"))
    if len(stub_line.encode("utf-8")) <= limit:
        return stub_line
    return json.dumps({"message": "log line truncated", "truncated": True})


def configure_rasta_logging() -> None:
    """Attach a JSON stdout handler to ``rasta`` once."""
    logger = logging.getLogger(GNANI_LOGGER)
    for handler in logger.handlers:
        if getattr(handler, "_rasta_json", False):
            return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    handler._rasta_json = True  # type: ignore[attr-defined]
    logger.addHandler(handler)
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)


def _status_from_exc(exc: BaseException) -> int | str:
    try:
        import httpx
    except ImportError:
        httpx = None  # type: ignore[assignment]
    if httpx is not None and isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, MissingApiKeyError):
        return "missing_key"
    if isinstance(exc, GnaniError) and exc.status is not None:
        return exc.status
    if isinstance(exc, GnaniError):
        return "error"
    return type(exc).__name__


def _gnani_request_id(result: Any) -> str | None:
    if result is None:
        return None
    value = getattr(result, "request_id", None)
    if isinstance(value, str) and value:
        return value
    return None


def log_gnani_call(
    *,
    endpoint: str,
    latency_ms: int,
    status: int | str,
    gnani_request_id: str | None = None,
    audio_seconds: float | None = None,
    **extra: Any,
) -> None:
    """Emit one JSON record for a Gnani call. Extra keys are preserved."""
    payload: dict[str, Any] = {
        "request_id": current_request_id(),
        "gnani_request_id": gnani_request_id,
        "endpoint": endpoint,
        "latency_ms": latency_ms,
        "status": status,
        "audio_seconds": audio_seconds,
    }
    for key, value in extra.items():
        if key.lower() in _REDACT_KEYS:
            continue
        if key not in payload:
            payload[key] = value
    logging.getLogger(GNANI_LOGGER).info("gnani_call", extra=payload)


def watch_gnani_call[T](
    endpoint: str,
    func: Callable[[], T],
    *,
    audio: bytes | None = None,
    audio_seconds: float | None = None,
    **extra: Any,
) -> T:
    """Run ``func`` and log one Gnani line, including on failure."""
    seconds = audio_seconds
    if seconds is None and audio is not None:
        seconds = wav_duration_seconds(audio)
    started = time.perf_counter()
    try:
        result = func()
    except Exception as exc:
        failed_seconds = seconds if not isinstance(exc, MissingApiKeyError) else None
        log_gnani_call(
            endpoint=endpoint,
            latency_ms=_elapsed_ms(started),
            status=_status_from_exc(exc),
            gnani_request_id=None,
            audio_seconds=failed_seconds,
            **extra,
        )
        raise
    if seconds is None and isinstance(result, (bytes, bytearray)):
        seconds = wav_duration_seconds(bytes(result))
    log_gnani_call(
        endpoint=endpoint,
        latency_ms=_elapsed_ms(started),
        status=200,
        gnani_request_id=_gnani_request_id(result),
        audio_seconds=seconds,
        **extra,
    )
    return result


def _elapsed_ms(started: float) -> int:
    return max(0, int(round((time.perf_counter() - started) * 1000)))
