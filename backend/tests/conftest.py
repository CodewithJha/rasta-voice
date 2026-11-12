"""Test-only helpers. The clients always hit the network; tests swap the
transport with ``httpx.MockTransport`` so CI needs no Gnani key."""

import io
import math
import struct
import wave

import pytest


def tone_wav(seconds: float = 0.3, rate: int = 8000, freq: float = 440.0) -> bytes:
    n = max(1, int(seconds * rate))
    frames = bytearray()
    for i in range(n):
        frames += struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / rate)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return buf.getvalue()


@pytest.fixture
def make_wav():
    """Factory for a short synthetic PCM WAV (a sine, not speech)."""
    return tone_wav
