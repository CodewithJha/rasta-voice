"""Demo dirt for the rider page. Stdlib only; not the scored benchmark mixer."""

from __future__ import annotations

import base64
import io
import math
import random
import struct
import wave

PHONE_RATE = 8_000
SIMULATE_SEED = 4
# Modest levels so a Timbre sample line can still be understood after dirt.
RUMBLE_GAIN = 0.16
HORN_GAIN = 0.28
HORN_HZ = 420.0
HORN_SECONDS = 0.16

CONDITIONS = frozenset({"clean", "noisy"})
CONDITION_HINT = "condition must be clean or noisy"


class BadClip(ValueError):
    """The upload is not a PCM WAV this demo path can prepare."""


def envelope(condition: str, wav: bytes, ingest: dict) -> dict:
    return {
        "condition": condition,
        "audio_base64": base64.b64encode(wav).decode("ascii"),
        "ingest": ingest,
    }


def prepare_for_ingest(audio: bytes, condition: str) -> bytes:
    """Return the mono WAV Prisma should receive for this condition."""
    if condition not in CONDITIONS:
        raise BadClip(CONDITION_HINT)
    samples, rate = read_pcm(audio)
    if not samples:
        raise BadClip("clip has no PCM samples")
    if condition == "noisy":
        samples, rate = dirty(samples, rate)
    return write_wav(samples, rate)


def dirty(samples: list[int], rate: int) -> tuple[list[int], int]:
    """Mix a horn burst and rumble, then downsample to 8 kHz."""
    return _downsample_to_phone(_mix(samples, rate, SIMULATE_SEED), rate)


def read_pcm(blob: bytes) -> tuple[list[int], int]:
    """Decode 16-bit PCM WAV to mono samples, including Timbre placeholder sizes."""
    if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise BadClip("clip is not a PCM WAV")
    pos = 12
    channels = 0
    rate = 0
    width = 0
    audio_format = 0
    pcm: bytes | None = None
    while pos + 8 <= len(blob):
        chunk_id = blob[pos : pos + 4]
        size = struct.unpack_from("<I", blob, pos + 4)[0]
        body = pos + 8
        if chunk_id == b"fmt " and body + 16 <= len(blob):
            audio_format, channels, rate, _byte_rate, _align, bits = struct.unpack_from(
                "<HHIIHH", blob, body
            )
            width = bits // 8
        elif chunk_id == b"data":
            available = len(blob) - body
            data_len = available if size in (0, 0xFFFFFFFF) else min(size, available)
            frame = width * channels
            if frame:
                data_len -= data_len % frame
            pcm = blob[body : body + data_len]
            if size in (0, 0xFFFFFFFF):
                break
            pos = body + size + (size & 1)
            continue
        if size in (0, 0xFFFFFFFF):
            raise BadClip("clip WAV header is invalid")
        nxt = body + size + (size & 1)
        if nxt <= pos:
            raise BadClip("clip WAV header is invalid")
        pos = nxt
    if audio_format != 1 or channels < 1 or rate < 1 or width != 2 or pcm is None:
        raise BadClip("clip must be 16-bit PCM WAV")
    count = len(pcm) // 2
    samples = list(struct.unpack("<" + "h" * count, pcm))
    if channels == 1:
        return samples, rate
    frames = len(samples) // channels
    mono = [
        int(round(sum(samples[i * channels + c] for c in range(channels)) / channels))
        for i in range(frames)
    ]
    return mono, rate


def write_wav(samples: list[int], rate: int) -> bytes:
    buf = io.BytesIO()
    payload = struct.pack("<" + "h" * len(samples), *[_clamp(s) for s in samples])
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(payload)
    return buf.getvalue()


def _mix(samples: list[int], rate: int, seed: int) -> list[int]:
    rng = random.Random(seed)
    rumble = _rumble(len(samples), rng)
    horn = _horn(len(samples), rate)
    mixed: list[int] = []
    for i, sample in enumerate(samples):
        value = sample / 32768.0 + RUMBLE_GAIN * rumble[i] + HORN_GAIN * horn[i]
        mixed.append(_clamp(int(round(value * 32768.0))))
    return mixed


def _rumble(n: int, rng: random.Random) -> list[float]:
    # Leaky integrator of white noise: a low road rumble, deterministic under seed 4.
    out = [0.0] * n
    acc = 0.0
    leak = 0.997
    for i in range(n):
        acc = acc * leak + rng.uniform(-1.0, 1.0) * (1.0 - leak)
        out[i] = acc
    peak = max((abs(x) for x in out), default=1.0) or 1.0
    return [x / peak for x in out]


def _horn(n: int, rate: int) -> list[float]:
    # One short honk a little into the clip so the speech onset is still heard.
    start = min(max(n - 1, 0), max(0, int(0.12 * n)))
    length = min(n - start, max(1, int(HORN_SECONDS * rate)))
    out = [0.0] * n
    if length <= 0:
        return out
    for i in range(length):
        env = math.sin(math.pi * i / length)
        phase = 2 * math.pi * HORN_HZ * i / rate
        out[start + i] = env * math.sin(phase)
    return out


def _downsample_to_phone(samples: list[int], rate: int) -> tuple[list[int], int]:
    if rate == PHONE_RATE:
        return samples, rate
    if rate <= 0 or rate % PHONE_RATE != 0:
        raise BadClip(f"sample rate must be a multiple of {PHONE_RATE} Hz")
    factor = rate // PHONE_RATE
    frames = len(samples) // factor
    if frames == 0:
        raise BadClip("clip is too short to downsample")
    out = [
        int(round(sum(samples[i * factor : (i + 1) * factor]) / factor)) for i in range(frames)
    ]
    return out, PHONE_RATE


def _clamp(sample: int) -> int:
    return max(-32768, min(32767, sample))
