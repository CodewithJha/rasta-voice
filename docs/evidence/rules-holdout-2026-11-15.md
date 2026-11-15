# Rules holdout measurement, 15 November 2026

Recorded at 9:48 AM IST (Asia/Calcutta, UTC+5:30) on the locked blind
holdout (`backend/tests/fixtures/intent_blind_holdout.jsonl`, 36 rows)
after the rules-v2 freeze. The adjacent JSON is the machine-readable
record. It stores row ids, labels, predictions, sources, fallback
reasons and latencies. It does not store transcripts, prompts, model
text or API keys.

The holdout was scored once after the rules were frozen. Labels and the
0.8 threshold were not changed. Gold and the tuning holdout remained
30/30 and 24/24.

Regenerated with:

```bash
python scripts/eval_intent.py --provider rules --sets blind \
  --write-evidence docs/evidence/rules-holdout-2026-11-15.json
```

## Results

| Measure | Score |
| --- | --- |
| Rules intent accuracy | 29/36 = 0.806 |
| Order id exact-match | 36/36 |
| ETA exact-match | 35/36 |

Per-intent: `customer_unreachable` 5/6, `address_issue` 4/6,
`item_missing` 4/6, `delay` 5/6, `accident_sos` 5/6, `other` 6/6.

The seven misses are `b03` (gold `customer_unreachable`, predicted
`other`), `b08` and `b09` (gold `address_issue`, predicted `other`),
`b16` (gold `item_missing`, predicted `other`), `b17` (gold
`item_missing`, predicted `address_issue`), `b22` (gold `delay`,
predicted `other`) and `b27` (gold `accident_sos`, predicted `other`).
Rules were not changed after this one-shot score.

This meets the issue 2 target of 0.8.
