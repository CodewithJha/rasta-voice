# 30 — Frontend production quality

- **Labels:** `area:app`, `day:3`, `ui`
- **Owner:** Member B: app & realtime
- **Target day:** Day 3 (14–15 Nov 2026), after 09 and 10 so you are upgrading the real screens, not the skeleton. Closes FE-01, FE-02, FE-03, FE-04, FE-05, FE-06, FE-07, PROD-08 (with 25), SEC-10 (with 27).
- **Depends on:** issues 09 and 10. Self-hosted fonts must stay as issue 27 left them. If 27 has not merged, self-host the fonts here and tell 27 to set CSP accordingly — do not leave the Google CDN in.

## Description

Make the rider chit and the dispatch slate hold up outdoors, on a slow phone, and in two languages.

Human view (FE-01): after a result, the chit shows intent, order, ETA, urgency, and the spoken reply control as typography, not only a JSON `<pre>`. Keep a collapsed "raw" block for judges who want the `request_id`.

i18n (FE-02): a small message catalogue (TypeScript modules, no paid i18n SaaS) with `en` and `hi-en` (Hinglish) strings for chrome: buttons, empty states, errors, SOS banner, passcode prompt. Default `hi-en`. A visible toggle, persisted in `localStorage` (not the passcode). `document.documentElement.lang` follows the toggle. Do not translate transcripts or model output; those stay as Prisma returned them.

Network (FE-03): every `fetch` has a 20 s abort, a retry of a safe GET (the slate poll) with backoff, and no automatic retry of credit-spending POSTs (issue 26 idempotency covers a user retry). Timeouts and offline (`navigator.onLine`, failed fetch) show a named state, not a hung "On the line…". Honour issue 09/10's 503/502/429 copy.

Errors (FE-04): `window` `error` and `unhandledrejection` handlers paint a non-blocking banner on the layout, and do not replace the whole `#app` with a blank page.

Mic (FE-05): if issue 07's Talk button is present, add a secure-context warning when `window.isSecureContext` is false, a clear "mic blocked" state, and a short hint to use the sample stream instead. Do not crash if `getUserMedia` is missing.

Lighthouse / budget (FE-06): self-hosted fonts only, `font-display: swap`, no extra JS libraries. Document a Lighthouse CI or a `lhci` run in issue 32; this issue sets a budget in `frontend/lighthouse-budget.json` (or the format 32 picks): performance ≥ 80 on desktop, a11y ≥ 90, best-practices ≥ 90, LCP under 3 s on simulated slow 4G of the built `/`. You run it once locally if 32 has not wired CI yet, and paste the scores in the PR.

Accessibility (FE-07): finish a WCAG AA pass on both columns: every control has a name, the hidden file input is still labelled, contrast 4.5:1 including phosphor on slate, visible focus (already in `styles.css`), `prefers-reduced-motion` disables the chit tilt and the SOS tone, 360 px still holds. Hit the remaining issues 09/10 hardening items rather than restyling from scratch. Do not copy a known SaaS shell; stay on the paper chit and the phosphor board.

## Files to touch

- `frontend/src/rider.ts`, `frontend/src/dispatch.ts`, `frontend/src/main.ts` (banner, lang toggle)
- `frontend/src/i18n/*.ts` (new)
- `frontend/src/rider.css`, `frontend/src/dispatch.css`, `frontend/src/styles.css`
- `frontend/index.html` (no Google Fonts)
- `frontend/lighthouse-budget.json` (new)
- `frontend/public/fonts/*` if 27 did not already add them

## Do not touch

Backend, `gnani_client/`, `benchmark/`, frozen `RiderEvent`. Do not add a UI framework or a CSS kit.

## Input / output contract

Chrome strings go through the catalogue. A missing key in `hi-en` falls back to `en` and fails a unit test once issue 32's vitest is in; until then, a small self-check script or a TypeScript exhaustiveness test is enough.

## Acceptance criteria

- [ ] After a sample ingest, the chit shows a human summary and a collapsed raw block with `request_id`.
- [ ] Locale toggle switches chrome to English and back, sets `lang`, and survives a reload. Transcripts are not rewritten.
- [ ] Abort/timeout/offline paths are visible. Credit-spending POSTs are not auto-retried.
- [ ] A thrown error in a click handler still leaves the slate on screen plus a banner.
- [ ] Secure-context and mic-blocked hints exist when the Talk button exists.
- [ ] `rg fonts.googleapis frontend` is empty. A Lighthouse (or budget) run is pasted in the PR.
- [ ] WCAG AA checks above hold at 360 px. `npm run check` passes.

## How to test

```bash
cd frontend && npm run check
# plus the Lighthouse command issue 32 documents, against npm run build
```

Resize to 360 px, toggle locale, turn the network off in devtools mid-sample, and confirm the error state. Keyboard-only through unlock (after 20), ack (after 25), and sample.
