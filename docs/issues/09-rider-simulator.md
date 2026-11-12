# 09 — Rider page clean/noisy toggle

- **Labels:** `area:app`, `day:2`, `ui`
- **Owner:** Member B: app & realtime
- **Target day:** Day 2 (13–14 Nov 2026)
- **Depends on:** issues 07 and 08. You own `rider.ts`; don't open this until those two have merged, or you will fight yourself.

## Description

The demo has to show the same utterance twice: once clean, once wrecked by the road. The scored wreckage lives in Member A's benchmark. This toggle is the on-screen version, and it is allowed to be a smaller mix. Label it that way in the UI so nobody quotes it as the award table: a line of small type, "Demo dirt. The scored mixes are in the benchmark."

Backend, new file `backend/rasta/simulate.py`, route in `backend/rasta/routes_sim.py`:

`POST /api/simulate` with the same multipart field `audio_file` plus a query `condition=clean|noisy`.

- Both `clean` and `noisy` return JSON with `condition`, `audio_base64` and the actual `ingest` result. `clean` preserves the audio samples, and the audio field is a valid WAV representation of the exact bytes sent to Prisma:

```json
{
  "condition": "noisy",
  "audio_base64": "<the wav that was actually transcribed>",
  "ingest": {"id": "...", "transcript": "...", "stt": {}, "event": {}}
}
```

- `noisy` mixes a short horn burst and rumble onto the PCM (a few lines, stdlib, seed 4), downsamples to 8000 Hz by averaging pairs, then sends **that** wav to `ingest`. The transcript the desk sees is a real Prisma transcript of the dirty audio. Show the dirty wav's play button so a viewer can hear what Prisma heard.

Frontend, `frontend/src/rider.ts` and `frontend/src/rider.css`:

- A two-position control, "Clean line" / "Noisy line", default Clean. Not a checkbox buried in a menu. Big enough to see on a phone.
- The existing upload and the **Speak a sample line** button both honour it (the sample route gets a `condition` query too: Timbre speaks, the server dirties it, Prisma transcribes the dirty audio).
- After a result, an `<audio controls>` plays `audio_base64` when the simulate route was used.
- A second `<audio controls>` plays the reply from `POST /api/reply/{id}` (issue 08). Button label: "Hear dispatch".
- Keep the chit look: paper, red spine, hard shadow. Don't introduce a card grid, a purple gradient, or a new font.

The stream path: if noisy, the browser can only dirty what it sends. Document in a code comment that live-mic noise is "play a horn buffer under the mic" summed in the worklet, not a second server mix. If that slips, the upload path's noisy toggle is the one the demo script uses, and the mic path stays clean. Don't block the issue on a perfect worklet mix.

## Files to touch

- `backend/rasta/simulate.py` (new)
- `backend/rasta/routes_sim.py` (new)
- `backend/rasta/main.py` (one include line)
- `backend/tests/test_simulate.py` (new)
- `frontend/src/rider.ts`
- `frontend/src/rider.css` (new, imported from `rider.ts`)

## Do not touch

`frontend/src/dispatch.ts`, `frontend/src/styles.css`, `frontend/src/main.ts`, `benchmark/`, `gnani_client/`.

## Input / output contract

See the JSON above. `condition` is exactly `clean` or `noisy`. Anything else is 400.

`ingest` is the stamped store record from issue 04. The audio in `audio_base64` is the exact audio Prisma was given.

Noisy audio is 8000 Hz mono 16-bit WAV. Clean audio keeps the upload's container only if you can hand Prisma the original bytes; otherwise re-wrap as wav and say so. Prefer re-wrap so the player always gets wav.

## Acceptance criteria

- [ ] `condition=noisy` on a wav generated in the test returns 8000 Hz wav. Test with `wave` on the decoded bytes. Prisma's HTTP transport is swapped inside the test (same pattern as `backend/tests/test_ingest.py`).
- [ ] `condition=clean` does not change the sample count of a wav you generated in the test.
- [ ] The test asserts the bytes posted to `/stt/v3` are the noisy wav (8000 Hz), not the clean upload.
- [ ] Live check with a real key: the sample line, noisy, still comes back as `customer_unreachable` / order 18 (verified on 12 Nov with 5 dB white noise at 8 kHz). Paste both transcripts in the PR.
- [ ] Bad `condition` is 400.
- [ ] In the browser, with a real key: toggle Noisy, run **Speak a sample line** (or the upload), hear the dirty clip, click **Hear dispatch**, hear Timbre's reply, see the slate update. Then toggle Clean and run it again. Both succeed.
- [ ] Phone width (a narrow window) still shows the toggle, the buttons, and the slate without overlapping the sticker into the buttons. Look at it.
- [ ] `npm run check` and `pytest backend/tests/test_simulate.py` pass.

## How to test

```bash
pytest backend/tests/test_simulate.py -q
cd frontend && npm run check
```

Browser, against `npm run dev` with the API up: the two toggles, both buttons, both audio players, then a 400px-wide window.

<!-- rasta-voice-audit-2026-11-12 -->

### Clean/noisy consistency acceptance

- [ ] For **both** conditions, the API returns one JSON envelope with the exact audio that Prisma received, an `ingest` event, and an accurate condition label. Do not mix a WAV-response contract and a JSON-response contract.
- [ ] Repeat the same utterance across conditions and verify the audible clip, transcript and event correspond to each condition, rather than silently reusing a clean transcript.


<!-- rasta-voice-hardening-2026-11-12 -->

### Mobile layout, states, and original design

The rider chit has to work in a rider's hand, outdoors, and it has to look like this product, not like a dashboard template.

Design brief (follow this, don't copy a known product):

- High-contrast, outdoor-readable rider screen: ink on paper under hard noon light. The existing chit (paper, red spine, hard shadow) stays the spine of the page. Do not restyle it into a card grid, a soft pastel app, a purple gradient, or a glass panel.
- Touch targets at least 44 px on the toggle, **Speak a sample line**, upload, and **Hear dispatch**. Hinglish microcopy is allowed on button labels and helper lines ("Clean line" / "Noisy line", "Bolo", "Sun lo") as long as a first-time judge still understands the control in English.
- At 360 px wide, the toggle, buttons, players, and chit stack in one column with no overlap, no horizontal scroll, and no text smaller than 14 px for body copy. Helper text can be 12 px if contrast still holds.
- Contrast: text and essential controls meet a 4.5:1 ratio against their background (the red spine and the paper). Focus rings are visible. Every control is reachable by keyboard (tab, enter/space on the toggle and buttons) and has an accessible name.

States, all in `rider.ts` / `rider.css`:

- Empty: the chit waits with a short line, not a blank card. No fake event.
- Loading: a visible busy state on the button that was pressed; it is disabled until the response arrives. Do not block the whole page with a modal.
- Error: show the server's meaning, not a raw stack.
  - 503 (missing `GNANI_API_KEY`) → a clear "key is not set on the server" line.
  - 502 (Gnani failed) → upstream failure, include `upstream_status` if the API sent it.
  - 429 (rate limit or credit budget from issue 13) → "demo is busy, try in a minute", not a silent no-op.
- Don't invent a 200 with a canned transcript to paper over any of these.

- [ ] At 360 px wide, the rider column is usable: toggle, primary actions, and players visible without overlap or sideways scroll.
- [ ] Empty, loading, 503, 502, and 429 states are implemented and distinguishable.
- [ ] Keyboard: tab order is sensible, focus is visible, controls have names. `npm run check` still passes.
- [ ] The look follows the brief above. No template kit, no copied shell, no new webfont.
