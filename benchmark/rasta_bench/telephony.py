"""Simulated telephony: box-average to 8 kHz, then G.711 mu-law encode/decode.

The WAV container holds linear 16-bit PCM after codec damage. These are not
recorded phone calls. Run ``python -m rasta_bench.telephony`` after the mixer.
Optional --dropouts writes a separate dataset, never replacing the default set.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from rasta_bench.wavio import atomic_write, pcm_wav, read_pcm

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "benchmark/data"
PHONE_RATE = 8000
BIAS = 132
DROPOUT_INTERVAL = 50


def linear_to_mulaw(sample: int) -> int:
    """Encode signed 16-bit PCM with G.711's 14-bit uniform input quantizer.

    Arithmetic right shift retains the negative-input quantization convention.
    The biased magnitude selects an exponent and four mantissa bits; the wire
    octet is complemented. No optional zero-trap substitution is applied.
    Reference: https://www.itu.int/rec/T-REC-G.711/
    """
    if type(sample) is not int or not -32768 <= sample <= 32767:
        raise ValueError("mu-law input must be a signed 16-bit integer")
    uniform = sample >> 2
    magnitude = min(8191, abs(uniform) + (BIAS >> 2))
    exponent = max(0, magnitude.bit_length() - 6)
    mantissa = (magnitude >> (exponent + 1)) & 15
    mask = 0x7F if uniform < 0 else 0xFF
    return ((exponent << 4) | mantissa) ^ mask


def mulaw_to_linear(code: int) -> int:
    """Decode a G.711 octet into linear signed 16-bit PCM."""
    if type(code) is not int or not 0 <= code <= 255:
        raise ValueError("mu-law code must be an integer in 0..255")
    unpacked = code ^ 0xFF
    magnitude = (((unpacked & 15) << 3) + BIAS) << ((unpacked >> 4) & 7)
    magnitude -= BIAS
    return -magnitude if unpacked & 0x80 else magnitude


def mulaw_roundtrip(samples: list[int]) -> list[int]:
    return [mulaw_to_linear(linear_to_mulaw(sample)) for sample in samples]


def downsample(samples: list[int], sample_rate: int) -> list[int]:
    """Average each integer-ratio block; retain a final partial block.

    This is the issue's simple box-average simulation, not a full telephone
    channel model. At most one 8 kHz output sample of duration rounding occurs.
    """
    if type(sample_rate) is not int or sample_rate < PHONE_RATE or sample_rate % PHONE_RATE:
        raise ValueError("source sample rate must be a positive multiple of 8000 Hz")
    factor = sample_rate // PHONE_RATE
    return [round(sum(block) / len(block))
            for start in range(0, len(samples), factor)
            if (block := samples[start:start + factor])]


def _read_pcm(path: Path) -> tuple[bytes, list[int], int]:
    blob = path.read_bytes()
    pcm, rate = read_pcm(blob)
    if rate < PHONE_RATE or rate % PHONE_RATE:
        raise ValueError("source sample rate must be a positive multiple of 8000 Hz")
    return blob, pcm, rate


def to_telephony(
    src_wav: str | Path, dest_wav: str | Path, *, dropouts: bool = False,
) -> dict:
    """Write decoded 8 kHz PCM and return conversion provenance for a manifest."""
    source, destination = Path(src_wav).resolve(), Path(dest_wav).resolve()
    if source == destination:
        raise ValueError("source and destination must not overlap")
    original, samples, rate = _read_pcm(source)
    converted = mulaw_roundtrip(downsample(samples, rate))
    if dropouts:
        for index in range(DROPOUT_INTERVAL - 1, len(converted), DROPOUT_INTERVAL):
            converted[index] = 0
    blob = pcm_wav(converted, PHONE_RATE)
    atomic_write(destination, blob)
    return {
        "telephony": "mulaw8k", "provenance": "simulated_telephony", "dropouts": dropouts,
        "sample_rate": PHONE_RATE, "source_sample_rate": rate,
        "duration_s": round(len(converted) / PHONE_RATE, 6),
        "source_duration_s": round(len(samples) / rate, 6),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "source_sha256": hashlib.sha256(original).hexdigest(),
    }


def generate_phone_clips(
    mix_manifest: str | Path = DATA / "mix_manifest.jsonl",
    manifest: str | Path = DATA / "phone_manifest.jsonl",
    audio_dir: str | Path = DATA / "audio/phone",
    *, dropouts: bool = False,
) -> list[dict]:
    source, manifest, audio_dir = (Path(path).resolve()
                                   for path in (mix_manifest, manifest, audio_dir))
    plan, keys, destinations = [], set(), set()
    for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            required = {"id", "noise", "snr_db", "path", "reference", "sample_rate"}
            if not isinstance(row, dict) or not required.issubset(row):
                raise ValueError("row is missing mix manifest fields")
            if not all(isinstance(row[name], str) and row[name].strip()
                       for name in ("id", "noise", "reference", "path")):
                raise ValueError("id, noise, reference and path must be nonempty strings")
            key = row["id"], row["noise"], row["snr_db"]
            path = Path(row["path"])
            path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
            destination = (audio_dir / path.name).resolve()
            if key in keys or destination in destinations:
                raise ValueError("duplicate mix condition or output filename")
            keys.add(key)
            destinations.add(destination)
            plan.append((row, path, destination))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"mix manifest line {number}: {exc}") from exc
    if not plan:
        raise ValueError("mix manifest is empty")
    inputs = {source, *(path for _, path, _ in plan)}
    if manifest in inputs or manifest in destinations or inputs.intersection(destinations):
        raise ValueError("input and output paths must not overlap")

    # Validate all sources before replacing any outputs. Do not retain all PCM in memory.
    for row, path, _ in plan:
        blob, _, rate = _read_pcm(path)
        if type(row["sample_rate"]) is not int or rate != row["sample_rate"]:
            raise ValueError(f"{path.name}: source rate differs from mix manifest")
        if "sha256" in row and hashlib.sha256(blob).hexdigest() != row["sha256"]:
            raise ValueError(f"{path.name}: source SHA-256 differs from mix manifest")
    rows = []
    for row, path, destination in plan:
        metadata = to_telephony(path, destination, dropouts=dropouts)
        stored_path = (destination.relative_to(ROOT).as_posix()
                       if destination.is_relative_to(ROOT) else str(destination))
        rows.append({**row, **metadata, "path": stored_path})
    atomic_write(manifest, "".join(json.dumps(row, ensure_ascii=False) + "\n"
                                    for row in rows).encode("utf-8"))
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mix-manifest", type=Path, default=DATA / "mix_manifest.jsonl")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--audio-dir", type=Path)
    parser.add_argument("--dropouts", action="store_true", help="use a separate dropout dataset")
    args = parser.parse_args(argv)
    suffix = "phone_dropouts" if args.dropouts else "phone"
    manifest = args.manifest or DATA / f"{suffix}_manifest.jsonl"
    audio_dir = args.audio_dir or DATA / f"audio/{suffix}"
    try:
        rows = generate_phone_clips(args.mix_manifest, manifest, audio_dir, dropouts=args.dropouts)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Simulated telephony complete: {len(rows)} PCM WAVs at 8000 Hz; "
          f"G.711 mu-law round-trip; dropouts={args.dropouts}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
