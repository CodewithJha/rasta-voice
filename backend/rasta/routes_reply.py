"""Rider-facing reply speech, with a bounded 10-minute process cache.

Six requests/minute per direct client IP, one concurrent Timbre reply call,
15-second HTTP timeout, no retries. Issue 13 can apply the shared speech budget
in addition to these local limits. A restart clears the cache with the store.
"""

import base64
import hashlib
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import TypedDict

import httpx
from fastapi import APIRouter, HTTPException, Request

from gnani_client.env import base_url, require_api_key
from gnani_client.errors import GnaniError
from gnani_client.tts import TimbreTTS
from gnani_client.wav import wav_duration_seconds
from rasta.reply import reply_text
from rasta.request_id import watch_gnani_call
from rasta.schema import RiderEvent
from rasta.store import attach_event_store

reply_router = APIRouter()
REPLY_TTL_SECONDS = 600
REPLY_CACHE_ENTRIES = 128
REPLY_CACHE_BYTES = 8_000_000
REPLY_REQUESTS_PER_MINUTE = 6
_attach_lock = threading.Lock()


class ReplyAudioPayload(TypedDict):
    text: str
    audio_base64: str
    content_type: str
    audio_seconds: float


class ReplySpeech:
    """Thread-safe cache and admission for synchronous FastAPI worker threads."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._state = threading.Lock()
        self._upstream = threading.Lock()
        self._cache: OrderedDict[tuple, tuple[float, ReplyAudioPayload]] = OrderedDict()
        self._clients: OrderedDict[str, deque] = OrderedDict()
        self._size = 0

    def _cached(self, cache_key: tuple, now: float) -> dict | None:
        # Caller holds _state. Expiry and eviction also keep memory bounded.
        for key, (expires, payload) in list(self._cache.items()):
            if expires <= now:
                self._size -= len(payload["audio_base64"])
                del self._cache[key]
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return dict(self._cache[cache_key][1])
        return None

    def reply(
        self,
        event_id: str,
        event: RiderEvent,
        client_ip: str,
        *,
        state: str | None = None,
        acked: bool = False,
    ) -> dict:
        key = require_api_key()  # Missing/revoked configuration cannot use old cached audio.
        text = reply_text(event, state, acked=acked)
        profile = hashlib.sha256(f"{key}\n{base_url()}".encode()).hexdigest()
        cache_key = (event_id, text, profile)
        with self._state:
            now = self.clock()
            recent = self._clients.setdefault(client_ip, deque())
            while recent and recent[0] <= now - 60:
                recent.popleft()
            if len(recent) >= REPLY_REQUESTS_PER_MINUTE:
                raise HTTPException(429, "Reply limit reached; retry in a minute.",
                                    headers={"Retry-After": "60"})
            recent.append(now)
            self._clients.move_to_end(client_ip)
            while len(self._clients) > 256:
                self._clients.popitem(last=False)
            cached = self._cached(cache_key, now)
            if cached is not None:
                return cached
        # Never park worker threads behind a slow speech request.
        if not self._upstream.acquire(blocking=False):
            raise HTTPException(429, "Reply speech is busy; retry shortly.",
                                headers={"Retry-After": "1"})
        try:
            with self._state:
                cached = self._cached(cache_key, self.clock())
                if cached is not None:
                    return cached
            try:
                with httpx.Client(timeout=15.0) as http:
                    audio = watch_gnani_call(
                        "tts_inference",
                        lambda: TimbreTTS(key=key, client=http).synthesize(text),
                    )
            except httpx.HTTPError as exc:
                raise GnaniError("Timbre TTS request failed") from exc
            seconds = wav_duration_seconds(audio)
            if (not audio.startswith(b"RIFF") or len(audio) > 1_000_000
                    or seconds is None or not 0 < seconds <= 30):
                raise GnaniError("Timbre TTS returned invalid reply WAV audio", status=200)
            payload: ReplyAudioPayload = {
                "text": text,
                "audio_base64": base64.b64encode(audio).decode("ascii"),
                "content_type": "audio/wav",
                "audio_seconds": seconds,
            }
            with self._state:
                self._cache[cache_key] = (self.clock() + REPLY_TTL_SECONDS, payload)
                self._size += len(payload["audio_base64"])
                while (len(self._cache) > REPLY_CACHE_ENTRIES
                       or self._size > REPLY_CACHE_BYTES):
                    _, (_, evicted) = self._cache.popitem(last=False)
                    self._size -= len(evicted["audio_base64"])
            return dict(payload)
        finally:
            self._upstream.release()


@reply_router.post("/api/reply/{event_id}")
def reply_to_event(event_id: str, request: Request) -> dict:
    # The sync route runs in FastAPI's worker pool. A disconnected caller does
    # not cancel the HTTP thread halfway through a charged synthesis/cache write.
    from rasta.main import _guard

    store = attach_event_store(request.app)
    record = next((row for row in store.list_since(None) if row["id"] == event_id), None)
    if record is None:
        raise HTTPException(404, "Event not found")
    with _attach_lock:
        attached = getattr(request.app.state, "reply_speech", None)
        if attached is None or attached[0] is not store:
            attached = (store, ReplySpeech())
            request.app.state.reply_speech = attached
    client_ip = request.client.host if request.client else "unknown"
    event = RiderEvent.model_validate(record["event"])
    acked = bool(record.get("ack_at") or record.get("ack_by"))
    state = record.get("state") if isinstance(record.get("state"), str) else None
    return _guard(lambda: attached[1].reply(
        event_id, event, client_ip, state=state, acked=acked,
    ))
