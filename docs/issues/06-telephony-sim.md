# 06 — 8 kHz telephony and codec artefacts

- **Labels:** `area:benchmark`, `day:2`, `audio`
- **Owner:** Member A: Himanshu (@himanshu748), benchmark & audio
- **Target day:** Day 2 (13–14 Nov 2026)
- **Depends on:** issue 05 (`mix_manifest.jsonl`).

## Description

Phone audio is not 16 kHz PCM. Take each mixed clip and:

1. Downsample to 8000 Hz by averaging. For a 16000 → 8000 step, each output sample is the mean of two inputs. Reject sample rates that are not a multiple of 8000 in the CLI, and cover 16000 in tests.
2. Round-trip G.711 μ-law. Implement the standard bias/exponent quantiser (ITU-T G.711). A test tone must survive, and a loud sine must not come back bit-identical — the point is the artefact.
3. Write 16-bit PCM WAV at 8000 Hz (decode μ-law back to linear so Prisma can eat a normal wav). The damage is in the samples, not in the container.

Optional, off by default: a second pass that zero-stuffs one sample in every 50, to imitate a packet nick. Flag `--dropouts`. Do not turn it on for the scored manifest unless you also add a column. The default scored set is downsample + μ-law only, so the chart has one telephony condition.

This is the audio the benchmark will send. REST and batch both accept 8 kHz wav.

Stdlib only.

## Files to touch

- `benchmark/rasta_bench/telephony.py` (new) — `mulaw_roundtrip(samples: list[int]) -> list[int]`, `to_telephony(src_wav, dest_wav)`, `python -m rasta_bench.telephony`
- `benchmark/tests/test_telephony.py` (new)
- `benchmark/data/phone_manifest.jsonl` (generated; commit it)

## Do not touch

`backend/`, `frontend/`, `gnani_client/`, the mixer. Read its manifest, don't rewrite it.

## Input / output contract

Input: `benchmark/data/mix_manifest.jsonl`.

Output line, same fields as the mix manifest plus:

```json
{
  "telephony": "mulaw8k",
  "sample_rate": 8000,
  "path": "benchmark/data/audio/phone/u01__horn__0.wav"
}
```

`reference`, `id`, `noise`, and `snr_db` are copied unchanged. Duration in seconds stays within 5% of the source (one sample of rounding is fine; a 2× error means the decimator is wrong).

## Acceptance criteria

- [ ] A 1-second 16 kHz tone becomes a 1-second 8 kHz wav (`wave.getframerate() == 8000`, frame count within 2 of 8000).
- [ ] μ-law round-trip of silence stays at 0, or within a few quanta of 0.
- [ ] μ-law round-trip of a full-scale sine is not byte-identical to the input, and the correlation stays positive (you did not scramble it into noise).
- [ ] CLI writes one phone wav per mix row and a manifest line.
- [ ] No new dependency. Tests do not need the full corpus: synthesise a wav in the test with `wave`.

## How to test

```bash
pytest benchmark/tests/test_telephony.py -q
python -m rasta_bench.telephony
python -c "import wave; w=wave.open('benchmark/data/audio/phone/u01__clean__clean.wav'); print(w.getframerate(), w.getnframes())"
```

The clean-row filename follows whatever issue 05 used for `noise: "clean"`. Match that stem. Don't invent a second naming scheme.

<!-- rasta-voice-audit-2026-11-12 -->

### Provenance and claim boundary

- [ ] All generated 8 kHz G.711-round-tripped WAVs and scores are explicitly called **simulated telephony**, not recorded cellular/telephone calls.
- [ ] README/demo only use "real telephonic recording" for genuine consented phone-channel evidence, if collected separately in the field-validation issue.

