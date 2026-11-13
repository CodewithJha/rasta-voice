"""Figure integrity uses test-only summaries and the committed live results."""

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from rasta_bench.chart import PROVENANCE, TITLE, main, render_svg

NS = {"s": "http://www.w3.org/2000/svg"}
ROOT = Path(__file__).resolve().parents[2]


def summary():
    return {
        "complete": True,
        "missing": [],
        "provenance": PROVENANCE,
        "primary_wer": "raw",
        "run_at": "2026-11-13T09:34:05+00:00",
        "grid": {"distinct_files": 2, "model_evaluations": 4, "systems": 2},
        "systems": [
            {
                "id": name,
                "wer": value,
                "config": {"with_denoise": denoise},
                "n": 2,
                "n_expected": 2,
                "complete": True,
            }
            for name, value, denoise in [("v30", 0.25, False), ("v30-key-denoise", 0.15, True)]
        ],
    }


def test_two_bars_title_run_date_counts_and_caveat():
    svg = render_svg(summary())
    root = ET.fromstring(svg)
    bars = root.findall(".//s:rect", NS)
    assert len(bars) == 2
    assert root.find("s:title", NS).text == TITLE
    assert [b.attrib["fill"] for b in bars] == ["#24180f", "#ffb703"]
    assert all(float(b.attrib["height"]) > 0 for b in bars)
    assert "13 Nov 2026, 15:04 IST" in svg
    assert "2 distinct clips" in svg and "4 model evaluations" in svg
    assert "not a model ranking" in svg and "0.25" in svg and "0.15" in svg


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"missing": [{}]},
        {"primary_wer": "normalized"},
        {"provenance": "fixture"},
        {"run_at": "2026-11-13"},
        {"grid": {"distinct_files": 2, "model_evaluations": 2, "systems": 2}},
    ],
)
def test_incomplete_or_mislabelled_source_is_rejected(change):
    with pytest.raises(ValueError):
        render_svg(summary() | change)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, True, None])
def test_invalid_raw_wer_is_rejected(value):
    data = summary()
    data["systems"][0]["wer"] = value
    with pytest.raises(ValueError):
        render_svg(data)


def test_xml_escaping_and_wer_over_one_are_explicit():
    data = summary()
    data["systems"][0].update(id='<system & "id">', wer=1.4)
    svg = render_svg(data)
    root = ET.fromstring(svg)
    assert root.find(".//s:rect", NS).attrib["data-system"] == '<system & "id">'
    assert "1.40 ↑" in svg and "Bar capped at 1" in svg
    assert 'y="124.00"' in svg


def test_committed_svg_and_readme_table_match_live_scores():
    results = ROOT / "benchmark/results"
    data = json.loads((results / "scores.json").read_text())
    assert (results / "wer.svg").read_text() == render_svg(data)
    svg = ET.fromstring(render_svg(data))
    assert len(svg.findall(".//s:rect", NS)) == len(data["systems"])
    readme = (
        (ROOT / "README.md")
        .read_text()
        .split("<!-- benchmark:start -->")[1]
        .split("<!-- benchmark:end -->")[0]
    )
    table = (results / "scores.md").read_text().split("| System |", 1)[1].split("\n\n", 1)[0]
    assert "| System |" + table in readme
    assert "synthetic" in readme and "benchmark/results/wer.svg" in readme
    assert "400" in readme and "80" in readme


def test_cli_refuses_bad_source_without_overwriting_output(tmp_path):
    source, out = tmp_path / "scores.json", tmp_path / "wer.svg"
    bad = copy.deepcopy(summary())
    bad["complete"] = False
    source.write_text(json.dumps(bad))
    out.write_text("previous figure")
    with pytest.raises(SystemExit) as failure:
        main(["--input", str(source), "--output", str(out)])
    assert failure.value.code == 1 and out.read_text() == "previous figure"
