"""OPENVID local model worker — runs a GGUF/llama.cpp endpoint as a worker.

Connects to any llama.cpp server / Ollama / local OpenAI-compatible endpoint.
Falls back gracefully when no local model is running.
"""
from __future__ import annotations

import json
import urllib.request


class LocalLLMWorker:
    """Local model via Ollama native /api/chat (no OpenAI shim quirks)."""
    name = "local-llm"
    topics = ["user.input"]

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen3.5:2b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def handle(self, payload: dict) -> dict:
        text = payload.get("text", "")
        eid = payload.get("_eid")
        try:
            body = json.dumps({"model": self.model, "stream": False, "messages": [
                {"role": "user", "content": text}]}).encode()
            req = urllib.request.Request(self.base_url + "/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            out = {"ok": True, "worker": self.name,
                   "text": (data.get("message", {}).get("content") or "").strip()}
        except Exception as e:
            out = {"ok": False, "worker": self.name, "text": f"local-llm offline: {e}"}
        if eid:
            out["reply_to"] = eid
        return out
