"""No live calls: transport replacement is confined to this test module."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "smoke.py"
spec = importlib.util.spec_from_file_location("rasta_smoke_cli", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

EVENT_ID = "716cc3e3-7fb1-4dc0-a655-d1c4d20b4da8"
PASSCODE = "synthetic-local-test-only"


class Service:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.unlocked = False
        self.key_set = True
        self.health_ok = True
        self.ready_status = 200
        self.ready = {
            "ok": True,
            "gnani_key_set": True,
            "db_writable": True,
            "rate_limit": {"ok": True},
            "demo_credits_remaining": 40,
            "demo_credits_exhausted": False,
        }
        self.intent = "customer_unreachable"
        self.request_id = "synthetic-provider-request"
        self.transcript = "Synthetic input only"
        self.include_event = True
        self.public_desk = False
        self.error_envelope = True
        self.unlock_status = 200
        self.sample_status = 200
        self.timeout = False
        self.headers = True
        self.security = True

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        rid = request.headers["X-Request-ID"]
        headers = {"X-Request-ID": rid} if self.headers else {}
        if self.security:
            headers.update(
                {
                    "Content-Security-Policy": "default-src 'self'",
                    "X-Content-Type-Options": "nosniff",
                }
            )
        path = request.url.path
        status, body = 200, {}
        if path == "/":
            return httpx.Response(200, text="Synthetic test page", headers=headers)
        if path == "/api/health":
            body = {"ok": self.health_ok, "gnani_key_set": self.key_set, "llm_provider": "rules"}
        elif path == "/api/ready":
            status, body = self.ready_status, self.ready
        elif path == "/api/dispatch/csrf":
            body = {"csrf_token": "synthetic-test-csrf"}
            headers["Set-Cookie"] = "rasta_unlock_csrf=synthetic-test-csrf; Path=/; HttpOnly"
        elif path == "/api/dispatch/unlock":
            assert request.headers.get("X-Dispatch-CSRF") == "synthetic-test-csrf"

            status = self.unlock_status
            self.unlocked = status == 200
            headers["Set-Cookie"] = "rasta_desk=synthetic-session; Path=/; HttpOnly; SameSite=Lax"
        elif path == "/api/events":
            if not self.unlocked and not self.public_desk:
                status = 401
                body = (
                    {
                        "error": {
                            "code": "unauthorized",
                            "message": "Unlock the desk",
                            "request_id": rid,
                        }
                    }
                    if self.error_envelope
                    else {"detail": "locked"}
                )
            else:
                if self.unlocked:
                    assert "rasta_desk=synthetic-session" in request.headers.get("Cookie", "")
                body = {"events": [{"id": EVENT_ID}] if self.include_event else []}
        elif path == "/api/ingest/sample":
            assert request.url.params["condition"] == "noisy"
            assert "Idempotency-Key" in request.headers
            if self.timeout:
                raise httpx.ReadTimeout("synthetic timeout", request=request)
            status = self.sample_status
            body = {
                "condition": "noisy",
                "audio_base64": "synthetic-test-audio",
                "ingest": {
                    "id": EVENT_ID,
                    "created_at": "2026-11-13T00:00:01+00:00",
                    "stt": {"request_id": self.request_id},
                    "event": {
                        "intent": self.intent,
                        "order_id": "18",
                        "transcript": self.transcript,
                    },
                },
            }
        else:
            raise AssertionError(f"unexpected route: {path}")
        return httpx.Response(status, json=body, headers=headers)


def run(service: Service, *, passcode=PASSCODE, strict=False):
    output = []
    with httpx.Client(
        base_url="http://127.0.0.1:8000/",
        transport=httpx.MockTransport(service),
        follow_redirects=False,
    ) as client:
        check = smoke.SmokeCheck(client, passcode, output.append)
        outcome = check.run(require_security_headers=strict)
    return outcome, check, "\n".join(output)


def speech_requests(service):
    return [r for r in service.requests if r.url.path == "/api/ingest/sample"]


@pytest.mark.parametrize("cap", [0, 1, 2])
def test_explicit_remote_retry_cap_controls_the_bound_without_extra_posts(cap):
    service = Service()
    with httpx.Client(
        base_url="http://localhost/", transport=httpx.MockTransport(service)
    ) as client:
        check = smoke.SmokeCheck(client, PASSCODE, lambda _line: None, max_server_retries=cap)
        assert check.run() == "passed"
    assert check.speech_calls_upper_bound == smoke.SAMPLE_LOGICAL_OPERATIONS * (1 + cap)
    assert len(speech_requests(service)) == 1


@pytest.mark.parametrize("cap", ["-1", "3", "nan", "secret-invalid-cap"])
def test_invalid_retry_cap_fails_before_http_without_echoing_input(cap, capsys):
    assert smoke.main(["--server-max-retries", cap]) == 1
    output = capsys.readouterr().out
    assert "speech_calls_upper_bound=0" in output
    assert cap not in output


@pytest.mark.parametrize("cli_cap, expected_cap", [(None, 1), ("0", 0)])
def test_cli_uses_operator_retry_cap_and_flag_overrides_env(
    monkeypatch, capsys, cli_cap, expected_cap
):
    service = Service()
    real_client = httpx.Client
    monkeypatch.setattr(
        smoke.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(service)),
    )
    monkeypatch.setenv("DISPATCH_PASSCODE", PASSCODE)
    monkeypatch.setenv("RASTA_UPSTREAM_MAX_RETRIES", "1")
    argv = [] if cli_cap is None else ["--server-max-retries", cli_cap]
    assert smoke.main(argv) == 0
    bound = smoke.SAMPLE_LOGICAL_OPERATIONS * (1 + expected_cap)
    assert f"speech_calls_upper_bound={bound}" in capsys.readouterr().out
    assert len(speech_requests(service)) == 1


@pytest.mark.parametrize("value, expected_cap", [("", 2), ("   ", 2), ("0", 0)])
def test_empty_example_retry_setting_uses_conservative_bound(
    monkeypatch, capsys, value, expected_cap
):
    service = Service()
    real_client = httpx.Client
    monkeypatch.setattr(
        smoke.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(service)),
    )
    monkeypatch.setenv("DISPATCH_PASSCODE", PASSCODE)
    monkeypatch.setenv("RASTA_UPSTREAM_MAX_RETRIES", value)
    assert smoke.main([]) == 0
    bound = smoke.SAMPLE_LOGICAL_OPERATIONS * (1 + expected_cap)
    assert f"speech_calls_upper_bound={bound}" in capsys.readouterr().out
    assert len(speech_requests(service)) == 1


def test_success_uses_one_paid_sample_and_checks_the_protected_desk():
    service = Service()
    outcome, check, output = run(service, strict=True)
    assert outcome == "passed"
    assert check.speech_calls_upper_bound == smoke.SAMPLE_LOGICAL_OPERATIONS * (
        1 + smoke.DEFAULT_SERVER_RETRY_CAP
    )
    assert len(speech_requests(service)) == 1
    assert EVENT_ID in output and "synthetic-provider-request" in output
    assert PASSCODE not in output and service.transcript not in output
    query = service.requests[-1].url.params
    assert query["since"] == "2026-11-13T00:00:00.999999+00:00"
    assert query["limit"] == "200"


def test_keyless_is_a_clean_skip_without_passcode_or_speech():
    service = Service()
    service.key_set = False
    service.headers = False  # Older local servers may not have issue 21 yet.
    outcome, check, output = run(service, passcode="")
    assert outcome == "skipped" and "skipped" in output
    assert check.speech_calls_upper_bound == 0
    assert len(service.requests) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("db_writable", False),
        ("demo_credits_remaining", 0),
        ("ok", None),
        ("rate_limit", {}),
        ("demo_credits_exhausted", True),
        ("rate_limit", {"ok": False}),
        ("gnani_key_set", False),
        ("demo_credits_remaining", None),
    ],
)
def test_bad_readiness_fails_before_any_speech(field, value):
    service = Service()
    service.ready[field] = value
    with pytest.raises(smoke.SmokeFailure):
        run(service)
    assert not speech_requests(service)


@pytest.mark.parametrize(
    "change",
    [
        "missing-passcode",
        "missing-ready",
        "public-desk",
        "old-error-shape",
        "bad-unlock",
        "missing-request-id",
        "security-headers",
    ],
)
def test_incomplete_deployments_fail_before_speech(change):
    service, kwargs = Service(), {}
    if change == "missing-passcode":
        kwargs["passcode"] = ""
    if change == "missing-ready":
        service.ready_status = 404
    if change == "public-desk":
        service.public_desk = True
    if change == "old-error-shape":
        service.error_envelope = False
    if change == "bad-unlock":
        service.unlock_status = 401
    if change == "missing-request-id":
        service.headers = False
    if change == "security-headers":
        service.security = False
        kwargs["strict"] = True
    with pytest.raises(smoke.SmokeFailure):
        run(service, **kwargs)
    assert not speech_requests(service)


@pytest.mark.parametrize(
    "change",
    [
        "wrong-intent",
        "missing-provider-id",
        "empty-transcript",
        "missing-event",
        "upstream-error",
        "timeout",
    ],
)
def test_paid_failures_do_not_retry_or_claim_success(change):
    service = Service()
    if change == "wrong-intent":
        service.intent = "delay"
    if change == "missing-provider-id":
        service.request_id = ""
    if change == "empty-transcript":
        service.transcript = ""
    if change == "missing-event":
        service.include_event = False
    if change == "upstream-error":
        service.sample_status = 502
    if change == "timeout":
        service.timeout = True
    with httpx.Client(
        base_url="http://127.0.0.1:8000/", transport=httpx.MockTransport(service)
    ) as client:
        check = smoke.SmokeCheck(client, PASSCODE, lambda text: None)
        with pytest.raises(smoke.SmokeFailure):
            check.run()
    assert len(speech_requests(service)) == 1
    assert check.speech_calls_upper_bound == smoke.SAMPLE_LOGICAL_OPERATIONS * (
        1 + smoke.DEFAULT_SERVER_RETRY_CAP
    )


def test_known_credentials_in_an_untrusted_request_id_are_redacted(monkeypatch):
    fake_key = "synthetic-key-" + str(uuid4())
    monkeypatch.setenv("GNANI_API_KEY", fake_key)
    service = Service()
    service.request_id = fake_key
    _, _, output = run(service)
    assert fake_key not in output and "[redacted]" in output


@pytest.mark.parametrize(
    "url",
    [
        "https://name:secret@example.com",
        "https://example.com/?key=bad",
        "https://example.com/#secret",
        "http://example.com",
        "file:///tmp/x",
    ],
)
def test_unsafe_base_urls_are_rejected(url):
    with pytest.raises(smoke.SmokeFailure):
        smoke.checked_base_url(url)


def test_cli_exit_code_and_call_tally_on_keyless_server(monkeypatch, capsys):
    service = Service()
    service.key_set = False
    real_client = httpx.Client
    monkeypatch.setattr(
        smoke.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(service)),
    )
    assert smoke.main([]) == 0
    output = capsys.readouterr().out
    assert "skipped" in output and "speech_calls_upper_bound=0" in output


def test_cli_failure_does_not_print_passcode_or_error_body(monkeypatch, capsys):
    service = Service()
    service.unlock_status = 401
    real_client = httpx.Client
    monkeypatch.setattr(
        smoke.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(service)),
    )
    monkeypatch.setenv("DISPATCH_PASSCODE", PASSCODE)
    assert smoke.main([]) == 1
    output = capsys.readouterr().out
    assert "failed" in output and "speech_calls_upper_bound=0" in output
    assert PASSCODE not in output


def test_positive_budget_is_not_assumed_to_be_one_credit_per_call():
    service = Service()
    service.ready["demo_credits_remaining"] = 1
    outcome, check, _ = run(service)
    assert (
        outcome == "passed"
        and check.speech_calls_upper_bound
        == smoke.SAMPLE_LOGICAL_OPERATIONS * (1 + smoke.DEFAULT_SERVER_RETRY_CAP)
    )


def test_nested_budget_shape_is_accepted():
    service = Service()
    service.ready["demo_credits_remaining"] = {"remaining": 20, "window": "synthetic"}
    assert run(service)[0] == "passed"


def test_cli_timeout_reports_possible_spend_without_a_retry(monkeypatch, capsys):
    service = Service()
    service.timeout = True
    real_client = httpx.Client
    monkeypatch.setattr(
        smoke.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(service)),
    )
    monkeypatch.setenv("DISPATCH_PASSCODE", PASSCODE)
    assert smoke.main([]) == 1
    output = capsys.readouterr().out
    bound = smoke.SAMPLE_LOGICAL_OPERATIONS * (1 + smoke.DEFAULT_SERVER_RETRY_CAP)
    assert f"speech_calls_upper_bound={bound}" in output and "failed" in output
    assert len(speech_requests(service)) == 1 and PASSCODE not in output


def test_cli_rejects_redirects_before_speech(monkeypatch, capsys):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.invalid/"})

    real_client = httpx.Client
    monkeypatch.setattr(
        smoke.httpx,
        "Client",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(handler)),
    )
    assert smoke.main([]) == 1
    output = capsys.readouterr().out
    assert "speech_calls_upper_bound=0" in output and len(seen) == 1


def test_invalid_cli_url_reports_zero_spend(capsys):
    assert smoke.main(["--base-url", "https://name:do-not-print@example.com"]) == 1
    output = capsys.readouterr().out
    assert "speech_calls_upper_bound=0" in output and "do-not-print" not in output


def test_unhealthy_process_is_not_a_successful_keyless_skip():
    service = Service()
    service.health_ok = False
    service.key_set = False
    with pytest.raises(smoke.SmokeFailure):
        run(service, passcode="")
    assert not speech_requests(service)
