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
