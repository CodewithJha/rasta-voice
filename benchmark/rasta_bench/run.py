"""Resumable, live-only Prisma batch benchmark.

From the repository root (GNANI_API_KEY is required even for cached rescoring):
    python -m rasta_bench.run --limit 8 --preflight
    python -m rasta_bench.run --limit 8 --credit-budget REMAINING \
        --credits-per-minute DASHBOARD_RATE

Default grid: 8 utterances x 5 noises x 2 SNRs = 80 files, 400 evaluations.
The operator must supply the remaining programme credits and the actual STT
credits/audio-minute rate; minutes are not silently equated to provider credits.
The additional local ceiling is 30 model-audio minutes / 200 distinct files.
Over-ceiling work needs --i-mean-it; the supplied credit budget is always hard.
No spending POST is automatically retried. A start with an ambiguous outcome
is inspected with GET on resume. An ambiguous create needs operator recovery
using the dashboard job id in its checkpoint, never a second blind upload.
Only complete runs produce a comparison table. Failed runs retain raw evidence.

API references: https://docs.gnani.ai/api/STTBatch/Create_Job and the official
Gnani Python SDK's BatchJob.files (original_path identifies an uploaded file).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx

from gnani_client.batch import PrismaBatch, batch_config
from gnani_client.env import require_api_key
from gnani_client.errors import GnaniError, MissingApiKeyError
from rasta.extract import extract_event
from rasta_bench.corpus import load_utterances
from rasta_bench.mix import NOISES
from rasta_bench.score import cer, wer
from rasta_bench.wavio import atomic_write, read_pcm

ROOT = Path(__file__).resolve().parents[2]
HINTS = ["order", "gate", "item", "accident"]
TERMINAL = {"COMPLETED", "PARTIAL_FAILURE", "FAILED", "START_FAILED", "CANCELLED"}
SYSTEMS = {
    name: batch_config(
        model="prisma-v2.5" if name.startswith("v25") else "prisma-v3.0",
        language_code="hi-IN" if name.startswith("v25") else "hi-IN,en-IN",
        keyterms=HINTS if name in {"v25-bias", "v30-key", "v30-key-denoise"} else None,
        with_denoise=name == "v30-key-denoise",
        output_format=None if name.startswith("v25") else "codemix",
    )
    for name in ("v25", "v25-bias", "v30", "v30-key", "v30-key-denoise")
}
_WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20), strict=True,
))
_TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(),
                 range(20, 100, 10), strict=True))
_HINDI = "shoonya ek do teen chaar paanch chhah saat aath nau das gyarah barah terah " \
    "chaudah pandrah solah satrah atharah unnees bees ikkees baees teis chaubees " \
    "pachchees chhabbees sattais atthais untees tees"
_NUMBERS = _WORDS | _TENS | dict(zip(_HINDI.split(), range(31), strict=True))
NORMALIZATION = (
    "NFKC, casefold, Unicode punctuation/symbols to spaces, collapse whitespace, "
    "decimal digits and English 0-199 / Roman Hindi 0-30 number words to digits. "
    "No translation or script transliteration. Raw metrics are preserved. "
    "Latin references and v3 codemix Hindi output may be cross-script; do not "
    "interpret those scores as a model ranking. Rules intent accuracy also "
    "reflects the extractor's script coverage."
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = "".join(" " if unicodedata.category(c)[0] in "PS" else c
                   for c in text if unicodedata.category(c) != "Cf")
    words = text.split()
    out = []
    i = 0
    while i < len(words):
        word = words[i]
        if word.isdecimal():
            out.append(str(int(word)))
        elif word in _NUMBERS:
            number = _NUMBERS[word]
            if word == "one" and i + 1 < len(words) and words[i + 1] == "hundred":
                number = 100
                i += 1
                if i + 1 < len(words) and words[i + 1] in (_WORDS | _TENS):
                    i += 1
                    number += (_WORDS | _TENS)[words[i]]
                    if words[i] in _TENS and i + 1 < len(words) \
                            and words[i + 1] in _WORDS and 0 < _WORDS[words[i + 1]] < 10:
                        i += 1
                        number += _WORDS[words[i]]
            elif word in _TENS and i + 1 < len(words) \
                    and words[i + 1] in _WORDS and 0 < _WORDS[words[i + 1]] < 10:
                i += 1
                number += _WORDS[words[i]]
            out.append(str(number))
        else:
            out.append(word)
        i += 1
    return " ".join(out)


def digest(value) -> str:
    blob = value if isinstance(value, bytes) else json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()
    return hashlib.sha256(blob).hexdigest()


def request_id_of(payload: dict) -> str | None:
    """Keep a Gnani request_id when the batch body actually returns one."""
    value = payload.get("request_id") or payload.get("requestId")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def credit_record(budget: float | None, credits_per_minute: float | None,
                  plan: dict) -> dict:
    """Stamp the operator-supplied cap. This is not a Gnani-reported balance."""
    return {
        "source": "operator_supplied",
        "budget": budget,
        "credits_per_minute": credits_per_minute,
        "estimated_new_credits_upper_bound": plan.get(
            "estimated_new_credits_upper_bound"),
    }


def save(path: Path, value: dict) -> None:
    atomic_write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())


@contextmanager
def output_lock(output: Path):
    """One process owns a result directory; OS releases the lock after a crash."""
    import fcntl

    output.mkdir(parents=True, exist_ok=True)
    with (output / ".run.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("another benchmark process owns this output directory") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def load_grid(root: Path, limit: int) -> list[dict]:
    if limit < 1:
        raise ValueError("limit must be positive")
    corpus = load_utterances(root / "benchmark/data/utterances.jsonl")
    ids = {row["id"]: row for row in corpus[:limit]}
    rows = []
    seen = set()
    for line in (root / "benchmark/data/phone_manifest.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["id"] not in ids or row["noise"] not in NOISES or row["snr_db"] not in (0, 10):
            continue
        key = (row["id"], row["noise"], row["snr_db"])
        if key in seen:
            raise ValueError(f"duplicate grid cell: {key}")
        seen.add(key)
        path = (root / row["path"]).resolve()
        if not path.is_relative_to((root / "benchmark/data/audio").resolve()):
            raise ValueError("manifest audio path escapes benchmark/data/audio")
        blob = path.read_bytes()
        samples, rate = read_pcm(blob, sample_rate=8000)
        if digest(blob) != row["sha256"] or not samples:
            raise ValueError(f"audio hash/PCM mismatch: {row['path']}")
        if row["reference"] != ids[row["id"]]["text"]:
            raise ValueError(f"reference mismatch: {row['id']}")
        rows.append(row | {"duration_s": len(samples) / rate,
                           "intent": ids[row["id"]]["intent"]})
    if len(rows) != len(ids) * len(NOISES) * 2 or not rows:
        raise ValueError("phone manifest does not contain the complete requested grid")
    return sorted(rows, key=lambda r: (r["id"], r["noise"], r["snr_db"]))


def cache_path(output: Path, config_hash: str, audio_hash: str) -> Path:
    return output / "raw" / f"{config_hash}_{audio_hash}.json"


def read_cached(output: Path, config_hash: str, row: dict) -> dict | None:
    path = cache_path(output, config_hash, row["sha256"])
    if not path.exists():
        return None
    value = json.loads(path.read_text())
    if (value.get("audio_sha256") != row["sha256"]
            or value.get("config_hash") != config_hash
            or not isinstance(value.get("full_transcript"), str)
            or not value.get("job_id") or not value.get("file_id")
            or value.get("transcript_sha256") != digest(value["full_transcript"])):
        raise ValueError(f"invalid evidence cache: {path.name}")
    return value


def preflight(rows: list[dict], systems: dict, output: Path, base: str) -> dict:
    remaining = 0.0
    evaluations = 0
    for config in systems.values():
        config_hash = digest({"config": config, "base": base})
        for row in rows:
            if read_cached(output, config_hash, row) is None:
                remaining += row["duration_s"] / 60
                evaluations += 1
    return {
        "utterances": len({r["id"] for r in rows}), "noises": list(NOISES),
        "snrs_db": [0, 10], "systems": len(systems), "distinct_files": len(rows),
        "model_evaluations": len(rows) * len(systems),
        "new_evaluations_upper_bound": evaluations,
        "audio_minutes": sum(r["duration_s"] for r in rows) / 60,
        "new_model_audio_minutes_upper_bound": remaining,
    }


def check_budget(plan: dict, credit_budget: float | None, credits_per_minute: float | None,
                 i_mean_it: bool) -> None:
    minutes = plan["new_model_audio_minutes_upper_bound"]
    if not i_mean_it and (plan["distinct_files"] > 200 or minutes > 30):
        raise ValueError("grid exceeds 200 files or 30 model-audio minutes; use --i-mean-it")
    if minutes == 0:
        return
    if (credit_budget is None or credits_per_minute is None
            or not math.isfinite(credit_budget) or credit_budget <= 0
            or not math.isfinite(credits_per_minute) or credits_per_minute <= 0):
        raise ValueError("live work needs --credit-budget and --credits-per-minute "
                         "from the programme dashboard; no credit conversion is assumed")
    if minutes * credits_per_minute > credit_budget:
        raise ValueError("estimated programme credit usage exceeds the hard supplied budget")


def _failure(exc: Exception) -> str:
    # Provider bodies and signed download URLs may contain credentials: do not persist them.
    return f"{type(exc).__name__}:{getattr(exc, 'status', None) or 'no_status'}"


def _retry_429(fn, *, sleep, attempts: int = 5):
    """Retry non-spending GETs on 429. Spending POSTs are never retried here."""
    last = None
    for attempt in range(attempts):
        try:
            return fn()
        except GnaniError as exc:
            last = exc
            if exc.status != 429 or attempt == attempts - 1:
                raise
            sleep(min(60, 2 ** (attempt + 2)))
    raise last


def _get_job(client: PrismaBatch, job_id: str, *, sleep, attempts: int = 5):
    """Retry job status GETs on 429. This is not a spending POST."""
    return _retry_429(lambda: client.get_job(job_id), sleep=sleep, attempts=attempts)


def _start_created(client: PrismaBatch, job_id: str, *, sleep, attempts: int = 5) -> dict:
    """Start a CREATED job, retrying only a 429. GET confirms the outcome."""
    last = None
    for attempt in range(attempts):
        try:
            client.start_job(job_id)
            return _get_job(client, job_id, sleep=sleep)
        except GnaniError as exc:
            last = exc
            if exc.status != 429 or attempt == attempts - 1:
                raise
            sleep(min(60, 2 ** (attempt + 2)))
            job = _get_job(client, job_id, sleep=sleep)
            if job.get("status") != "CREATED":
                return job
    raise last


def _files(client: PrismaBatch, job_id: str, *, sleep=time.sleep) -> dict[str, dict]:
    reply = _retry_429(lambda: client.list_files(job_id, status=None), sleep=sleep)
    if reply.get("pagination", {}).get("has_more"):
        raise ValueError("unexpected file pagination; checkpoint retained, do not re-upload")
    rows = reply.get("data")
    if not isinstance(rows, list):
        raise ValueError("batch file list has no data array")
    result = {}
    for row in rows:
        name = Path(row.get("original_path", "")).name
        if not name or name in result:
            raise ValueError("batch files have missing/duplicate original_path")
        result[name] = row
    return result


def collect_job(client: PrismaBatch, state: dict, checkpoint: Path, output: Path,
                *, sleep=time.sleep, clock=time.monotonic, timeout: float = 900) -> None:
    if state.get("finished"):
        return
    job_id = state.get("job_id")
    if not job_id:
        raise ValueError("ambiguous create checkpoint: recover job_id from dashboard first")
    deadline = clock() + timeout
    # GET first on every resume, especially after an ambiguous start response.
    # If the job is still CREATED, start it even when a previous start attempt
    # was rate-limited: GET is the source of truth, not the local flag.
    job = _get_job(client, job_id, sleep=sleep)
    if request_id := request_id_of(job) or state.get("request_id"):
        state["request_id"] = request_id
        save(checkpoint, state)
    if job.get("status") == "CREATED":
        state["start_attempted"] = True
        save(checkpoint, state)
        job = _start_created(client, job_id, sleep=sleep)
    while job.get("status") not in TERMINAL:
        if clock() >= deadline:
            state["error"] = "job_timeout_900_seconds"
            save(checkpoint, state)
            return
        if job.get("status") == "CREATED":
            # Previous start was rate-limited or otherwise missed; GET is truth.
            job = _start_created(client, job_id, sleep=sleep)
            continue
        sleep(min(10, max(0, deadline - clock())))
        job = _get_job(client, job_id, sleep=sleep)
    state["status"] = job["status"]
    files = _files(client, job_id, sleep=sleep)
    errors = {}
    for name, audio_hash in state["files"].items():
        row = files.get(name, {})
        if row.get("status") != "COMPLETED" or not row.get("transcript_url"):
            errors[name] = "file_" + str(row.get("status", "missing"))
            continue
        target = cache_path(output, state["config_hash"], audio_hash)
        if target.exists():
            continue
        try:
            doc = _retry_429(lambda: client.fetch_transcript(row["transcript_url"]), sleep=sleep)
        except (GnaniError, httpx.HTTPError):
            # One fresh signed URL, GET only. Never recreate/start a charged job.
            row = _files(client, job_id, sleep=sleep).get(name, {})
            if not row.get("transcript_url"):
                raise ValueError("refreshed file has no transcript URL") from None
            url = row["transcript_url"]
            doc = _retry_429(lambda: client.fetch_transcript(url), sleep=sleep)
        if not isinstance(doc.get("full_transcript"), str):
            raise ValueError("transcript document has no full_transcript string")
        evidence = {
            "audio_sha256": audio_hash, "config_hash": state["config_hash"],
            "config": state["config"], "job_id": job_id, "file_id": row["file_id"],
            "evaluated_at": datetime.now(UTC).isoformat(),
            "full_transcript": doc["full_transcript"],
            "transcript_sha256": digest(doc["full_transcript"]),
        }
        if request_id := state.get("request_id") or request_id_of(job):
            evidence["request_id"] = request_id
            state["request_id"] = request_id
        save(target, evidence)
    state["errors"] = errors
    state["finished"] = True
    state.pop("error", None)
    save(checkpoint, state)


def evaluate(root: Path, rows: list[dict], systems: dict, output: Path, client: PrismaBatch,
             *, sleep=time.sleep, clock=time.monotonic, timeout: float = 900) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for system, config in systems.items():
        config_hash = digest({"config": config, "base": client.base})
        selected = {r["sha256"] for r in rows}
        reserved = set()
        checkpoints = []
        for path in sorted((output / "jobs").glob("*.json")):
            state = json.loads(path.read_text())
            if (state["config_hash"] == config_hash
                    and selected.intersection(state["files"].values())):
                reserved.update(state["files"].values())
                checkpoints.append((path, state))
        pending = [r for r in rows if r["sha256"] not in reserved
                   and read_cached(output, config_hash, r) is None]
        # Twenty files avoids the default first-page limit without editing frozen clients.
        for start in range(0, len(pending), 20):
            if start:
                # Avoid bursting adjacent create POSTs into a 429.
                sleep(2)
            group = pending[start:start + 20]
            names = {Path(r["path"]).name: r["sha256"] for r in group}
            if len(names) != len(group):
                raise ValueError("uploaded basenames must be unique")
            state = {"system": system, "config": config, "config_hash": config_hash,
                     "files": names, "created_at": datetime.now(UTC).isoformat()}
            path = output / "jobs" / f"{digest([config_hash, names])}.json"
            # Reserve before the POST. An interrupted upload cannot silently spend twice.
            save(path, state)
            try:
                clips = [(Path(r["path"]).name, (root / r["path"]).read_bytes()) for r in group]
                reply = client.create_job(clips, config)
                if not reply.get("job_id"):
                    raise ValueError("create response has no job_id")
                state["job_id"] = reply["job_id"]
                if request_id := request_id_of(reply):
                    state["request_id"] = request_id
                save(path, state)
            except (GnaniError, httpx.HTTPError, ValueError) as exc:
                state["error"] = _failure(exc)
                save(path, state)
                raise
            checkpoints.append((path, state))
        for index, (path, state) in enumerate(checkpoints):
            if index:
                sleep(3)
            if not state.get("job_id"):
                raise ValueError("ambiguous create checkpoint: recover job_id from dashboard first")
            print(f"{system}: collecting {state.get('job_id', 'ambiguous-create')}", flush=True)
            try:
                collect_job(client, state, path, output, sleep=sleep, clock=clock, timeout=timeout)
            except (GnaniError, httpx.HTTPError, ValueError) as exc:
                state["error"] = _failure(exc)
                save(path, state)
                # Stop on account failures. No subsequent model can spend through a 402.
                if isinstance(exc, GnaniError) and exc.status in {401, 402, 403, 429}:
                    raise


def _metrics(records: list[dict], expected: int) -> dict:
    complete = len(records) == expected
    keys = ("wer", "cer", "normalized_wer", "normalized_cer", "intent_accuracy")
    return {"n": len(records), "n_expected": expected, "complete": complete} | {
        key: sum(r[key] for r in records) / expected if complete else None for key in keys
    }


def summarize(rows: list[dict], systems: dict, output: Path, base: str, plan: dict) -> dict:
    records = []
    missing = []
    jobs = defaultdict(set)
    request_ids = defaultdict(set)
    for system, config in systems.items():
        config_hash = digest({"config": config, "base": base})
        for row in rows:
            evidence = read_cached(output, config_hash, row)
            if evidence is None:
                missing.append({"system": system, "path": row["path"],
                                "audio_sha256": row["sha256"]})
                continue
            ref, hyp = row["reference"], evidence["full_transcript"]
            predicted = extract_event(hyp, provider="rules")
            cross_script = bool(re.search("[\u0900-\u097f]", hyp)) != bool(
                re.search("[\u0900-\u097f]", ref))
            records.append({"system": system, "id": row["id"], "noise": row["noise"],
                            "snr_db": row["snr_db"], "audio_sha256": row["sha256"],
                            "config_hash": config_hash, "job_id": evidence["job_id"],
                            "request_id": evidence.get("request_id"),
                            "file_id": evidence["file_id"], "cross_script": cross_script,
                            "wer": wer(ref, hyp), "cer": cer(ref, hyp),
                            "normalized_wer": wer(normalize(ref), normalize(hyp)),
                            "normalized_cer": cer(normalize(ref), normalize(hyp)),
                            "intent_accuracy": float(predicted.intent.value == row["intent"])})
            jobs[system].add(evidence["job_id"])
            if evidence.get("request_id"):
                request_ids[system].add(evidence["request_id"])
    complete = not missing
    systems_out = []
    by_noise: list[dict] = []
    by_snr: list[dict] = []
    for system, config in systems.items():
        matched = [r for r in records if r["system"] == system]
        systems_out.append({"id": system, "config": config,
                            "cross_script_n": sum(r["cross_script"] for r in matched),
                            **_metrics(matched, len(rows))})
        for key, destination in (("noise", by_noise), ("snr_db", by_snr)):
            for value in sorted({r[key] for r in rows}):
                subset = [r for r in matched if r[key] == value]
                destination.append({"system": system, key: value,
                                    **_metrics(subset, sum(r[key] == value for r in rows))})
    report = {"run_at": datetime.now().astimezone().isoformat(), "complete": complete,
              "provenance": "live_prisma_batch_on_synthetic_simulated_telephony",
              "metric_policy": NORMALIZATION, "primary_wer": "raw",
              "grid": plan, "job_ids": {k: sorted(v) for k, v in jobs.items()},
              "request_ids": {k: sorted(v) for k, v in request_ids.items()},
              "systems": systems_out, "by_noise": by_noise, "by_snr_db": by_snr,
              "evaluations": records, "missing": missing}
    if plan.get("credit"):
        report["credit"] = plan["credit"]
    save(output / "scores.json", report)
    lines = ["# Live Prisma on synthetic 8 kHz phone clips", "", f"Scored at: {report['run_at']}",
             "", NORMALIZATION, "", f"{len(rows)} distinct files; {plan['model_evaluations']} "
             f"expected model evaluations; {len(records)} completed.", ""]
    credit = plan.get("credit") or {}
    if credit.get("source") == "operator_supplied":
        lines += [
            "Credit cap is operator-supplied, not a Gnani-reported remaining balance: "
            f"budget {credit.get('budget')}, {credit.get('credits_per_minute')} "
            "credits/audio-minute, estimated new-credit upper bound "
            f"{credit.get('estimated_new_credits_upper_bound')}.",
            "",
        ]
    if complete:
        lines += ["WER/CER below are raw; normalized metrics are separate columns.", "",
                  "| System | Raw WER | Raw CER | Normalized WER | Normalized CER | "
                  "Intent accuracy | n |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for row in systems_out:
            lines.append(f"| {row['id']} | {row['wer']:.4f} | {row['cer']:.4f} | "
                         f"{row['normalized_wer']:.4f} | {row['normalized_cer']:.4f} | "
                         f"{row['intent_accuracy']:.4f} | {row['n']} |")
        lines += ["", "| Noise | v30 raw WER | v30-key-denoise raw WER |",
                  "| --- | --- | --- |"]
        for noise in NOISES:
            values = {r["system"]: r["wer"] for r in by_noise if r["noise"] == noise}
            if {"v30", "v30-key-denoise"} <= values.keys():
                lines.append(f"| {noise} | {values['v30']:.4f} | {values['v30-key-denoise']:.4f} |")
    else:
        lines += ["INCOMPLETE: no comparison table is published. Inspect missing in scores.json "
                  "and jobs/*.json; successful raw evidence is retained for resume."]
    atomic_write(output / "scores.md", ("\n".join(lines) + "\n").encode())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--preflight", action="store_true",
                        help="validate files, print costs; no HTTP")
    parser.add_argument("--i-mean-it", action="store_true")
    parser.add_argument("--credit-budget", type=float)
    parser.add_argument("--credits-per-minute", type=float)
    parser.add_argument("--systems", nargs="+", choices=SYSTEMS, default=list(SYSTEMS))
    parser.add_argument("--output", type=Path, default=ROOT / "benchmark/results")
    args = parser.parse_args(argv)
    try:
        require_api_key()
        client = PrismaBatch()
        rows = load_grid(ROOT, args.limit)
        systems = {name: SYSTEMS[name] for name in args.systems}
        plan = preflight(rows, systems, args.output, client.base)
        plan["estimated_new_credits_upper_bound"] = (
            plan["new_model_audio_minutes_upper_bound"] * args.credits_per_minute
            if args.credits_per_minute is not None else None)
        plan["credit"] = credit_record(
            args.credit_budget, args.credits_per_minute, plan)
        print(json.dumps(plan, indent=2), flush=True)
        if args.preflight:
            return 0
        with output_lock(args.output):
            # Recheck under the process lock: another run may just have finished.
            check_budget(plan, args.credit_budget, args.credits_per_minute, args.i_mean_it)
            failure = None
            try:
                evaluate(ROOT, rows, systems, args.output, client)
            except (GnaniError, httpx.HTTPError, ValueError) as exc:
                failure = _failure(exc)
            report = summarize(rows, systems, args.output, client.base, plan)
        if failure:
            print(f"Stopped: {failure}. See checkpoints; no automatic spending retry.",
                  file=sys.stderr)
        return 0 if report["complete"] and failure is None else 1
    except (ValueError, OSError, GnaniError) as exc:
        # Missing-key text is safe and intentionally loud. No provider bodies or signed URLs.
        message = str(exc) if isinstance(exc, MissingApiKeyError) or not isinstance(
            exc, GnaniError) else _failure(exc)
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
