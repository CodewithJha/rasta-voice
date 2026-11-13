"""Live path: audio bytes -> Gnani Prisma REST -> RiderEvent."""

from gnani_client.stt import RIDER_KEYTERMS, RIDER_TOPIC, PrismaSTT
from gnani_client.tts import TimbreTTS
from gnani_client.wav import wav_duration_seconds
from rasta.extract import extract_event_with_source
from rasta.request_id import watch_gnani_call

MAX_CLIP_BYTES = 2_000_000
CLIP_TOO_LARGE = "clip must be under 2 MB (Prisma REST is 30 seconds)"

# Synthetic rider line for the "speak a sample" demo. Timbre says it, Prisma
# hears it. Numbers are words so Timbre does not have to guess.
SAMPLE_LINE = (
    "Bhaiya, gate band hai aur customer phone nahi utha raha. "
    "Order eighteen pe main das minute se khada hoon."
)

# Latin script out, so the rules extractor and the dispatcher read one script.
STT_FORMAT = "transliterate"


class ClipTooLarge(ValueError):
    pass


class EmptyClip(ValueError):
    pass


def reject_oversize_clip(data: bytes) -> bytes:
    """Raise ``ClipTooLarge`` when ``data`` exceeds ``MAX_CLIP_BYTES``."""
    if len(data) > MAX_CLIP_BYTES:
        raise ClipTooLarge(CLIP_TOO_LARGE)
    return data


async def read_upload_clip(audio_file) -> bytes:
    """Read an upload, stopping at one byte past the clip ceiling.

    Size rejection stays with the caller so it can run inside ``_guard``.
    """
    return await audio_file.read(MAX_CLIP_BYTES + 1)


def ingest(audio: bytes, filename: str = "clip.wav") -> dict:
    if not audio:
        raise EmptyClip("empty audio")
    reject_oversize_clip(audio)
    stt = PrismaSTT()
    result = watch_gnani_call(
        "stt_rest",
        lambda: stt.transcribe(
            audio,
            filename=filename,
            model="prisma-v3.0",
            language_code="hi-IN,en-IN",
            output_format=STT_FORMAT,
            keyterms=RIDER_KEYTERMS,
            topic=RIDER_TOPIC,
        ),
        audio=audio,
    )
    extracted = extract_event_with_source(result.transcript)
    return {
        "transcript": result.transcript,
        "stt": {
            "model": result.model,
            "request_id": result.request_id,
            "detected_language_code": result.detected_language_code,
            "processing_time": result.processing_time,
            "audio_seconds": wav_duration_seconds(audio),
        },
        "event": extracted.event.model_dump(mode="json"),
        "extractor_source": extracted.source,
        "fallback_reason": extracted.fallback_reason,
    }


def speak_sample(text: str = SAMPLE_LINE) -> bytes:
    """Synthesize a rider line with Timbre (16 kHz WAV) for the sample route."""
    return watch_gnani_call(
        "tts_inference",
        lambda: TimbreTTS().synthesize(text, sample_rate=16000),
    )
