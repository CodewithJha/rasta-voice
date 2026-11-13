"""The built UI is served at / without shadowing /api/health."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rasta.main import _mount_static
from rasta.settings import clear_settings_cache


def test_health_json_wins_over_the_built_index(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RASTA_STATIC_DIR", str(tmp_path))
    clear_settings_cache()
    (tmp_path / "index.html").write_text("<!doctype html><title>desk</title>", encoding="utf-8")
    probe = FastAPI()

    @probe.get("/api/health")
    def health() -> dict:
        return {"ok": True, "gnani_key_set": False}

    _mount_static(probe)
    with TestClient(probe) as client:
        health_response = client.get("/api/health")
        assert health_response.json() == {"ok": True, "gnani_key_set": False}
        assert "application/json" in health_response.headers["content-type"]
        page = client.get("/")
        assert page.status_code == 200
        assert "desk" in page.text
        assert "text/html" in page.headers["content-type"]
    clear_settings_cache()


def test_missing_dist_does_not_mount_a_shadow_route(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RASTA_STATIC_DIR", str(tmp_path / "missing"))
    clear_settings_cache()
    probe = FastAPI()

    @probe.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    _mount_static(probe)
    with TestClient(probe) as client:
        assert client.get("/api/health").json() == {"ok": True}
        assert client.get("/").status_code == 404
    clear_settings_cache()
