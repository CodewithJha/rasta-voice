"""Invalid evaluation options never consume credits or replace evidence."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "eval_intent.py"
spec = importlib.util.spec_from_file_location("eval_intent_cli", SCRIPT)
assert spec is not None and spec.loader is not None
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


@pytest.fixture
def forbid_scoring(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid options must fail before scoring any split")

    monkeypatch.setattr(cli, "_run", unexpected)
    monkeypatch.setattr(cli, "evaluate_rows", unexpected)


@pytest.mark.parametrize("provider", ["rules", "gemini", "groq"])
def test_target_without_blind_is_rejected_before_scoring(provider, forbid_scoring):
    with pytest.raises(SystemExit) as error:
        cli.main(["--provider", provider, "--sets", "gold", "--enforce-target"])
    assert error.value.code == 2


@pytest.mark.parametrize("provider", ["gemini", "groq"])
def test_missing_key_cannot_overwrite_live_evidence(
    provider, forbid_scoring, monkeypatch, tmp_path,
):
    from rasta.settings import clear_settings_cache

    # Explicit empty environment takes precedence over a private local .env.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GROQ_API_KEY", "")
    clear_settings_cache()
    path = tmp_path / "existing.json"
    path.write_text("previous measured evidence\n", encoding="utf-8")
    try:
        with pytest.raises(SystemExit) as error:
            cli.main(["--provider", provider, "--sets", "blind", "--write-evidence", str(path)])
        assert error.value.code == 2
        assert path.read_text() == "previous measured evidence\n"
    finally:
        clear_settings_cache()


def test_corpus_only_live_provider_is_rejected_before_scoring(forbid_scoring):
    with pytest.raises(SystemExit) as error:
        cli.main(["--provider", "gemini", "--sets", "corpus"])
    assert error.value.code == 2


def test_unknown_provider_is_rejected_before_scoring(forbid_scoring):
    with pytest.raises(SystemExit) as error:
        cli.main(["--provider", "unknown"])
    assert error.value.code == 2


def test_valid_rules_evidence_is_still_reproducible(tmp_path):
    import json

    path = tmp_path / "rules.json"
    assert cli.main(["--sets", "blind", "--write-evidence", str(path)]) == 0
    payload = json.loads(path.read_text())
    assert payload["provider"] == payload["model"] == "rules"
    assert payload["n"] == 36
    assert payload["intent_correct"] / payload["n"] >= 0.8
    assert payload["llm_attempts"] == 0
    assert all(row["source"] == "rules" for row in payload["rows"])
