# Rider and dispatch workflow

The original screen put microphone, upload, two sample modes, noise controls,
reply playback, and a locked dispatcher together. The rider now starts with
one primary action: record an update. Samples remain an explicit secondary
action; upload and audio-test controls are behind a labelled disclosure.

## Screens

- `/#rider` (default): record, check the actual transcript and extracted fields,
  then request and play a spoken confirmation. Successful ingestion already
  stores the event; there is no invented extra Send or review-before-send step.
- `/#dispatch`: unlock using the existing protected session, then acknowledge
  and resolve real updates. Desk polling starts only when this view is opened
  and pauses when the view is hidden. Navigation waits for an active rider
  operation to finish so a microphone cannot be hidden while recording.

A read-only readiness request checks the configured key and local allowance
before speech controls become available. Known missing-key/exhausted states
explain what the operator must fix and expose Check again. An unavailable
readiness endpoint is reported as unknown, never as a successful speech test.
The server remains authoritative for all credit, concurrency and rate limits.

## Design system

Uses the CSS/token layer of Devalok's MIT-licensed
[`@devalok/shilp-sutra` 0.60.0](https://shilp-sutra.devalok.in/), processed by
Tailwind 4's Vite plugin. This is deliberately a token integration into the
existing TypeScript app, not a React component migration. No React component
barrel or external runtime CDN is imported. Fonts are bundled locally and
remain covered by the existing same-origin CSP.

The visual system uses white surfaces, dark text, green primary controls,
consistent typography and focus states, straight borders, a three-step guide,
and responsive navigation. Informational empty states never pretend that a
recording, provider response or delivery event exists. English and Hinglish
chrome stay in the catalogue; transcripts are displayed unchanged.

## Verification

Run from `frontend`: `npm run check`, `npm run check:tests`, `npm test`,
`npm run build`, and `npm run test:e2e`. The keyless browser suite checks both
views at 1280/360/400 px, no speech requests on page load, keyboard disclosure
and retry, real missing-key 503, authenticated dispatch, CSRF and acknowledge /
resolve persistence. `RASTA_E2E_LIVE=1` remains separately opt-in; its order-18
assertion is unchanged. A keyless preview is not live voice acceptance.
