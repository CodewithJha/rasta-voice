# Rasta Voice — three-day plan

Contest deadline: **15 Nov 2026, 18:00 IST**. The public post goes out by **14 Nov 2026, 18:00 IST**, even if the benchmark has only a small live run. Do not block the post on a perfect table.

Today in this repo is the skeleton (live Prisma STT and Timbre TTS, rule extractor, upload → JSON, chit + slate). There is no mock mode anywhere in the app. Everything below is a file in `docs/issues/`. Merge them in the order listed. Same-day issues with no dependency can be pull requests at the same time.

## Owners

| | Member A: benchmark & audio | Member B: app & realtime |
| --- | --- | --- |
| Trees | `benchmark/`, `docs` benchmark section, `docs/SUBMISSION.md` | `backend/rasta/` (except the frozen schema), `frontend/`, `Dockerfile` |
| Frozen for both | `gnani_client/` (call it, don't rewrite it), `shared/rider_event.schema.json`, `backend/rasta/schema.py`, `frontend/src/types.ts`, `frontend/src/main.ts`, `frontend/src/styles.css` | same |

If a client bug blocks you, one small fix in `gnani_client/` is allowed in your PR. Say so in the PR body. Do not restyle the other person's screen.

## Days

**Day 1 — 12–13 Nov.** Corpus, LLM extractor, clean Timbre clips, in-memory event list. End of day: `POST /api/ingest` still works, and a gold file of utterances exists.

**Day 2 — 13–14 Nov.** Noise, telephony, realtime socket, spoken reply, rider toggle, dispatch list. End of day: a person can demo the desk on localhost, noisy and clean.

**Day 3 — 14–15 Nov.** Scored run, chart, README section, free host, 60-second script, post, submission pass. Post is live by 14 Nov 18:00 IST. Repo is contest-ready before 15 Nov 18:00 IST.

## Issue order

| # | Issue | Owner | Day | Depends on |
| --- | --- | --- | --- | --- |
| 01 | [Synthetic Hinglish rider corpus](issues/01-utterance-corpus.md) | A | 1 | skeleton |
| 02 | [Free-tier LLM extractor and intent eval](issues/02-llm-extractor.md) | B | 1 | skeleton |
| 03 | [Clean clips from Timbre](issues/03-timbre-clean-clips.md) | A | 1 | 01 |
| 04 | [In-memory dispatch event store](issues/04-event-store.md) | B | 1 | skeleton |
| 05 | [Procedural noise mixer](issues/05-noise-mixer.md) | A | 2 | 03 |
| 06 | [8 kHz telephony and codec artefacts](issues/06-telephony-sim.md) | A | 2 | 05 |
| 07 | [Prisma realtime WebSocket](issues/07-realtime-stt.md) | B | 2 | 04 |
| 08 | [Timbre Hinglish confirmation](issues/08-tts-reply.md) | A | 2 (land early) | 04 |
| 09 | [Rider page clean/noisy toggle](issues/09-rider-simulator.md) | B | 2 | 07, 08 |
| 10 | [Live dispatcher dashboard](issues/10-dispatch-dashboard.md) | B | 2 | 04 |
| 11 | [Benchmark runner](issues/11-benchmark-runner.md) | A | 3 | 06 |
| 12 | [Chart and README benchmark section](issues/12-benchmark-chart-readme.md) | A | 3 | 11 |
| 13 | [Free-host deploy](issues/13-free-host-deploy.md) | B | 3 | 09, 10 |
| 14 | [60-second demo script](issues/14-demo-video-script.md) | B | 3 | 09 |
| 15 | [LinkedIn and X post](issues/15-social-post.md) | A | 3 (publish 14 Nov) | 09, 18 video |
| 16 | [Submission checklist](issues/16-submission-check.md) | A | 3 | 12, 13, 15, 18 |
| 17 | [Consented real-world noisy speech validation](issues/17-field-validation.md) | A | 3 | 06, 11 |
| 18 | [Working demo video and final submission](issues/18-demo-video-and-submission.md) | B | 3 (video by 14 Nov) | 09, 14 |
| 19 | [SQLite event store](issues/19-sqlite-event-store.md) | B | 2 (land early) | 04 |
| 20 | [Dispatcher passcode](issues/20-dispatcher-passcode.md) | B | 2 | 10 |
| 21 | [Structured logging and request IDs](issues/21-structured-logging.md) | B | 2 | skeleton |
| 22 | [Health and readiness](issues/22-health-and-readiness.md) | B | 3 | 13, 19 |
| 23 | [Docs pack](issues/23-docs-pack.md) | A | 3 | 19, 20, 21, 22 |
| 24 | [End-to-end smoke test](issues/24-e2e-smoke-test.md) | A | 3 | 13, 20 |

Load balance (12 Nov): 08 and 15 moved from B to A, so B can give 07 (true live streaming), 13 (credit and abuse limits) and 18 (the video) their full time. A lands 08 early on Day 2 with a narrow change in `backend/rasta/`, flagged in the PR body.

Hardening (12 Nov, later): 19–22 go to B (store, passcode, logs, ready). 23 and 24 go to A (docs pack and the live smoke script). The count is even (12 and 12); A's added work is lighter so B still has time for 07, 13, and 18.

Day 2 note for Member B: finish 07, and wait for A's 08, before opening 09. 10 can land beside 07 because it only touches `frontend/src/dispatch.ts` and a new stylesheet. Do not both edit `frontend/src/rider.ts`. Land 19 early, once 04 is in, and keep the issue 04 JSON so 10 does not wait on sqlite. Land 21 in parallel with 19 if you are not both rewriting `main.py`. Land 20 only after 10's slate is mergeable; 20 is the other Day 2 edit to `dispatch.ts`.

Day 3 note: 15 needs the public working-app video from 18 (a photo is not enough), but does not wait on 12. If the chart is merged, quote one number. If it is not, quote the live sample result from the README (Timbre line → Prisma transcript, word for word) and say the scored run follows before the deadline. Publish by 14 Nov 18:00 IST anyway. 22 waits for 13 and 19. 23 waits for 19–22 and describes only what has actually merged. 24 waits for 13 and 20; 16's checklist runs `scripts/smoke.py` against the public URL.

## Rules that apply to every issue

- Synthetic audio and synthetic order tokens only. No real phone numbers, call recordings, customer names, or government IDs. An 8-digit run is not an `order_id`.
- Free tools only. Gnani credits are the contest grant. LLM is Groq or Gemini free tier. Host is Hugging Face Spaces or Render free. No paid APIs, no paid fonts, no paid dataset.
- Real Gnani calls only. No mock flags, canned transcripts, tone stand-ins, or fixture scores in app, benchmark, or docs. A missing `GNANI_API_KEY` is a loud error, never a silent fallback.
- CI (`ruff`, `pytest`, `npm run check`) stays green with no secrets. Tests fake the HTTP transport inside the test file (`httpx.MockTransport` or monkeypatch), never through a flag in app code. Live tests are opt-in and skip when `GNANI_API_KEY` is absent.
- Watch credits: one REST STT call per clip, one TTS call per line. Cache generated audio under `benchmark/data/audio/` and do not regenerate it on every run.
- `extract_event(transcript) -> RiderEvent` stays that signature. Extra optional args are fine. Removing the rule fallback is not.
