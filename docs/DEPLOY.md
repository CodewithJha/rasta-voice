# Deploy secrets

This note covers process secrets the desk and speech paths need. Host
choice, rate limits, and a public URL are issue 13.

## Required environment

Set these in the process environment or an ignored `.env` file. Do not
commit values, print them, or add them to health or ready payloads.

- `GNANI_API_KEY` — Prisma and Timbre. If it is missing, speech routes
  return 503.
- `DISPATCH_PASSCODE` — shared desk passcode. If it is missing or empty,
  `GET /api/events`, `POST /api/dispatch/unlock`, and later desk write
  or ack routes return 503 with `DISPATCH_PASSCODE is not set`. The rider
  routes stay public.

Optional lockout knobs, with defaults of 5 failures in 600 seconds:

- `DISPATCH_UNLOCK_MAX_FAILURES`
- `DISPATCH_UNLOCK_WINDOW_SECONDS`

A local or Vite dev origin already on `CORS_ALLOW_ORIGINS` can send
cookies after unlock. Do not widen that list to `*`.

## Passcode rotation

1. Choose a new `DISPATCH_PASSCODE`.
2. Update the secret in the process environment.
3. Restart the app workers so they load the new value.
4. Existing desk cookies were signed with the previous secret, so they
   fail closed. Dispatchers must unlock again from the slate.

After five wrong unlock attempts from one address inside the window, the
unlock route returns 429 until the window expires.

## Health and readiness

`GET /api/health` is the cheap liveness probe: the process is up. It
returns `ok`, `gnani_key_set`, and `llm_provider` only. It does not
touch disk, the event store, a credit budget, or Gnani. Keep the host
container health check on this path until the issue 13 image can be
pointed at the readiness probe below.

`GET /api/ready` is readiness, for operators and the issue 24 smoke.
It reports `gnani_key_set`, `db_writable`, `rate_limit`,
`demo_credits_remaining`, `demo_credits_exhausted`, `schema_version`,
`circuit_breaker`, and `events_in_store`. Fields that issue 13, 19, or
29 have not shipped yet are the string `not_deployed`; this process
does not invent a second budget or a shadow database. `events_in_store`
is the current in-memory desk length.

HTTP 200 means the process should stay in rotation. A missing Gnani
key or a spent (or not-yet-deployed) credit budget stays 200: speech
routes already return 503, and the payload shows
`demo_credits_remaining: 0` and `demo_credits_exhausted: true` when
issue 13's budget is present and exhausted. HTTP 503 with
`ok: false` and `db_writable: false` is reserved for a configured
durable store that cannot be written, so the host can take the
process out of rotation. Neither payload includes
`DISPATCH_PASSCODE`, `GNANI_API_KEY`, or any other raw secret.
