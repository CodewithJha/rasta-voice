"""Generate clean Timbre speech stems; cache successful calls on disk.

Run from the repository root with GNANI_API_KEY in the environment:
    python -m rasta_bench.speak

The manifest is checkpointed after each successful clip. Only a complete,
successful live run should be committed as benchmark/data/clean_manifest.jsonl.
"""

import argparse
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import wave
from pathlib import Path

import httpx

from gnani_client.env import api_key, require_api_key
from gnani_client.errors import GnaniError
from gnani_client.tts import TimbreTTS
from gnani_client.wav import wav_duration_seconds
from rasta_bench.corpus import load_utterances

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "benchmark/data"
MODEL = "timbre-v3.0"
VOICE = "Shivani"
LANGUAGE = "hi-en"
SAMPLE_RATE = 16000


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
        try:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_manifest(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    entries = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            entry = json.loads(line)
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise ValueError("expected an object with a string id")
            if entry["id"] in entries:
                raise ValueError("duplicate id")
        except ValueError as exc:
            raise ValueError(f"manifest line {number}: {exc}") from exc
        entries[entry["id"]] = entry
    return entries


def _duration(blob: bytes) -> float:
    """Validate PCM format and measure actual bytes, not streaming frame counts."""
    try:
        with wave.open(io.BytesIO(blob), "rb") as audio:
            if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (
                SAMPLE_RATE, 1, 2,
            ):
                raise ValueError("Timbre must return mono 16-bit PCM WAV at 16000 Hz")
            pcm = audio.readframes(len(blob) // 2 + 1)
    except (wave.Error, EOFError) as exc:
        raise ValueError("Timbre returned an invalid PCM WAV") from exc
    duration = wav_duration_seconds(blob)
    if not pcm or len(pcm) % 2 or duration is None or duration <= 0:
        raise ValueError("Timbre returned empty or incomplete PCM audio")
    if duration != round(len(pcm) / (SAMPLE_RATE * 2), 3):
        raise ValueError("Timbre returned inconsistent PCM timing metadata")
    return duration


def _synthesize(tts: TimbreTTS, text: str) -> bytes:
    # Only an explicit rate-limit rejection is retried. A timeout could have
    # consumed credit already, so it is left for the operator to investigate.
    for attempt in range(4):
        try:
            return tts.synthesize(
                text, model=MODEL, voice=VOICE, language=LANGUAGE,
                sample_rate=SAMPLE_RATE, container="wav",
            )
        except GnaniError as exc:
            if exc.status != 429 or attempt == 3:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable retry state")


def generate_clean_clips(
    corpus: str | Path = DATA / "utterances.jsonl",
    manifest: str | Path = DATA / "clean_manifest.jsonl",
    audio_dir: str | Path = DATA / "audio/clean",
    *,
    force: bool = False,
) -> list[dict]:
    """Synthesize sequentially and checkpoint each success for a safe rerun.

    Cache hits require matching text, synthesis settings, file path, SHA-256,
    PCM format and duration. References and spoken text are identical: tags
    are optional in issue 03 and this clean baseline deliberately uses none.
    A key is required even when the whole corpus is cached.
    """
    require_api_key()
    rows = load_utterances(corpus)
    if not rows:
        raise ValueError("corpus is empty")
    manifest, audio_dir = Path(manifest).resolve(), Path(audio_dir).resolve()
    source = Path(corpus).resolve()
    targets = [audio_dir / f"{row['id']}.wav" for row in rows]
    if source == manifest or source in targets or manifest in targets:
        raise ValueError("corpus, manifest and audio paths must not overlap")
    previous = _read_manifest(manifest)
    completed = {}
    planned = []
    for row, path in zip(rows, targets, strict=True):
        stored_path = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
        expected = {
            "id": row["id"], "reference": row["text"], "spoken_text": row["text"],
            "path": stored_path, "voice": VOICE, "model": MODEL,
            "language": LANGUAGE, "sample_rate": SAMPLE_RATE,
        }
        cached = previous.get(row["id"], {})
        if all(cached.get(key) == value for key, value in expected.items()) and path.is_file():
            blob = path.read_bytes()
            if hashlib.sha256(blob).hexdigest() == cached.get("sha256"):
                try:
                    duration = _duration(blob)
                except ValueError:
                    pass
                else:
                    if duration == cached.get("duration_s"):
                        completed[row["id"]] = {**expected, "sha256": cached["sha256"],
                                                "duration_s": duration}
        planned.append((expected, path))

    def checkpoint() -> list[dict]:
        entries = [completed[row["id"]] for row in rows if row["id"] in completed]
        content = "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries)
        _atomic_write(manifest, content.encode("utf-8"))
        return entries

    with httpx.Client(timeout=60.0) as http:
        tts = TimbreTTS(client=http)
        for expected, path in planned:
            if not force and expected["id"] in completed:
                continue
            print(f"{expected['id']}: requesting Timbre speech", flush=True)
            blob = _synthesize(tts, expected["spoken_text"])
            duration = _duration(blob)
            _atomic_write(path, blob)
            completed[expected["id"]] = {
                **expected, "sha256": hashlib.sha256(blob).hexdigest(), "duration_s": duration,
            }
            checkpoint()
    return checkpoint()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DATA / "utterances.jsonl")
    parser.add_argument("--manifest", type=Path, default=DATA / "clean_manifest.jsonl")
    parser.add_argument("--audio-dir", type=Path, default=DATA / "audio/clean")
    parser.add_argument(
        "--force", action="store_true", help="regenerate even matching cached clips"
    )
    args = parser.parse_args(argv)
    try:
        rows = generate_clean_clips(args.corpus, args.manifest, args.audio_dir, force=args.force)
    except (GnaniError, httpx.HTTPError, OSError, ValueError) as exc:
        message = str(exc)
        if key := api_key():
            message = message.replace(key, "[redacted]")
        print(message, file=sys.stderr)
        return 1
    print(f"Clean manifest complete: {len(rows)} clips. Spot-check speech before committing it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
