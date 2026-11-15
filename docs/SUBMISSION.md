# Submission packet

## Latest verified assets, 15 November 2026

- [One-page product pitch](PITCH.pdf).
- [Public 122-second product video](https://github.com/user-attachments/assets/c9136446-2a79-42f0-90ba-6dbdc7293b03), using the existing deployed UI, real Gnani responses and an illustrative synthetic rider message.
- [Published LinkedIn post](https://www.linkedin.com/feed/update/urn:li:activity:7527676685782159360/), with the actual Gnani AI company mention and both required hashtags; native video playback was verified.
- [Final team handoff](FINAL_SUBMISSION_HANDOFF.md). Priyanshu will fill the official form. No submission receipt has been verified.
- The free Render service was redeployed at application commit `be7fffb2db4f7b59dcab1f9dc236627dfbcbb708`, deploy `dep-dbso1egn74is73ae55dg`, with the approved process-local allowance of 20. Readiness showed 20 remaining immediately after restart. This is not a provider balance or a hard billing cap.
- PR #107 remains unmerged and is not deployed at the user's request. The current UI is retained.
- Live microphone/WebSocket acceptance, authenticated desk acceptance, consented field recordings and rollback evidence remain open. The synthetic video does not close these gates.

The dated checkpoints below are historical wherever this update supplies newer evidence.

Status checked 15 November 2026 at 06:38 UTC (12:08 IST). **Not submitted.**
This packet separates verified application evidence from the remaining human
and public steps. [Earlier audits](SUBMISSION_HISTORY.md) remain preserved.

## Links and version

- Live app: https://rasta-voice-himanshu748.onrender.com/
- Repository: https://github.com/CodewithJha/rasta-voice
- Deployed main: `be7fffb2db4f7b59dcab1f9dc236627dfbcbb708`
- Live Render deploy: `dep-dbsknsuk1f9s739is77g`, free Singapore service.
- UX candidate: [PR 107](https://github.com/CodewithJha/rasta-voice/pull/107),
  head `69b5d3f04f838716182ddd7948806bb51d1718bb`. All ten checks pass;
  code-owner review is still required. It is **not deployed**.
- Official programme: https://www.gnani.ai/internship
- Official submission form linked by the programme:
  https://forms.cloud.microsoft/r/dfFShbp7W7

The programme page was rechecked on 15 November. It gives a deadline of
**15 November 2026, 18:00 IST (12:30 UTC)**. A working-app video and a live
nominated LinkedIn or X post with the real Gnani AI tag and both
`#GnaniAI` and `#GreatIndianAIInternshipChallenge` are required before final
submission. This document and the drafts are not publication or a receipt.

## Fields verified in the actual submission form

The official Microsoft form was opened and read on 15 November. Its mandatory
fields are full name, registered email, higher education institution, project
URL and video URL. Team entries also have a teammate registered-email field.
The project URL must include a **solution pitch no longer than one page**;
[the one-page PDF pitch](PITCH.pdf) ([text version](PITCH.md)) is prepared for that purpose. Its video field
explicitly requires a **2-3 minute working demo**. A separate optional field
asks for a LinkedIn or X solution post tagging Gnani for bonus awards.
The programme page still requests nominated public demo posts and both hashtags;
prepare that evidence rather than interpreting an optional form field as a waiver.

Do not guess the primary/teammate registered emails. No personal form fields
were filled and Submit was not pressed. After this PR merges, the project URL
can point directly to the public repository's `docs/PITCH.pdf`. The candidate
pitch is currently on the PR branch; verify the chosen public URL before using it.

## Copy for the form

**Title:** Rasta Voice: Hinglish delivery updates for riders and dispatchers

**Problem and users:** Delivery riders need to explain delays, unreachable
customers and other delivery problems while working in noisy surroundings.
Rasta Voice turns a spoken Hinglish update into readable dispatch information
and a spoken confirmation. Riders and dispatchers have different jobs: riders
report the issue; dispatchers acknowledge and resolve the resulting update.

**How it works:** Gnani Prisma transcribes a short upload, a synthetic sample
or microphone stream. A validated extractor produces the intent, short order
identifier, ETA, urgency and next action. The server stores the event in SQLite.
An authenticated dispatcher sees it and can acknowledge or resolve it with an
audit trail. Gnani Timbre generates a state-aware spoken confirmation. Missing
order numbers prompt clarification rather than a guessed identifier.

**Actual Gnani integrations:** Prisma v3.0 REST STT (`POST /stt/v3`), Prisma
streaming (`/stt/v3/stream`) and Timbre v3.0 TTS
(`POST /api/v1/tts/inference`). The completed speech benchmark also uses
Prisma batch recognition, including denoise settings. Its batch job IDs are
not REST request IDs. Production uses the `rules` extractor; optional Groq
and Gemini extraction paths are documented separately and are not used by
the public sample recorded below.

**Contributions:** Himanshu Kumar (@himanshu748): synthetic corpus and
noise/telephony tooling, benchmark and verification tooling, quality/security
CI, release evidence, hosting verification, spoken-number/count corrections,
and the proposed rider/dispatcher UX redesign. Priyanshu Jha (@CodewithJha):
API, extraction integration, realtime streaming, spoken replies, original
rider/desk UI, authentication, request logging, rules-v2 implementation and
peer review. Both owners follow protected PR review. Do not imply a third
teammate or a submitted/public video that has not been verified.

**Testing and limits:** The latest candidate CI passes 2,048 Python tests with
91% coverage, Ruff, mypy, contract checks, 4 Node tests, 23 Vitest cases,
8 keyless browser tests, secret/dependency/SAST scans, Docker/Trivy and load.
One live browser test remains skipped. Rules intent accuracy on the unchanged
36-row blind holdout is 29/36 (0.806), meeting its 0.8 target. The separate
maintainer-recorded Groq and Gemini holdout runs each scored 35/36 end to end;
those provider runs were not repeated during this verification. See
[EXTRACTOR.md](EXTRACTOR.md) for fallback accounting and preserved misses.

The speech benchmark contains 400 evaluations of controlled synthetic audio,
not recordings of customers or a carrier telephone network. Raw WER has
cross-script caveats; it is not an independent field-quality claim. No
consented field recordings have been collected. Frame the project as a
Hinglish voice workflow with synthetic noise experiments; do not claim that
it has proven the Noise Canceller award's real-telephony criterion.

## Fresh public sample evidence

One noisy synthetic sample was run on the deployed revision, with no client
retry and configured server retries zero. At 06:38 UTC it returned HTTP 200:

| Field | Actual value |
| --- | --- |
| Intent | `customer_unreachable` |
| Order | `18` |
| ETA | 10 minutes |
| Urgency | `high` |
| Extractor | `rules` |
| Prisma model | `prisma-v3.0` |
| Prisma request ID | `01a1dded-6a57-7833-b8cd-688768beca3e` |
| Application request ID | `6301fe2b-2a13-4413-a5e3-5155b7bfd9d4` |
| Stored event ID returned by ingest | `6c008768-9cf6-4a00-9995-8e89e9de66d0` |
| Returned sample duration | 6.48 seconds |
| Local admission allowance | 9 before, 7 after this two-operation sample |

The unchanged strict sample assertions passed. The earlier `order a teen`
failure is retained in the [historical record](evidence/render-live-smoke-2026-11-14.json).
A new passing sample does not erase that limitation or establish a field
accuracy rate. The allowance is process-local, resets on restart and is not
a provider balance or hard billing cap. No new spoken reply, microphone,
authenticated desk read or browser playback was verified in this sample.
The full `scripts/smoke.py` flow is still unverified on this revision because
the private desk passcode was unavailable to this execution.

Sanitized [sample evidence](evidence/submission-live-sample-2026-11-15.json)
and [public HTTP evidence](evidence/submission-public-http-2026-11-15.json)
record the actual checks. Do not publish any secret or real customer data.

## Subsequent real-browser check

At 06:44 UTC the public browser triggered one more noisy synthetic sample,
with no retry. Prisma request `01a1ddf3-5a42-780d-a70f-6ba9c0b6d699` returned
`customer_unreachable` and ETA 10, but transcribed `order a teen`; its order
was null. Event `9af450e5-cf7e-436b-8cb6-43c1b04fee9d` was shown in the
actual rider UI. This browser take **fails the unchanged order-18 check**.
After this sample and its reply, readiness reported four local call units
remaining and three stored events; no additional speech request was triggered.
The earlier API sample pass is a single observation, not reliable end-to-end
acceptance. No sample was retried to obtain a passing screenshot.

The returned sample played to completion in the browser (6.00 seconds). One
additional real Timbre reply requested order confirmation instead of guessing:
`Order number saaf nahi hua. Surakshit jagah rukiye aur dispatch se order ki pushti kijiye.`
Its 5.52-second audio was played using the native controls. Playback evidence
is the observed media duration/time/ended state with no media error, not a
claim of human listening, microphone capture, a video or desk authentication.
The browser sample plus reply used three logical operations. See the
[sanitized browser evidence](evidence/submission-browser-2026-11-15.json).

## Final checklist

| Gate | Status | Next action |
| --- | --- | --- |
| Protected reviewed main and free public host | Verified | Keep the current deployment until a reviewed replacement is ready |
| Strict noisy sample response, order 18 | API sample passed; subsequent browser sample failed | Keep both observations; reliable live acceptance remains open |
| New rider UX | CI and viewport screenshots verified; not merged/deployed | CodewithJha reviews PR 107; merge only after approval/checks, then deploy and recheck |
| Authenticated live desk and full smoke CLI | Not verified on this revision | Operator provides the existing passcode privately to the test environment, then verifies this actual sample in the desk |
| Browser sample/reply playback | Native players completed; no media error | Keep the DOM/media-state evidence separate from a public video or human listening claim |
| Real microphone/WebSocket | Not verified | Test with an explicitly consenting team member and invented details |
| Live-provider Playwright | Not verified | Run its unchanged strict assertions with legitimate configured credentials and a bounded budget |
| Consented field validation (#17) | `not_collected` | Collect the required lawful, explicitly consented clips and genuine responses; keep raw clips/identities outside git |
| Actual rollback rehearsal | Not performed | Authorized operator uses the host dashboard; the connector has no rollback operation |
| Working-app demo video | Not recorded or watched | Record the required 2-3 minute take from [demo-script.md](demo-script.md), publish it and verify playback |
| Nominated LinkedIn or X demo post | Not published/verified | Review [social-post.md](social-post.md), attach the actual video, select the real tag and verify both hashtags |
| Final form and receipt | Not submitted/observed | Supply the verified video/post links, submit through the official form, then record its actual confirmation and time |

The remaining open implementation/evidence issues are #13, #17, #24 and #32.
Do not close them solely because a synthetic response or keyless CI passed.
