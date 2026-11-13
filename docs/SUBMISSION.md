# Submission evidence

**Status: not submitted.** Audited 13 Nov 2026 at 14:46 IST against
`af11363324ee81fc2e053f99036941a667e10034` (merged passcode and logging work).
This is a dated checkpoint. Re-run the checks against the final submission
commit; green unit tests do not replace a working public demonstration.

**Benchmark follow-up:** main `7b78f9c` now contains the completed live default
grid, scored 13 Nov 2026 at 15:04 IST: 80 distinct files, 400 evaluations,
20 batch job IDs and raw transcripts in `benchmark/results/`. Main `0b2b393`
also contains #73: the README table and committed SVG are now published, and
issue 12 is complete. The public-smoke CLI is merged in `3154f30`;
its deployed run remains outstanding. Other audit evidence below stays dated
to `af11363`.

The [official programme page](https://www.gnani.ai/internship), checked on
13 Nov, states **15 Nov 2026, 18:00 IST** as the final submission deadline.
It requires a public working-app video, a live nominated post with the Gnani
tag and both hashtags, and submission through its linked form. Our internal
post target is 14 Nov, 18:00 IST. Neither target is a submission confirmation.

## Candidate update, 14 November 2026 IST

The draft integration in [PR 92](https://github.com/CodewithJha/rasta-voice/pull/92)
combines the pending security, privacy and API repairs with their prerequisites.
It is not merged or deployed. Its [dated integration evidence](evidence/integration-2026-11-14.md)
records 1,854 passing Python tests, 90.93% coverage, 57 typed source files,
23 frontend unit tests, real keyless Ack/Resolve browser coverage, a scanned
non-root image and bounded keyless load. It preserves the first failed load
measurement and the exact source-digest secret-scan false-positive record.
The README now records the conditional SOCKS prerequisite; this is not a claim
that a new clean install or public live smoke has been completed here.

Before the final checklist can become all yes:

- Priyanshu reviews the small pending PRs. Upload/CSRF 86/87 land before their
  dependent browser test 90. Repairs 88/89 target his privacy/API branches
  83/85; Himanshu re-reviews those updated peer PRs before merging. Rule fix
  91 leaves the 8/36 versus 0.8 acceptance failure open. The draft aggregate
  92 must be updated after prerequisites merge, then reviewed as the smaller
  remaining integration change. Neither owner merges their own PR.
- Priyanshu provides the verified free-host origin and deployed revision, and
  resolves the owner-side branch-enforcement limitation. Public speech stays
  paused until release prerequisites are verified.
- Himanshu runs the bounded public smoke and records actual IDs/channel
  evidence. Consented field recordings remain separate from this public host.
- Priyanshu times the actual script, records and publishes the working-app
  video, and confirms official submission. Himanshu verifies the playable
  video and nominated posts with their real public URLs.

The historical table below remains dated to its original audit. No live
provider success, consent, post, video, host or form receipt is invented.

## Checklist

Every `no` remains open with an owner. A draft, historical README claim or
passing test with a substituted HTTP transport is not live provider evidence.

| Check | Done | Evidence and next owner |
| --- | --- | --- |
| README setup without additions | no | A new checkout and virtual environment installed `requirements-dev.txt`, but this workspace's SOCKS proxy caused 40 test failures because optional `socksio` was absent. Installing `httpx[socks]` resolved them. Himanshu: record the proxy-specific prerequisite or repeat the exact README on a supported ordinary network. |
| Python and frontend checks after that prerequisite | yes | Ruff passes; mypy passes on 44 production files; schema/types match. Pytest: `1576 passed, 1 skipped, 1 xfailed, 3 warnings in 13.33s`, coverage 91.04%. Fresh `npm ci` followed by `npm run check` passes TypeScript and 4 Node tests. |
| Live hello path | no | No new live Prisma request ID recorded in this audit. Himanshu, issues 24/16: run the noisy sample on the final configured host and verify `customer_unreachable`, order `18`. |
| Gnani is actually used | no | Code calls Prisma and Timbre, and clean manifests record synthetic Timbre durations, but this checkpoint has no fresh provider request ID paired with a measured live clip. Himanshu: attach both after the live run. |
| No runtime mock paths | yes | Case-insensitive `mock`, `GNANI_MOCK` and `canned` search of the four runtime source trees returned no matches. Tests remain separate; details below. |
| Missing key is loud | yes | A real local Uvicorn server with an empty speech key returned HTTP 503 from `POST /api/ingest/sample`, with the missing-key message and request ID `de6c0efb-74d6-406a-8666-df3c6de6b4c0`. No provider call occurred. |
| Benchmark section | yes | Main `0b2b393` includes #73: the README markers contain the exact `scores.md` table, committed `wer.svg`, run date, 80-file/400-evaluation counts, synthetic-data statement, operator-supplied credit wording and the raw/normalized cross-script caveats. #70 provides all 400 evaluations, 20 batch job IDs and raw transcripts. |
| No real personal data in inspected repository text | yes | The digit scan produced 869 matching lines, manually classified below. No actual personal identifier was found in those matches. This static check does not establish runtime redaction or retention; Priyanshu's issue 28 remains open. |
| Demo script read-through | no | `demo-script.md` is a planned 60-second shot list, with 52 spoken words and budgeted provider waits. No timed read-through or completed take was performed. Priyanshu, issues 14/18: time the actual working-app take. |
| Public video watched | no | No public video URL is recorded. Priyanshu, issue 18: provide it; Himanshu must watch it and compare audio, transcript and event before marking this yes. |
| Posts and Gnani attribution verified | no | `social-post.md` contains drafts and empty publication checkboxes. Himanshu, issue 15: publish after the video exists, verify the real tag and `#GnaniAI` plus `#GreatIndianAIInternshipChallenge`, then record each nominated URL. |
| Public deployment | no | `DEPLOY.md` covers secrets only and explicitly leaves the host/public URL to issue 13. Priyanshu: provide a working public origin and verify its health. |
| Public demo credit protection | no | Desk authentication is merged, but a deployed speech quota/rate limit and readiness evidence have not been verified. Priyanshu, issues 13/22/27: enforce and demonstrate them before sharing the URL. |
| End-to-end public smoke | no | The CLI from #68 is merged in `3154f30`; it is not public live-success evidence. Local no-key health exits 0 with a skip. A configured preflight stops at missing `/api/ready` (404), before speech. Priyanshu: deploy 13/22/26 and public headers from 27; Himanshu: run issue 24 and record IDs below. |
| Field-validation channel identified | no | Committed phone manifests identify synthetic 8 kHz/G.711 simulation, not a consented telephone recording. No noisy-microphone or real telephone-channel evidence was collected here. Himanshu, issue 17: record consent and channel provenance separately. |
| Official form submitted | no | No form confirmation was observed. Priyanshu, issue 18, with Himanshu's evidence: submit the final explanation, actual APIs/models, both members' contributions, video and nominated post links. Then record the confirmation and time. |
| Submitted before deadline | no | No submission confirmation exists. Priyanshu and Himanshu: finish before 15 Nov 2026, 18:00 IST. |

## Reproduced checks

From a new worktree at the commit above:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check gnani_client backend benchmark
pytest
```

The first pytest run was `40 failed, 1536 passed, 1 skipped, 1 xfailed`.
The failures traced to HTTPX trying to use this environment's inherited SOCKS
proxy without its optional transport dependency. Proxy configuration was
preserved. With the environment-specific addition below, the full suite passed:

```bash
pip install 'httpx[socks]'
pytest
# 1576 passed, 1 skipped, 1 xfailed, 3 warnings in 13.33s
# Required test coverage of 80% reached. Total coverage: 91.04%
mypy backend/rasta gnani_client benchmark
python scripts/check_frontend_types.py
cd frontend
npm ci
npm run check
```

The optional SOCKS package was installed locally, not added as a repository
dependency. The unmodified README setup row therefore remains `no` for this
workspace. No speech credits were used. Default tests substitute transports
only inside test files, and the live test skipped without a provider key.

## Text and data inspection

Runtime fake-path scan:

```bash
rg -n -i 'mock|GNANI_MOCK|canned' \
  backend/rasta gnani_client/gnani_client benchmark/rasta_bench frontend/src
```

Result: **no matches**. Repository prose about mocks is not a runtime path.

Personal-data candidate scan:

```bash
rg -n '[0-9]{8,}' benchmark/data docs backend frontend shared
```

Result at the audited commit: **869 matching lines**. Review:

- 855 manifest lines contain digit runs inside SHA-256 integrity fields.
  Parsing every manifest record found long digit runs only in `sha256` or
  `source_sha256`, never the spoken text or order tokens. There are 48 clean,
  768 mixed and 768 phone-manifest records.
- 10 backend/benchmark test lines deliberately exercise rejection of long
  numeric order tokens, malicious reply content and phone-like strings.
  These are synthetic adversarial fixtures, not collected customer data.
- 3 issue-description lines specify a synthetic privacy-test example.
- 1 issue-description line specifies the HSTS max-age value.

No matching personal data was identified. This document adds the audit commit
and local correlation IDs, so a later scan will have additional non-personal
matches. Inspect them again rather than requiring a literal zero count.
The full-history secret scan was green on the reviewed logging PR; no key,
passcode, cookie or raw customer recording is included in this checkpoint.

## Public evidence to fill after verification

| Evidence | Current value | Owner |
| --- | --- | --- |
| Public app URL and health request ID | not recorded | Priyanshu, issue 13 |
| Noisy sample's Prisma request ID | not recorded | Himanshu, issue 24 |
| Timbre request ID, if returned, and measured clip duration | not recorded | Himanshu, issues 24/16 |
| Smoke output, event ID and speech-call upper bound | not recorded | Himanshu, issue 24 |
| Actual provider charge or remaining balance | not verified; #70 records an operator-supplied cap, not a provider balance; no credits used in this audit | Himanshu |
| Public working-app video URL, watch date and duration | not recorded | Priyanshu, issue 18; Himanshu verifies |
| Nominated X post URL | not published | Himanshu, issue 15 |
| Nominated LinkedIn post URL | not published | Himanshu, issue 15 |
| Official submission confirmation and time | not submitted | Priyanshu, issue 18 |

After the deployment prerequisites land, run the merged smoke CLI once with the secrets
already supplied through the process environment. Do not put their values in
the command, recording, document or shell history:

```bash
python scripts/smoke.py --base-url <verified-public-origin> --require-security-headers
```

Paste only safe request IDs, event ID, intent and call upper bound here. The
CLI checks readiness and authentication before one noisy sample, makes no
client speech retry, and reports `SAMPLE_LOGICAL_OPERATIONS * (1 + server_retry_cap)`
after dispatch, including a potentially charged timeout. The default cap is two
server retries per operation under issue 29, giving a conservative six-attempt
bound. Only use `--server-max-retries` or `RASTA_UPSTREAM_MAX_RETRIES` after verifying
the remote host's cap; a local setting does not discover remote configuration.
The earlier
two-call bound at the original audit checkpoint did not include server retries.
The bound is not proof of the provider's actual charge. A keyless
skip is not a completed public smoke.

## Project explanation for the final form

Rasta Voice is a Hinglish voice copilot for delivery riders who need to report
problems from noisy surroundings. Prisma transcribes speech; the extractor
turns the transcript into an intent, short synthetic order token, ETA, urgency
and suggested dispatch action. The desk lists events behind a shared passcode.
Timbre can speak the corresponding confirmation. The benchmark compares
controlled synthetic noise and simulated telephone audio. It does not establish
accuracy on real telephone calls. The live default grid now has 400 completed
evaluations from #70. Raw mean WER ranges from 0.7292 to 0.8429, but many
outputs use a different script from the Latin references; this is not a
clean model ranking. The README table and raw-WER chart are committed from #73
in main `0b2b393`; issue 12 is complete.

Actual integration paths to name in the form: Prisma v3.0 REST STT at
`POST /stt/v3`, its streaming route at `/stt/v3/stream`, and Timbre v3.0 TTS at
`POST /api/v1/tts/inference`. The completed default grid used the Prisma batch API, including denoise
settings. Its 20 job IDs are recorded in `scores.json`; the batch responses did
not return request IDs, so do not relabel job IDs as REST request IDs. State which extractor provider was actually used in the recording.

The team is exactly two people:

- **Himanshu Kumar (@himanshu748):** corpus, synthetic audio/noise/telephony
  tooling, benchmark runner, verification tooling, quality/security CI and docs.
- **Priyanshu Jha (@CodewithJha):** API, extraction integration, realtime
  streaming, spoken reply, rider/desk UI, passcode and request logging.
  Hosting, final public video and form submission remain pending.

Use this explanation only after updating the evidence rows. It is a prepared
write-up, not a submitted form or confirmation of contest completion.
