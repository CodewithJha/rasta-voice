# Extractor and intent eval

Issue 02 adds a free-tier LLM path in front of the keyword rules. The
frozen `RiderEvent` is unchanged. `extractor_source` and `fallback_reason`
live on the ingest envelope, not inside `event`.

## Headline result

Rules intent accuracy on the **blind holdout** is **8/36 = 0.222** after
the channel-bound contact-failure fix. That is still below the issue's
0.8 target. This pull request delivers the extractor infrastructure and
the evaluation harness; it does not close issue 2. The 0.8 acceptance
bar remains open.

Two checks are kept distinct, with constants in
`backend/rasta/intent_eval.py`:

- A regression floor `BLIND_RULES_BASELINE = 6/36`, asserted as a
  normal test. This floor is not raised when a later review fix moves
  the score, and it is not raised by retuning or relabelling.
- An acceptance check against `HOLDOUT_ACCURACY_TARGET = 0.8`, marked
  `pytest.mark.xfail(strict=True)`. It is an expected failure today and
  becomes a hard error (XPASS) when the target is met, so the marker
  has to be removed.

`python scripts/eval_intent.py` always prints `TARGET MET` or
`TARGET NOT MET` for the blind rules score and exits 0. Pass
`--enforce-target` to exit 1 when the target is unmet. CI does not pass
that flag until the issue 2 accuracy work lands. Do not treat the 24/24
tuning-holdout score as an independent result.

## Providers

`LLM_PROVIDER` selects the first hop:

- `rules` (default, and what CI runs) — the keyword extractor in
  `backend/rasta/extract.py`.
- `groq` — OpenAI-compatible `POST {GROQ_BASE_URL}/chat/completions` with
  `GROQ_API_KEY`. Default model `openai/gpt-oss-20b`, checked 12 Nov 2026
  against Groq's deprecations (`llama-3.1-8b-instant` left the free and
  developer tiers on 16 Aug 2026).
- `gemini` — `POST {GEMINI_BASE_URL}/models/{model}:generateContent` with
  the key in the `x-goog-api-key` header. Default model
  `gemini-3.5-flash-lite`, checked 12 Nov 2026 against Google's Gemini
  docs (recommended Flash-Lite for new work).

There is no vendor SDK and no mock mode in application code. Tests swap
`httpx.MockTransport`. The HTTP client is process-wide, created with
`timeout=LLM_TIMEOUT_SECONDS` (default 4). Issue 29 will take that client
over; this issue already closes it in the FastAPI lifespan.

On a missing key, timeout, connection error, 401/403, a second 429/5xx
(one retry, backoff, never after 401/403), invalid JSON, or a JSON object
that fails `RiderEvent` validation, the call falls back to rules and the
envelope records `extractor_source: "rules"` plus a short
`fallback_reason`. Logs include the reason only: no transcript, no prompt,
no model text, no key. An open circuit breaker (hook for issue 29) is the
same fallback, with reason `circuit_open`.

## Evaluation splits

| Split | File | Rows | Role |
| --- | --- | --- | --- |
| Development | `intent_gold.jsonl` | 30, 5 per intent | May be inspected while improving generalisable rules |
| Tuning holdout | `intent_tuning_holdout.jsonl` | 24, 4 per intent | Seen during rule expansion. Preserved for regression, not independent |
| Blind holdout | `intent_blind_holdout.jsonl` | 36, 6 per intent | Independent test. Labels were assigned and committed before scoring |
| Reference | `benchmark/data/utterances.jsonl` | 48, 8 per intent | Himanshu's corpus. Scored, not used for tuning, not edited |

The 24-line file was first written as an independent holdout. After a
7/24 first pass, generalisable Hinglish patterns were added and the same
file then scored 24/24. That makes it a **tuning holdout**: it was seen
during rule expansion, so it is no longer an independent test. The cases
and labels were not changed, and they stay in the tree as a regression
set. A new 36-line blind holdout was written and committed in
`440bcda` before any extractor was run on those lines.

