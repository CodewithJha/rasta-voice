# Intent gold, tuning holdout, and blind holdout

Labels in these files are frozen. Do not change a label after seeing a
prediction, and do not drop a row to raise a score.

| File | Split | Rows | Role |
| --- | --- | --- | --- |
| `intent_gold.jsonl` | development | 30, 5 per intent | May be inspected while improving generalisable rules or the prompt |
| `intent_tuning_holdout.jsonl` | tuning / regression | 24, 4 per intent | Originally written as an independent holdout. It was then used to guide rule expansion (7/24 to 24/24), so it is no longer an independent test. All cases and labels are preserved for regression |
| `intent_blind_holdout.jsonl` | blind holdout | 36, 6 per intent | Fresh labelled set. Written and committed (`440bcda`) before any extractor was run on it. This is the independent test. The 0.8 target is measured here |

Fields match the issue 01 corpus: `id`, `intent`, `order_id`, `eta_minutes`, `text`. The lines are invented Hinglish in Latin script, the way Prisma transliterate returns them. There are no 8-digit runs, no real names, and no real phone numbers.

The stacked gate/phone case lives in the gold set (`g01`). The tuning holdout keeps a different contact-failure line that also mentions a locked gate (`h04`), plus negatives, code-mixing, and number words. The blind set uses new scenarios and phrasing, not close paraphrases of either earlier file.

Himanshu's `benchmark/data/utterances.jsonl` is a second untouched reference set. The eval script can score it, but it is not this split and must not be edited from this tree.
