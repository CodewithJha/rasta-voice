"""Live path: audio bytes -> Gnani Prisma REST -> RiderEvent."""

from gnani_client.stt import RIDER_KEYTERMS, RIDER_TOPIC, PrismaSTT
from gnani_client.tts import TimbreTTS
from gnani_client.wav import wav_duration_seconds
from rasta.extract import extract_event_with_source
from rasta.redact import redact_record
from rasta.request_id import watch_gnani_call
from rasta.resilience import UPSTREAM_STT, UPSTREAM_TTS, get_upstream_runtime

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


def _shared_client():
    runtime = get_upstream_runtime()
    return None if runtime is None else runtime.client


def _run_upstream(upstream: str, endpoint: str, func, **watch_kwargs):
    runtime = get_upstream_runtime()

    def work():
        return watch_gnani_call(endpoint, func, **watch_kwargs)

    if runtime is None:
        return work()
    return runtime.call_gnani(upstream, work)


def ingest(audio: bytes, filename: str = "clip.wav") -> dict:
    if not audio:
        raise EmptyClip("empty audio")
    reject_oversize_clip(audio)
    stt = PrismaSTT(client=_shared_client())
    result = _run_upstream(
        UPSTREAM_STT,
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
    return redact_record(
        {
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
    )


def speak_sample(text: str = SAMPLE_LINE) -> bytes:
    """Synthesize a rider line with Timbre (16 kHz WAV) for the sample route."""
    return _run_upstream(
        UPSTREAM_TTS,
        "tts_inference",
        lambda: TimbreTTS(client=_shared_client()).synthesize(text, sample_rate=16000),
    )
