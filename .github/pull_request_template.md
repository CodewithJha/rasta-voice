## Pull request

- **Closes #**
- **Owner:** A (Himanshu / @himanshu748) or B (Priyanshu Jha / @CodewithJha)
- **Files and trees touched:**

## Frozen contracts

Does this change `shared/`, `backend/rasta/schema.py`, `frontend/src/types.ts`, `gnani_client/`, or `.github/`?

- [ ] No
- [ ] Yes — this is a contract pull request, or it follows a merged contract pull request: #

## Checks

- [ ] Tests added or updated for this change
- [ ] Local checks ran: `ruff check gnani_client backend benchmark`, `pytest`, and `npm run check` (from `frontend/`)
- [ ] No secrets in the branch (no `.env`, no API keys, no passcodes)
- [ ] Synthetic data only: no real phone numbers, call recordings, customer names, or government IDs
- [ ] Real Gnani APIs only: no mock mode, canned transcripts, or fixture scores in app code (tests may use `httpx.MockTransport` inside the test file)
- [ ] UI changes include screenshots or a short screen recording (skip if this pull request has no UI)
