"""Exercise the documented copied environment without calling a speech provider."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PREFIXES = (
    "RASTA_",
    "LLM_",
    "GROQ_",
    "GEMINI_",
    "GNANI_",
    "DISPATCH_",
    "EVENT_STORE_",
    "SOS_",
    "CORS_",
)


def run_with_example(tmp_path: Path, code: str, **overrides: str) -> None:
    shutil.copyfile(ROOT / ".env.example", tmp_path / ".env")
    # Preserve the machine's network configuration, but isolate app settings.
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith(SETTINGS_PREFIXES)
    }
    environment.update(
        PYTHONPATH=os.pathsep.join(
            str(ROOT / path)
            for path in (
                "backend",
                "gnani_client",
                "benchmark",
            )
        ),
        GNANI_API_KEY="",
        GROQ_API_KEY="",
        GEMINI_API_KEY="",
        DISPATCH_PASSCODE="",
        RASTA_DB_PATH=str(tmp_path / "events.sqlite"),
    )
    environment.update(overrides)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_copied_example_starts_keyless_application(tmp_path: Path) -> None:
    run_with_example(
        tmp_path,
        """
from dotenv import load_dotenv
load_dotenv('.env', override=False)
from fastapi.testclient import TestClient
from rasta.main import app
from rasta.settings import get_settings
assert get_settings().rasta_env == 'development'
with TestClient(app) as client:
    health = client.get('/api/health')
    assert health.status_code == 200
    assert health.json()['gnani_key_set'] is False
    assert client.post('/api/ingest/sample').status_code == 503
""",
    )


def test_example_cannot_override_explicit_production_validation(tmp_path: Path) -> None:
    run_with_example(
        tmp_path,
        """
from dotenv import load_dotenv
load_dotenv('.env', override=False)
from rasta.settings import SettingsError
try:
    import rasta.main
except SettingsError as error:
    assert 'DISPATCH_PASSCODE' in str(error)
else:
    raise AssertionError('Production boot accepted a missing passcode')
""",
        RASTA_ENV="production",
        RASTA_ALLOWED_HOSTS="localhost",
    )
