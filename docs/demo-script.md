# Working-app demo plan

This is a planned take, not a completed recording or a measured 60-second run.
Use only the actual working application and invented delivery details. Keep
keys, desk passcodes and unrelated customer/user content out of the frame.
Do not splice a different run's audio, transcript or result into a take.

## Before recording

1. Confirm the approved deployed revision in [SUBMISSION.md](SUBMISSION.md).
   PR 107's new UI is not public until reviewed, merged and deployed. Do not
   describe its screenshots as the live application.
2. Confirm `/api/ready` reports a configured key, writable database and at
   least three available local call units. This is not the provider balance.
3. Open a second app window and unlock Dispatch with the existing private
   passcode before filming. Do not expose the passcode field or devtools.
4. Use the locale actually shown in the take. English names below have these
   version-specific equivalents:

| Action | Deployed main `be7fffb` | PR 107 candidate, only after deploy |
| --- | --- | --- |
| Synthetic noisy sample | Noisy line, then Speak a sample line | Upload or test audio, Add road noise, then Try a sample |
| Rider result | Chit with transcript and facts | Your delivery update |
| Submitted sample playback | Native player under What Prisma heard | Native player under Submitted audio |
| Spoken reply request | Hear dispatch | Hear reply |
| Dispatcher | Dispatch slate on the same page | Dispatch navigation, Delivery updates |
| Acknowledge | Ack | Acknowledge |
| Resolve | Resolve | Mark resolved |

## Planned 60-second take

| Time | Show | Say |
| --- | --- | --- |
| 0-8 s | Rider screen, primary action in frame | Rasta Voice helps delivery riders explain a problem in Hinglish and gives dispatch a clear update. |
| 8-12 s | Select the noisy synthetic sample and activate it once | This example is synthetic. Timbre generates the audio and Prisma transcribes it. |
| 12-25 s | Actual request completes; play the returned sample using its native audio controls | Let the actual audio play. Provider wait time is variable; this window is a plan, not a latency claim. |
| 25-36 s | Actual transcript and fields, then the matching event in the unlocked dispatcher window | Read only what the actual result says. For a passing standard sample: customer unreachable, order eighteen, ten-minute delay. |
| 36-49 s | Request the spoken reply once, then press Play on its native audio control | Timbre gives a spoken confirmation. Do not claim that requesting audio automatically played it. |
| 49-57 s | Acknowledge the same synthetic event, then resolve it | Dispatch can take responsibility and close the update. |
| 57-60 s | App and project name | Built with Gnani Prisma and Timbre. |

This sample costs two logical speech operations; the separate reply costs one
more. With the verified zero-retry configuration, the intended upper bound is
three provider attempts. No retakes or speech retries should happen silently.
The local admission counter may also include other users' operations.

Time the real take. If waits or playback overrun 60 seconds, use an honest
longer demo or make a new explicitly budgeted take. Do not speed up audio,
hide a failed request or state that an incomplete take passed. If the order
is unresolved, show the clarification behavior and record the limitation;
the strict order-18 acceptance gate still fails that take.

## After recording

Watch the entire saved video. Verify audio playback, transcript, event and
dispatch actions belong to the same run. Check the frame for secrets. Upload
it to a public location you control and open its actual URL signed out to
verify playback. Paste the verified URL into the nominated post and final
form. A script, generated concept or keyless screenshot is not the video.
