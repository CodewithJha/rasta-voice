import hashlib
import io
import json
import math
import os
import random
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from rasta_bench import mix


def tone(seconds=1.0, rate=16000, frequency=440, amplitude=0.1):
    return [amplitude * math.sin(2 * math.pi * frequency * i / rate)
            for i in range(round(seconds * rate))]


def read_pcm(blob):
    with wave.open(io.BytesIO(blob), "rb") as wav:
        params = wav.getparams()
        raw = wav.readframes(len(blob) // 2 + 1)
    return params, [value[0] / 32768 for value in struct.iter_unpack("<h", raw)]


@pytest.mark.parametrize("snr", [20, 10, 0])
def test_requested_snr_measured_from_actual_mix(snr):
    signal = tone()
    noise = [random.Random(i).uniform(-1, 1) for i in range(len(signal))]
    mixed = mix.mix_samples(signal, noise, snr)
    # Measure the difference from the original, not a gain returned by the implementation.
    residual = [out - original for out, original in zip(mixed, signal, strict=True)]
    signal_power = sum(value * value for value in signal)
    noise_power = sum(value * value for value in residual)
    measured = 10 * math.log10(signal_power / noise_power)
    assert measured == pytest.approx(snr, abs=0.01)
    if snr == 0:
        assert math.sqrt(noise_power / signal_power) == pytest.approx(1, rel=0.2)
    # A low-amplitude tone does not clip, so PCM quantization preserves that ratio too.
    _, decoded = read_pcm(mix.wav_bytes(mixed, 16000))
    quantized_noise_power = sum((out - original) ** 2
                                for out, original in zip(decoded, signal, strict=True))
    assert 10 * math.log10(signal_power / quantized_noise_power) == pytest.approx(snr, abs=0.05)


def test_saturation_keeps_sign_and_does_not_normalize_the_whole_clip():
    _, decoded = read_pcm(mix.wav_bytes([-2, -1, 0, 0.25, 1, 2], 16000))
    assert decoded == [-1, -1, 0, 0.25, 32767 / 32768, 32767 / 32768]


@pytest.mark.parametrize("signal, noise, snr", [([], [], 0), ([1], [1, 2], 0),
                                                ([1], [0], 0), ([1], [1], float("nan")),
                                                ([1], [1], float("inf"))])
def test_unusable_mix_is_rejected(signal, noise, snr):
    with pytest.raises(ValueError):
        mix.mix_samples(signal, noise, snr)


@pytest.mark.parametrize("kind", mix.NOISES)
def test_noise_generators_are_seeded_non_silent_and_length_preserving(kind):
    generator = getattr(mix, kind)
    first = generator(16000, random.Random(124))
    assert len(first) == 16000
    assert any(value != 0 for value in first)
    assert all(-1 <= value <= 1 for value in first)
    assert first == generator(16000, random.Random(124))
    assert mix.wav_bytes(first, 16000) == mix.wav_bytes(
        generator(16000, random.Random(124)), 16000)


def test_horn_has_two_separated_bursts():
    samples = mix.horn(16000, random.Random(12))
    assert any(samples[1600:4800]) and any(samples[8800:12000])
    assert not any(samples[:1600] + samples[4800:8800] + samples[12000:])


def test_traffic_has_less_high_frequency_energy_than_white_noise():
    noisy = mix.traffic(16000, random.Random(43))
    white = [random.Random(i).uniform(-1, 1) for i in range(16000)]

    def roughness(values):
        return sum((b - a) ** 2 for a, b in zip(values, values[1:])) / sum(x*x for x in values)

    assert roughness(noisy) < roughness(white) / 5


def test_crosstalk_is_delayed_second_audio_not_a_repeated_or_stretched_clip():
    other = [0.2, -0.3, 0.4] * 500
    output = mix.crosstalk(16000, random.Random(1), other=other, delay_ms=300)
    assert output[:4800] == [0.0] * 4800
    assert output[4800:6300] == other
    assert output[6300:] == [0.0] * 9700


@pytest.fixture
def inputs(tmp_path):
    source = tmp_path / "clean_manifest.jsonl"
    rows = []
    for identifier, frequency, seconds in (("u01", 440, 1.0), ("u02", 660, 0.8)):
        blob = mix.wav_bytes(tone(seconds=seconds, frequency=frequency), 16000)
        path = tmp_path / f"{identifier}.wav"
        path.write_bytes(blob)
        rows.append({"id": identifier, "path": str(path), "reference": "भैया order 18",
                     "sample_rate": 16000, "sha256": hashlib.sha256(blob).hexdigest()})
    source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    return source, tmp_path / "mix_manifest.jsonl", tmp_path / "mixed"


def test_full_cartesian_product_formats_references_seeds_and_clean_bytes(inputs):
    rows = mix.generate_mixes(*inputs)
    source, manifest, _ = inputs
    originals = {row["id"]: row for row in map(json.loads, source.read_text().splitlines())}
    assert len(rows) == 32
    assert rows == list(map(json.loads, manifest.read_text().splitlines()))
    assert len({row["path"] for row in rows}) == 32
    for identifier, original in originals.items():
        subset = [row for row in rows if row["id"] == identifier]
        assert {(row["noise"], row["snr_db"]) for row in subset} == {
            ("clean", None), *((kind, snr) for kind in mix.NOISES for snr in mix.SNRS),
        }
        _, clean_pcm = read_pcm(Path(original["path"]).read_bytes())
        for row in subset:
            blob = Path(row["path"]).read_bytes()
            params, samples = read_pcm(blob)
            assert (params.nchannels, params.sampwidth, params.framerate) == (1, 2, 16000)
            assert len(samples) == len(clean_pcm)
            assert row["duration_s"] == len(clean_pcm) / 16000
            assert row["sha256"] == hashlib.sha256(blob).hexdigest()
            assert row["reference"] == original["reference"]
            if row["noise"] == "clean":
                assert blob == Path(original["path"]).read_bytes()
                assert row["seed"] is None
            else:
                expected_seed = int(identifier[1:])*1000 + mix.SNRS.index(row["snr_db"])*10
                assert row["seed"] == expected_seed + mix.NOISES.index(row["noise"])
                assert row["snr_basis"] == "pre_clip"
                assert row["clipped_samples"] == 0
            if row["noise"] == "crosstalk":
                assert row["crosstalk_source_id"] != identifier
                assert 200 <= row["crosstalk_delay_ms"] <= 400
                assert row["crosstalk_fallback"] is None


def test_complete_rerun_is_byte_identical_and_global_rng_independent(inputs):
    rows = mix.generate_mixes(*inputs)
    before = {row["path"]: Path(row["path"]).read_bytes() for row in rows}
    manifest_before = inputs[1].read_bytes()
    random.seed(999)
    for _ in range(20):
        random.random()
    assert mix.generate_mixes(*inputs) == rows
    assert inputs[1].read_bytes() == manifest_before
    assert all(Path(path).read_bytes() == blob for path, blob in before.items())


def test_single_source_reports_low_tone_fallback(inputs):
    source, _, _ = inputs
    source.write_text(source.read_text().splitlines()[0] + "\n")
    rows = mix.generate_mixes(*inputs)
    cross = [row for row in rows if row["noise"] == "crosstalk"]
    assert len(cross) == 3
    assert all(row["crosstalk_source_id"] is None for row in cross)
    assert all(row["crosstalk_fallback"] == "low_tone" for row in cross)


def test_streaming_headers_preserve_real_duration_and_clean_bytes(inputs):
    source = inputs[0]
    row = json.loads(source.read_text().splitlines()[0])
    path = Path(row["path"])
    blob = bytearray(path.read_bytes())
    blob[4:8] = b"\xff" * 4
    position = blob.index(b"data") + 4
    blob[position:position + 4] = b"\xff" * 4
    path.write_bytes(blob)
    row["sha256"] = hashlib.sha256(blob).hexdigest()
    source.write_text(json.dumps(row) + "\n")
    rows = mix.generate_mixes(*inputs)
    assert all(row["duration_s"] == 1 for row in rows)
    assert Path(rows[0]["path"]).read_bytes() == bytes(blob)
    assert all(len(read_pcm(Path(row["path"]).read_bytes())[1]) == 16000 for row in rows)


def test_nondefault_rate_is_preserved(inputs):
    source = inputs[0]
    row = json.loads(source.read_text().splitlines()[0])
    row["sample_rate"] = 8000
    blob = mix.wav_bytes(tone(rate=8000), 8000)
    Path(row["path"]).write_bytes(blob)
    row["sha256"] = hashlib.sha256(blob).hexdigest()
    source.write_text(json.dumps(row) + "\n")
    for row in mix.generate_mixes(*inputs):
        params, samples = read_pcm(Path(row["path"]).read_bytes())
        assert params.framerate == row["sample_rate"] == 8000
        assert len(samples) == 8000


def test_mismatched_source_rates_fail_before_writing(inputs):
    source, manifest, audio_dir = inputs
    rows = list(map(json.loads, source.read_text().splitlines()))
    rows[0]["sample_rate"] = 8000
    blob = mix.wav_bytes(tone(rate=8000), 8000)
    Path(rows[0]["path"]).write_bytes(blob)
    rows[0]["sha256"] = hashlib.sha256(blob).hexdigest()
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="matching sample rates"):
        mix.generate_mixes(*inputs)
    assert not manifest.exists() and not audio_dir.exists()


