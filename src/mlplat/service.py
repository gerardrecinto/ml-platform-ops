"""Scoring service on the standard library: /score, /healthz, /readyz, /metrics. SIGHUP reloads the registry; a bad registry keeps serving the old model and raises mlplat_reload_failed."""
from __future__ import annotations

import json
import os
import pathlib
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .model import RegistryError, decide, load

BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)


class State:
    def __init__(self, registry: pathlib.Path):
        self.registry = pathlib.Path(registry)
        self.lock = threading.Lock()
        self.model = None
        self.version = None
        self.ready = False
        self.reload_failed = 0
        self.codes: dict[str, int] = {}
        self.buckets = [0] * len(BUCKETS)
        self.count = 0
        self.total = 0.0
        self.reload()

    def reload(self) -> bool:
        try:
            reg = load(self.registry)
        except RegistryError:
            with self.lock:
                self.reload_failed = 1
            return False
        with self.lock:
            self.model, self.version, self.ready, self.reload_failed = reg["models"][reg["active"]], reg["active"], True, 0
        return True

    def observe(self, code: int, seconds: float) -> None:
        with self.lock:
            self.codes[str(code)] = self.codes.get(str(code), 0) + 1
            self.count += 1
            self.total += seconds
            for i, b in enumerate(BUCKETS):
                if seconds <= b:
                    self.buckets[i] += 1

    def metrics(self) -> str:
        with self.lock:
            out = ["# TYPE mlplat_requests_total counter"]
            out += [f'mlplat_requests_total{{code="{c}"}} {n}' for c, n in sorted(self.codes.items())]
            out.append("# TYPE mlplat_request_duration_seconds histogram")
            out += [f'mlplat_request_duration_seconds_bucket{{le="{b}"}} {n}' for b, n in zip(BUCKETS, self.buckets)]
            out += [
                f'mlplat_request_duration_seconds_bucket{{le="+Inf"}} {self.count}',
                f"mlplat_request_duration_seconds_sum {self.total:.6f}",
                f"mlplat_request_duration_seconds_count {self.count}",
                "# TYPE mlplat_model_info gauge",
                f'mlplat_model_info{{version="{self.version}"}} {1 if self.ready else 0}',
                "# TYPE mlplat_reload_failed gauge",
                f"mlplat_reload_failed {self.reload_failed}",
            ]
        return "\n".join(out) + "\n"


def make_handler(state: State):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, body: str, ctype: str = "application/json") -> None:
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/healthz":
                self._send(200, '{"status":"alive"}')
            elif self.path == "/readyz":
                self._send(200 if state.ready else 503, json.dumps({"ready": state.ready, "model": state.version}))
            elif self.path == "/metrics":
                self._send(200, state.metrics(), "text/plain; version=0.0.4")
            else:
                self._send(404, '{"error":"not found"}')

        def do_POST(self):
            t0 = time.perf_counter()
            code, body = 200, ""
            if self.path != "/score":
                code, body = 404, '{"error":"not found"}'
            elif not state.ready:
                code, body = 503, '{"error":"no model loaded"}'
            else:
                try:
                    n = int(self.headers.get("Content-Length", 0))
                    feats = json.loads(self.rfile.read(n))["features"]
                    s, flag = decide(state.model, feats)
                    body = json.dumps({"score": round(s, 4), "fraud": flag, "model_version": state.version})
                except (ValueError, KeyError, TypeError):
                    code, body = 400, '{"error":"body must be {\\"features\\": {...}}"}'
            self._send(code, body)
            state.observe(code, time.perf_counter() - t0)

    return H


def serve(registry: pathlib.Path, port: int) -> ThreadingHTTPServer:
    state = State(registry)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    httpd.state = state
    return httpd


def main() -> None:
    httpd = serve(pathlib.Path(os.environ.get("REGISTRY", "registry/registry.json")), int(os.environ.get("PORT", "8080")))
    signal.signal(signal.SIGHUP, lambda *_: httpd.state.reload())
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown).start())
    httpd.serve_forever()


if __name__ == "__main__":
    main()
