# 24 — End-to-end smoke test

- **Labels:** `day:3`, `test`, `api`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026), after the desk is authenticated (issue 20) and a public URL exists (issue 13). Issue 16 runs this script against the deployed URL and pastes the last lines into `docs/SUBMISSION.md`.
- **Depends on:** issues 13 and 20. The noisy simulate route (issue 09) and the store (issues 04 and 19) must already be on the server you point at; if a step's route is missing, fail clearly, don't skip it as success.

## Description

Add an opt-in script, `scripts/smoke.py`, that walks the live product the way a judge will: Timbre speaks a sample line, the server dirties it (or you call the noisy sample path), Prisma transcribes, the extractor builds an event, and that event appears on the desk when you present the dispatch passcode.

It talks to a base URL you pass in, default `http://127.0.0.1:8000`. It uses real Gnani calls on that server. There is no mock mode and no local stand-in for Prisma or Timbre.

Flow (keep it to a small credit budget, at most four Gnani calls, preferably two):

1. `GET /api/health` and, if present, `GET /api/ready`. Fail if health is down. Ready may warn (key not set, credits exhausted) and should fail when the body says the demo cannot run.
2. If the remote health payload has `gnani_key_set: false`, print a clear skip line and exit 0 so a laptop without a live demo does not go red. Do not call speech routes in that case.
3. `POST /api/ingest/sample?condition=noisy` if that query exists, otherwise `POST /api/ingest/sample` followed by one noisy `POST /api/simulate` only if you can do it without a second Timbre call. Prefer the single noisy sample route so the budget stays at two Gnani calls (Timbre + Prisma).
4. Assert the JSON has a real `stt.request_id`, a non-empty transcript, and an `event.intent` (the standard sample line should still be `customer_unreachable`, order `18` — if it is not, fail and print what you got, don't rewrite the assertion to pass).
5. Unlock the desk (`POST /api/dispatch/unlock` with `DISPATCH_PASSCODE` from the environment, or send `X-Dispatch-Passcode`) and `GET /api/events`. Assert the ingest `id` is in the list. A missing passcode in the local env is a hard fail once you have reached this step (the deployed desk must not be open), unless health already caused a skip.

Exit 0 on success or on a clean skip. Exit non-zero on any failed assertion, HTTP error other than the skip path, or a response that looks canned (no `request_id`). Print, as plain text:

- skip or pass or fail
- base URL (not the passcode, not any API key)
- our `X-Request-ID` values if the server sent them
- each Gnani `request_id`
- the event id and intent
- the number of speech calls you triggered (so issue 16 can add it to the credit tally)

Do not print transcripts longer than a short preview (one line, truncated). Do not print cookies or secrets.

The script is stdlib plus `httpx` if httpx is already a dependency of the repo you install; prefer stdlib `urllib` if you want zero extra imports. It is not part of the default `pytest` run and not part of GitHub Actions, because those have no key and no live credits. A short comment at the top of the file says that.

Issue 16 adds a checklist row: run `python scripts/smoke.py --base-url <public URL>` with the deploy secrets in the environment, and paste the printed request ids and call count into `docs/SUBMISSION.md`. Coordinate with that issue; you can add the row in this PR if 16's file is already there, otherwise describe the command in the PR and leave the tick box to 16.

## Files to touch

- `scripts/smoke.py` (new)
- `docs/SUBMISSION.md` or this issue's notes, only to record the command
- `README.md` only if you add a one-line "Live smoke" command under Setup or Checks

## Do not touch

`gnani_client/`, frozen schema, frontend, benchmark scores. Do not put the script behind an app mock flag.

## Input / output contract

```bash
python scripts/smoke.py --base-url http://127.0.0.1:8000
```

Needs `DISPATCH_PASSCODE` in the environment when the desk is protected (it should be). Remote `gnani_key_set: false` → exit 0, stdout contains `skipped`. Failure → exit 1 (or another non-zero) and a reason on stderr or stdout. Success → exit 0 and a `passed` line with call count and ids.

## Acceptance criteria

- [ ] Script exists, is documented, and is opt-in (not in the default CI pytest).
- [ ] Against a local or deployed server with key and passcode set, the noisy sample path produces an event that then appears on `GET /api/events`.
- [ ] Exit non-zero on a wrong intent, missing request id, or failed desk fetch.
- [ ] Exit 0 with a skip message when the remote key is not set. No speech calls in that path.
- [ ] At most four Gnani calls, documented in the script comment; prefer two.
- [ ] Stdout includes call count and request ids, and never includes `GNANI_API_KEY` or `DISPATCH_PASSCODE`.
- [ ] Issue 16's write-up (or the PR) states that the checklist will run this against the public URL.

## How to test

```bash
python scripts/smoke.py --base-url http://127.0.0.1:8000   # API up, key and passcode set
# point at a server with gnani_key_set false and confirm a skip:
python scripts/smoke.py --base-url http://127.0.0.1:8000; echo exit:$?
```

Run it once against the issue 13 public URL before calling this done, if the URL is already live. Paste the printed ids in the PR, never the secrets.
