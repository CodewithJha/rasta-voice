# 18 - Publish a working demo video and verify final contest submission

- **Labels:** `member-b`, `area:app`, `day:3`, `demo`, `contest`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI; Member A: Himanshu (@himanshu748) verifies benchmark claims
- **Target day:** Public video and post by 14 Nov 2026, 18:00 IST; completed official submission before 15 Nov 2026, 18:00 IST.
- **Depends on:** #09 (demoable rider UI) and #14 (script). Use #15's post copy and links. #12 (scores) and #13 (host) improve the video, but must not delay a truthful localhost recording.
- **Official requirements:** https://www.gnani.ai/internship

## Description

A script, screenshot, photo-only post, or saved form draft is not a complete contest entry. The official programme calls for a publicly posted **working-application video** and a completed final form with the demo and nominated social links.

Record the real Rasta Voice application working with invented rider speech. Aim for 60 seconds for the demo-award route. Show:

1. Audible synthetic Hinglish rider input with its noisy condition clearly identified.
2. The exact audio being sent to live Gnani Prisma, with actual transcript and model/request evidence if available.
3. The resulting dispatch action, intent, order, and urgency in the live slate.
4. Timbre reply playback only if #08 actually works; do not show a simulated successful reply.
5. A WER chart or numerical claim only when supported by #11/#12 committed, live-run results.

Do not fake a response, swap samples silently, misrepresent generated noise as real phone recordings, include API keys or `.env` in the video, or show real personal data. You may trim pauses, but do not change results. If a feature is broken, record the working subset and explain the limitation.

Publish the **video** on LinkedIn and/or X using #15's copy. Tag Gnani AI and include **#GnaniAI** and **#GreatIndianAIInternshipChallenge**. Verify the video plays from the publicly shared post. Nominate a link for every social platform used in the official form.

Complete and submit the official form with the project name/explanation, Gnani models/APIs, each member's contribution (Himanshu and Priyanshu), video, and nominated post link(s). Capture a safe completion status or submission receipt without exposing personal form fields. A saved draft is not evidence of submission.

## Files to touch

- `docs/demo-evidence.md` (new; video URL, duration, recorded steps, Gnani model/request evidence, posted links, verified form status)
- `docs/social-post.md` (fill published links in #15)
- Coordinate with Himanshu (Member A) on `docs/SUBMISSION.md` (#16)

## Do not touch

Benchmark or app code except for a tested bugfix necessary to reproduce the actual demo. Do not commit large video files, credentials, private form responses, or raw customer/rider recordings.

## Input / output contract

`docs/demo-evidence.md` includes the public video URL, duration, recording date, exact app actions seen in the recording, model name(s), actual Prisma `request_id` if present, public post links, nominated platform(s), and submission status (`not submitted`, `submitted (confirmation captured)`, or `unknown`). It may include a non-sensitive confirmation reference; do not copy PII from the form.

## Acceptance criteria

- [ ] A public playable video of the working app is posted, not just a script or screenshot.
- [ ] The actual processed speech, visible event and spoken reply (if shown) come from real Gnani calls.
- [ ] Synthetic/field audio, limitations, and any benchmark claims are labeled truthfully.
- [ ] The nominated post contains the video, Gnani mention/tag and both required hashtags.
- [ ] The published post and video URLs work and match the links supplied in the official form.
- [ ] The final form contains project details, Gnani models/APIs, Himanshu and Priyanshu's contributions, video and nominated posts.
- [ ] Final submission is confirmed by 15 Nov 2026, 18:00 IST; no 'done' check from an unsent draft.
- [ ] #16 independently verifies the public links and confirmed submission status.

## How to test

Open the final post/video from a fresh browser session and watch the clip. Compare the demo claims with the running app and committed benchmark results. Verify submission completion in the programme form and record only safe proof in `docs/demo-evidence.md`.

