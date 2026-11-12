# 08 — Timbre Hinglish confirmation

- **Labels:** `area:app`, `day:2`, `tts`
- **Owner:** Member B: app & realtime
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
| `accident_sos` | Ask if they are okay, tell them a person is coming, tell them to pull the bike aside. Start with `<whispers>`. Do not be cute. |
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
- [ ] Accident line starts with `<whispers>`.
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
