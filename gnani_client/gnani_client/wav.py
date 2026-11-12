"""WAV helpers. Stdlib only."""

import struct


def wav_duration_seconds(blob: bytes) -> float | None:
    """Duration of a PCM WAV, tolerant of streaming headers.

    Timbre streams its WAV, so the RIFF and ``data`` sizes in the header are
    placeholders (0xFFFFFFFF). ``wave`` trusts them and reports hours. This
    walks the chunks, reads ``fmt``, and measures the bytes actually present.
    Returns None for anything that is not a PCM WAV.
    """
    if len(blob) < 12 or blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        return None
    pos = 12
    byte_rate = 0
    while pos + 8 <= len(blob):
        chunk_id = blob[pos : pos + 4]
        size = struct.unpack("<I", blob[pos + 4 : pos + 8])[0]
        body = pos + 8
        if chunk_id == b"fmt " and body + 16 <= len(blob):
            byte_rate = struct.unpack("<I", blob[body + 8 : body + 12])[0]
        elif chunk_id == b"data":
            if not byte_rate:
                return None
            available = len(blob) - body
            data_len = available if size in (0, 0xFFFFFFFF) else min(size, available)
            return round(data_len / byte_rate, 3)
        pos = body + size + (size & 1)
    return None
