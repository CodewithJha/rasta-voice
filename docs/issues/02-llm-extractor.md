# 02 — Free-tier LLM extractor and intent eval

- **Labels:** `area:app`, `day:1`, `llm`
- **Owner:** Member B: Priyanshu Jha (@CodewithJha), app, realtime & UI
- **Target day:** Day 1 (12–13 Nov 2026)
- **Depends on:** skeleton merged. Does not wait on issue 01. Keep the rule extractor as the fallback and as the CI path.

## Description

Replace the "not implemented" branch in `extract_event` with a real call to a free LLM, then check it against a gold file.

`LLM_PROVIDER=rules` (the default) stays the keyword extractor in `backend/rasta/extract.py`. It is a real extractor, not a stand-in: it is the fallback whenever the LLM key is missing or the free tier fails, and it is what CI runs. Prisma transcripts arrive transliterated (Latin script, numbers as words), so prompt and gold rows should look like that.

`LLM_PROVIDER=groq` calls Groq's OpenAI-compatible chat completions endpoint with `GROQ_API_KEY`. `LLM_PROVIDER=gemini` calls the Gemini generateContent endpoint with `GEMINI_API_KEY`. Use `httpx`, which is already installed. Do not add an SDK. Look up the current free model id on the day you implement it (Groq and Gemini retire ids). Put the id in one constant at the top of `backend/rasta/llm.py` with a comment of the date you checked.

The prompt:

- System text says the rider speaks Hinglish, possibly with horns in the transcript, and the model must return one JSON object and nothing else.
- The object matches `RiderEvent`. Intent is one of the six enum values. `order_id` is a short token or null. Never copy an 8-digit number into `order_id`.
- Include two shot examples: the gate/phone line, and the missing-item line. No real personal data.
- Temperature 0.

Parse the JSON. Validate it with `RiderEvent`. On timeout, non-200, or invalid JSON, fall back to the rules and keep going. Do not let a flaky free tier 500 the rider. Do not log the API key. Do not put the key in the repo.

Gold set: `backend/tests/fixtures/intent_gold.jsonl`, at least 20 lines, same fields as issue 01's corpus (you may write your own; do not block on Himanshu's (Member A) file). A test runs `extract_event(text, provider="rules")` on the gold rows and reports accuracy, targeting at least 0.8 on an independent, locked holdout. Do not change gold labels or cherry-pick phrases to make rules pass. Include the stacked "gate band / nahi utha" case and adversarial distractors. A failed target is a genuine failure to fix or report, not a reason to rewrite the evaluation set.

A second test calls the live provider only when the matching key is in the environment. Otherwise it skips. Do not record live transcripts that contain anything but your gold text.

## Files to touch

- `backend/rasta/llm.py` (new)
- `backend/rasta/extract.py` (the provider branch only; do not delete `_by_rules`)
- `backend/tests/fixtures/intent_gold.jsonl` (new)
- `backend/tests/test_llm.py` (new)

## Do not touch

`frontend/`, `benchmark/`, `gnani_client/`, `shared/rider_event.schema.json`, `rasta/schema.py`. The function `extract_event(transcript, provider=None) -> RiderEvent` stays importable as it is today.

## Input / output contract

Input: transcript string, optional provider name.

Output: a `RiderEvent` that `model_dump(mode="json")` accepts against the shared schema. `confidence` from the LLM may be the model's own number in `[0, 1]`. The rule fallback keeps `0.5` / `0.0`.

Live request shape (Groq):

```json
{
  "model": "<free model id>",
  "temperature": 0,
  "messages": [
    {"role": "system", "content": "<prompt>"},
    {"role": "user", "content": "<transcript>"}
  ]
}
```

POST `https://api.groq.com/openai/v1/chat/completions` with `Authorization: Bearer $GROQ_API_KEY`.

Gemini: POST to the free `generateContent` method. Read the current URL from Google's docs when you implement it. Response text is parsed the same way.

## Acceptance criteria

- [ ] `LLM_PROVIDER=rules` behaviour for the existing `test_extract.py` cases is unchanged.
- [ ] `LLM_PROVIDER=groq` with no key raises a clear error from the LLM helper, and `extract_event` catches it and returns the rule event.
- [ ] Gold file has at least 20 rows and no 8-digit numbers.
- [ ] Rules accuracy on that file is at least 0.8.
- [ ] Unit tests for the Groq/Gemini request shape swap the HTTP transport inside the test (`httpx.MockTransport`), not via a flag in `llm.py`.
- [ ] Live test is skipped in CI (no key in the workflow).
- [ ] `pytest` and `ruff check backend` pass.

## How to test

```bash
pytest backend/tests/test_extract.py backend/tests/test_llm.py -q
LLM_PROVIDER=groq GROQ_API_KEY=... pytest backend/tests/test_llm.py -q -k live
```

