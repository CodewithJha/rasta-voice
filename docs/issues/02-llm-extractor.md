# 02 — Free-tier LLM extractor and intent eval

- **Labels:** `area:app`, `day:1`, `llm`
- **Owner:** Member B: app & realtime
- **Target day:** Day 1 (12–13 Nov 2026)
- **Depends on:** skeleton merged. Does not wait on issue 01. Keep the rule extractor as the fallback and as the CI path.

## Description

Replace the "not implemented" branch in `extract_event` with a real call to a free LLM, then check it against a gold file.

`LLM_PROVIDER=mock` stays the rule table in `backend/rasta/extract.py`. That path is what CI runs.

`LLM_PROVIDER=groq` calls Groq's OpenAI-compatible chat completions endpoint with `GROQ_API_KEY`. `LLM_PROVIDER=gemini` calls the Gemini generateContent endpoint with `GEMINI_API_KEY`. Use `httpx`, which is already installed. Do not add an SDK. Look up the current free model id on the day you implement it (Groq and Gemini retire ids). Put the id in one constant at the top of `backend/rasta/llm.py` with a comment of the date you checked.

The prompt:

- System text says the rider speaks Hinglish, possibly with horns in the transcript, and the model must return one JSON object and nothing else.
- The object matches `RiderEvent`. Intent is one of the six enum values. `order_id` is a short token or null. Never copy an 8-digit number into `order_id`.
- Include two shot examples: the gate/phone line, and the missing-item line. No real personal data.
- Temperature 0.

Parse the JSON. Validate it with `RiderEvent`. On timeout, non-200, or invalid JSON, fall back to the rules and keep going. Do not let a flaky free tier 500 the rider. Do not log the API key. Do not put the key in the repo.

Gold set: `backend/tests/fixtures/intent_gold.jsonl`, at least 20 lines, same fields as issue 01's corpus (you may write your own; do not block on Member A's file). A test runs `extract_event(text, provider="mock")` on every row and asserts intent accuracy of at least 0.8. That locks the rules against the gold you just wrote, so write gold the rules can pass, including the stacked "gate band / nahi utha" case.

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

- [ ] `LLM_PROVIDER=mock` behaviour for the existing `test_extract.py` cases is unchanged.
- [ ] `LLM_PROVIDER=groq` with no key raises a clear error from the LLM helper, and `extract_event` catches it and returns the rule event.
- [ ] Gold file has at least 20 rows and no 8-digit numbers.
- [ ] Mock accuracy on that file is at least 0.8.
- [ ] Live test is skipped in CI (no key in the workflow).
- [ ] `pytest` and `ruff check backend` pass.

## How to test

```bash
pytest backend/tests/test_extract.py backend/tests/test_llm.py -q
LLM_PROVIDER=groq GROQ_API_KEY=... pytest backend/tests/test_llm.py -q -k live
```
