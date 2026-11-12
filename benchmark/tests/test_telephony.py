import hashlib
import io
import json
import math
import os
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from rasta_bench import telephony


def make_wav(samples, rate=16000, channels=1, width=2):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return output.getvalue()


def read_wav(path):
    with wave.open(str(path), "rb") as wav:
        params = wav.getparams()
        raw = wav.readframes(params.nframes)
    return params, [value[0] for value in struct.iter_unpack("<h", raw)]


def sine(rate=16000, frames=16000, amplitude=32767):
    return [round(amplitude * math.sin(2 * math.pi * 440 * i / rate)) for i in range(frames)]


# Known G.711 vectors independently checked using CPython 3.12 audioop.
# Tests do not import audioop (removed in Python 3.13) or require a codec package.
@pytest.mark.parametrize("linear, encoded, decoded", [
    (-32768, 0x00, -32124), (-1000, 0x4E, -988), (-132, 0x6F, -132),
    (-32, 0x7B, -32), (-8, 0x7E, -8), (-1, 0x7E, -8),
    (0, 0xFF, 0), (1, 0xFF, 0), (4, 0xFE, 8), (32, 0xFB, 32),
    (132, 0xEF, 132), (1000, 0xCE, 988), (32767, 0x80, 32124),
])
def test_known_g711_vectors(linear, encoded, decoded):
    assert telephony.linear_to_mulaw(linear) == encoded
    assert telephony.mulaw_to_linear(encoded) == decoded
    assert telephony.mulaw_roundtrip([linear]) == [decoded]


def test_entire_signed_pcm_encoding_domain_matches_independent_reference():
    # SHA of audioop.lin2ulaw(struct.pack('<65536h', *range(-32768,32768)), 2).
    encoded = bytes(telephony.linear_to_mulaw(sample) for sample in range(-32768, 32768))
    assert hashlib.sha256(encoded).hexdigest() == (
        "81d633c9e6972a18c74a58720b96cb8ca0bdd096d4060b646dd708c3b846019a"
    )


def test_entire_octet_decoding_domain_matches_independent_reference():
    # SHA of audioop.ulaw2lin(bytes(range(256)), 2), little-endian signed PCM.
    decoded = struct.pack("<256h", *(telephony.mulaw_to_linear(code) for code in range(256)))
    assert hashlib.sha256(decoded).hexdigest() == (
        "3dab54339e520bb2c924826e3b72a917a2b612e9fd12fc867500f1d983a75827"
    )


@pytest.mark.parametrize("sample", [-32769, 32768, 1.5, True, "1"])
def test_encoder_rejects_non_pcm_values(sample):
    with pytest.raises(ValueError, match="16-bit"):
        telephony.linear_to_mulaw(sample)


@pytest.mark.parametrize("code", [-1, 256, 1.5, False])
def test_decoder_rejects_non_octets(code):
    with pytest.raises(ValueError, match="0..255"):
        telephony.mulaw_to_linear(code)


def test_silence_stays_zero():
    assert telephony.mulaw_roundtrip([0] * 8000) == [0] * 8000


def test_downsample_is_block_average_and_retains_partial_tail():
    assert telephony.downsample([100, 300, -300, -100, 500], 16000) == [200, -200, 500]
    assert telephony.downsample([1, 2, 3, 4, 5, 6], 24000) == [2, 5]
    assert telephony.downsample([100, -200], 8000) == [100, -200]


@pytest.mark.parametrize("rate", [0, 4000, 11025, 22050, 44100, 16000.0])
def test_unsupported_sample_rate_is_rejected(rate):
    with pytest.raises(ValueError, match="multiple of 8000"):
        telephony.downsample([1, 2, 3], rate)


