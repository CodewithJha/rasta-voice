# Live Gemini holdout measurement, 14 November 2026

Recorded at 9:30 PM IST (Asia/Calcutta, UTC+5:30) on the locked blind
holdout (`backend/tests/fixtures/intent_blind_holdout.jsonl`, 36 rows).
The adjacent JSON is the machine-readable record. It stores row ids,
labels, predictions, sources, fallback reasons and latencies. It does
not store transcripts, prompts, model text or API keys.

Regenerated with:

```bash
python scripts/eval_intent.py --provider gemini --sets blind \
  --write-evidence docs/evidence/gemini-holdout-2026-11-14.json
```

## Conditions

- Provider: `gemini`
- Model: `gemini-3.5-flash-lite` (checked 12 Nov 2026, re-checked 14 Nov 2026)
- Timeout: 4.0 s (issue-body default; not raised)
- Groq key: not set, so Groq was not scored
- A rules fallback is never counted as an LLM success
- Holdout labels were not changed

## Results

| Measure | Score |
| --- | --- |
| Rules on the same split (CI path) | 8/36 = 0.222 |
| Gemini end-to-end (fallbacks counted as rules) | 26/36 = 0.722 |
| Gemini validated (LLM answers only) | 24/26 = 0.923 |
| Order id exact-match (end-to-end) | 31/36 |
| ETA exact-match (end-to-end) | 35/36 |

Ten of 36 calls fell back to rules after HTTP 429 (one retry each). One
HTTP 503 was retried once and then returned a validated LLM event. There
were no timeouts under the 4 s budget.

The two validated LLM misses were `b31` and `b32` (gold `other`, predicted
`delay`). Of the ten 429 fallbacks, two were correct by the rules path
and eight were not.

Latency over all 36 calls: mean 886.0 ms, p50 832.8 ms, min 522.4 ms,
max 1928.3 ms. LLM-only latency (26 validated answers): mean 1003.2 ms,
p50 905.0 ms, min 721.2 ms, max 1928.3 ms. Fallback latency (10 429s):
mean 581.5 ms, p50 562.1 ms, min 522.4 ms, max 741.5 ms.

End-to-end 0.722 is still below the issue 2 target of 0.8. The production
timeout was not raised to chase that score.
