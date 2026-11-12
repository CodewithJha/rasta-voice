# 10 — Live dispatcher dashboard

- **Labels:** `area:app`, `day:2`, `ui`
- **Owner:** Member B: Prakhar (@CodewithJha), app, realtime & UI
- **Target day:** Day 2 (13–14 Nov 2026)
- **Depends on:** issue 04 (`GET /api/events`). Parallel with 07 and 08. Do not edit `rider.ts` or `rider.css`.

## Description

The slate today only hears the `rasta:event` fired in this browser tab. A dispatcher on another screen needs the store. Poll it.

In `frontend/src/dispatch.ts`:

- On load, `GET /api/events` and paint every event, oldest at the top, newest last (a paper tape, not a reverse-chrono feed that jumps).
- Every 2 seconds, poll `GET /api/events?since=<created_at of the last row>`. Append. Don't redraw the whole list if nothing new arrived.
- Keep the phosphor panel. New rules go in `frontend/src/dispatch.css`, imported from `dispatch.ts`.
- High urgency: the word HIGH in the stamp red `#9b2226` on the phosphor background, so it reads as a lamp, not as a Bootstrap badge.
- Accident intent: prefix the row with the word `SOS`.
- Show intent, order, eta, urgency, and the dispatch action. Truncate the action with CSS, and put the full sentence in a `title` attribute.
- Empty state stays a sentence: "Dark. No drop has come in on this desk."
- The existing `rasta:event` listener can stay as a fast path, but the poll is the source of truth. If both fire, don't duplicate ids. Key rows by `id`.

No chart library. No table component. A `<ol>` of rows is enough.

If `GET /api/events` 404s because issue 04 isn't merged yet, show "Desk list isn't up" and don't throw. Once 04 is in, the sentence goes away. Don't crash the rider chit.

## Files to touch

- `frontend/src/dispatch.ts`
- `frontend/src/dispatch.css` (new)

## Do not touch

`frontend/src/rider.ts`, `frontend/src/styles.css`, `frontend/src/main.ts`, `backend/` (04 already shipped the route), `benchmark/`.

## Input / output contract

Consumes issue 04's list:

```json
{"events": [{"id": "...", "created_at": "...", "event": {"intent": "delay", "urgency": "low", "order_id": "7", "eta_minutes": 20, "dispatch_action": "..."}}]}
```

Renders one row per event. No new endpoint.

## Acceptance criteria

- [ ] With a real key, two clicks of **Speak a sample line** on the rider page produce two rows, stable across a refresh (the store is in the API process, so the refresh repaints from `GET /api/events`).
- [ ] A second browser tab pointed at the same frontend shows the same rows within one poll, without clicking anything in that tab.
- [ ] High urgency renders the urgency word in `#9b2226`. Check the computed colour, or look: the sample line's event is high.
- [ ] Empty store shows the dark-desk sentence, not a blank panel and not an error.
- [ ] `npm run check` passes. Keyboard: you can tab to the rider controls and the slate text is readable. No new click target that lacks a name.

## How to test

Start API and `npm run dev`. Open two windows. In one, run **Speak a sample line** twice (needs `GNANI_API_KEY`; four Gnani calls total). Watch the other. Refresh both. Narrow one window until the layout stacks and confirm the slate is still readable.


<!-- rasta-voice-hardening-2026-11-12 -->

### Mobile layout, states, and original design

The slate is a dense ops board for a dispatcher on a small laptop or a phone held in landscape, not a marketing dashboard.

Design brief (follow this, don't copy a known product):

- Keep the phosphor panel and the lamp-red HIGH stamp (`#9b2226`). Rows stay a paper tape (`<ol>`), oldest at the top. Do not replace it with a KPI row, a chart, a card masonry, or a pastel table.
- Dense but readable: intent, order, ETA, urgency, and action on one row at desktop; wrap to two lines at 360 px rather than truncating the intent or the SOS prefix. Touch or click targets on any later ack control are at least 44 px.
- Contrast on the phosphor background meets 4.5:1 for body text and the SOS/HIGH labels. Focus is visible. The board itself is a live region or equivalent so new rows are announced; the empty sentence stays keyboard-reachable text, not a mystery blank.

States, all in `dispatch.ts` / `dispatch.css`:

- Empty: keep "Dark. No drop has come in on this desk."
- Loading: a quiet first-load indicator until the first `GET /api/events` returns; subsequent polls fail softly without flashing the whole board empty.
- Error:
  - 401 (after issue 20's passcode) → a short unlock prompt, not a stack trace and not a redirect that takes down the rider chit.
  - 503 (a down or misconfigured desk, or a missing `DISPATCH_PASSCODE` once issue 20 lands) → "Desk isn't ready".
  - 502 → "Upstream failed", don't invent rows.
  - 429 → "Desk is rate-limited, polling will retry", and back off the poll rather than hammering.
  - 404 remains "Desk list isn't up" until issue 04 is merged.
- Never paint placeholder events to fill the empty state.

At 360 px wide the rider chit and the slate stack; the slate remains readable, SOS/HIGH stay visible, and there is no horizontal scroll.

- [ ] At 360 px wide the slate is readable, stacked under the chit, with no overlap or sideways scroll.
- [ ] Empty, first-load, 401, 503, 502, and 429 states are implemented and distinguishable. Polling backs off on 429.
- [ ] Keyboard and contrast checks above pass. `npm run check` still passes.
- [ ] The look follows the brief. No template kit, no copied ops-console shell, no chart library.

<!-- rasta-voice-production-2026-11-12 -->

### Production: hooks for workflow and alerts

Issue 25 owns ack/resolve, the SOS tone, and the usage strip. This issue should not paint itself into a corner:

- [ ] Render a `state` field if the envelope has one, and leave room in the row for later Ack/Resolve buttons without a layout rewrite. If 25 has not merged, ignore unknown envelope keys rather than crashing.
- [ ] `aria-live` on the board (hardening section) must be compatible with an assertive SOS update in 25.
- [ ] Polling backs off on 401 (show the unlock prompt from issue 20) and on 429, and never tight-loops.
- [ ] Do not display unredacted long digit runs if issue 28 has already replaced them; do not invent your own redaction here.
