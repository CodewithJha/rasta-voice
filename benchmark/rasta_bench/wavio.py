"""Shared mono 16-bit PCM I/O for the benchmark, using only the standard library.

Read the PCM bytes actually present in streamed WAVs, including Timbre's
placeholder RIFF/data sizes. Writing always produces a normal PCM WAV header.
"""

import io
import os
import sys
import tempfile
import wave
from array import array
from collections.abc import Iterable
from pathlib import Path


def atomic_write(path: Path, blob: bytes) -> None:
    """Replace a file only after its complete contents have been flushed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(blob)
            output.flush()
            os.fsync(output.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_pcm(blob: bytes, *, sample_rate: int | None = None) -> tuple[list[int], int]:
    """Return signed samples and rate, validating mono, 16-bit and complete PCM.

    An optional expected rate adds the caller's format constraint. Durations
    must use the returned sample count rather than the declared WAV frame count.
    """
    try:
        with wave.open(io.BytesIO(blob), "rb") as wav:
            rate = wav.getframerate()
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                    or (sample_rate is not None and rate != sample_rate)):
                suffix = f" at {sample_rate} Hz" if sample_rate is not None else ""
                raise ValueError(f"source must be mono 16-bit PCM WAV{suffix}")
            raw = wav.readframes(len(blob) // 2 + 1)
    except (wave.Error, EOFError) as exc:
        raise ValueError("invalid source PCM WAV") from exc
    if not raw or len(raw) % 2:
        raise ValueError("source PCM is empty or incomplete")
    pcm = array("h")
    pcm.frombytes(raw)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tolist(), rate


def pcm_wav(samples: Iterable[int], sample_rate: int) -> bytes:
    """Encode signed 16-bit samples as mono little-endian PCM without rescaling."""
    pcm = array("h", samples)
    if sys.byteorder != "little":
        pcm.byteswap()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()
