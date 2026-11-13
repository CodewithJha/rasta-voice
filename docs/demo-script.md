# 60-second demo script

Script and shot list only. The recording, public post and official form
are issue 18, using the copy in issue 15. There is no committed live
`scores.json`, so this script never states a WER.

The clock is a planned working-app take, not a spoken-only read-through.
Spoken lines are measured at 130 words/min (52 words, 24 s). Wait and
play windows are budgets, not a live timed run: no speech credits were
spent for this script. The sample line is 19 words (~8.8 s) and the
Timbre confirmation is 14 words (~6.5 s) at that same rate, rounded up
to 10 s and 8 s so short pauses still fit. If a provider wait or a clip
overruns its window, stop the take and use the backup take.

The chit does not autoplay. **Speak a sample line** and **Hear dispatch**
only reveal the native players. You must click **Play** under **What
Prisma heard** and under **Sun lo — the Timbre confirmation**.

## Beats

| Clock | Duration | Basis | On screen | Said |
| --- | --- | --- | --- | --- |
| 0–6 s | 6 s | 13 words at 130 wpm | The rider chit, night page. Do not tour the desk chrome. | This is Rasta Voice: Hinglish help for a rider on a noisy line. |
| 6–8 s | 2 s | 4 words at 130 wpm, plus the two clicks | Click **Noisy line**, then **Speak a sample line**. | This audio is synthetic. |
| 8–16 s | 8 s | Budgeted wait (Timbre, then Prisma) | Keep the chit in frame. Wait until **What Prisma heard** and the transcript appear. If this wait passes 8 s, stop the take. | (silence) |
| 16–26 s | 10 s | Budgeted play (19-word sample ≈ 8.8 s at 130 wpm, rounded up) | Click **Play** on the native controls under **What Prisma heard**. Let the clip play. Do not skip this click. | (silence) |
| 26–30 s | 4 s | 6 words at 130 wpm | Frame the **Dispatch slate** row: `customer unreachable`, `order 18`, `HIGH`, and the dispatch action. | Slate: customer unreachable, order 18, HIGH. |
| 30–31 s | 1 s | Click | Click **Hear dispatch** on the chit. That is a third, uncached Timbre call. | (silence) |
| 31–37 s | 6 s | Budgeted wait (one Timbre call) | Wait until the player under **Sun lo — the Timbre confirmation** is visible. If this wait passes 6 s, stop the take. | (silence) |
| 37–45 s | 8 s | Budgeted play (14-word confirmation ≈ 6.5 s at 130 wpm, rounded up) | Click **Play** on that native player. Let the confirmation finish. Do not skip this click. | (silence) |
| 45–52 s | 7 s | 13 words at 130 wpm | Stay on the same noisy sample: the 8 kHz audio Prisma received, and its transcript. Do not open a chart or the README. | I will not quote a WER. Prisma's transcript is here, word for word. |
| 52–60 s | 8 s | 16 words at 130 wpm | The page again, chit and slate both visible, no terminal or `.env`. | Noise Canceller entry, mixed Hinglish. Gnani AI, Great Indian AI Internship Challenge. No real customer calls. |

Total planned take: 60 s (24 s spoken, 3 s of clicks, 14 s of budgeted waits, 18 s of budgeted playback).

The 26–30 s spoken slate matches the current rules extractor and Timbre
template for this sample line (`customer_unreachable`, order `18`, urgency
`HIGH`, and the "call the customer once from dispatch" action). If a live
Prisma transcript changes the intent, say what the slate actually shows.
Do not invent a field.

## Shot list

Himanshu, or anyone else recording, should be able to follow this without
having seen a walkthrough.

1. From the repository root, with `GNANI_API_KEY` already in the ignored
   `.env` (not in the shell history you will film), run
   `uvicorn rasta.main:app --host 127.0.0.1 --port 8000 --workers 1`.
   `LLM_PROVIDER=rules` is enough. In a second terminal, from `frontend/`,
   run `npm ci` if needed, then `npm run dev`.
2. Open only the Vite URL printed in that terminal, usually
   `http://127.0.0.1:5173/`. Close any editor, terminal, or tab that could
   show a key, a `.env` file, or a real phone number.
3. Start the first beat tight on the rider chit (page title **Rasta Voice**,
   night-coloured ticket). The desk may be visible later; do not describe
   its chrome in the opening seconds.
4. Click **Noisy line**, then **Speak a sample line**, and say "This audio
   is synthetic." Wait until the chit shows the clip and transcript under
   **What Prisma heard**. This REST sample spends two live speech calls
   (Timbre, then Prisma). If the request returns 503 or 402, or if this
   wait passes 8 s, stop the take; do not play a stand-in recording or
   type a fake transcript.
5. Click **Play** on the native controls under **What Prisma heard**. The
   chit does not autoplay. Let the clip run in this 10 s window. If it is
   still going at 26 s, stop the take.
6. Frame the **Dispatch slate** row that just arrived: intent
   `customer unreachable`, `order 18`, `HIGH`, and the dispatch action.
   Click **Hear dispatch** on the chit. Wait until the player under
   **Sun lo — the Timbre confirmation** appears. If that wait passes 6 s,
   stop the take.
7. Click **Play** on that confirmation player. It also does not autoplay.
   Let the confirmation finish in the 8 s window. If it overruns, stop
   the take. Do not cut in a successful reply from a different run.
8. Stay on that same chit result. Point at the noisy 8 kHz audio the API
   returned and at Prisma's transcript next to it. Do not open
   `README.md`, `benchmark/results/`, or any chart. The scored table is
   not in the repository yet.
9. Widen to the full page (chit and slate). End on "No real customer
   calls."
10. Have a second take ready if the first sample is slow, a clip runs
    long, or the slate lags.

Pass this shot list to issue 18 for the actual recording and to issue 15
for the post. This file is not a completed contest submission.
