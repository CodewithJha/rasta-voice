# Live Gemini holdout measurement, 15 November 2026

Recorded at 9:48 AM IST (Asia/Calcutta, UTC+5:30) on the locked blind
holdout (`backend/tests/fixtures/intent_blind_holdout.jsonl`, 36 rows).
The adjacent JSON is the machine-readable record. It stores row ids,
labels, predictions, sources, fallback reasons and latencies. It does
not store transcripts, prompts, model text or API keys.

Regenerated with:

```bash
python scripts/eval_intent.py --provider gemini --sets blind \
  --write-evidence docs/evidence/gemini-holdout-2026-11-15.json
```

## Conditions

- Provider: `gemini`
- Model: `gemini-3.5-flash-lite` (checked 12 Nov 2026, re-checked 14 Nov 2026)
- Timeout: 4.0 s (issue-body default; not raised)
- Request pacing: `LLM_MIN_REQUEST_INTERVAL_SECONDS=4.0`
- Groq key: unset in this process, so a retryable failure would have
  fallen back to rules rather than cascading to Groq
- A rules fallback is never counted as an LLM success
- Holdout labels were not changed

## Results

| Measure | Score |
| --- | --- |
| Rules on the same split (CI path, same morning) | 29/36 = 0.806 |
| Gemini end-to-end (fallbacks counted as rules) | 35/36 = 0.972 |
| Gemini validated (LLM answers only) | 35/36 = 0.972 |
| Order id exact-match (end-to-end) | 28/36 |
| ETA exact-match (end-to-end) | 35/36 |

All 36 calls returned a validated LLM event. There were no HTTP 429s
and no timeouts under the 4 s budget. The unpaced 14 Nov Gemini run on
the same labels had ten HTTP 429 fallbacks; pacing removed those 429s
on this run.

The one validated LLM miss was `b21` (gold `delay`, predicted
`address_issue`).

Latency over all 36 rows includes the 4.0 s minimum request interval,
so it is not comparable to the unpaced 14 Nov figures: mean 3916.0 ms,
p50 4002.2 ms, min 1315.4 ms, max 4446.2 ms.
