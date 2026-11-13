"""Exercise the real k6 script against a local test-only HTTP fixture.

No application mock mode, speech provider, key or external URL is involved.
Run: python loadtest/tests/safety.py --k6 /path/to/k6
"""

import argparse
import json
import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4


def run_case(binary: str, mode: str) -> None:
    state = {"calls": 0, "active": 0, "peak": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):
            pass

        def respond(self, status, body, correlation=True):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            if correlation:
                self.send_header("X-Request-ID", str(uuid4()))
            self.end_headers()
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                # k6 abort() can close its other VU's already-outbound socket.
                pass

        def do_GET(self):
            assert self.path in {"/api/health", "/api/ready"}
            self.respond(200, {"ok": True, "gnani_key_set": False, "db_writable": True})

        def do_POST(self):
            assert self.path == "/api/ingest/sample"
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            with lock:
                state["calls"] += 1
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            try:
                time.sleep(0.05)
                self.respond(429 if mode == "rate_limit" else 200, {}, mode != "missing_id")
            finally:
                with lock:
                    state["active"] -= 1

    class Server(ThreadingHTTPServer):
        request_queue_size = 128
        daemon_threads = True

    server = Server(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.json"
            env = os.environ.copy()
            env.update(
                BASE_URL=f"http://127.0.0.1:{server.server_port}",
                SPEECH="1", CI="0", K6_NO_USAGE_REPORT="true",
                DISPATCH_PASSCODE="", SUMMARY_PATH=str(summary),
            )
            result = subprocess.run(
                [binary, "run", "--quiet", "loadtest/k6.js"],
                env=env, capture_output=True, text=True, timeout=45,
            )
            report = json.loads(summary.read_text())
            assert report["elapsed_seconds"] > 0, report
            assert report["speech"]["calls"] == state["calls"], report
            assert 0 < state["calls"] <= 4, state
            assert state["peak"] <= 2, state
            if mode == "success":
                assert result.returncode == 0, result.stdout + result.stderr
                assert state["calls"] == 4, state
            else:
                assert result.returncode != 0, report
                assert report["speech_error_rate"] > 0, report
                # At most the two already-outbound VUs can complete on abort.
                assert state["calls"] <= 2, state
            print(
                f"{mode}: exit={result.returncode}, "
                f"sample_posts={state['calls']}, peak_speech={state['peak']}"
            )
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k6", default="k6")
    args = parser.parse_args()
    for case in ("success", "missing_id", "rate_limit"):
        run_case(args.k6, case)
