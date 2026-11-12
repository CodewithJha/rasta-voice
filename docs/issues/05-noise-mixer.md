# 05 — Procedural noise mixer

- **Labels:** `area:benchmark`, `day:2`, `audio`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 2 (13–14 Nov 2026)
- **Depends on:** issue 03 (clean wavs and `clean_manifest.jsonl`).

## Description

Build the messy part of the award. Mix each clean clip with synthetic noise at several signal-to-noise ratios. Do not download traffic recordings. A downloaded clip is someone else's audio and it is not reproducible. Generate everything from `random.Random(seed)` and `math`.

Noise kinds, each a function of `(n_samples, rng) -> list[float]` in roughly `-1..1`:

| Kind | What to generate |
| --- | --- |
| `traffic` | White noise, then a short moving average so it rumbles |
| `horn` | Two sine bursts (around 400 Hz and 550 Hz) with silence between them |
| `wind` | Noise multiplied by a slow sine so the level breathes |
| `crowd` | Four detuned narrow noises summed (band-limit by averaging different window sizes) |
| `crosstalk` | A second clean clip, delayed by 200–400 ms, scaled to sit under the rider. If there is no second clip, use a low tone and say so in the manifest. |

SNR in dB, power ratio on the float mix before int16 clipping:

```text
noise_gain = signal_rms / (10 ** (snr_db / 20) * noise_rms)
mixed = signal + noise_gain * noise
```

Guard `noise_rms == 0`. Clip to int16. SNRs to emit: `20`, `10`, `0`, plus the untouched clean file copied through as `snr: null` and `noise: "clean"`.

Seed formula: `seed = int(id_number) * 1000 + snr_index * 10 + noise_index` so a row always rebuilds the same mix.

Stdlib only: `wave`, `array`, `random`, `math`. No numpy, no scipy, no ffmpeg.

## Files to touch

- `benchmark/rasta_bench/mix.py` (new) — `python -m rasta_bench.mix`
- `benchmark/tests/test_mix.py` (new)
- `benchmark/data/mix_manifest.jsonl` (generated; commit it)

## Do not touch

`backend/`, `frontend/`, `gnani_client/`. Do not edit `score.py` unless a test forces a bugfix.

## Input / output contract

Input: `benchmark/data/clean_manifest.jsonl` and the wavs it points at.

Output line:

```json
{
  "id": "u01",
  "noise": "horn",
  "snr_db": 0,
  "path": "benchmark/data/audio/mixed/u01__horn__0.wav",
  "reference": "<same reference as the clean manifest>",
  "sample_rate": 16000,
  "seed": 1000
}
```

Paths under `benchmark/data/audio/` stay gitignored. The manifest is committed. A full cartesian product of 40 lines × 5 noises × 3 SNRs is fine (about 600 short files, local only). The committed manifest lists every mix. Tests do not need all 600; they call the mix function on a tone.

## Acceptance criteria

- [ ] A unit test builds a sine, mixes it with a known noise at 0 dB, and checks the noise RMS and the signal RMS land within 20% of each other after gain.
- [ ] The same seed reproduces the same bytes.
- [ ] Output wav is mono 16-bit, same sample rate as the input, duration within 1% of the input.
- [ ] `noise: "clean"` rows have identical bytes to the source.
- [ ] No network, no new dependency. `pytest benchmark/tests/test_mix.py` passes.
- [ ] `python -m rasta_bench.mix` reads the clean manifest and writes the mixed manifest.

## How to test

```bash
pytest benchmark/tests/test_mix.py -q
python -m rasta_bench.mix
python -c "import json; print(sum(1 for _ in open('benchmark/data/mix_manifest.jsonl')))"
```