<!-- rasta-voice-audit-2026-11-12 -->

### Independent evaluation acceptance

- [ ] Split examples into development and an independent holdout before tuning any rules or prompt; at least six varied held-out utterances, preferably not near-paraphrases of the training examples.
- [ ] Include negative/distractor cases, code-mixing, number words, and non-matching `other` utterances; each gold intent is assigned before checking model output.
- [ ] Report per-intent accuracy/confusion, rule-only accuracy, and live LLM accuracy when available; do not mislabel a rule fallback as an LLM success.
- [ ] Document the frozen holdout and any failures honestly. Never lower the threshold by changing gold labels after seeing predictions.


<!-- rasta-voice-hardening-2026-11-12 -->

### LLM timeout and extractor source

The free tier can hang. Do not let that block ingest.

- Time out the Groq or Gemini HTTP call after 4 seconds by default. Make the limit configurable with `LLM_TIMEOUT_SECONDS` (a positive float). Pass it as `timeout=` to `httpx`, not a background thread you then ignore.
- On timeout, connection error, non-200, or invalid JSON, fall back to `_by_rules` and keep going. The rider still gets an event. Log the fallback reason without the key or the raw model text if it might contain secrets.
- `RiderEvent` stays frozen: `shared/rider_event.schema.json` has `additionalProperties: false`, and `backend/rasta/schema.py` uses `extra="forbid"`. Do not add `source` (or any new field) to the schema, `schema.py`, or `frontend/src/types.ts`.
- Put the extractor source on the ingest envelope instead, next to `transcript`, `stt`, and `event`:

```json
{
  "transcript": "...",
  "stt": {},
  "event": { "...RiderEvent fields only..." },
  "extractor_source": "llm"
}
```

`extractor_source` is `"llm"` when the validated event came from the free-tier call, and `"rules"` when the rules path ran (default provider, missing key, or any fallback). Issue 04's store should persist this field if it is present; do not drop it on `append`.

- `extract_event(...)` keeps returning `RiderEvent`. If you need the source inside the backend, return it from a helper (`extract_event_with_source`) or attach it on the dict in `pipeline.ingest`. Do not change the public signature to return a tuple that breaks `extract_event(transcript) -> RiderEvent`.
- A unit test in `test_llm.py` forces the HTTP transport to stall past the timeout (or raises `httpx.TimeoutException`) and asserts the rule event is returned and the envelope (or helper) reports `extractor_source: "rules"`. Swap the transport inside the test; no app flag.

- [ ] Default timeout is 4 seconds and `LLM_TIMEOUT_SECONDS` overrides it.
- [ ] A hanging or timed-out LLM call falls back to rules; ingest does not 500.
- [ ] `extractor_source` is `llm` or `rules` on the API envelope, not inside `event`.
- [ ] `shared/rider_event.schema.json`, `backend/rasta/schema.py`, and `frontend/src/types.ts` are unchanged.
- [ ] The timeout-path test exists and passes without a live key.

<!-- rasta-voice-production-2026-11-12 -->

### Production: bounded LLM calls

Issue 29 owns retries, the shared client, and the breaker. This issue still has to be a safe caller:

- [ ] The 4 s timeout (or `LLM_TIMEOUT_SECONDS`) is applied on the shared client once 29 lands, not on a one-off `httpx.Client` that 29 then cannot close.
- [ ] Do not retry the LLM more than once, and never retry after a 401/403. A second failure falls back to rules and sets `extractor_source` to `rules`.
- [ ] Open-breaker on the LLM (issue 29) is a rules fallback, not a 500 and not a hung ingest.
- [ ] Prompts and model text are not written to logs. Issue 21's default stays "no full transcript".
- [ ] A test covers "LLM times out once, rules succeed, envelope source is `rules`".

## Implementation notes (12 Nov 2026)

The extractor infrastructure and evaluation harness landed in the Member B
tree: typed settings in `backend/rasta/settings.py`, providers in
`backend/rasta/llm.py` and `backend/rasta/extractors/`, the existing
`_by_rules` fallback, gold, tuning, and blind holdout fixtures, and
`scripts/eval_intent.py`. Frozen contracts were not touched. This does
not close the issue. The 0.8 accuracy acceptance on the independent
holdout remains open.

The original 24-line holdout was used to guide rule expansion, so it is
kept as a tuning/regression set. The independent test is
`intent_blind_holdout.jsonl` (36 lines, frozen in `440bcda` before it
was scored). Rules accuracy there is 8/36 = 0.222 after the
channel-bound contact fix (earlier official runs were 6/36). The 6/36
figure stays as a regression floor, distinct from the 0.8 target. The
measured numbers are in [docs/EXTRACTOR.md](../EXTRACTOR.md).
