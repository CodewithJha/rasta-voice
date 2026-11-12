import io
import json
import os
import struct
import subprocess
import sys
import wave
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path

import httpx
import pytest

from gnani_client.errors import GnaniError, MissingApiKeyError
from gnani_client.tts import TimbreTTS
from rasta_bench import speak


@pytest.fixture
def inputs(tmp_path):
    corpus = tmp_path / "utterances.jsonl"
    rows = [
        {"id": "u01", "intent": "customer_unreachable", "order_id": "18",
         "eta_minutes": None, "text": "bhaiya customer phone nahi utha raha, order 18"},
        {"id": "u02", "intent": "delay", "order_id": None,
         "eta_minutes": 20, "text": "भैया traffic hai, bees minute lagenge"},
    ]
    corpus.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    return corpus, tmp_path / "clean_manifest.jsonl", tmp_path / "audio/clean"


@pytest.fixture
def audio():
    # A tiny test-only PCM fixture. Production never generates substitute audio.
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<h", 1200) * 1600)
    return out.getvalue()


@pytest.fixture
def transport(monkeypatch, audio):
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    requests = []
    responses = []

    def handler(request):
        requests.append(request)
        return responses.pop(0) if responses else httpx.Response(200, content=audio)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(TimbreTTS, "_http", lambda self: nullcontext(client))
        yield requests, responses


def test_live_request_shape_and_manifest(inputs, transport, audio):
    requests, _ = transport
    entries = speak.generate_clean_clips(*inputs)
    corpus, manifest, audio_dir = inputs
    references = [json.loads(line)["text"] for line in corpus.read_text().splitlines()]
    assert len(entries) == len(requests) == 2
    assert entries == [json.loads(line) for line in manifest.read_text().splitlines()]
    for entry, reference, request in zip(entries, references, requests, strict=True):
        assert entry["reference"] == entry["spoken_text"] == reference
        assert entry["sha256"] == sha256(audio).hexdigest()
        assert entry["duration_s"] == 0.1
        assert entry["language"] == "hi-en"
        path = Path(entry["path"])
        assert path == audio_dir / f"{entry['id']}.wav"
        assert path.read_bytes() == audio
        with wave.open(str(path), "rb") as wav:
            assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        assert str(request.url) == "https://api.vachana.ai/api/v1/tts/inference"
        assert request.headers["X-API-Key-ID"] == "test-key"
        payload = json.loads(request.content)
        assert payload == {
            "text": reference, "voice": "Shivani", "model": "timbre-v3.0",
            "language": "hi-en", "speed": 1.0,
            "audio_config": {"sample_rate": 16000, "num_channels": 1, "sample_width": 2,
                             "encoding": "linear_pcm", "container": "wav"},
        }


def test_cache_makes_zero_calls_and_force_regenerates(inputs, transport):
    requests, _ = transport
    original = speak.generate_clean_clips(*inputs)
    requests.clear()
    assert speak.generate_clean_clips(*inputs) == original
    assert not requests
    assert speak.generate_clean_clips(*inputs, force=True) == original
    assert len(requests) == 2


@pytest.mark.parametrize("change", ["text", "voice", "model", "language", "sample_rate",
                                    "path", "sha256", "duration_s", "missing", "corrupt"])
def test_stale_cache_regenerates_only_affected_clip(inputs, transport, change):
    requests, _ = transport
    entries = speak.generate_clean_clips(*inputs)
    corpus, manifest, _ = inputs
    if change == "text":
        rows = [json.loads(line) for line in corpus.read_text().splitlines()]
        rows[0]["text"] += ", dispatch se baat karao"
        corpus.write_text("".join(json.dumps(row) + "\n" for row in rows))
    elif change == "missing":
        Path(entries[0]["path"]).unlink()
    elif change == "corrupt":
        Path(entries[0]["path"]).write_bytes(b"not a wav")
    else:
        entries[0][change] = "stale"
        manifest.write_text("".join(json.dumps(row) + "\n" for row in entries))
    requests.clear()
    result = speak.generate_clean_clips(*inputs)
    assert len(requests) == 1
    assert json.loads(requests[0].content)["text"] == result[0]["reference"]


def test_streaming_headers_use_actual_audio_bytes(inputs, transport, audio):
    _, responses = transport
    streamed = bytearray(audio)
    streamed[4:8] = b"\xff" * 4
    start = streamed.index(b"data") + 4
    streamed[start:start + 4] = b"\xff" * 4
    responses.extend([httpx.Response(200, content=bytes(streamed))] * 2)
    assert all(row["duration_s"] == 0.1 for row in speak.generate_clean_clips(*inputs))


def test_checkpoint_resumes_without_repeating_success(inputs, transport, audio):
    requests, responses = transport
    # Preserve the first success when the second call runs out of credit.
    responses.extend([httpx.Response(200, content=audio),
                      httpx.Response(402, json={"message": "Out of credit"})])
    with pytest.raises(GnaniError) as info:
        speak.generate_clean_clips(*inputs)
    assert info.value.status == 402
    assert len(inputs[1].read_text().splitlines()) == 1
    requests.clear()
    result = speak.generate_clean_clips(*inputs)
    assert len(result) == 2
    assert len(requests) == 1
    assert "traffic" in json.loads(requests[0].content)["text"]


