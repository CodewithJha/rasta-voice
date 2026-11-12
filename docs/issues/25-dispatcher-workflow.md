# 25 — Dispatcher workflow, SOS escalation, and audit trail

- **Labels:** `area:app`, `day:3`, `api`, `ui`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 3 (14–15 Nov 2026). Land after 10, 19, and 20 so the slate, the store, and the passcode exist. This is P0 product work: without it the desk is a read-only log.
- **Depends on:** issues 10, 19, and 20. Uses the envelope extension rule from issue 02 (do not add fields to frozen `RiderEvent`). Closes PROD-01, PROD-02, PROD-03, PROD-04, PROD-05, PROD-06, PROD-07, PROD-08, DATA-05, API-06, OBS-02, OBS-05, ARCH-05, ARCH-06, PRIV-05.

## Description

A production desk has to take action. Add a lifecycle, an acknowledgement path, a resolve path, an SOS escalation path, a synthetic rider token, a dispatcher actor token, an audit log, and a small usage panel. Keep the frozen `event` object untouched. Put new fields on the store envelope next to `id`, `created_at`, `transcript`, `stt`, `event`, and `extractor_source`.

Envelope additions (all optional for old rows, required on new ones):

- `state`: `new` | `acked` | `resolved` | `escalated`
- `rider_id`: a short synthetic token (`r_`); never a phone number or a personal name
- `ack_by`, `ack_at`, `resolved_by`, `resolved_at`, `escalated_at`: synthetic dispatcher token and UTC ISO timestamps, or null
- `version`: integer, starts at 1, increments on every state change (for `If-Match`)

Lifecycle:

- Ingest, simulate, and stream create `state=new`, `version=1`, and a `rider_id` from an optional `X-Rider-Id` header if it matches `^r_[A-Za-z0-9_-]{1,32}$`, otherwise a new token.
- `POST /api/events/{id}/ack` and `POST /api/events/{id}/resolve` require the desk passcode (issue 20). Body may include `{"actor": "d_anju"}` (same shape, prefix `d_`). If missing, use a server-made token and set it on the desk cookie so the same browser stays one actor. Require header `If-Match: "<version>"`. Success increments `version` and returns the stamped record. Mismatch is 409. `ack` is allowed from `new` or `escalated`. `resolve` is allowed from `acked` (and from `escalated` only after an ack in the same request or a previous ack). Illegal transitions are 409 with a clear code.
- `POST /api/events/{id}/escalate` is allowed from `new` or `acked`. The server also auto-escalates an `accident_sos` event that stays `new` for `SOS_ACK_SECONDS` (default 60). A small sweeper in the lifespan loop (or on list/ready) performs that update and writes the audit row.
- Audit table (SQLite, issue 19's database): `at`, `event_id`, `actor`, `action` (`ingest|ack|resolve|escalate|delete|unlock|view`), `request_id`, `detail` (short JSON, no transcript, no secrets). `GET /api/events/{id}/audit` is passcode-protected and returns that list oldest-first.
- Admin usage, passcode-protected: `GET /api/admin/usage` returns store count by state, Gnani call count and remaining demo credits from issue 13's counter, 4xx/5xx counts since boot, circuit state from issue 29 if present, and `sos_unacked`. This is the in-process dashboard (OBS-02, PROD-07). Do not add a paid analytics snippet.

Frontend, `dispatch.ts` / `dispatch.css` only (the rider column stays in `rider.ts`):

- Each row shows state, rider token, and, when allowed, **Ack** and **Resolve** buttons (44 px targets, named). Send `If-Match`. On 409, refresh that row and say "desk changed, try again".
- `accident_sos` in `new` or `escalated`: a persistent SOS banner, the `SOS` prefix already required by issue 10, and a short notification tone played once per event (honour `prefers-reduced-motion` / a mute control). `aria-live="assertive"` for SOS, `polite` for other new rows.
- A compact usage strip (credits remaining, unacked SOS) fed by `/api/admin/usage` on a slower poll (15 s). Do not paint fake numbers if the call fails.

Issue 08's accident spoken line must keep saying that a human has been asked, not that help is coming, until `state` is `acked` or later. If 08 has merged, add a small hook: `reply_text` may take the envelope state, or the reply route re-renders the template from the current state. Coordinate in the PR, do not edit `rider.ts` here if issue 30 or 09 is open.

## Files to touch

- `backend/rasta/store.py` (envelope fields, version, transitions)
- `backend/rasta/routes_events.py` (ack, resolve, escalate, audit, usage)
- `backend/rasta/audit.py` (new) and a migrations step in the issue 19 migrator
- `backend/rasta/reply.py` only if the accident line must read state
- `backend/tests/test_workflow.py` (new)
- `frontend/src/dispatch.ts`, `frontend/src/dispatch.css`
- `.env.example` (`SOS_ACK_SECONDS=`)

## Do not touch

`shared/rider_event.schema.json`, `backend/rasta/schema.py`, `frontend/src/types.ts` `RiderEvent` fields, `frontend/src/rider.ts`, `frontend/src/main.ts`, `benchmark/`, `gnani_client/`. Extend the ingest TypeScript envelope in `types.ts` only if you are not breaking the frozen event type (same commit as any envelope type change).

## Input / output contract

`POST /api/events/{id}/ack` with `If-Match: "1"` and a valid desk cookie:

```json
{"id": "...", "version": 2, "state": "acked", "ack_by": "d_anju", "ack_at": "2026-11-14T10:00:00+00:00", "event": {"intent": "accident_sos"}}
```

409 body uses the issue 26 error envelope, code `version_conflict` or `illegal_transition`.

`GET /api/admin/usage`:

```json
{"events": {"new": 2, "acked": 1, "resolved": 4, "escalated": 1}, "demo_credits_remaining": 40, "gnani_calls": 12, "sos_unacked": 1}
```

## Acceptance criteria

- [ ] New ingest rows are `state=new`, `version=1`, with a synthetic `rider_id`. The `event` object still validates against the frozen schema.
- [ ] Ack, resolve, and escalate follow the transitions above. Illegal transitions and stale `If-Match` return 409. Tests cover both.
- [ ] An `accident_sos` left `new` for `SOS_ACK_SECONDS` becomes `escalated` and an audit row is written. A test uses a 0-second (or patched) threshold.
- [ ] `GET /api/events/{id}/audit` lists ingest and the state changes, and never contains a transcript, a passcode, or an API key.
- [ ] Desk routes remain passcode-protected. Rider ingest stays public.
- [ ] The slate shows Ack/Resolve, a live SOS banner and a one-shot tone (with a mute), and a usage strip with real numbers. 409 is visible. `npm run check` passes.
- [ ] The accident Timbre line still does not claim dispatch is on the way until an ack exists.
- [ ] `pytest` and `ruff check backend` pass. No network.

## How to test

```bash
pytest backend/tests/test_workflow.py -q
```

With API, frontend, passcode, and a key: speak the sample line, ack it on the slate from one tab, try to ack it from another tab with the stale version, then run a synthetic accident line and wait for auto-escalate with `SOS_ACK_SECONDS=2`.
