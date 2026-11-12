"""Tiny PCM WAV writer. Stdlib only, so mock mode needs no audio library."""

import io
import math
import struct
import wave


def tone_wav(seconds: float = 0.3, rate: int = 8000, freq: float = 440.0) -> bytes:
    n = max(1, int(seconds * rate))
    frames = bytearray()
    for i in range(n):
        sample = int(6000 * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack("<h", sample)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(frames)
    return buf.getvalue()
