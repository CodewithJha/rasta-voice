import io
import struct
import wave
from pathlib import Path

import pytest

from rasta_bench import wavio


def reference_wav(samples, rate=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return output.getvalue()


@pytest.mark.parametrize("rate", [8000, 16000, 24000])
def test_signed_samples_keep_exact_pcm_and_header_bytes(rate):
    samples = [-32768, -1000, -1, 0, 1, 1000, 32767]
    expected = reference_wav(samples, rate)
    assert wavio.pcm_wav(iter(samples), rate) == expected
    assert wavio.read_pcm(expected) == (samples, rate)


def test_placeholder_sizes_use_only_present_samples():
    samples = [-32768, -1, 0, 1, 32767]
    streamed = bytearray(reference_wav(samples))
    streamed[4:8] = b"\xff" * 4
    streamed[40:44] = b"\xff" * 4
    assert wavio.read_pcm(bytes(streamed), sample_rate=16000) == (samples, 16000)


@pytest.mark.parametrize("kind", ["invalid", "empty", "partial", "stereo", "8bit", "rate"])
def test_invalid_pcm_is_rejected(kind):
    blob = bytearray(reference_wav([100, -100]))
    if kind == "invalid":
        blob = b"not a WAV"
    elif kind == "empty":
        blob = reference_wav([])
    elif kind == "partial":
        blob = blob[:-1]
    elif kind == "stereo":
        blob[22:24] = struct.pack("<H", 2)
    elif kind == "8bit":
        blob[34:36] = struct.pack("<H", 8)
    elif kind == "rate":
        blob[24:28] = struct.pack("<I", 8000)
    with pytest.raises(ValueError):
        wavio.read_pcm(bytes(blob), sample_rate=16000)


def test_atomic_write_creates_parents_and_replaces_complete_file(tmp_path):
    destination = tmp_path / "nested" / "clip.wav"
    wavio.atomic_write(destination, b"original")
    wavio.atomic_write(destination, b"complete replacement")
    assert destination.read_bytes() == b"complete replacement"
    assert list(destination.parent.iterdir()) == [destination]


@pytest.mark.parametrize("failure", ["flush", "replace"])
def test_atomic_failure_keeps_original_and_removes_temporary_file(tmp_path, monkeypatch, failure):
    destination = tmp_path / "manifest.jsonl"
    destination.write_bytes(b"original")

    def fail(*args):
        raise OSError("disk failure")

    if failure == "flush":
        monkeypatch.setattr(wavio.os, "fsync", fail)
    else:
        monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk failure"):
        wavio.atomic_write(destination, b"replacement")
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [destination]
