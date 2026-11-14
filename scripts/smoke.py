#!/usr/bin/env python3
"""Opt-in live deployment check, never invoked by default CI as a live script.

One noisy sample starts two logical operations (Timbre then Prisma).
Server retries can make up to six provider attempts under issue 29's
two-retry cap per operation. This CLI never retries its sample POST.
There are no extra synthesis calls or application mock modes.
Unit tests replace the HTTP transport inside their test file only.
A valid no-key health response is a clean exit-0 skip. Configured deployments
must pass the request-id, readiness, unauthorized-error and cookie-auth checks
from issues 20/21/22/26 before the sample. Positive readiness credit units are
not assumed to equal provider-call costs. The server still enforces its budget.
After a charged timeout the conservative upper bound is not an exact bill.
Use --require-security-headers on the public deployment after issue 27 lands.
"""

from __future__ import annotations

import argparse
import ipaddress
import math
import os
import re
import sys
from collections.abc import Callable
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
INTENTS = frozenset(
    {"customer_unreachable", "address_issue", "item_missing", "delay", "accident_sos", "other"}
)
# Two logical operations, each with one initial attempt plus at most two
# server retries. Conservative even on deployments without issue 29 retries.
SAMPLE_LOGICAL_OPERATIONS = 2
DEFAULT_SERVER_RETRY_CAP = 2  # Published issue 29 default/max; never infer remote settings.


def server_retry_cap(value: object) -> int:
    try:
        cap = int(str(value))
    except ValueError:
        raise SmokeFailure("server retry cap must be an integer from 0 to 2") from None
    if not 0 <= cap <= DEFAULT_SERVER_RETRY_CAP:
        raise SmokeFailure("server retry cap must be an integer from 0 to 2")
    return cap


class SmokeFailure(Exception):
    """A safe, operator-facing failure without response bodies or credentials."""


def checked_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise SmokeFailure("invalid base URL") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SmokeFailure("base URL needs HTTP(S), without credentials, query or fragment")
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if parsed.scheme != "https" and not loopback:
        raise SmokeFailure("a non-local deployment must use HTTPS")
    if port is not None and not 1 <= port <= 65535:
        raise SmokeFailure("invalid base URL port")
    return value.rstrip("/") + "/"


