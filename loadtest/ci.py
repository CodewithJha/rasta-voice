"""Run real keyless API load and a closed-port negative check in one process tree."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def ready(origin: str) -> dict:
    with urlopen(f"{origin}/api/ready", timeout=1) as response:
        return json.load(response)


def run(binary: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    passcode = secrets.token_urlsafe(32)  # Synthetic, private to this test process.
    env = os.environ.copy()
    env.update(
        GNANI_API_KEY="", LLM_PROVIDER="rules", RASTA_ENV="development",
        DISPATCH_PASSCODE=passcode, RASTA_DB_PATH=str(directory / "events.sqlite"),
        PYTHONPATH="backend:gnani_client:benchmark",
        K6_NO_USAGE_REPORT="true", CI="true", SPEECH="0", PROFILE="local",
    )
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    origin = f"http://127.0.0.1:{port}"
    env["BASE_URL"] = origin
    with (directory / "api.log").open("w") as api_log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "rasta.main:app", "--host", "127.0.0.1",
             "--port", str(port), "--no-access-log"],
            env=env, stdout=api_log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 15
            while True:
                try:
                    before = ready(origin)
                    break
                except (URLError, TimeoutError, ConnectionError):
                    if server.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError(
                            "The real API failed to become ready; see api.log"
                        ) from None
                    time.sleep(0.1)
            assert before["ok"] and before["db_writable"] is True
            assert before["gnani_key_set"] is False
            command = [binary, "run", "--quiet", "--log-output=none", "loadtest/k6.js"]
            env["SUMMARY_PATH"] = str(directory / "ops-desk.json")
            with (directory / "ops-desk.log").open("w") as log:
                result = subprocess.run(
                    command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=50,
                )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Ops/desk load failed (exit {result.returncode}); see ops-desk.log"
                )
            measured = json.loads(Path(env["SUMMARY_PATH"]).read_text())
            assert measured["thresholds_passed"] and measured["speech"]["calls"] == 0
            assert measured["desk_vus"] == 10 and measured["desk"]["calls"] > 0
            after = ready(origin)
            assert after["gnani_key_set"] is False
            assert after["demo_credits_remaining"] == before["demo_credits_remaining"]
            print("Real keyless ops/desk load passed; speech count zero and budget unchanged.")

            # A bound but non-listening socket guarantees a closed target, without
            # assuming a well-known port is unused on a developer's machine.
            with socket.socket() as closed_target:
                closed_target.bind(("127.0.0.1", 0))
                env["BASE_URL"] = f"http://127.0.0.1:{closed_target.getsockname()[1]}"
                env["DISPATCH_PASSCODE"] = ""
                env["SUMMARY_PATH"] = str(directory / "closed-port.json")
                with (directory / "closed-port.log").open("w") as log:
                    negative = subprocess.run(
                        command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=50,
                    )
            failed = json.loads(Path(env["SUMMARY_PATH"]).read_text())
            assert negative.returncode == 99, "Expected a k6 threshold failure, not a startup error"
            assert failed["ops_error_rate"] == 1 and not failed["thresholds_passed"]
            assert failed["speech"]["calls"] == 0
            print("Closed-port threshold failure verified (exit 99); no speech was attempted.")
            for path in directory.glob("*.log"):
                assert passcode not in path.read_text(), "Synthetic passcode in a test log"
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k6", default="k6")
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    run(arguments.k6, arguments.output_dir.resolve())
