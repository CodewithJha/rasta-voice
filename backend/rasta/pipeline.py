"""Live path: audio bytes -> Gnani Prisma REST -> RiderEvent."""

from gnani_client.stt import RIDER_KEYTERMS, RIDER_TOPIC, PrismaSTT
from gnani_client.tts import TimbreTTS
from gnani_client.wav import wav_duration_seconds
from rasta.extract import extract_event

_MAX_BYTES = 2_000_000

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
        output_format=STT_FORMAT,
        keyterms=RIDER_KEYTERMS,
        topic=RIDER_TOPIC,
    )
    event = extract_event(result.transcript)
    return {
        "transcript": result.transcript,
        "stt": {
            "model": result.model,
            "request_id": result.request_id,
            "detected_language_code": result.detected_language_code,
            "processing_time": result.processing_time,
            "audio_seconds": wav_duration_seconds(audio),
        },
        "event": event.model_dump(mode="json"),
    }


def speak_sample(text: str = SAMPLE_LINE) -> bytes:
    """Synthesize a rider line with Timbre (16 kHz WAV) for the sample route."""
    return TimbreTTS().synthesize(text, sample_rate=16000)
