"""Real response policies, including the outer exception response."""

import os
import subprocess
import sys

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from rasta.security import HSTS, SECURITY_HEADERS, SecuredApp
from rasta.settings import clear_settings_cache


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("RASTA_ENV", "development")
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "false")
    clear_settings_cache()
    yield
    clear_settings_cache()


def secured_app():
    app = SecuredApp()

    @app.get("/")
    def index():
        return {"page": "synthetic-test"}

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/missing-key")
    def missing_key():
        raise HTTPException(503, "GNANI_API_KEY is not set.")

    @app.get("/unhandled")
    def unhandled():
        raise RuntimeError("test-only failure")

    return app


@pytest.mark.parametrize(
    "path,status",
    [
        ("/", 200),
        ("/api/health", 200),
        ("/missing-key", 503),
        ("/unhandled", 500),
        ("/absent", 404),
    ],
)
def test_headers_cover_success_and_all_error_layers(path, status):
    response = TestClient(secured_app(), raise_server_exceptions=False).get(path)
    assert response.status_code == status
    for key, value in SECURITY_HEADERS.items():
        assert response.headers[key] == value
    assert response.headers["x-request-id"]
    assert "Strict-Transport-Security" not in response.headers
    csp = response.headers["Content-Security-Policy"]
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert "script-src 'self'" in csp


def test_hsts_requires_https_or_explicit_production(monkeypatch):
    app = secured_app()
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/").headers["Strict-Transport-Security"] == HSTS
    # A direct client cannot spoof a secure platform proxy by default.
    with TestClient(app) as client:
        assert (
            "Strict-Transport-Security"
            not in client.get("/", headers={"X-Forwarded-Proto": "https"}).headers
        )
    monkeypatch.setenv("RASTA_TRUST_PROXY_HEADERS", "true")
    clear_settings_cache()
    assert (
        TestClient(app)
        .get("/", headers={"X-Forwarded-Proto": "https"})
        .headers["Strict-Transport-Security"]
        == HSTS
    )
    monkeypatch.setenv("RASTA_ENV", "production")
    clear_settings_cache()
    assert TestClient(app).get("/").headers["Strict-Transport-Security"] == HSTS


def test_real_production_app_disables_generated_docs(tmp_path):
    env = {
        **os.environ,
        "RASTA_ENV": "production",
        "RASTA_ALLOWED_HOSTS": "testserver",
        "DISPATCH_PASSCODE": "synthetic-process-test",
        "GNANI_API_KEY": "",
        "RASTA_DB_PATH": str(tmp_path / "desk.sqlite"),
        "RASTA_STATIC_DIR": "",
        "PYTHONPATH": "backend:gnani_client:benchmark",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
from fastapi.testclient import TestClient
from rasta.main import app
with TestClient(app) as client:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404, path
    assert client.get("/api/health").status_code == 200
""",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_development_keeps_generated_docs():
    from rasta.main import app

    assert TestClient(app).get("/openapi.json").status_code == 200