A first rules scoring of the blind set was run at that point, **before**
later review fixes to the contact rule. Those fixes came from the
review (false escalations on answered calls), not from inspecting the
blind misses as a tuning list. After each extractor freeze the blind
set was scored once as a regression check. The first two official rules
runs were **6/36 = 0.167**. After the channel-bound contact fix
(`a97476c`) a third rules run was **8/36 = 0.222**. The two new hits
were `b05` ("uthata nahi", the same verb family as "nahi utha" /
"uthaya nahi") and `b06` ("number continuously busy", a channel-bound
busy phrase). They were not added by targeting those lines. The 0.8
target is still unmet. Those numbers are left as measured.

## Measured rules accuracy (intent only, 12 Nov 2026)

| Split | Score |
| --- | --- |
| Development gold | 30/30 = 1.000 |
| Tuning holdout (after expansion; not independent) | 24/24 = 1.000 (was 7/24 = 0.292 before expansion) |
| Blind holdout, first run (before `be41004`) | 6/36 = 0.167 |
| Blind holdout, second run (after `be41004`) | 6/36 = 0.167 |
| Blind holdout, third run (after `a97476c`, official) | 8/36 = 0.222 |
| Benchmark corpus (reference) | 41/48 = 0.854 (was 40/48 = 0.833 before expansion) |

Blind per-intent accuracy, third run: `customer_unreachable` 2/6,
`address_issue` 0/6, `item_missing` 0/6, `delay` 2/6, `accident_sos` 0/6,
`other` 4/6. The first two runs were the same except
`customer_unreachable` 0/6. Order id exact-match is 36/36. ETA exact-match is 35/36;
the one miss is `b31`, where "do minute" in an `other` line is parsed as
an ETA of 2. Confusion is almost all true-intent rows falling through to
`other`, plus `b30` (`accident_sos` predicted `delay` because of
"traffic"), `b35` (`other` predicted `accident_sos` because a safety
video mentioned "accident"), and `b36` (`other` predicted `delay`).

The remaining corpus misses are almost all Devanagari lines (`u07`,
`u08`, `u16`, `u24`, `u32`, `u40`). Prisma is asked for
`format=transliterate`, so the rules stay Latin-script. `u14` is a
subtler address paraphrase that still falls through.

## Live LLM measurement (Gemini, 12 Nov 2026)

A Groq key was not present. `GEMINI_API_KEY` was set; the default model
was `gemini-3.5-flash-lite`. Thirty-six calls were made on the blind
set, twice:

1. **Before** `be41004` (preliminary; extractor not yet in its final
   form). 35/36 calls hit the 4 s timeout and fell back to rules. One
   call returned a validated LLM event (`b14`, `item_missing`, correct,
   3974 ms). End-to-end accuracy, counting fallbacks as rules and not as
   LLM successes, was 7/36 = 0.194. LLM-validated accuracy was 1/1.
   Latency over all 36 calls: mean 4046 ms, p95 4064 ms (dominated by
   the timeout). LLM-only latency: 3974 ms.
2. **After** `be41004` (official, extractor frozen; same 4 s timeout).
   23/36 calls returned a validated LLM event. 10/36 timed out and
   3/36 returned HTTP 429 after the one allowed retry, all falling back
   to rules. End-to-end accuracy, counting fallbacks as rules and not as
   LLM successes, was 23/36 = 0.639. LLM-validated accuracy was 21/23 =
   0.913; the two LLM misses were `b21` (`delay` predicted
   `address_issue`) and `b32` (`other` predicted `delay`). Latency over
   all 36 calls: mean 2018 ms, p50 1177 ms, p95 4071 ms, min 541 ms,
   max 5277 ms. LLM-only latency: mean 1181 ms, p50 1036 ms, p95 2388
   ms. This second run is not an improvement from the receive-precision
   fix (the rules score was unchanged). It is a different service-latency
   outcome under the same 4 s budget, so both runs are reported. The
   production timeout was not raised to improve the score. End-to-end
   0.639 is still below the 0.8 issue target.

A rules fallback is never counted as an LLM success. CI has no LLM key;
`pytest -k live` skips.

```bash
pytest backend/tests/test_extract.py backend/tests/test_llm.py backend/tests/test_intent_eval.py -q
python scripts/eval_intent.py
python scripts/eval_intent.py --enforce-target  # exits 1 until the 0.8 target is met
```
