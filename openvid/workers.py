"""OPENVID workers: shell, memory, llm. Each is a plain object with
`name`, `topics`, `handle(payload) -> dict`."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.request
from pathlib import Path


class ShellWorker:
    name = "shell"
    topics = ["agent.action"]

    def handle(self, payload: dict) -> dict:
        if payload.get("action") != "shell.run":
            return {"ok": False, "error": "unsupported action"}
        cmd = payload.get("cmd", "")
        t0 = time.time()
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return {
            "ok": p.returncode == 0,
            "action": "shell.run",
            "cmd": cmd,
            "stdout": p.stdout[-8000:],
            "stderr": p.stderr[-2000:],
            "rc": p.returncode,
            "dur": round(time.time() - t0, 2),
        }


class MemoryWorker:
    name = "memory"
    topics = ["agent.action"]

    def __init__(self, home: Path):
        self.dir = Path(home) / "memory"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.episodes = self.dir / "episodes.jsonl"

    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        if act == "memory.write":
            with self.episodes.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload["data"], ensure_ascii=False) + "\n")
            return {"ok": True}
        if act == "memory.read":
            query = payload.get("query", "").lower()
            hits = []
            if self.episodes.exists():
                for line in self.episodes.read_text(encoding="utf-8").splitlines()[-500:]:
                    if query in line.lower():
                        hits.append(json.loads(line))
            return {"ok": True, "hits": hits[-20:]}
        return {"ok": False, "error": f"unsupported: {act}"}


class LLMWorker:
    """Chat via OpenAI-compatible endpoint (OpenRouter, local, GPU worker)."""
    name = "llm"
    topics = ["user.input"]

    def __init__(self, base_url: str, api_key: str, model: str, answer_topic: str = "agent.answer"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.answer_topic = answer_topic

    def handle(self, payload: dict) -> dict:
        text = payload.get("text", "")
        eid = payload.get("_eid")
        try:
            answer = self._chat(text)
            out = {"ok": True, "worker": "llm", "text": answer}
        except Exception as e:
            out = {"ok": False, "worker": "llm", "text": f"llm error: {e}"}
        if eid:
            out["reply_to"] = eid
        return out

    def _chat(self, text: str) -> str:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
        }).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
        return data["choices"][0]["message"]["content"]
