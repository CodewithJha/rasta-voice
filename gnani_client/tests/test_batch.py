import json

import httpx

from gnani_client.batch import PrismaBatch, batch_config
from gnani_client.stt import MOCK_TRANSCRIPT


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
        mock=False,
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


def test_mock_batch_completes_offline():
    client = PrismaBatch(key="", mock=True)
    created = client.create_job([("clip.wav", b"x")], {"model": "prisma-v3.0"})
    assert created["status"] == "CREATED"
    assert client.start_job(created["job_id"])["status"] == "STARTING"
    assert client.get_job(created["job_id"])["status"] == "COMPLETED"
    files = client.list_files(created["job_id"])
    assert files["files"][0]["full_transcript"] == MOCK_TRANSCRIPT
