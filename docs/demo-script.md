# 60-second demo script

Script and shot list only. The recording, public post and official form
are issue 18, using the copy in issue 15. There is no committed live
`scores.json`, so this script never states a WER.

Timed from a calm read-through of the spoken words at 130 words/min.
Cut until the total was 60 seconds or under.

## Beats

| Clock | Measured | On screen | Said |
| --- | --- | --- | --- |
| 0–8 s | 8 s | The rider chit, night page. Do not tour the desk chrome. | This is Rasta Voice: Hinglish help for a delivery rider speaking on a noisy phone line in traffic. |
| 8–20 s | 13 s | Click **Noisy line**, then **Speak a sample line**. Keep the chit in frame while the clip plays. | I switch to Noisy line and press Speak a sample line. You hear: the gate is shut, the customer is not picking up, order 18. This audio is synthetic. |
| 20–35 s | 13 s | The dispatch slate row for that event, then click **Hear dispatch** and let the confirmation play. | The dispatch slate fills: customer unreachable, order 18, HIGH — call the customer once from dispatch, then log the attempt. Prisma heard the line, and Hear dispatch plays Timbre's confirmation. |
| 35–50 s | 15 s | Stay on the same noisy sample on the chit: the audio Prisma received, and its transcript, word for word. Do not open a chart or the README. | The scored table is not in the README yet, so I will not quote a WER. Here is the same 8 kilohertz noisy sample: Timbre's line, then Prisma's transcript, word for word. |
| 50–60 s | 9 s | The page again, chit and slate both visible, no terminal or `.env`. | This is our Noise Canceller entry, mixed Hinglish. Hashtags: Gnani AI, Great Indian AI Internship Challenge. No real customer calls. |

Total read-through: 58 s

The 20–35 s spoken slate matches the current rules extractor and Timbre
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
4. For the second beat, click **Noisy line**, then **Speak a sample line**.
   Wait until the chit shows the clip and transcript. This REST sample
   spends two live speech calls (Timbre, then Prisma). If the request
   returns 503 or 402, stop the take; do not play a stand-in recording or
   type a fake transcript.
5. For the third beat, frame the **Dispatch slate** row that just arrived:
   intent `customer unreachable`, `order 18`, `HIGH`, and the dispatch
   action. Click **Hear dispatch** on the chit and let the confirmation
   finish. That is a third uncached Timbre call.
6. For the fourth beat, stay on that same chit result. Point at the noisy
   8 kHz audio the API returned and at Prisma's transcript next to it.
   Do not open `README.md`, `benchmark/results/`, or any chart. The scored
   table is not in the repository yet.
7. For the last beat, widen to the full page (chit and slate). End on
   "No real customer calls."
8. Have a second take ready if the first sample is slow or the slate
   lags. Do not cut in a successful reply from a different run.

Pass this shot list to issue 18 for the actual recording and to issue 15
for the post. This file is not a completed contest submission.