@pytest.mark.parametrize("change", ["hash", "reference", "id", "duplicate", "rate", "json"])
def test_invalid_inputs_fail_before_writing_outputs(inputs, change):
    source, manifest, audio_dir = inputs
    rows = list(map(json.loads, source.read_text().splitlines()))
    if change == "hash":
        rows[0]["sha256"] = "0" * 64
    elif change == "reference":
        rows[0]["reference"] = ""
    elif change == "id":
        rows[0]["id"] = "../bad"
    elif change == "duplicate":
        rows.append(rows[0])
    elif change == "rate":
        rows[0]["sample_rate"] = 8000
    source.write_text("invalid json" if change == "json" else "".join(
        json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="clean manifest line"):
        mix.generate_mixes(*inputs)
    assert not manifest.exists()
    assert not audio_dir.exists()


def test_empty_manifest_and_overlapping_paths_are_rejected(inputs):
    source, _, audio_dir = inputs
    with pytest.raises(ValueError, match="overlap"):
        mix.generate_mixes(source, source, audio_dir)
    assert not audio_dir.exists()
    source.write_text("")
    with pytest.raises(ValueError, match="empty"):
        mix.generate_mixes(*inputs)


def test_cli_uses_real_files_without_a_key_and_failure_is_clear(inputs, capsys):
    env = {key: value for key, value in os.environ.items() if key != "GNANI_API_KEY"}
    source, manifest, audio_dir = inputs
    result = subprocess.run([sys.executable, "-m", "rasta_bench.mix", "--clean-manifest",
                             str(source), "--manifest", str(manifest), "--audio-dir",
                             str(audio_dir)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "32 rows" in result.stdout
    assert len(manifest.read_text().splitlines()) == 32
    assert mix.main(["--clean-manifest", str(source / "missing")]) == 1
    assert "Traceback" not in capsys.readouterr().err
