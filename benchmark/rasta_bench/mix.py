"""Deterministic synthetic noise mixes. No network, credentials or extra dependencies.

Run ``python -m rasta_bench.mix`` after generating the clean Timbre clips.
SNR labels describe signal/noise power before PCM clipping, not recorded noise.
"""

import argparse
import hashlib
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from rasta_bench.wavio import atomic_write, pcm_wav, read_pcm

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "benchmark/data"
SAMPLE_RATE = 16000
NOISES = ("traffic", "horn", "wind", "crowd", "crosstalk")
SNRS = (20, 10, 0)


def rms(samples: list[float]) -> float:
    return math.sqrt(math.fsum(value * value for value in samples) / len(samples)) if samples else 0


def _average(samples: list[float], window: int) -> list[float]:
    """Causal moving average, with zero padding at the beginning."""
    result, total = [], 0.0
    for i, value in enumerate(samples):
        total += value
        if i >= window:
            total -= samples[i - window]
        result.append(total / window)
    return result


def traffic(n_samples: int, rng: random.Random, *, sample_rate: int = SAMPLE_RATE) -> list:
    white = [rng.uniform(-1, 1) for _ in range(n_samples)]
    return _average(white, max(1, round(sample_rate * 0.003)))


def horn(n_samples: int, rng: random.Random, *, sample_rate: int = SAMPLE_RATE) -> list:
    """Two tapered sine bursts, separated by silence, even for short clips."""
    result = [0.0] * n_samples
    for start, end, frequency in ((0.1, 0.3, 400), (0.55, 0.75, 550)):
        first, last = int(start * n_samples), int(end * n_samples)
        frequency += rng.uniform(-5, 5)
        phase = rng.uniform(0, 2 * math.pi)
        for i in range(first, last):
            envelope = math.sin(math.pi * (i - first + 0.5) / (last - first)) ** 2
            result[i] = envelope * math.sin(2 * math.pi * frequency * i / sample_rate + phase)
    return result


def wind(n_samples: int, rng: random.Random, *, sample_rate: int = SAMPLE_RATE) -> list:
    phase = rng.uniform(0, 2 * math.pi)
    return [rng.uniform(-1, 1) * (0.5 + 0.5 * math.sin(2 * math.pi * 0.7 * i / sample_rate
                                                   + phase)) for i in range(n_samples)]


def crowd(n_samples: int, rng: random.Random, *, sample_rate: int = SAMPLE_RATE) -> list:
    """Four independent smoothed noise bands on detuned carriers, not real voices."""
    result = [0.0] * n_samples
    for window, center in ((41, 170), (59, 230), (83, 310), (101, 390)):
        band = _average([rng.uniform(-1, 1) for _ in range(n_samples)],
                        max(1, round(window * sample_rate / SAMPLE_RATE)))
        frequency = center + rng.uniform(-8, 8)
        for i, value in enumerate(band):
            result[i] += value * math.sin(2 * math.pi * frequency * i / sample_rate) / 4
    return result


def crosstalk(
    n_samples: int, rng: random.Random, *, sample_rate: int = SAMPLE_RATE,
    other: list[float] | None = None, delay_ms: int | None = None,
) -> list:
    """Delay a second clean clip; pad/crop it to the rider's length without looping."""
    delay = round((rng.randint(200, 400) if delay_ms is None else delay_ms) * sample_rate / 1000)
    count = max(0, n_samples - delay)
    if other is None:
        other = [0.5 * math.sin(2 * math.pi * 180 * i / sample_rate) for i in range(count)]
    return ([0.0] * min(delay, n_samples) + other[:count]
            + [0.0] * max(0, count - len(other)))


def mix_samples(signal: list[float], noise: list[float], snr_db: float) -> list[float]:
    """Return the float mix before clipping, with the requested RMS power ratio."""
    if not signal or len(signal) != len(noise):
        raise ValueError("signal and noise must have the same nonzero length")
    if not math.isfinite(snr_db):
        raise ValueError("SNR must be finite")
    noise_rms = rms(noise)
    if noise_rms == 0:
        raise ValueError("noise has zero RMS; cannot label it with a finite SNR")
    gain = rms(signal) / (10 ** (snr_db / 20) * noise_rms)
    return [speech + gain * interference
            for speech, interference in zip(signal, noise, strict=True)]


def wav_bytes(samples: list[float], sample_rate: int) -> bytes:
    return pcm_wav((max(-32768, min(32767, round(value * 32768))) for value in samples),
                   sample_rate)


@dataclass
class CleanClip:
    row: dict
    path: Path
    blob: bytes
    samples: list[float]
    rate: int


