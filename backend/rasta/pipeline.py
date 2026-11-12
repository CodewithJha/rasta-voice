"""Hello-world path: audio bytes -> Prisma (or mock) -> RiderEvent."""

from gnani_client.stt import RIDER_KEYTERMS, RIDER_TOPIC, PrismaSTT
from rasta.extract import extract_event

_MAX_BYTES = 2_000_000


class ClipTooLarge(ValueError):
    pass


class EmptyClip(ValueError):
    pass


def ingest(audio: bytes, filename: str = "clip.wav") -> dict:
    if not audio:
        raise EmptyClip("empty audio")
    if len(audio) > _MAX_BYTES:
        raise ClipTooLarge("clip must be under 2 MB (Prisma REST is 30 seconds)")
    stt = PrismaSTT()
    result = stt.transcribe(
        audio,
        filename=filename,
        model="prisma-v3.0",
        language_code="hi-IN,en-IN",
        output_format="codemix",
        keyterms=RIDER_KEYTERMS,
        topic=RIDER_TOPIC,
    )
    event = extract_event(result.transcript)
    return {
        "transcript": result.transcript,
        "stt": {
            "model": result.model,
            "mock": result.mock,
            "request_id": result.request_id,
            "detected_language_code": result.detected_language_code,
        },
        "event": event.model_dump(mode="json"),
    }
