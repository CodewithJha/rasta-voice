# 07 — Prisma realtime WebSocket

- **Labels:** `area:app`, `day:2`, `stt`
- **Owner:** Member B: app & realtime
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

Mock mode: do not open a socket. After commit, emit one transcript and that transcript is `MOCK_TRANSCRIPT` from `gnani_client.stt`. Then run `extract_event` and `store.append`, and send the stamped record to the browser as one JSON text frame.

Add the `websockets` package to `gnani_client/pyproject.toml` in this PR. Pin a current 13.x or whatever `additional_headers` matches (the docs note that `websockets` < 13 wants `extra_headers`).

Browser side, in `frontend/src/rider.ts` only:

- A button, "Talk". `getUserMedia({audio: true})`, `AudioContext`, resample to 16-bit PCM with a `ScriptProcessor` or `AudioWorklet`. If the mic permission fails, the button shows the error in the existing `<pre>` and does not crash the page.
- A second button, "Stream the canned tone", sends the same socket a few silent-or-tone PCM frames and a commit, so the demo works on a machine with no mic. Mock mode answers with the fixed Hinglish line.
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
{"type": "transcript", "text": "bhaiya gate band hai, customer phone nahi utha raha, order 18", "mock": true}
```

Then, when extraction finishes:

```json
{"type": "event", "id": "...", "created_at": "...", "transcript": "...", "stt": {}, "event": {}}
```

`stt_stream.transcribe_pcm(pcm: bytes, sample_rate: int) -> SttResult` is the function the route calls. In mock mode it returns `MOCK_TRANSCRIPT` and does not connect. A unit test feeds it bytes and asserts no socket attempt (pass a client factory that would raise if called).

## Acceptance criteria

- [ ] Mock `transcribe_pcm` returns the canned transcript and never builds a WebSocket.
- [ ] A test of `stream_headers` / the new module asserts the live URL path is `/stt/v3/stream` and the telephony preset sets `x-sample-rate` to `8000`.
- [ ] With the API in mock mode, the "canned tone" button on the rider page ends with the slate showing customer unreachable / order 18. Click it. Don't only look at the DOM.
- [ ] Mic denial shows a message and leaves the upload form working.
- [ ] The Gnani key is read on the server only. Confirm the frontend bundle has no `GNANI` string (`rg GNANI frontend/src` is empty).
- [ ] `pytest`, `ruff`, and `npm run check` pass.

## How to test

```bash
pytest gnani_client/tests/test_stream.py backend/tests -q
cd frontend && npm run check
```

Then, with `uvicorn` and `npm run dev`: click **Stream the canned tone**, confirm the slate, then refuse the mic in the browser site settings and click **Talk**.
