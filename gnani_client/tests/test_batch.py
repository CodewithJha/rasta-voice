import json

import httpx
import pytest

from gnani_client.batch import PrismaBatch, batch_config
from gnani_client.errors import MissingApiKeyError


def test_v3_config_keeps_keyterms_and_denoise():
    config = batch_config(
        model="prisma-v3.0",
        language_code="hi-IN,en-IN",
        with_denoise=True,
        keyterms=["HDFC Bank", "order"],
        output_format="codemix",
    )
    assert config["with_denoise"] is True
    assert config["keyterms"] == ["HDFC Bank", "order"]
    assert "bias_list" not in config


def test_v25_config_uses_bias_list():
    config = batch_config(
        model="prisma-v2.5",
        language_code="hi-IN",
        keyterms=["order", "gate"],
        output_format="codemix",
    )
    assert "keyterms" not in config
    assert "format" not in config
    assert config["bias_list"] == ["order", "gate"]
    assert config["bias_score"] == 1.0


def test_create_job_posts_config_as_json():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        seen["key"] = request.headers["X-API-Key-ID"]
        return httpx.Response(201, json={"job_id": "job-9", "status": "CREATED"})

    client = PrismaBatch(
        key="test-key",
        base="https://api.vachana.ai",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    config = batch_config(
        model="prisma-v3.0",
        language_code="indic-auto",
        with_denoise=True,
        keyterms=["accident"],
    )
    created = client.create_job([("noisy.wav", b"RIFFfake")], config)
    assert created["job_id"] == "job-9"
    assert seen["url"] == "https://api.vachana.ai/stt/v3/batch/jobs"
    assert seen["key"] == "test-key"
    body = seen["body"]
    assert isinstance(body, bytes)
    assert b"with_denoise" in body
    assert b"prisma-v3.0" in body
    assert b"accident" in body
    assert json.dumps(config).encode() in body or b'"with_denoise": true' in body


def test_missing_key_fails_loudly(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        PrismaBatch()


def test_files_then_presigned_transcript():
    seen: list[tuple[str, str | None]] = []
    signed = "https://results.example/job-9/file-1.json?X-Amz-Expires=3600"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("X-API-Key-ID")))
        if request.url.path.endswith("/files"):
            return httpx.Response(
                200,
                json={
                    "job_id": "job-9",
                    "data": [
                        {"file_id": "file-1", "status": "COMPLETED", "transcript_url": signed}
                    ],
                    "pagination": {"has_more": False, "next_cursor": None, "total_count": 1},
                },
            )
        return httpx.Response(200, json={"full_transcript": "order 4 mein ek item missing"})

    client = PrismaBatch(
        key="test-key",
        base="https://api.vachana.ai",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    files = client.list_files("job-9")
    url = files["data"][0]["transcript_url"]
    doc = client.fetch_transcript(url)
    assert doc["full_transcript"] == "order 4 mein ek item missing"
    files_url = "https://api.vachana.ai/stt/v3/batch/jobs/job-9/files?status=COMPLETED"
    assert seen[0] == (files_url, "test-key")
    assert seen[1] == (signed, None)
