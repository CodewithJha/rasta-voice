# Field validation: not yet measured

**Status, 14 November 2026: no consented field samples collected.**

The benchmark in `benchmark/results/scores.md` reports **synthetic** 8 kHz/G.711-processed audio. Its live Prisma responses do **not** constitute real microphone or telephone-channel validation. We have not captured consented field recordings, have not sent any field audio to Prisma, and have no real-world WER/CER, latency, intent accuracy or provider request ID to report. A public demonstration or submission must not imply otherwise.

## Safe capture and reproducibility procedure

1. Obtain explicit consent from the speaker, and record consent **privately**, not in this repository. Speak only invented Hinglish rider lines from the corpus. Do not involve customers or bystanders.
2. Capture at least four short clips, ideally matched quiet/noisy pairs. Record whether the signal genuinely traversed a telephone network (`phone`) or was captured by a microphone (`mic`). Resampling mic audio to 8 kHz, using G.711, or placing a phone beside a mic does **not** establish telephone-network provenance.
3. Keep all original audio, private consent records, speaker identities, and call metadata **outside the repository and outside the public Space**. The app has no field-audio upload or storage path.
4. Send each consented recording to the **real Prisma** provider only with an authorized key and an approved, bounded credit budget. Use a model/settings configuration comparable to `benchmark/rasta_bench/run.py`, and preserve the actual request ID if returned. If an ID was not returned, leave it `null` with an explicit reason.
5. Manually redact reference/hypothesis text before committing results. Populate `benchmark/results/field_validation.json` with records using the contract below. Calculate scores from the committed texts using `rasta_bench.score.wer/cer` and `rasta_bench.run.normalize`. For intent use `extract_event(transcript, provider="rules")`, not a model success inferred from a rules fallback.
6. Run `python -m rasta_bench.field_validation --require-measured` and `pytest benchmark/tests/test_field_validation.py -q`; include per-record scores, aggregates and limited-sample caveats in this report. Until actual responses are present the strict command correctly exits nonzero.

Each result row uses these fields (one anonymized row per actual recording): `id`, `source` (`mic` or verified `phone`), `capture_method` (`microphone` or `telephone_network`), `condition` (`quiet` or `noisy`), `recorded_at` (ISO date), `speaker_id` (`s1`, etc.), `consent_confirmed` (true), `sample_rate_hz`, `codec`, `resampled`, `g711_processed`, `reference`, `transcript`, `model`, `request_id` (or `null` with `request_id_unavailable_reason`), `gold_intent`, `predicted_intent`, `intent_provider` (`rules`), `wer`, `cer`, `normalized_wer`, `normalized_cer`, `intent_correct`, `settings` and optional `latency_ms`.

The `settings` object permits only `language_code`, `keyterms`, `with_denoise`, and `output_format`, with no API credentials. Model versions and fields should match the actual response. The validator rejects impossible provenance combinations, unsupported labels, unexpected metadata, repeated IDs and mismatched calculations.

## Measurement and interpretation

No field sample exists yet, so the number of genuine telephone captures is **zero**. We cannot compare quiet/noisy field conditions, compute a valid mean or attribute any noise-cancellation gains from field data. Once available, report sample count, paired conditions, channel source, source-specific WER/CER and intent accuracy, cross-script effects and provider request IDs. Small samples are descriptive, not statistically representative. If no genuine phone-channel capture becomes available, state this limitation explicitly in the submission.
