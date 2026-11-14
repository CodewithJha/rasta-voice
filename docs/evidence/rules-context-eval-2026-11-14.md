# Rule context correction, 14 November 2026

Refs issue 2. This change fixes false keyword escalation. **The independent
accuracy acceptance remains unmet.** No LLM success is claimed.

The rule implementation and development regressions were frozen in
`cc36618ce34ec7ac2cde1843e75b77d02329cb4c` before paired evaluation against the
unchanged fixtures. This is a local freeze commit; the JSON also records
content hashes for verification after GitHub uploads create different commit IDs.
Baseline is the extractor on main `d0b6bbc`. The locked
holdout SHA-256 is recorded in the adjacent JSON. Its text and labels were
not inspected or changed. The earlier 24-row tuning split is seen data,
not an independent result. No further rule tuning used these scores.

| Split | Before | After |
| --- | --- | --- |
| Development gold | 30/30 | 30/30 |
| Seen tuning split | 24/24 | 24/24 |
| Locked holdout | 7/36 (19.44%) | 8/36 (22.22%) |

| Holdout intent | Before | After |
| --- | --- | --- |
| customer_unreachable | 1/6 | 1/6 |
| address_issue | 0/6 | 0/6 |
| item_missing | 0/6 | 0/6 |
| delay | 2/6 | 2/6 |
| accident_sos | 0/6 | 0/6 |
| other | 4/6 | 5/6 |

The JSON includes the complete confusion matrices and secondary order/ETA
exact matches. Both runs used rules for every row and made zero LLM calls.
The 0.8 target, original regression floor and strict expected-failure marker
remain unchanged. A real Groq/Gemini evaluation requires the matching private
key. A new independent validation set is needed before any future work
claims broader generalization after tuning on known examples.

Code inspection motivated whole-word matches (`plate` must not mean `late`),
local explicit negation and removing the ambiguous `ek item` trigger. Status
negation cannot suppress a separate affirmative problem. Accident-prevention
failures such as `accident nahi rok paya` still escalate. Existing contact
ordering, all original extractor regressions and gold/tuning behavior remain.
New regression utterances are development examples, not a scored holdout.

These corrections do not make a rule extractor a safety authority, and the
poor held-out coverage must remain visible to operators and submission claims.
