"""OPENVID HTTP API — thin REST surface over the same kernel.

Endpoints:
    GET  /health            -> {status, workers, events}
    POST /ask {text}        -> full turn, waits for answer
    POST /action {action,...} -> fire agent.action, returns eid
    GET  /result/<eid>      -> poll for worker result
Run: python -m openvid.server  (port 8765)
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .kernel import Kernel
from .workers import LLMWorker, MemoryWorker, ShellWorker
from .skills import SkillWorker
from .webui import WEBUI_HTML


def _build_kernel(home=None) -> Kernel:
    k = Kernel(home=home)
    k.register(ShellWorker())
    k.register(MemoryWorker(k.home))
    k.register(SkillWorker(k.home))
    base = os.environ.get("OPENVID_LLM_BASE", "https://openrouter.ai/api/v1")
    key = os.environ.get("OPENVID_LLM_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENVID_LLM_MODEL", "z-ai/glm-5.3-flash")
    if key:
        k.register(LLMWorker(base, key, model))
    return k


def run(port: int = 8765, home=None):
    k = _build_kernel(home)
    k.start()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/index"):
                body = WEBUI_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/health":
                return self._send(200, {
                    "status": "alive", "workers": list(k.workers),
                    "pending": {t: k.bus.pending(t) for t in
                                ("user.input", "agent.action", "worker.result")}})
            if self.path.startswith("/result/"):
                eid = self.path.rsplit("/", 1)[-1]
                for ev in k.bus.claim("worker.result", "http"):
                    p = ev["payload"]
                    k.bus.complete(ev["id"])
                    if p.get("reply_to") == eid:
                        return self._send(200, p)
                return self._send(404, {"error": "not ready or unknown eid"})
            self._send(404, {"error": "unknown"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "bad json"})
            if self.path == "/ask":
                return self._send(200, {"answer": k.ask(payload.get("text", ""))})
            if self.path == "/action":
                eid = k.bus.publish("agent.action", payload)
                return self._send(200, {"eid": eid})
            self._send(404, {"error": "unknown"})

        def log_message(self, *a):
            pass

    print(f"OPENVID HTTP API on :{port} — workers: {', '.join(k.workers)}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--home", default=None)
    run(ap.parse_args().port, ap.parse_args().home)
