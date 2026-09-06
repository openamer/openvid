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
from .files import FileWorker
from .web import WebWorker
from .sysinfo import SysWorker
from .swarm import SwarmWorker
from .adaptive_llm import AdaptiveLocalLLM
from .selfimprove import SelfImprovement
from .learnloop import LearnLoop
from .voice import stt_openai, tts_openai
from . import gateway as gw
from .webui import WEBUI_HTML


def _build_kernel(home=None) -> Kernel:
    k = Kernel(home=home)
    k.register(ShellWorker())
    k.register(MemoryWorker(k.home))
    k.register(SkillWorker(k.home))
    k.register(FileWorker(k.home))
    k.register(WebWorker())
    k.register(SysWorker())
    k.register(SwarmWorker())
    if os.environ.get("OPENVID_ADAPTIVE_LOCAL", "1") == "1":
        k.register(AdaptiveLocalLLM(k.home))
    base = os.environ.get("OPENVID_LLM_BASE", "https://openrouter.ai/api/v1")
    key = os.environ.get("OPENVID_LLM_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENVID_LLM_MODEL", "z-ai/glm-5.3-flash")
    if key:
        if os.environ.get("OPENVID_AGENT_MODE", "1") != "0":
            # full agent loop: LLM decides tool usage (default)
            from .agent_loop import AgentLoopWorker
            k.register(AgentLoopWorker(base, key, model,
                                       max_steps=8).attach(k.bus).attach_sessions(k.sessions))
        else:
            k.register(LLMWorker(base, key, model))
    return k


def run(port: int = 8765, home=None):
    k = _build_kernel(home)
    k.start()
    # autonomous growth (auto_approve via env, default on)
    auto = os.environ.get("OPENVID_AUTO_APPROVE", "1") == "1"
    si = SelfImprovement(k.home, k.bus, auto_approve=auto)
    si.start(interval=float(os.environ.get("OPENVID_SI_INTERVAL", "3600")))
    LearnLoop(k.home, k.bus).start()
    # multi-channel messaging (opt-in via env tokens)
    if any(os.environ.get(x) for x in
           ("OPENVID_TG_TOKEN", "OPENVID_DISCORD_TOKEN", "OPENVID_WEBHOOK_PORT")):
        def ask_with_session(text, session_id="default"):
            return k.ask(text, session_id=session_id)
        import threading as _th
        _th.Thread(target=gw.run_gateway, args=(ask_with_session,), daemon=True).start()

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
            if self.path.startswith("/tts?"):
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                text = (qs.get("text") or [""])[0]
                key = os.environ.get("OPENAI_API_KEY", "")
                if not (text and key):
                    return self._send(400, {"error": "text + OPENAI_API_KEY required"})
                try:
                    mp3 = tts_openai(text, key)
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("Content-Length", str(len(mp3)))
                    self.end_headers()
                    self.wfile.write(mp3)
                except Exception as e:
                    self._send(502, {"error": str(e)})
                return
            if self.path == "/health":
                return self._send(200, {
                    "status": "alive", "workers": list(k.workers),
                    "gpu_hint": os.environ.get("OPENVID_GPU_URL", ""),
                    "pending": {t: k.bus.pending(t) for t in
                                ("user.input", "agent.action", "worker.result")}})
            if self.path.startswith("/result/"):
                eid = self.path.rsplit("/", 1)[-1]
                for ev in k.bus.claim("worker.result", "http"):
                    p = ev["payload"]
                    k.bus.complete(ev["id"])
                    if p.get("reply_to") == eid or p.get("_rid") == eid:
                        return self._send(200, p)
                return self._send(404, {"error": "not ready or unknown eid"})
            self._send(404, {"error": "unknown"})

        def _stt(self, payload):
            audio = payload.get("audio", "")
            key = os.environ.get("OPENAI_API_KEY", "")
            if not (audio and key):
                return self._send(400, {"error": "audio + OPENAI_API_KEY required"})
            try:
                return self._send(200, stt_openai(audio, key))
            except Exception as e:
                return self._send(502, {"error": str(e)})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "bad json"})
            if self.path == "/ask":
                return self._send(200, {"answer": k.ask(
                    payload.get("text", ""), session_id=payload.get("session_id", "default"))})
            if self.path == "/reset":
                k.sessions.reset(payload.get("session_id", "default"))
                return self._send(200, {"ok": True})
            if self.path == "/action":
                eid = k.bus.publish("agent.action", {**payload, "_rid": ""})
                # stamp eid as _rid (claim+republish like kernel.ask does)
                for ev in k.bus.claim("agent.action", "http-stamp"):
                    p = ev["payload"]; p["_rid"] = ev["eid"]
                    k.bus.complete(ev["id"])
                    k.bus.publish("agent.action", p)
                    eid = ev["eid"]
                return self._send(200, {"eid": eid})
            if self.path == "/stt":
                return self._stt(payload)
            if self.path == "/config":
                allowed = {"OPENVID_LLM_MODEL", "OPENVID_FILES_ROOT",
                           "OPENVID_AUTO_APPROVE", "OPENVID_AGENT_MODE",
                           "OPENVID_ADAPTIVE_LOCAL"}
                changes = {kk: str(vv) for kk, vv in payload.items() if kk in allowed}
                for kk, vv in changes.items():
                    os.environ[kk] = vv
                return self._send(200, {"ok": True, "applied": changes,
                                        "note": "model/pool changes apply on restart"})
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
