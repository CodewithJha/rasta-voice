# 17 - Consented real-world noisy speech validation

- **Labels:** `member-a`, `area:benchmark`, `day:3`, `award`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 3 (14-15 Nov 2026), ideally before the final chart and demo.
- **Depends on:** #06 for a synthetic telephony baseline and #11 for scoring. A small REST check may start earlier.
- **Purpose:** Provide evidence for the Noise Canceller award beyond procedural noise. This is a separate field-validation set, not a replacement for the reproducible synthetic benchmark.

## Description

Record 4-8 short, invented Hinglish rider phrases spoken by one or two explicitly consenting team members. Prefer genuine phone-channel capture if available and lawful, otherwise record through a microphone in a genuinely noisy location. Do not call a microphone recording a telephone call. Never record real customers, actual delivery workers, uninvolved bystanders, personal addresses, real order IDs, or phone numbers.

Re-use corpus reference lines. When feasible, capture the same phrase under quiet and noisy conditions and record the actual provenance (`phone` or `mic`), date, sample rate/codec if known, noise setting, an anonymous speaker id, and the invented reference transcript. Resampling microphone audio to 8 kHz is not evidence of a telephone network.

Send the actual captured audio to Prisma with the model/hints comparable to #11. Compute reference-vs-hypothesis WER/CER, intent accuracy and any reported latency. Apply the explicit normalization documented in #11. Show every sample's results plus aggregate statistics with small-sample caveats. Preserve request IDs and settings for reproducibility. If a genuine phone channel cannot be tested, state that explicitly.

Store only anonymized text results in git. Keep raw speech, identifiable consent records, and original call audio outside the repo and outside the public deliverables. This added validation must not hold up a truthful public video and submission.

## Files to touch

- `benchmark/results/field_validation.json` (new; anonymized outcomes)
- `benchmark/results/field_validation.md` (new; conditions, comparisons, caveats)
- `benchmark/tests/test_field_validation.py` (new; offline validation of result calculations)
- `.gitignore` only if necessary to exclude private captured recordings

## Do not touch

`backend/`, `frontend/`, `gnani_client/`, or the live synthetic scores of #11.

## Input / output contract

Each JSON result row contains an anonymized `id`, `source` (`phone` or `mic`), `condition`, `reference`, `transcript`, `model`, `request_id` when available, `wer`, `cer`, `intent_correct`, and relevant settings. The Markdown report labels which data actually came through a telephone channel, which data is only acoustically noisy, and whether any audio is resampled or G.711-processed.

## Acceptance criteria

- [ ] Consented participants speak invented rider lines; document if fewer than 4 clips were feasible.
- [ ] For every clip, provenance and method are honest, with phone/mic distinguished.
- [ ] Reported scores arise from actual Gnani responses and match the committed reference/transcript text; no invented WER.
- [ ] Results describe a small sample, limitations and contrasting noise/phone conditions.
- [ ] No real customer content, personal phone numbers, participant identifiers, private audio, or API keys are committed.
- [ ] Automated offline test recomputes WER/CER/intent correctness from the recorded JSON text.
- [ ] A live request ID or job ID is recorded when returned. Missing IDs are explicitly identified, not invented.
- [ ] If real phone capture is impossible before the deadline, report that limitation. Contest submission proceeds honestly without claiming real-call validation.

## How to test

Run `pytest benchmark/tests/test_field_validation.py -q`, compare scores with `rasta_bench.score`, inspect the local recordings by ear with permission, and check `git diff --cached` for accidental media or identity leakage.