def test_one_second_tone_preserves_duration_with_lossy_positive_correlation(tmp_path):
    source, destination = tmp_path / "source.wav", tmp_path / "phone.wav"
    original = sine()
    source.write_bytes(make_wav(original))
    metadata = telephony.to_telephony(source, destination)
    params, decoded = read_wav(destination)
    assert (params.nchannels, params.sampwidth, params.framerate, params.nframes) == (
        1, 2, 8000, 8000,
    )
    # Independent pair averages, rather than comparing the codec with its own output.
    averaged = [round((original[i] + original[i+1]) / 2) for i in range(0, len(original), 2)]
    assert decoded != averaged
    correlation = sum(a*b for a, b in zip(averaged, decoded, strict=True)) / math.sqrt(
        sum(a*a for a in averaged) * sum(b*b for b in decoded))
    assert correlation > 0.99
    assert metadata["duration_s"] == metadata["source_duration_s"] == 1
    assert metadata["telephony"] == "mulaw8k"
    assert metadata["provenance"] == "simulated_telephony"
    assert metadata["dropouts"] is False


def test_odd_sample_count_loses_at_most_one_output_sample_of_timing(tmp_path):
    source, destination = tmp_path / "odd.wav", tmp_path / "phone.wav"
    source.write_bytes(make_wav(sine(frames=16001)))
    metadata = telephony.to_telephony(source, destination)
    assert read_wav(destination)[0].nframes == 8001
    assert abs(metadata["duration_s"] - metadata["source_duration_s"]) <= 1/8000


def test_streaming_headers_do_not_create_hours_of_silence(tmp_path):
    source, destination = tmp_path / "streamed.wav", tmp_path / "phone.wav"
    blob = bytearray(make_wav(sine()))
    blob[4:8] = b"\xff" * 4
    position = blob.index(b"data") + 4
    blob[position:position+4] = b"\xff" * 4
    source.write_bytes(blob)
    metadata = telephony.to_telephony(source, destination)
    assert read_wav(destination)[0].nframes == 8000
    assert metadata["source_duration_s"] == metadata["duration_s"] == 1
    assert source.read_bytes() == blob


def test_optional_dropouts_zero_exactly_every_fiftieth_sample(tmp_path):
    source, normal, dropped = (tmp_path / name for name in ("source.wav", "normal.wav", "drop.wav"))
    source.write_bytes(make_wav([1000] * 1600))
    telephony.to_telephony(source, normal)
    metadata = telephony.to_telephony(source, dropped, dropouts=True)
    _, baseline = read_wav(normal)
    _, affected = read_wav(dropped)
    assert metadata["dropouts"] is True
    assert len(affected) == len(baseline) == 800
    assert [i for i, (a, b) in enumerate(zip(baseline, affected)) if a != b] == list(
        range(49, 800, 50))
    assert all(affected[i] == 0 for i in range(49, 800, 50))


@pytest.fixture
def inputs(tmp_path):
    rows = []
    for identifier, noise, snr in (("u01", "clean", None), ("u01", "horn", 0)):
        path = tmp_path / f"{identifier}__{noise}__{snr if snr is not None else 'clean'}.wav"
        blob = make_wav(sine(amplitude=2000))
        path.write_bytes(blob)
        rows.append({"id": identifier, "noise": noise, "snr_db": snr, "reference": "भैया order 18",
                     "sample_rate": 16000, "seed": None if noise == "clean" else 1021,
                     "path": str(path), "sha256": hashlib.sha256(blob).hexdigest(),
                     "duration_s": 1.0, "snr_basis": "pre_clip", "clipped_samples": 0})
    manifest = tmp_path / "mix_manifest.jsonl"
    manifest.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    return manifest, tmp_path / "phone_manifest.jsonl", tmp_path / "phone"


def test_manifest_fields_hashes_names_and_reproducible_rerun(inputs):
    source, manifest, audio_dir = inputs
    original_bytes = source.read_bytes()
    originals = list(map(json.loads, source.read_text().splitlines()))
    rows = telephony.generate_phone_clips(*inputs)
    assert len(rows) == 2
    assert rows == list(map(json.loads, manifest.read_text().splitlines()))
    previous = manifest.read_bytes()
    audio_before = {row["path"]: Path(row["path"]).read_bytes() for row in rows}
    for row, original in zip(rows, originals, strict=True):
        for field in ("id", "noise", "snr_db", "seed", "reference", "snr_basis", "clipped_samples"):
            assert row[field] == original[field]
        assert Path(row["path"]) == audio_dir / Path(original["path"]).name
        assert row["source_sha256"] == original["sha256"]
        assert row["sha256"] == hashlib.sha256(Path(row["path"]).read_bytes()).hexdigest()
        assert row["sha256"] != original["sha256"]
        assert row["sample_rate"] == 8000 and row["source_sample_rate"] == 16000
        assert row["dropouts"] is False and row["provenance"] == "simulated_telephony"
    assert telephony.generate_phone_clips(*inputs) == rows
    assert manifest.read_bytes() == previous and source.read_bytes() == original_bytes
    assert all(Path(path).read_bytes() == blob for path, blob in audio_before.items())


