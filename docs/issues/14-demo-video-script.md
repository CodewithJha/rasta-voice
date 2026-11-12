# 14 — 60-second demo video script

- **Labels:** `area:app`, `day:3`, `demo`
- **Owner:** Member B: app & realtime
- **Target day:** Day 3 (14–15 Nov 2026). Write it as soon as issue 09 is demoable so a phone camera can roll on the 14th.
- **Depends on:** issue 09. If issue 12 has merged, the last beat points at the chart. If it has not, the script says "the scored table is in the README" and does not invent a WER.

## Description

Write `docs/demo-script.md`. It is a script, not the video file. The video stays out of git (it is large, and the contest form will take a link or an upload from the team). The script must be readable aloud in 60 seconds or less at a calm pace. Time each beat. Read it aloud once and write the actual seconds you took next to the target. If the total is over 60, cut words, don't talk faster.

Beats:

| Clock | On screen | Said |
| --- | --- | --- |
| 0–8 | The chit, night page, no dashboard chrome tour | Who it's for: a rider in traffic, Hinglish, a noisy phone line. Name Rasta Voice. |
| 8–20 | Toggle to Noisy. Play the utterance. | One real line, spoken: the gate is shut and the customer is not picking up, order 18. Say the audio is synthetic. |
| 20–35 | Slate fills: intent, order, action. Then the reply plays. | What dispatch is told, in one sentence. Mention Prisma heard it and Timbre answered. |
| 35–50 | README chart, or the SVG file full screen | v2.5 against v3.0, hints, denoise, on 8 kHz phone audio. One comparison, only if the number is in the committed live `scores.json`. If the scored run is not in yet, show the live sample result instead (Timbre line → Prisma transcript, word for word, also on 8 kHz noisy audio). Never quote a number that did not come from Prisma. |
| 50–60 | The page again | Noise Canceller entry. Mixed Hinglish. Hashtags spoken once: Gnani AI, Great Indian AI Internship Challenge. "No real customer calls." |

Do not show a terminal full of keys, a `.env` file, or a phone number. Do not claim a WER the JSON does not contain.

Add a shot list under the beats: which URL, which button, which file to have open. A teammate who was not in the room should be able to record it.

## Files to touch

- `docs/demo-script.md` (new)

## Do not touch

Application code. If the UI is missing a label the script needs, file that as a one-line fix on the issue 09 files only, in this PR, and say why.

## Input / output contract

The markdown file has the five beats with target seconds and measured seconds, the shot list, and a final line `Total read-through: NN s` with NN ≤ 60.

## Acceptance criteria

- [ ] Every beat names the on-screen target and the words.
- [ ] The synthetic-data sentence is in the script.
- [ ] No WER is stated unless you paste the matching snippet from the scores file under the beat.
- [ ] You read it aloud and recorded the time. The total is 60 seconds or under.
- [ ] No application code changed, or the exception is a label fix described in the PR.

## How to test

Read the script with a timer. A second person (Member A) reads it once without having seen the app and lists any step they cannot perform. Fix the shot list until that list is empty.

<!-- rasta-voice-audit-2026-11-12 -->

### Video delivery boundary

This issue delivers the **script and shot list** only. It is not finished contest delivery. Coordinate with the separate working-video-and-submission issue: record the actual application, publish a playable public video and verify the official submission, without waiting for perfect benchmark numbers.

- [ ] Time the script against the actual working screen transitions. Remove footage of broken or unimplemented controls; label simulated audio conditions truthfully.
- [ ] Pass the shot list to the owner of the publishing/submission issue and verify a working video can be recorded with it.

