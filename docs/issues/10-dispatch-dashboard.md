# 10 — Live dispatcher dashboard

- **Labels:** `area:app`, `day:2`, `ui`
- **Owner:** Member B: app & realtime
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