class SmokeCheck:
    def __init__(
        self,
        client: httpx.Client,
        passcode: str,
        emit: Callable[[str], None] = print,
        *,
        max_server_retries: int = DEFAULT_SERVER_RETRY_CAP,
    ) -> None:
        self.client = client
        self.passcode = passcode
        self.emit = emit
        self.speech_calls_upper_bound = 0
        self.provider_attempts_bound = SAMPLE_LOGICAL_OPERATIONS * (
            1 + server_retry_cap(max_server_retries)
        )
        self._redactions = tuple(
            value
            for value in (
                passcode,
                os.environ.get("GNANI_API_KEY", ""),
            )
            if value
        )

    def say(self, value: str) -> None:
        for secret in self._redactions:
            value = value.replace(secret, "[redacted]")
        self.emit(value)

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        request_id = str(uuid4())
        headers = {"X-Request-ID": request_id, **kwargs.pop("headers", {})}
        try:
            response = self.client.request(method, path, headers=headers, **kwargs)
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            self.say(f"{method} {path} request_id={request_id}")
            raise SmokeFailure("HTTP request failed; no retry was made") from exc
        returned_id = response.headers.get("X-Request-ID")
        if returned_id is not None and not SAFE_ID.fullmatch(returned_id):
            raise SmokeFailure("response contains an invalid X-Request-ID")
        self.say(
            f"{method} {path} status={response.status_code} "
            f"request_id={returned_id or 'not_available'}"
        )
        return response

    @staticmethod
    def body(response: httpx.Response) -> dict:
        try:
            value = response.json()
        except ValueError as exc:
            raise SmokeFailure("expected a JSON response") from exc
        if not isinstance(value, dict):
            raise SmokeFailure("expected a JSON object")
        return value

    @staticmethod
    def status(response: httpx.Response, expected: int) -> None:
        if response.status_code != expected:
            raise SmokeFailure(f"expected HTTP {expected}, got {response.status_code}")

    @staticmethod
    def request_id(response: httpx.Response) -> str:
        value = response.headers.get("X-Request-ID", "")
        if not SAFE_ID.fullmatch(value):
            raise SmokeFailure("X-Request-ID is missing; issue 21 must be deployed")
        return value

    @staticmethod
    def security_headers(response: httpx.Response) -> None:
        if (
            not response.headers.get("Content-Security-Policy", "").strip()
            or response.headers.get("X-Content-Type-Options", "").lower() != "nosniff"
        ):
            raise SmokeFailure("CSP or nosniff header is missing; check issue 27")

    def run(self, *, require_security_headers: bool = False) -> str:
        self.say(f"base_url={self.client.base_url}")
        self.client.cookies.clear()
        health = self.request("GET", "api/health")
        self.status(health, 200)
        payload = self.body(health)
        if payload.get("ok") is not True:
            raise SmokeFailure("health does not confirm a live process")
        if payload.get("gnani_key_set") is False:
            self.say("skipped: remote Gnani key is not set; no speech calls")
            return "skipped"
        if payload.get("gnani_key_set") is not True:
            raise SmokeFailure("health does not confirm a configured speech path")
        self.request_id(health)
        if not self.passcode:
            raise SmokeFailure("DISPATCH_PASSCODE must be set locally before live checks")
        if require_security_headers:
            self.security_headers(health)
            page = self.request("GET", "")
            self.status(page, 200)
            self.security_headers(page)

        ready_response = self.request("GET", "api/ready")
        self.status(ready_response, 200)
        self.request_id(ready_response)
        ready = self.body(ready_response)
        budget = ready.get("demo_credits_remaining")
        remaining = budget.get("remaining") if isinstance(budget, dict) else budget
        limiter = ready.get("rate_limit")
        if (
            ready.get("ok") is not True
            or ready.get("gnani_key_set") is not True
            or ready.get("db_writable") is not True
            or ready.get("demo_credits_exhausted") is not False
            or isinstance(remaining, bool)
            or not isinstance(remaining, (int, float))
            or (isinstance(remaining, float) and not math.isfinite(remaining))
            or remaining <= 0
            or not isinstance(limiter, dict)
            or limiter.get("ok") is not True
        ):
            raise SmokeFailure("readiness does not confirm DB, limiter and available demo budget")

        denied = self.request("GET", "api/events")
        self.status(denied, 401)
        rid = self.request_id(denied)
        error = self.body(denied).get("error")
        if (
            not isinstance(error, dict)
            or error.get("code") != "unauthorized"
            or not isinstance(error.get("message"), str)
            or not error["message"]
            or error.get("request_id") != rid
        ):
            raise SmokeFailure("unauthorized error envelope differs from issue 26")

        challenge = self.request("GET", "api/dispatch/csrf")
        self.status(challenge, 200)
        token = self.body(challenge).get("csrf_token")
        if not isinstance(token, str) or not token:
            raise SmokeFailure("desk CSRF challenge missing")
        unlock = self.request(
            "POST",
            "api/dispatch/unlock",
            json={"passcode": self.passcode},
            headers={"X-Dispatch-CSRF": token},
        )
        if unlock.status_code not in {200, 204}:
            raise SmokeFailure(f"desk unlock failed with HTTP {unlock.status_code}")
        self.request_id(unlock)
        authenticated = self.request("GET", "api/events")
        self.status(authenticated, 200)
        self.request_id(authenticated)
        if not isinstance(self.body(authenticated).get("events"), list):
            raise SmokeFailure("authenticated desk list is not an events envelope")

        # From this point a timeout can have spent calls; report the upper bound,
        # never retry the charged POST or claim an unknown actual charge is zero.
        self.speech_calls_upper_bound = self.provider_attempts_bound
        sample = self.request(
            "POST",
            "api/ingest/sample",
            params={"condition": "noisy"},
            headers={"Idempotency-Key": str(uuid4())},
        )
        self.status(sample, 200)
        self.request_id(sample)
        outer = self.body(sample)
        record = outer.get("ingest")
        if outer.get("condition") != "noisy" or not isinstance(record, dict):
            raise SmokeFailure("expected the noisy sample envelope from issue 09")
        event, stt = record.get("event"), record.get("stt")
        if not isinstance(event, dict) or not isinstance(stt, dict):
            raise SmokeFailure("sample lacks event or STT metadata")
        gnani_id = stt.get("request_id")
        if not isinstance(gnani_id, str) or not SAFE_ID.fullmatch(gnani_id):
            raise SmokeFailure("sample lacks a non-empty provider request ID")
        if not isinstance(event.get("transcript"), str) or not event["transcript"].strip():
            raise SmokeFailure("sample transcript is empty")
        intent = event.get("intent")
        if intent != "customer_unreachable" or event.get("order_id") != "18":
            safe_intent = intent if isinstance(intent, str) and intent in INTENTS else "invalid"
            raise SmokeFailure(f"unexpected sample event: intent={safe_intent}; expected order 18")
        try:
            event_id = str(UUID(record["id"]))
            created = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                raise ValueError("naive timestamp")
            cutoff = created - timedelta(microseconds=1)
        except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
            raise SmokeFailure("sample ID or created_at is invalid") from exc
        self.say(f"event_id={event_id} intent={intent} gnani_request_id={gnani_id}")
        listed = self.request(
            "GET", "api/events", params={"since": cutoff.isoformat(), "limit": 200}
        )
        self.status(listed, 200)
        self.request_id(listed)
        events = self.body(listed).get("events")
        if not isinstance(events, list) or not any(
            isinstance(row, dict) and row.get("id") == event_id for row in events
        ):
            raise SmokeFailure("new sample event is absent from the authenticated desk")
        self.say("passed: one noisy sample reached the protected desk")
        return "passed"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="API base URL; non-local hosts require HTTPS",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="per-request timeout in seconds (default 30, at most 120)",
    )
    parser.add_argument(
        "--require-security-headers",
        action="store_true",
        help="require CSP and nosniff on / and health after issue 27",
    )
    parser.add_argument(
        "--server-max-retries",
        default=(
            os.environ.get("RASTA_UPSTREAM_MAX_RETRIES", "").strip()
            or str(DEFAULT_SERVER_RETRY_CAP)
        ),
        help="verified remote retry cap (0..2); env RASTA_UPSTREAM_MAX_RETRIES or default 2",
    )
    args = parser.parse_args(argv)
    try:
        retry_cap = server_retry_cap(args.server_max_retries)
        base = checked_base_url(args.base_url)
        if not math.isfinite(args.timeout) or not 0 < args.timeout <= 120:
            raise SmokeFailure("timeout must be finite and between 0 and 120 seconds")
    except SmokeFailure as exc:
        print(f"failed: {exc}")
        print("speech_calls_upper_bound=0")
        return 1
    try:
        client = httpx.Client(base_url=base, timeout=args.timeout, follow_redirects=False)
    except (ImportError, httpx.HTTPError, ValueError, UnicodeError):
        print("failed: HTTP client setup failed")
        print("speech_calls_upper_bound=0")
        return 1
    with client:
        check = SmokeCheck(
            client,
            os.environ.get("DISPATCH_PASSCODE", "").strip(),
            max_server_retries=retry_cap,
        )
        try:
            check.run(require_security_headers=args.require_security_headers)
        except SmokeFailure as exc:
            check.say(f"failed: {exc}")
            return 1
        finally:
            check.say(f"speech_calls_upper_bound={check.speech_calls_upper_bound}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
