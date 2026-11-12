# 09 — Rider page clean/noisy toggle

- **Labels:** `area:app`, `day:2`, `ui`
- **Owner:** Member B: app & realtime
- **Target day:** Day 2 (13–14 Nov 2026)
- **Depends on:** issues 07 and 08. You own `rider.ts`; don't open this until those two have merged, or you will fight yourself.

## Description

The demo has to show the same utterance twice: once clean, once wrecked by the road. The scored wreckage lives in Member A's benchmark. This toggle is the on-screen version, and it is allowed to be a smaller mix. Label it that way in the UI so nobody quotes it as the award table: a line of small type, "Demo dirt. The scored mixes are in the benchmark."

Backend, new file `backend/rasta/simulate.py`, route in `backend/rasta/routes_sim.py`:

`POST /api/simulate` with the same multipart field `audio_file` plus a query `condition=clean|noisy`.

- `clean` returns the wav unchanged, as `audio/wav`, plus an `X-Rasta-Condition: clean` header. Also run the normal ingest and return... two responses can't share a body. Return JSON instead:

```json
{
  "condition": "noisy",
  "audio_base64": "<the wav that was actually transcribed>",
  "ingest": {"id": "...", "transcript": "...", "stt": {}, "event": {}}
}
```

- `noisy` mixes a short horn burst and rumble onto the PCM (a few lines, stdlib, seed 4), downsamples to 8000 Hz by averaging pairs, then sends **that** wav to `ingest`. The transcript the desk sees is the transcript of the dirty audio. In mock mode the transcript is still the canned line, because mock STT ignores bytes. That is honest: show the dirty wav's play button anyway, and let the slate say `stt.mock`. When the key is live, the noisy condition is a real Prisma call on the dirty audio. Don't hide that.

Frontend, `frontend/src/rider.ts` and `frontend/src/rider.css`:

- A two-position control, "Clean line" / "Noisy line", default Clean. Not a checkbox buried in a menu. Big enough to see on a phone.
- The existing upload and the canned-tone stream both honour it.
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

`ingest` is the stamped store record from issue 04. The audio in `audio_base64` is the audio Prisma (or the mock) was given.

Noisy audio is 8000 Hz mono 16-bit WAV. Clean audio keeps the upload's container only if you can hand Prisma the original bytes; otherwise re-wrap as wav and say so. Prefer re-wrap so the player always gets wav.

## Acceptance criteria

- [ ] `condition=noisy` on a generated tone returns 8000 Hz wav. Test with `wave` on the decoded bytes.
- [ ] `condition=clean` does not change the sample count of a wav you generated in the test.
- [ ] Mock ingest inside the payload still has `event.intent == customer_unreachable` for the canned path. For an uploaded tone in mock mode, same, because mock STT is fixed. Assert `stt.mock` is true.
- [ ] Bad `condition` is 400.
- [ ] In the browser: toggle Noisy, run **Canned night drop** (or the upload), hear a clip, click **Hear dispatch**, hear the mock tone, see the slate update. Then toggle Clean and run it again. Both succeed.
- [ ] Phone width (a narrow window) still shows the toggle, the buttons, and the slate without overlapping the sticker into the buttons. Look at it.
- [ ] `npm run check` and `pytest backend/tests/test_simulate.py` pass.

## How to test

```bash
pytest backend/tests/test_simulate.py -q
cd frontend && npm run check
```

Browser, against `npm run dev` with the API up: the two toggles, both buttons, both audio players, then a 400px-wide window.
