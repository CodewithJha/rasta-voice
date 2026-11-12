# 08 — Timbre Hinglish confirmation

- **Labels:** `area:app`, `day:2`, `tts`
- **Note:** this touches `backend/rasta/` (Member B's tree). Keep the change to the reply route and its template module, and tell Member B in the PR body. Land it early on Day 2, because #09 depends on it.
- **Owner:** Member A: benchmark & audio (moved from Member B on 12 Nov to balance load)
- **Target day:** Day 2 (13–14 Nov 2026)
- **Depends on:** issue 04 (the stored event is what you reply to). Can be written beside issue 07. Do not edit `rider.ts` here if 07 is open; this issue's frontend change is a play button that can land after 07, or in issue 09. Prefer: this PR is backend-only, and issue 09 adds the play button. That keeps `rider.ts` in one person's hands one PR at a time.

## Description

After the desk understands the rider, Timbre says one short Hinglish line back. The rider hears that dispatch got it. The line is a template, not another LLM call. Templates are easier to keep free of phone numbers and they stay under a couple of seconds.

`backend/rasta/reply.py`:

```python
def reply_text(event: RiderEvent) -> str: ...
```

One sentence, Hinglish, at most one tag from `AUDIO_TAGS`, placed where the docs say a tag applies (before the words it should colour, not dangling at the end).

| Intent | Shape of the line |
| --- | --- |
| `customer_unreachable` | Tell them dispatch will call the customer once, and to wait by the gate. `<pauses>` between the two clauses. |
| `address_issue` | Ask them to stay near a landmark. No tag, or `<slow>`. |
| `item_missing` | Tell them to hold the drop, the hub will check the bag. |
| `delay` | Repeat the ETA if `eta_minutes` is set ("bees minute"), else say traffic is noted. |
| `accident_sos` | Ask if they are okay, tell them a person is coming, tell them to pull the bike aside. Use a calm, clearly audible, untagged emergency response. Do not use `<whispers>` or promise a human is coming unless dispatch has actually acknowledged the emergency. Ask about safety and suggest stopping in a safe place. |
| `other` | A short "suna, aage badho" with no tag. |

No order id read out as a phone number. Speaking "order atharah" is fine.

Route, new file `backend/rasta/routes_reply.py`:

`POST /api/reply/{event_id}` loads the event from the store, synthesises with `TimbreTTS`, and returns JSON:

```json
{
  "text": "Theek hai. <pauses> Aap gate ke paas ruko.",
  "audio_base64": "<wav bytes, standard base64>",
  "content_type": "audio/wav",
  "audio_seconds": 1.8
}
```

Always a real Timbre call with the client's defaults (`timbre-v3.0`, `Shivani`, `hi-en`). Missing key → 503 with the client's message; a Timbre error → 502 with `upstream_status` (reuse the `_guard` mapping in `main.py`). `audio_seconds` comes from `gnani_client.wav.wav_duration_seconds` (Timbre's WAV header sizes are placeholders). One include line in `main.py`.

Unknown id → 404. Do not accept a raw transcript from the browser for this route. The text comes from the stored event, so the browser cannot make Timbre say an arbitrary string.

## Files to touch

- `backend/rasta/reply.py` (new)
- `backend/rasta/routes_reply.py` (new)
- `backend/rasta/main.py` (one include line)
- `backend/tests/test_reply.py` (new)

## Do not touch

`frontend/` (issue 09 plays the audio), `gnani_client/tts.py`, `benchmark/`, the schema.

## Input / output contract

Input: event id already stored by issue 04.

Output: JSON above. `audio_base64` decodes to bytes starting with `RIFF`. `text` is the exact string sent to Timbre.

`reply_text` is pure and tested without audio.

## Acceptance criteria

- [ ] Each intent has a test that the line is non-empty, contains no 8-digit run, and contains at most one `<` tag.
- [ ] Accident line is calm and audible, uses no `<whispers>` tag, and never claims that a human was dispatched without a real acknowledgement.
- [ ] `POST /api/reply/{id}` after a sample ingest returns a wav. In the test, swap Timbre's HTTP transport (`monkeypatch.setattr(TimbreTTS, "_http", ...)` with `httpx.MockTransport`, same pattern as `backend/tests/test_ingest.py`) and assert the request body's `text` equals `reply_text(event)`.
- [ ] With `GNANI_API_KEY` unset the route answers 503 with the missing-key message.
- [ ] Unknown id returns 404.
- [ ] A made-up body cannot override the spoken text (the route has no `text` field).
- [ ] `pytest backend/tests/test_reply.py` passes with no key (transport swapped in the test only, nothing fake in app code).
- [ ] One live call with a real key: paste the spoken text and `audio_seconds` in the PR.

## How to test

```bash
pytest backend/tests/test_reply.py -q
```

Manual, after 09 wires the button: play the reply in the browser and confirm the `<pre>` shows the Hinglish line, not only a silent success.

<!-- rasta-voice-audit-2026-11-12 -->

### Safety and truthfulness acceptance

- [ ] An `accident_sos` template asks for immediate human review, never says assistance has been dispatched unless a verified human acknowledgement exists, and avoids any advice that could put a rider into moving traffic.
- [ ] An `other` or uncertain intent does not falsely tell the rider it is safe to continue. A human-review instruction is preferable to unverified assurance.
- [ ] Test emergency and uncertain replies for natural Hindi/Hinglish pronunciation, audibility and absence of fabricated dispatch promises.


<!-- rasta-voice-production-2026-11-12 -->

### Production: reply spending and state

- [ ] Timeouts and retries follow issue 29 (no unbounded Timbre retries; 402 is not retried).
- [ ] A second `POST /api/reply/{id}` for the same event, within 10 minutes, may reuse cached audio (bytes in SQLite or a process cache) or honour an `Idempotency-Key` from issue 26, so "Hear dispatch" twice does not spend two TTS credits. A test with a swapped transport asserts a single upstream call.
- [ ] The accident template still does not claim help is on the way unless issue 25's envelope `state` is `acked` or later. If 25 has not merged, keep the cautious wording for every accident reply.
- [ ] The route is a rider-facing, rate-limited path (issue 13), not a desk-only path. Do not require the dispatch passcode, and do not accept a client-supplied `text`.
