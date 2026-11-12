# 07 — Prisma realtime WebSocket

- **Labels:** `area:app`, `day:2`, `stt`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 2 (13–14 Nov 2026)
- **Depends on:** issue 04, only so the transcript you emit can be stored with the same `append`. If 04 has not merged, land this behind it the same day. Do not start issue 09 until this is merged.

## Description

The rider does not upload a file in the real demo. They talk. Prisma's realtime endpoint is `wss://api.vachana.ai/stt/v3/stream` (or `PrismaSTT.stream_url`). The skeleton already builds the headers in `stream_headers`. Use them. Add the socket loop in a new module so you don't rewrite `gnani_client/stt.py`.

Protocol, from the docs:

- Upgrade headers include `x-api-key-id`, `model`, `language_code`, `x-sample-rate`, `format`. Use `preset="telephony"` when the browser sends 8 kHz, and the default 16 kHz headers when the browser sends 16 kHz. The browser must tell you which.
- Send binary frames of 16-bit mono PCM, 1024 bytes each.
- When the rider stops, send a text frame `{"type": "commit"}`.
- Read JSON frames. A transcript looks like `{"type": "transcript", "text": "...", "segment_id": "...", "latency": 320}`. An error frame has `type: "error"`.
- Session limit is 15 minutes. Idle timeout default is 60 seconds. For the demo, close the socket on commit. Don't hold it open.

Always open the real socket. After commit, collect the transcript frames, then run `extract_event` and `store.append`, and send the stamped record to the browser as one JSON text frame. If `GNANI_API_KEY` is missing, close the browser socket with an `{"type": "error"}` frame carrying the missing-key message. If Gnani sends an error frame or refuses the handshake (401/402/429), forward its message the same way. Never invent a transcript.

Add the `websockets` package to `gnani_client/pyproject.toml` in this PR. Pin a current 13.x or whatever `additional_headers` matches (the docs note that `websockets` < 13 wants `extra_headers`).

Browser side, in `frontend/src/rider.ts` only:

- A button, "Talk". `getUserMedia({audio: true})`, `AudioContext`, resample to 16-bit PCM with a `ScriptProcessor` or `AudioWorklet`. If the mic permission fails, the button shows the error in the existing `<pre>` and does not crash the page.
- A second button, "Stream a sample line", so the demo works on a machine with no mic: the API asks Timbre for `pipeline.SAMPLE_LINE` as raw 16 kHz PCM (`container="raw"`, `sample_rate=16000`), then streams it through the same Prisma realtime path in 1024-byte frames. Real TTS in, real realtime STT out.
- On a transcript message, paint the JSON the way the upload path already does, and dispatch `rasta:event` so the slate updates.

Backend socket: `WS /api/stream` on a new router `backend/rasta/routes_stream.py`. One `include_router` line in `main.py`. The browser talks to your API, and your API talks to Gnani, so the key never reaches the browser.

## Files to touch

- `gnani_client/stt_stream.py` (new)
- `gnani_client/pyproject.toml` (add `websockets`)
- `gnani_client/tests/test_stream.py` (new)
- `backend/rasta/routes_stream.py` (new)
- `backend/rasta/main.py` (one include line)
- `frontend/src/rider.ts` (the two buttons)
- `frontend/package.json` only if you need a dev type. Prefer no new frontend dependency.

## Do not touch

`frontend/src/dispatch.ts` (issue 10), `frontend/src/styles.css` (put three new rules in `frontend/src/rider.css` and import it from `rider.ts`), `benchmark/`, `extract.py` except to call `extract_event`.

## Input / output contract

Browser → API: binary PCM frames, then a text frame `{"type":"commit","sample_rate":16000}`.

API → browser: text frames.

```json
{"type": "transcript", "text": "Bhaiya, gate band hai aur customer phone nahi utha raha...", "segment_id": "seg_1"}
```

Then, when extraction finishes:

```json
{"type": "event", "id": "...", "created_at": "...", "transcript": "...", "stt": {}, "event": {}}
```

