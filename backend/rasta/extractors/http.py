"""Shared HTTP client and a single bounded retry for LLM calls.

This module uses the process-wide issue 29 client when one is attached,
or a fallback ``httpx.Client`` configured with ``LLM_TIMEOUT_SECONDS``.
The timeout is passed to httpx as ``timeout=``.

Retries stay bounded. 401 and 403 are never retried. Timeouts and
connection errors fall through to the caller without a retry, so a hung
free tier fails fast into the rules fallback. Issue 29 records LLM
success and failure on the ``llm`` breaker.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

from rasta.extractors.base import LlmError
from rasta.settings import Settings, get_settings

log = logging.getLogger("rasta")

RETRYABLE_STATUS = frozenset({429, *range(500, 600)})
NO_RETRY_STATUS = frozenset({401, 403})

_lock = threading.Lock()
_client: httpx.Client | None = None
_client_timeout: float | None = None


def build_client(
    settings: Settings | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    """Create a client whose timeout is the configured LLM budget."""
    cfg = settings or get_settings()
    timeout = httpx.Timeout(cfg.llm_timeout_seconds)
    if transport is not None:
        return httpx.Client(timeout=timeout, transport=transport)
    return httpx.Client(timeout=timeout)


def get_shared_client(settings: Settings | None = None) -> httpx.Client:
    """Return the process-wide client, creating it if needed.

    Prefer the issue 29 runtime client when it is attached. Otherwise the
    client is recreated if the configured timeout has changed, so a test
    cannot leave a stale 4-second budget after ``LLM_TIMEOUT_SECONDS``.
    """
    from rasta.resilience import get_upstream_runtime

    runtime = get_upstream_runtime()
    if runtime is not None and not runtime.client.is_closed:
        return runtime.client
    global _client, _client_timeout
    cfg = settings or get_settings()
    with _lock:
        if (
            _client is None
            or _client.is_closed
            or _client_timeout != cfg.llm_timeout_seconds
        ):
            if _client is not None and not _client.is_closed:
                _client.close()
            _client = build_client(cfg)
            _client_timeout = cfg.llm_timeout_seconds
        return _client


def close_shared_client() -> None:
    """Close the process-wide client. The FastAPI lifespan calls this."""
    global _client, _client_timeout
    with _lock:
        if _client is not None and not _client.is_closed:
            _client.close()
        _client = None
        _client_timeout = None


def resolve_client(
    client: httpx.Client | None,
    settings: Settings | None = None,
) -> httpx.Client:
    """Use the injected client, or the shared one."""
    return client if client is not None else get_shared_client(settings)


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    settings: Settings,
    sleeper: Callable[[float], None] = time.sleep,
    **kwargs: Any,
) -> httpx.Response:
    """Send one HTTP request, retrying at most once on 429 or 5xx.

    Does not log the URL query (keys must not be placed there), the
    request body, or the response body.
    """
    from rasta.resilience import UPSTREAM_LLM, get_upstream_runtime

    runtime = get_upstream_runtime()
    if runtime is not None:
        breaker = runtime.breakers[UPSTREAM_LLM]
        if not breaker.allow():
            runtime.publish()
            raise LlmError("LLM circuit is open", reason="circuit_open")

    attempts = settings.llm_max_retries + 1
    last_error: LlmError | None = None
    for index in range(attempts):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            _record_llm(success=False)
            raise LlmError("LLM call timed out", reason="timeout") from exc
        except httpx.RequestError as exc:
            _record_llm(success=False)
            raise LlmError("LLM connection failed", reason="connection_error") from exc

        status = response.status_code
        if status == 200:
            _record_llm(success=True)
            return response
        reason = f"http_{status}"
        error = LlmError(f"LLM HTTP {status}", reason=reason)
        if status in NO_RETRY_STATUS:
            _record_llm(success=False)
            raise error
        if status in RETRYABLE_STATUS and index < attempts - 1:
            delay = settings.llm_retry_backoff_seconds * (2**index)
            log.warning("LLM HTTP %s, retrying once", status)
            if delay > 0:
                sleeper(delay)
            last_error = error
            continue
        _record_llm(success=False)
        raise error
    assert last_error is not None
    _record_llm(success=False)
    raise last_error


def _record_llm(*, success: bool) -> None:
    from rasta.resilience import get_upstream_runtime

    runtime = get_upstream_runtime()
    if runtime is None:
        return
    if success:
        runtime.record_llm_success()
    else:
        runtime.record_llm_failure()
