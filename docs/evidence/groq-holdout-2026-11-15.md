# Live Groq holdout measurement, 15 November 2026

Recorded at 9:45 AM IST (Asia/Calcutta, UTC+5:30) on the locked blind
holdout (`backend/tests/fixtures/intent_blind_holdout.jsonl`, 36 rows).
The adjacent JSON is the machine-readable record. It stores row ids,
labels, predictions, sources, fallback reasons and latencies. It does
not store transcripts, prompts, model text or API keys.

Regenerated with:

```bash
python scripts/eval_intent.py --provider groq --sets blind \
  --write-evidence docs/evidence/groq-holdout-2026-11-15.json
```

## Conditions

- Provider: `groq`
- Model: `openai/gpt-oss-20b` (checked 12 Nov 2026, re-checked 14 Nov 2026)
- Timeout: 4.0 s (issue-body default; not raised)
- Request pacing: `LLM_MIN_REQUEST_INTERVAL_SECONDS=4.0`
- Gemini key: unset in this process, so a retryable failure fell back
  to rules rather than cascading to Gemini
- A rules fallback is never counted as an LLM success
- Holdout labels were not changed

## Results

| Measure | Score |
| --- | --- |
| Rules on the same split (CI path, same morning) | 29/36 = 0.806 |
| Groq end-to-end (fallbacks counted as rules) | 35/36 = 0.972 |
| Groq validated (LLM answers only) | 33/34 = 0.971 |
| Order id exact-match (end-to-end) | 33/36 |
| ETA exact-match (end-to-end) | 36/36 |

Two of 36 calls fell back to rules after HTTP 429 (one retry each):
`b26` and `b29`. Both of those rules events were correct. There were
no timeouts under the 4 s budget.

The one validated LLM miss was `b27` (gold `accident_sos`, predicted
`delay`).

Latency over all 36 rows includes the 4.0 s minimum request interval,
so it is not comparable to the unpaced 14 Nov Gemini figures: mean
5435.5 ms, p50 4120.7 ms, min 685.8 ms, max 9745.0 ms.