@pytest.mark.parametrize("change", ["hash", "rate", "duplicate", "filename", "json", "empty"])
def test_bad_manifest_fails_without_outputs(inputs, change):
    source, manifest, audio_dir = inputs
    rows = list(map(json.loads, source.read_text().splitlines()))
    if change == "hash":
        rows[1]["sha256"] = "0" * 64
    elif change == "rate":
        rows[1]["sample_rate"] = 24000
    elif change == "duplicate":
        rows.append(rows[0])
    elif change == "filename":
        rows[1]["path"] = rows[0]["path"]
    source.write_text("" if change == "empty" else "bad" if change == "json" else
                      "".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError):
        telephony.generate_phone_clips(*inputs)
    assert not manifest.exists() and not audio_dir.exists()


@pytest.mark.parametrize("kind", ["bad_wav", "stereo", "8bit", "rate", "empty_pcm"])
def test_invalid_audio_fails_before_writing(tmp_path, kind):
    source, destination = tmp_path / "source.wav", tmp_path / "out.wav"
    blobs = {"bad_wav": b"bad", "stereo": make_wav([1, 2]*20, channels=2),
             "8bit": make_wav([1]*20, width=1), "rate": make_wav([1]*20, rate=44100),
             "empty_pcm": make_wav([])}
    source.write_bytes(blobs[kind])
    with pytest.raises(ValueError):
        telephony.to_telephony(source, destination)
    assert not destination.exists()


def test_overlap_does_not_overwrite_source(inputs):
    source, _, audio_dir = inputs
    original = source.read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        telephony.generate_phone_clips(source, source, audio_dir)
    assert source.read_bytes() == original
    first_wav = Path(json.loads(source.read_text().splitlines()[0])["path"])
    with pytest.raises(ValueError, match="overlap"):
        telephony.to_telephony(first_wav, first_wav)
    with pytest.raises(ValueError, match="overlap"):
        telephony.generate_phone_clips(source, inputs[1], first_wav.parent)


def test_cli_is_offline_and_dropouts_cannot_replace_default_dataset(inputs, monkeypatch):
    source, _, _ = inputs
    monkeypatch.setattr(telephony, "DATA", source.parent)
    assert telephony.main([]) == 0
    baseline = source.parent / "phone_manifest.jsonl"
    baseline_bytes = baseline.read_bytes()
    rows = list(map(json.loads, baseline.read_text().splitlines()))
    audio_bytes = {row["path"]: Path(row["path"]).read_bytes() for row in rows}
    assert telephony.main(["--dropouts"]) == 0
    assert baseline.read_bytes() == baseline_bytes
    assert all(Path(path).read_bytes() == blob for path, blob in audio_bytes.items())
    alternate = source.parent / "phone_dropouts_manifest.jsonl"
    assert all(row["dropouts"] for row in map(json.loads, alternate.read_text().splitlines()))


def test_subprocess_cli_needs_no_key_and_reports_invalid_rate(inputs):
    source, manifest, audio_dir = inputs
    env = {key: value for key, value in os.environ.items() if key != "GNANI_API_KEY"}
    command = [sys.executable, "-m", "rasta_bench.telephony", "--mix-manifest", str(source),
               "--manifest", str(manifest), "--audio-dir", str(audio_dir)]
    result = subprocess.run(command, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Simulated telephony complete: 2" in result.stdout
    first = json.loads(source.read_text().splitlines()[0])
    Path(first["path"]).write_bytes(make_wav(sine(rate=44100), rate=44100))
    failure = subprocess.run(command, env=env, capture_output=True, text=True)
    assert failure.returncode == 1
    assert "multiple of 8000" in failure.stderr and "Traceback" not in failure.stderr
