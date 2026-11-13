"""Batch evidence comes from HTTP; only these tests replace the transport."""

import io
import json
import re
import wave

import httpx
import pytest

from gnani_client.batch import PrismaBatch
from rasta_bench import run
from rasta_bench.score import wer


@pytest.fixture
def grid(tmp_path):
    rows = []
    references = ("order eighteen mein item missing", "customer phone nahi utha raha")
    for i, reference in enumerate(references):
        blob = io.BytesIO()
        with wave.open(blob, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(8000)
            wav.writeframes(bytes([i, 0]) * 160)
        path = tmp_path / f"u0{i + 1}__horn__0.wav"
        path.write_bytes(blob.getvalue())
        rows.append({"id": f"u0{i + 1}", "noise": "horn", "snr_db": 0,
                     "path": path.name, "reference": reference, "duration_s": 0.02,
                     "intent": "item_missing" if i == 0 else "customer_unreachable",
                     "sha256": run.digest(blob.getvalue())})
    return tmp_path, rows, tmp_path / "results"


@pytest.fixture
def upstream():
    calls = []
    jobs = {}
    started = set()
    transcripts = ["order 18 mein item missing", "customer phone nahi utha raha"]
    behavior = {"expired": False, "status": "COMPLETED", "create_error": None,
                "download_failed_once": False, "partial": False, "has_more": False}

    def handler(request):
        calls.append(request)
        path = request.url.path
        if request.method == "POST" and path.endswith("/jobs"):
            if behavior["create_error"]:
                return httpx.Response(behavior["create_error"], json={"message": "secret-body"})
            names = re.findall(rb'filename="([^"]+)"', request.content)
            identifier = f"job-{len(jobs)}"
            jobs[identifier] = [name.decode() for name in names]
            return httpx.Response(201, json={"job_id": identifier})
        if path.endswith("/start"):
            started.add(path.split("/")[-2])
            return httpx.Response(202, json={"status": "RUNNING"})
        if path.endswith("/files"):
            job_id = path.split("/")[-2]
            data = [{"file_id": f"file-{i}", "original_path": f"uploads/{name}",
                     "status": "FAILED" if behavior["partial"] and i == 1 else "COMPLETED",
                     "transcript_url": f"https://transcripts.test/{job_id}/{i}"}
                    for i, name in enumerate(reversed(jobs[job_id]))]
            return httpx.Response(200, json={"data": data,
                                            "pagination": {"has_more": behavior["has_more"]}})
        if request.url.host == "transcripts.test":
            assert "X-API-Key-ID" not in request.headers
            if behavior["expired"] and not behavior["download_failed_once"]:
                behavior["download_failed_once"] = True
                return httpx.Response(403, text="signed-url-expired")
            # Reverse response order deliberately: matching must use original_path.
            idx = 1 - int(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={"full_transcript": transcripts[idx]})
        identifier = path.rsplit("/", 1)[-1]
        return httpx.Response(200, json={
            "status": behavior["status"] if identifier in started else "CREATED"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = PrismaBatch(key="test-key", client=http)
    return client, calls, behavior


def test_configs_are_exact():
    for key in ("v25", "v25-bias"):
        assert not {"keyterms", "format", "topic"} & run.SYSTEMS[key].keys()
        assert run.SYSTEMS[key]["language_code"] == "hi-IN"
    assert run.SYSTEMS["v25-bias"]["bias_list"] == run.HINTS
    assert run.SYSTEMS["v30-key-denoise"]["with_denoise"] is True
    assert run.SYSTEMS["v30-key"]["keyterms"] == run.HINTS
    assert run.SYSTEMS["v30"]["format"] == "codemix"


def test_batch_math_provenance_and_cache_resume(grid, upstream):
    root, rows, output = grid
    client, calls, _ = upstream
    systems = {k: run.SYSTEMS[k] for k in ("v25-bias", "v30-key-denoise")}
    plan = run.preflight(rows, systems, output, client.base)
    assert plan["distinct_files"] == 2 and plan["model_evaluations"] == 4
    run.evaluate(root, rows, systems, output, client, sleep=lambda _: None)
    result = run.summarize(rows, systems, output, client.base, plan)
    assert result["complete"]
    assert len(result["evaluations"]) == 4
    assert result["systems"][0]["wer"] == pytest.approx(
        wer(rows[0]["reference"], "order 18 mein item missing") / 2)
    assert result["systems"][0]["normalized_wer"] == 0
    assert result["systems"][0]["intent_accuracy"] == 1
    assert all(r["job_id"] and r["file_id"] for r in result["evaluations"])
    assert "Raw WER" in (output / "scores.md").read_text()
    assert "X-API-Key-ID" not in "".join(p.read_text() for p in output.rglob("*.json"))
    assert "transcripts.test" not in "".join(p.read_text() for p in output.rglob("*.json"))
    prior = len(calls)
    run.evaluate(root, rows, systems, output, client)
    assert len(calls) == prior  # no re-upload, no poll, no transcript download
    assert run.preflight(rows, systems, output, client.base)["new_evaluations_upper_bound"] == 0
    run.check_budget(run.preflight(rows, systems, output, client.base), None, None, False)


def test_config_and_audio_changes_invalidate_cache(grid, upstream):
    root, rows, output = grid
    client, calls, _ = upstream
    systems = {"one": run.SYSTEMS["v30"]}
    run.evaluate(root, rows, systems, output, client)
    changed = {"one": run.SYSTEMS["v30-key"]}
    assert run.preflight(rows, changed, output, client.base)["new_evaluations_upper_bound"] == 2
    rows[0]["sha256"] = "different-audio"
    assert run.preflight(rows, systems, output, client.base)["new_evaluations_upper_bound"] == 1
    assert len([r for r in calls if r.method == "POST" and r.url.path.endswith("/jobs")]) == 1


def test_signed_url_refresh_does_not_reupload(grid, upstream):
    root, rows, output = grid
    client, calls, behavior = upstream
    behavior["expired"] = True
    run.evaluate(root, rows, {"v30": run.SYSTEMS["v30"]}, output, client)
    assert len(list((output / "raw").glob("*.json"))) == 2
    assert sum(r.url.path.endswith("/files") for r in calls) == 2
    assert sum(r.method == "POST" and r.url.path.endswith("/jobs") for r in calls) == 1


@pytest.mark.parametrize("code", [400, 401, 402, 403, 429, 500])
def test_create_not_retried_or_reuploaded_after_error(grid, upstream, code):
    root, rows, output = grid
    client, calls, behavior = upstream
    behavior["create_error"] = code
    systems = {"v30": run.SYSTEMS["v30"]}
    with pytest.raises(Exception):
        run.evaluate(root, rows, systems, output, client)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="ambiguous create"):
        run.evaluate(root, rows, systems, output, client)
    assert len(calls) == 1
    result = run.summarize(rows, systems, output, client.base,
                           run.preflight(rows, systems, output, client.base))
    assert not result["complete"] and result["systems"][0]["wer"] is None
    assert "no comparison table" in (output / "scores.md").read_text()
    assert "secret-body" not in "".join(p.read_text() for p in output.rglob("*.json"))


def test_partial_failure_keeps_errors_and_successful_evidence(grid, upstream):
    root, rows, output = grid
    client, calls, behavior = upstream
    behavior["status"] = "PARTIAL_FAILURE"
    behavior["partial"] = True
    systems = {"v30": run.SYSTEMS["v30"]}
    run.evaluate(root, rows, systems, output, client)
    plan = run.preflight(rows, systems, output, client.base)
    result = run.summarize(rows, systems, output, client.base, plan)
    assert not result["complete"] and len(result["missing"]) == 1
    assert len(list((output / "raw").glob("*.json"))) == 1
    assert "file_FAILED" in next((output / "jobs").glob("*.json")).read_text()
    prior = len(calls)
    run.evaluate(root, rows, systems, output, client)
    assert len(calls) == prior


def test_poll_timeout_is_bounded_and_resume_never_posts_again(grid, upstream):
    root, rows, output = grid
    client, calls, behavior = upstream
    behavior["status"] = "RUNNING"
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    systems = {"v30": run.SYSTEMS["v30"]}
    run.evaluate(root, rows, systems, output, client, clock=lambda: now[0], sleep=sleep, timeout=25)
    assert sleeps == [10, 10, 5]
    assert "job_timeout" in next((output / "jobs").glob("*.json")).read_text()
    behavior["status"] = "COMPLETED"
    posts = sum(r.method == "POST" for r in calls)
    run.evaluate(root, rows, systems, output, client)
    assert sum(r.method == "POST" for r in calls) == posts
    assert len(list((output / "raw").glob("*.json"))) == 2


def test_unexpected_pagination_is_not_silently_scored(grid, upstream):
    root, rows, output = grid
    client, _, behavior = upstream
    behavior["has_more"] = True
    run.evaluate(root, rows, {"v30": run.SYSTEMS["v30"]}, output, client)
    assert not list((output / "raw").glob("*.json"))
    assert "ValueError" in next((output / "jobs").glob("*.json")).read_text()


@pytest.mark.parametrize("text, expected", [
    ("  ORDER—EIGHTEEN! ", "order 18"), ("bees minute", "20 minute"),
    ("twenty-one", "21"), ("one hundred eighty", "180"),
    ("order १८", "order 18"), ("कस्टमर", "कस्टमर"),
])
def test_normalization_preserves_script_and_maps_numbers(text, expected):
    assert run.normalize(text) == expected


def test_budget_guards_do_not_assume_provider_credit_units():
    plan = {"distinct_files": 80, "new_model_audio_minutes_upper_bound": 27.733}
    with pytest.raises(ValueError, match="dashboard"):
        run.check_budget(plan, None, None, False)
    with pytest.raises(ValueError, match="hard supplied budget"):
        run.check_budget(plan, 10, 2, True)
    run.check_budget(plan, 60, 2, False)
    for count, minutes in [(201, 1), (80, 31)]:
        with pytest.raises(ValueError, match="i-mean-it"):
            run.check_budget({"distinct_files": count,
                              "new_model_audio_minutes_upper_bound": minutes}, 500, 1, False)


def test_missing_key_is_loud_and_no_results_written(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    assert run.main(["--output", str(tmp_path)]) == 1
    assert "GNANI_API_KEY is not set" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_cache_tampering_is_rejected_without_upload(grid, upstream):
    root, rows, output = grid
    client, calls, _ = upstream
    systems = {"v30": run.SYSTEMS["v30"]}
    run.evaluate(root, rows, systems, output, client)
    path = next((output / "raw").glob("*.json"))
    value = json.loads(path.read_text())
    value["full_transcript"] = "unverified edit"
    path.write_text(json.dumps(value))
    prior = len(calls)
    with pytest.raises(ValueError, match="invalid evidence"):
        run.preflight(rows, systems, output, client.base)
    assert len(calls) == prior


def test_output_lock_prevents_a_second_spending_process(tmp_path):
    with run.output_lock(tmp_path):
        with pytest.raises(ValueError, match="another benchmark process"):
            with run.output_lock(tmp_path):
                pytest.fail("second process entered the critical section")
    with run.output_lock(tmp_path):
        pass


def test_manifest_hash_and_grid_completeness_are_checked(grid):
    root, rows, _ = grid
    data = root / "benchmark/data"
    audio = data / "audio/phone"
    audio.mkdir(parents=True)
    corpus = []
    manifest = []
    for row in rows:
        corpus.append({"id": row["id"], "text": row["reference"], "intent": row["intent"],
                       "order_id": None, "eta_minutes": None})
        for noise in run.NOISES:
            for snr in (0, 10):
                path = audio / f"{row['id']}__{noise}__{snr}.wav"
                path.write_bytes((root / row["path"]).read_bytes())
                manifest.append(row | {"noise": noise, "snr_db": snr,
                                       "path": str(path.relative_to(root))})
    (data / "utterances.jsonl").write_text("".join(json.dumps(r) + "\n" for r in corpus))
    file = data / "phone_manifest.jsonl"
    file.write_text("".join(json.dumps(r) + "\n" for r in manifest))
    assert len(run.load_grid(root, 2)) == 20
    manifest[0]["sha256"] = "broken"
    file.write_text("".join(json.dumps(r) + "\n" for r in manifest))
    with pytest.raises(ValueError, match="audio hash"):
        run.load_grid(root, 2)
    file.write_text("")
    with pytest.raises(ValueError, match="complete requested grid"):
        run.load_grid(root, 2)