def _load_clips(manifest: Path) -> list[CleanClip]:
    clips, seen = [], set()
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or not re.fullmatch(r"u[0-9]{2}", row.get("id", "")):
                raise ValueError("id must be u followed by two ASCII digits")
            if row["id"] in seen:
                raise ValueError("duplicate id")
            if not isinstance(row.get("reference"), str) or not row["reference"].strip():
                raise ValueError("reference must be nonempty text")
            path = Path(row["path"])
            path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
            blob = path.read_bytes()
            if "sha256" in row and hashlib.sha256(blob).hexdigest() != row["sha256"]:
                raise ValueError("source SHA-256 does not match clean manifest")
            pcm, rate = read_pcm(blob)
            if row["sample_rate"] != rate:
                raise ValueError("source PCM data or sample rate is inconsistent")
            clips.append(CleanClip(row, path, blob, [sample / 32768 for sample in pcm], rate))
            seen.add(row["id"])
        except (ValueError, KeyError, TypeError, OSError) as exc:
            raise ValueError(f"clean manifest line {number}: {exc}") from exc
    if not clips:
        raise ValueError("clean manifest is empty")
    return clips


def generate_mixes(
    clean_manifest: str | Path = DATA / "clean_manifest.jsonl",
    manifest: str | Path = DATA / "mix_manifest.jsonl",
    audio_dir: str | Path = DATA / "audio/mixed",
) -> list[dict]:
    source, manifest, audio_dir = map(lambda p: Path(p).resolve(),
                                     (clean_manifest, manifest, audio_dir))
    clips = _load_clips(source)
    if len({clip.rate for clip in clips}) != 1:
        raise ValueError("crosstalk sources must have matching sample rates")
    ordered = sorted(clips, key=lambda clip: clip.row["id"])
    partners = {clip.row["id"]: ordered[(i + 1) % len(ordered)]
                for i, clip in enumerate(ordered)}
    inputs = {source, *(clip.path for clip in clips)}
    outputs = {audio_dir / f"{clip.row['id']}__{kind}__{snr}.wav"
               for clip in clips for kind, snrs in [("clean", ("clean",)),
                                                   *((kind, SNRS) for kind in NOISES)]
               for snr in snrs}
    if manifest in inputs or manifest in outputs or inputs.intersection(outputs):
        raise ValueError("input and output paths must not overlap")
    rows = []

    def emit(clip: CleanClip, kind: str, snr: int | None, seed: int | None,
             blob: bytes, **details) -> None:
        path = audio_dir / f"{clip.row['id']}__{kind}__{snr if snr is not None else 'clean'}.wav"
        atomic_write(path, blob)
        rows.append({
            "id": clip.row["id"], "noise": kind, "snr_db": snr,
            "path": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path),
            "reference": clip.row["reference"], "sample_rate": clip.rate, "seed": seed,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "duration_s": round(len(clip.samples) / clip.rate, 6), **details,
        })

    generators = {"traffic": traffic, "horn": horn, "wind": wind, "crowd": crowd}
    for clip in clips:
        emit(clip, "clean", None, None, clip.blob)
        for snr_index, snr in enumerate(SNRS):
            for noise_index, kind in enumerate(NOISES):
                seed = int(clip.row["id"][1:]) * 1000 + snr_index * 10 + noise_index
                rng, details = random.Random(seed), {}
                if kind == "crosstalk":
                    partner = partners[clip.row["id"]] if len(clips) > 1 else None
                    delay_ms = rng.randint(200, 400)
                    noise = crosstalk(len(clip.samples), rng, sample_rate=clip.rate,
                                      other=partner.samples if partner else None, delay_ms=delay_ms)
                    details = {"crosstalk_source_id": partner.row["id"] if partner else None,
                               "crosstalk_delay_ms": delay_ms,
                               "crosstalk_fallback": None if partner else "low_tone"}
                else:
                    noise = generators[kind](len(clip.samples), rng, sample_rate=clip.rate)
                mixed = mix_samples(clip.samples, noise, snr)
                clipped = sum(value < -1 or value > 32767 / 32768 for value in mixed)
                emit(clip, kind, snr, seed, wav_bytes(mixed, clip.rate),
                     snr_basis="pre_clip", clipped_samples=clipped, **details)
        print(f"{clip.row['id']}: 1 clean copy and 15 synthetic mixes", flush=True)
    atomic_write(manifest, "".join(json.dumps(row, ensure_ascii=False) + "\n"
                                    for row in rows).encode("utf-8"))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean-manifest", type=Path, default=DATA / "clean_manifest.jsonl")
    parser.add_argument("--manifest", type=Path, default=DATA / "mix_manifest.jsonl")
    parser.add_argument("--audio-dir", type=Path, default=DATA / "audio/mixed")
    args = parser.parse_args(argv)
    try:
        rows = generate_mixes(args.clean_manifest, args.manifest, args.audio_dir)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Mix manifest complete: {len(rows)} rows. All noise is synthetic; SNR is pre-clipping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
