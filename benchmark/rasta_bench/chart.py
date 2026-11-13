"""Render the committed live benchmark as SVG, without network or plotting deps."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TITLE = "Live Prisma on synthetic 8 kHz phone clips"
PROVENANCE = "live_prisma_batch_on_synthetic_simulated_telephony"
INK, SODIUM, STAMP, PAPER = "#24180f", "#ffb703", "#9b2226", "#f3e6c8"


def render_svg(scores: dict[str, Any]) -> str:
    """Plot raw per-system mean WER only for a complete live summary.

    WER can exceed one because of insertions. The requested axis stops at
    one; such bars get an explicit cap marker and keep their true value label.
    """
    if (
        scores.get("complete") is not True
        or scores.get("missing")
        or scores.get("provenance") != PROVENANCE
        or scores.get("primary_wer") != "raw"
    ):
        raise ValueError("a complete live summary with raw primary WER is required")
    try:
        stamp = datetime.fromisoformat(scores["run_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError("run_at must be an ISO timestamp with a timezone") from exc
    if stamp.tzinfo is None:
        raise ValueError("run_at must include a timezone")
    grid, systems = scores.get("grid"), scores.get("systems")
    if not isinstance(grid, dict) or not isinstance(systems, list) or not systems:
        raise ValueError("grid and non-empty systems are required")
    files, evaluations = grid.get("distinct_files"), grid.get("model_evaluations")
    if (
        type(files) is not int
        or files <= 0
        or type(evaluations) is not int
        or evaluations != files * len(systems)
        or grid.get("systems") != len(systems)
    ):
        raise ValueError("file, system and model-evaluation counts disagree")
    values: list[tuple[str, float, bool]] = []
    seen: set[str] = set()
    for row in systems:
        if not isinstance(row, dict):
            raise ValueError("each system must be an object")
        name, value, config = row.get("id"), row.get("wer"), row.get("config")
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise ValueError("system IDs must be non-empty and unique")
        if (
            row.get("complete") is not True
            or row.get("n") != files
            or row.get("n_expected") != files
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
            or not isinstance(config, dict)
        ):
            raise ValueError("each system needs complete counts and finite non-negative WER")
        seen.add(name)
        values.append((name, float(value), config.get("with_denoise") is True))

    width, height = 720, 420
    left, right, top, bottom = 62, 22, 124, 300
    worst = max(value for _, value, _ in values)
    ymax = min(1.0, (math.floor(min(worst, 1.0) * 10) + 1) / 10)
    slot = (width - left - right) / len(values)
    bar_width = min(62.0, slot * 0.55)
    run_date = stamp.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime(
        "%d %b %Y, %H:%M IST"
    )
    desc = (
        f"Raw mean word error rate. {files} distinct synthetic clips, "
        f"{evaluations} model evaluations. Script mismatch prevents a clean model ranking. "
        f"Run timestamp: {scores['run_at']}."
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{TITLE}</title>',
        f'<desc id="desc">{escape(desc)}</desc>',
        f'<path d="M0 0H{width}V{height}H0Z" fill="{PAPER}"/>',
        f'<g font-family="system-ui, sans-serif" fill="{INK}">',
        f'<text x="{left}" y="32" font-size="23" font-weight="700">{TITLE}</text>',
        f'<text x="{left}" y="56" font-size="12">Run: {run_date}</text>',
        f'<text x="{left}" y="77" font-size="12">Raw mean WER · {files} distinct clips · '
        f"{evaluations} model evaluations · sodium bar: denoise</text>",
        f'<text x="{left}" y="99" fill="{STAMP}" font-size="12" font-weight="600">'
        "Cross-script outputs: descriptive results, not a model ranking.</text>",
    ]
    for step in range(round(ymax * 10) + 1):
        tick = step / 10
        y = bottom - tick / ymax * (bottom - top)
        parts += [
            f'<path d="M{left} {y:.2f}H{width - right}" stroke="{INK}" opacity="0.15"/>',
            f'<text x="{left - 10}" y="{y + 4:.2f}" text-anchor="end" '
            f'font-size="11">{tick:.1f}</text>',
        ]
    parts.append(f'<path d="M{left} {top}V{bottom}H{width - right}" fill="none" stroke="{INK}"/>')
    capped = False
    for index, (name, value, denoise) in enumerate(values):
        center = left + slot * (index + 0.5)
        bar_height = min(value, ymax) / ymax * (bottom - top)
        y = bottom - bar_height
        mark = " ↑" if value > ymax else ""
        capped |= bool(mark)
        parts += [
            f'<rect x="{center - bar_width / 2:.2f}" y="{y:.2f}" '
            f'width="{bar_width:.2f}" height="{bar_height:.2f}" '
            f'fill="{SODIUM if denoise else INK}" data-system="{escape(name, quote=True)}">'
            f"<title>{escape(name)}: raw WER {value:.4f}</title></rect>",
            f'<text x="{center:.2f}" y="{y - 8:.2f}" text-anchor="middle" '
            f'font-size="13" font-weight="700">{value:.2f}{mark}</text>',
            f'<text x="{center:.2f}" y="322" text-anchor="middle" '
            f'font-size="11">{escape(name)}</text>',
        ]
    parts += [
        f'<text x="{left}" y="357" font-size="12">Synthetic rider speech; simulated '
        "8 kHz mu-law telephone audio, not real calls.</text>",
        f'<text x="{left}" y="378" font-size="11">Normalized metrics fold case, '
        "punctuation and number words; they do not transliterate scripts.</text>",
    ]
    if capped:
        parts.append(
            f'<text x="{left}" y="400" font-size="11">'
            '↑ Bar capped at 1; label shows actual raw WER.</text>'
        )
    return "\n".join(parts + ["</g>", "</svg>", ""])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "benchmark/results/scores.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark/results/wer.svg")
    args = parser.parse_args(argv)
    try:
        scores = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(scores, dict):
            raise ValueError("scores must be a JSON object")
        svg = render_svg(scores)
        args.output.write_text(svg, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"chart: {exc}\n")
    print(f"Wrote {args.output}; no provider calls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