`stt_stream.transcribe_pcm(pcm: bytes, sample_rate: int, *, connect=websockets.connect) -> SttResult` is the function the route calls. It always connects to Gnani. The `connect` parameter exists so the unit test can pass a fake socket factory inside the test (records sent frames, replays scripted server frames). No env flag or app-level switch fakes the socket.

## Acceptance criteria

- [ ] `transcribe_pcm` with a fake `connect` (defined in the test file) sends 1024-byte binary frames then `{"type":"commit"}`, and joins the transcript frames it gets back.
- [ ] With `GNANI_API_KEY` unset, `WS /api/stream` replies with an error frame naming the missing key, and the page shows it.
- [ ] A test of `stream_headers` / the new module asserts the live URL path is `/stt/v3/stream` and the telephony preset sets `x-sample-rate` to `8000`.
- [ ] With a real key, the "Stream a sample line" button ends with the slate showing customer unreachable / order 18. Click it. Don't only look at the DOM.
- [ ] One manual live test with a real voice through the mic. Paste the transcript and Gnani `request_id` in the PR (synthetic words only).
- [ ] Mic denial shows a message and leaves the upload form working.
- [ ] The Gnani key is read on the server only. Confirm the frontend bundle has no `GNANI` string (`rg GNANI frontend/src` is empty).
- [ ] `pytest`, `ruff`, and `npm run check` pass.

## How to test

```bash
pytest gnani_client/tests/test_stream.py backend/tests -q
cd frontend && npm run check
```

Then, with `GNANI_API_KEY` set, `uvicorn` and `npm run dev`: click **Stream a sample line**, confirm the slate, talk into the mic once, then refuse the mic in the browser site settings and click **Talk**.

<!-- rasta-voice-audit-2026-11-12 -->

### Realtime behavior acceptance (not just socket-shaped batch)

- [ ] With a live microphone, frames are forwarded to the upstream Gnani WebSocket **while recording**; do not buffer the full utterance and send only after the rider presses Stop.
- [ ] Implement an async browser-frame-to-upstream pump with bounded buffering/backpressure, and propagate partial transcripts as they arrive. `transcribe_pcm(bytes, ...)` may remain as a test/sample helper, but must not be the only live microphone path.
- [ ] Commit ends the stream only after queued audio frames drain; session cancellation, disconnect and upstream errors close both sockets and free resources.
- [ ] An integration test proves upstream receives audio *before* the browser commit frame; a real manual mic run records time to first transcript and final event (do not invent latency).
- [ ] Throttle the Timbre sample's PCM frames to realistic elapsed playback time when the video claims live streaming; do not treat a rapid batch send as proof of live latency.


<!-- rasta-voice-production-2026-11-12 -->

### Production: websocket lifecycle

The audit section already requires a live pump, backpressure, and cleanup. Production adds hard limits and origin checks (SEC-14, REL-06, FE-05):

- [ ] Enforce Prisma's 15-minute session cap and a 60 s idle timeout on both sockets; close cleanly with an error frame the UI can show.
- [ ] Cap concurrent `/api/stream` sessions (`RASTA_MAX_STREAMS`, default 2). A third caller gets an immediate error frame or a 429 close, and no upstream socket is opened.
- [ ] Check `Origin` against the same allow list as issue 27. Missing or foreign origins are closed before `getUserMedia` audio is forwarded.
- [ ] Apply issue 13's credit budget to every stream (open plus elapsed time if that is how 13 counts). An exhausted budget does not start a Gnani socket.
- [ ] Server shutdown (issue 29) closes browser and upstream sockets and cancels the pump. Tests or a documented shutdown hook prove no leaked tasks.
- [ ] Ping/pong or an application heartbeat so a half-open TCP session cannot sit until the 15-minute cap.
- [ ] Secure-context warning and mic-blocked copy may live in issue 30; this issue at least must not crash when `getUserMedia` is missing and must not put the Gnani key in any browser frame.
