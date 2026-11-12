# Rasta Voice — three-day plan

Contest deadline: **15 Nov 2026, 18:00 IST**. The public post goes out by **14 Nov 2026, 18:00 IST**, even if the benchmark has only a small live run. Do not block the post on a perfect table.

Today in this repo is the skeleton (live Prisma STT and Timbre TTS, rule extractor, upload → JSON, chit + slate). There is no mock mode anywhere in the app. Everything below is a file in `docs/issues/`. Merge them in the order listed. Same-day issues with no dependency can be pull requests at the same time.

## Owners

The team is exactly these two people. There is no third contributor.

| | Member A: Himanshu (@himanshu748), benchmark & audio | Member B: Prakhar (@CodewithJha), app, realtime & UI |
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
| 25 | [Dispatcher workflow, SOS, and audit](issues/25-dispatcher-workflow.md) | B | 3 | 10, 19, 20 |
| 26 | [API contract](issues/26-api-contract.md) | B | 3 | 19, 21 |
| 27 | [Security hardening](issues/27-security-hardening.md) | B | 3 | 13, 20 |
| 28 | [Privacy, retention, and deletion](issues/28-privacy-retention.md) | B | 3 | 19 |
| 29 | [Upstream resilience](issues/29-upstream-resilience.md) | B | 2 (land early) | skeleton |
| 30 | [Frontend production quality](issues/30-frontend-production.md) | B | 3 | 09, 10 |
| 31 | [Load tests and latency budgets](issues/31-load-tests.md) | A | 3 | 13, 22 |
| 32 | [Quality gates](issues/32-quality-gates.md) | A | 3 | 09, 10, 24 |
| 33 | [CI/CD and supply chain](issues/33-cicd-supply-chain.md) | A | 3 | 13, 32 |
| 34 | [Operations and legal docs](issues/34-ops-and-legal-docs.md) | A | 3 | 23 |
| 35 | [Post-contest operations stretch](issues/35-post-contest-ops.md) | A | post-contest | P0 merged, 13 |

Load balance (12 Nov): 08 and 15 moved from Prakhar (B) to Himanshu (A), so Prakhar can give 07 (true live streaming), 13 (credit and abuse limits) and 18 (the video) their full time. Himanshu lands 08 early on Day 2 with a narrow change in `backend/rasta/`, flagged in the PR body.

Hardening (12 Nov, later): 19–22 go to Prakhar (B) (store, passcode, logs, ready). 23 and 24 go to Himanshu (A) (docs pack and the live smoke script).

Production (12 Nov, later still): the 01–24 plan is an MVP, not a production system. Gaps and the definition of done live in [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). New work: 25–30 to Prakhar (B) (workflow, API, security, privacy, resilience, frontend quality — UI stays with Prakhar). 31–34 to Himanshu (A) (k6, quality gates, CI/CD, ops and legal docs). 35 is post-contest, also Himanshu. In-contest counts are then A 16, B 18. The heavier P0 app work is Prakhar's; the heavier CI and docs work is Himanshu's.

Day 2 note for Prakhar (Member B): finish 07, and wait for Himanshu's (Member A) 08, before opening 09. 10 can land beside 07 because it only touches `frontend/src/dispatch.ts` and a new stylesheet. Do not both edit `frontend/src/rider.ts`. Land 19 early, once 04 is in, and keep the issue 04 JSON so 10 does not wait on sqlite. Land 21 in parallel with 19 if you are not both rewriting `main.py`. Land 20 only after 10's slate is mergeable; 20 is the other Day 2 edit to `dispatch.ts`. Land 29 early as well (shared HTTP client, retries, breaker, no event-loop stall); 02, 07, and 08 should use that client rather than opening their own.

Day 3 note: 15 needs the public working-app video from 18 (a photo is not enough), but does not wait on 12. If the chart is merged, quote one number. If it is not, quote the live sample result from the README (Timbre line → Prisma transcript, word for word) and say the scored run follows before the deadline. Publish by 14 Nov 18:00 IST anyway. 22 waits for 13 and 19. 23 waits for 19–22 and describes only what has actually merged. 24 waits for 13 and 20; 16's checklist runs `scripts/smoke.py` against the public URL.

Production cut line on Day 3: P0 issues and the production sections on 07, 13, 19, 20, 21, 27, 28, 29, and 25 must merge before the public URL is shared widely and before anyone calls the app production-ready. P1 (30–34, 26, 31, 32) should land in the same window if they do not delay the video or the form. If time runs out, ship the P0 desk, record an honest demo, and leave P1 boxes open in the register. Issue 35 (staging, off-site backups, a self-hosted error tracker, automated tag-to-prod) is explicitly after 15 Nov 2026, 18:00 IST. The form and the video still win over a late P1 patch.

## Rules that apply to every issue

- Synthetic audio and synthetic order tokens only. No real phone numbers, call recordings, customer names, or government IDs. An 8-digit run is not an `order_id`.
- Free tools only. Gnani credits are the contest grant. LLM is Groq or Gemini free tier. Host is Hugging Face Spaces or Render free. No paid APIs, no paid fonts, no paid dataset.
- Real Gnani calls only. No mock flags, canned transcripts, tone stand-ins, or fixture scores in app, benchmark, or docs. A missing `GNANI_API_KEY` is a loud error, never a silent fallback.
- CI (`ruff`, `pytest`, `npm run check`) stays green with no secrets. Tests fake the HTTP transport inside the test file (`httpx.MockTransport` or monkeypatch), never through a flag in app code. Live tests are opt-in and skip when `GNANI_API_KEY` is absent.
- Watch credits: one REST STT call per clip, one TTS call per line. Cache generated audio under `benchmark/data/audio/` and do not regenerate it on every run.
- `extract_event(transcript) -> RiderEvent` stays that signature. Extra optional args are fine. Removing the rule fallback is not.