def test_rate_limit_retries_are_bounded(inputs, transport, monkeypatch):
    requests, responses = transport
    sleeps = []
    monkeypatch.setattr(speak.time, "sleep", sleeps.append)
    responses.extend([httpx.Response(429, json={"message": "Rate limited"})] * 4)
    with pytest.raises(GnaniError) as info:
        speak.generate_clean_clips(*inputs)
    assert info.value.status == 429
    assert sleeps == [1, 2, 4]
    assert len(requests) == 4
    assert not inputs[1].exists()
    assert not inputs[2].exists()


def test_rate_limit_then_success(inputs, transport, monkeypatch):
    requests, responses = transport
    sleeps = []
    monkeypatch.setattr(speak.time, "sleep", sleeps.append)
    responses.append(httpx.Response(429, json={"message": "Rate limited"}))
    assert len(speak.generate_clean_clips(*inputs)) == 2
    assert len(requests) == 3
    assert sleeps == [1]


@pytest.mark.parametrize("body", [b"not a wav", b"RIFF", b""])
def test_invalid_audio_does_not_create_evidence(inputs, transport, body):
    _, responses = transport
    responses.append(httpx.Response(200, content=body))
    with pytest.raises((ValueError, GnaniError)):
        speak.generate_clean_clips(*inputs)
    assert not inputs[1].exists()
    assert not inputs[2].exists()


def test_wrong_rate_rejected(inputs, transport, audio):
    _, responses = transport
    wrong_rate = bytearray(audio)
    wrong_rate[24:28] = struct.pack("<I", 8000)
    responses.append(httpx.Response(200, content=bytes(wrong_rate)))
    with pytest.raises(ValueError, match="16000"):
        speak.generate_clean_clips(*inputs)
    assert not inputs[1].exists()


@pytest.mark.parametrize("offset, value", [(22, 2), (34, 8)])
def test_wrong_channels_or_sample_width_rejected(inputs, transport, audio, offset, value):
    _, responses = transport
    invalid = bytearray(audio)
    invalid[offset:offset + 2] = struct.pack("<H", value)
    responses.append(httpx.Response(200, content=bytes(invalid)))
    with pytest.raises(ValueError, match="16000"):
        speak.generate_clean_clips(*inputs)
    assert not inputs[1].exists()


def test_inconsistent_byte_rate_is_rejected(inputs, transport, audio):
    _, responses = transport
    invalid = bytearray(audio)
    invalid[28:32] = struct.pack("<I", 16000)
    responses.append(httpx.Response(200, content=bytes(invalid)))
    with pytest.raises(ValueError, match="timing"):
        speak.generate_clean_clips(*inputs)
    assert not inputs[1].exists()


def test_missing_key_fails_before_writing(inputs, monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    with pytest.raises(MissingApiKeyError):
        speak.generate_clean_clips(*inputs)
    assert not inputs[1].exists()
    assert not inputs[2].exists()


def test_cli_missing_key_exits_nonzero():
    env = {key: value for key, value in os.environ.items() if key != "GNANI_API_KEY"}
    result = subprocess.run([sys.executable, "-m", "rasta_bench.speak"],
                            capture_output=True, text=True, env=env)
    assert result.returncode == 1
    assert "GNANI_API_KEY is not set" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_redacts_upstream_key(inputs, transport, capsys):
    _, responses = transport
    responses.append(httpx.Response(401, json={"message": "rejected test-key"}))
    corpus, manifest, audio_dir = inputs
    assert speak.main(["--corpus", str(corpus), "--manifest", str(manifest),
                       "--audio-dir", str(audio_dir)]) == 1
    error = capsys.readouterr().err
    assert "test-key" not in error
    assert "[redacted]" in error


def test_invalid_manifest_fails_without_calls(inputs, transport):
    requests, _ = transport
    inputs[1].write_text("not json\n")
    with pytest.raises(ValueError, match="manifest line 1"):
        speak.generate_clean_clips(*inputs)
    assert not requests


def test_empty_corpus_fails_without_calls(inputs, transport):
    requests, _ = transport
    inputs[0].write_text("")
    with pytest.raises(ValueError, match="empty"):
        speak.generate_clean_clips(*inputs)
    assert not requests


def test_output_paths_cannot_overwrite_input(inputs, transport):
    requests, _ = transport
    corpus, _, audio_dir = inputs
    original = corpus.read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        speak.generate_clean_clips(corpus, corpus, audio_dir)
    assert corpus.read_bytes() == original
    assert not requests


def test_audio_outputs_are_gitignored():
    result = subprocess.run(["git", "check-ignore", "benchmark/data/audio/clean/u01.wav"],
                            cwd=speak.ROOT, text=True, capture_output=True)
    assert result.returncode == 0
