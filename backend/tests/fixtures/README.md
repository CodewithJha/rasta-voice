# Intent gold and holdout

These files were frozen on 12 Nov 2026. Every label was assigned before any
rule or prompt was tuned for this issue. Do not change a label after seeing
a prediction, and do not drop a row to raise a score.

| File | Split | Rows | Role |
| --- | --- | --- | --- |
| `intent_gold.jsonl` | development | 30, 5 per intent | May be inspected while improving generalisable rules or the prompt |
| `intent_holdout.jsonl` | locked holdout | 24, 4 per intent | Independent of the gold phrasing. The 0.8 accuracy target applies here |

Fields match the issue 01 corpus: `id`, `intent`, `order_id`, `eta_minutes`, `text`. The lines are invented Hinglish in Latin script, the way Prisma transliterate returns them. There are no 8-digit runs, no real names, and no real phone numbers.

The stacked gate/phone case lives in the gold set (`g01`). The holdout has a different contact-failure line that also mentions a locked gate (`h04`), plus negatives, code-mixing, number words, and `other` utterances that should not match a dispatch intent.

Himanshu's `benchmark/data/utterances.jsonl` is a separate reference set. The eval script can score it, but it is not this split and must not be edited from this tree.
