# Live Prisma on synthetic 8 kHz phone clips

Scored at: 2026-11-13T09:34:05.153014+00:00

NFKC, casefold, Unicode punctuation/symbols to spaces, collapse whitespace, decimal digits and English 0-199 / Roman Hindi 0-30 number words to digits. No translation or script transliteration. Raw metrics are preserved. Latin references and v3 codemix Hindi output may be cross-script; do not interpret those scores as a model ranking. Rules intent accuracy also reflects the extractor's script coverage.

80 distinct files; 400 expected model evaluations; 400 completed.

Credit cap is operator-supplied, not a Gnani-reported remaining balance: budget 40.0, 1.0 credits/audio-minute, estimated new-credit upper bound 24.05333333333341.

WER/CER below are raw; normalized metrics are separate columns.

| System | Raw WER | Raw CER | Normalized WER | Normalized CER | Intent accuracy | n |
| --- | --- | --- | --- | --- | --- | --- |
| v25 | 0.8429 | 0.8123 | 0.8012 | 0.8107 | 0.0000 | 80 |
| v25-bias | 0.8429 | 0.8123 | 0.8012 | 0.8107 | 0.0000 | 80 |
| v30 | 0.7461 | 0.5833 | 0.6546 | 0.5316 | 0.2250 | 80 |
| v30-key | 0.7439 | 0.5828 | 0.6546 | 0.5316 | 0.2250 | 80 |
| v30-key-denoise | 0.7292 | 0.5625 | 0.6334 | 0.5077 | 0.2000 | 80 |

| Noise | v30 raw WER | v30-key-denoise raw WER |
| --- | --- | --- |
| traffic | 0.7254 | 0.6784 |
| horn | 0.6225 | 0.6819 |
| wind | 0.7205 | 0.7420 |
| crowd | 0.7828 | 0.6970 |
| crosstalk | 0.8794 | 0.8466 |
