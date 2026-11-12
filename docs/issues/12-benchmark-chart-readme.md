# 12 — Chart and README benchmark section

- **Labels:** `area:benchmark`, `day:3`, `docs`
- **Owner:** Member A: benchmark & audio
- **Target day:** Day 3 (14–15 Nov 2026), morning if you can, so the post can quote it.
- **Depends on:** issue 11 (`benchmark/results/scores.json`).

## Description

Turn the scores into the picture that goes in the README and the demo. No matplotlib, no plotly, no CDN chart. Write an SVG from the JSON with string templates in `benchmark/rasta_bench/chart.py`.

One grouped bar chart: mean WER by system. Y axis from 0 to a tick above the worst bar (or 1.0, whichever is smaller). Label each bar with the system id under it, rotated if needed, and the WER to two decimals on top. Title:

- If `scores.json` has `"mock": true` and there is no `scores.live.json`: `Fixture run — not a live Prisma score`.
- If `scores.live.json` exists: `Live Prisma on synthetic 8 kHz phone clips` and plot the live file.

Colours from the app, not a new palette: ink `#24180f`, sodium `#ffb703`, stamp `#9b2226`, paper `#f3e6c8`. The denoise bar can be sodium. The others ink. Background paper.

Write `benchmark/results/wer.svg`.

README: edit only between the markers already in the file:

```html
<!-- benchmark:start -->
<!-- benchmark:end -->
```

Inside, in this order:

1. One paragraph: what was mixed (the five noises), the telephony (8 kHz μ-law), the systems (v2.5 vs v3.0, hints, denoise), and the line that this is synthetic rider speech, not a real call corpus.
2. The markdown table copied from `scores.md` (or `scores.live.md` when that is the plotted file).
3. The SVG, as `![WER by system](benchmark/results/wer.svg)`.
4. A sentence that says whether the numbers are fixture or live. If they are fixture, say the live command (`GNANI_MOCK=0 python -m rasta_bench.run --limit 8`).

Do not rewrite the setup section, the architecture diagram, or the skeleton description.

## Files to touch

- `benchmark/rasta_bench/chart.py` (new)
- `benchmark/tests/test_chart.py` (new)
- `benchmark/results/wer.svg` (generated, committed)
- `README.md` between the benchmark markers only

## Do not touch

Anything outside those markers in `README.md`. `frontend/`, `backend/`, `gnani_client/`.

## Input / output contract

Input: `benchmark/results/scores.json`, or `scores.live.json` when present.

Output: an SVG file that contains one `<rect>` per system and a `<title>` (or a text node) equal to the chart title above. Width around 720, height around 420, so it reads in the README without a horizontal scroll on a laptop.

## Acceptance criteria

- [ ] Test builds a tiny scores dict with two systems and checks the SVG has two rects and the fixture title when `mock` is true.
- [ ] Test with `mock: false` checks the live title.
- [ ] The README section contains the table, the image, and the word "synthetic".
- [ ] `git diff README.md` shows changes only between the markers. Look before you commit.
- [ ] `pytest benchmark/tests/test_chart.py` passes.

## How to test

```bash
python -m rasta_bench.chart
pytest benchmark/tests/test_chart.py -q
```

Open `benchmark/results/wer.svg` in a browser. The bars should be visible, labelled, and not stacked on top of the axis labels.
