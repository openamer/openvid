"""OPENVID Sessions — multi-turn conversation history.

Sessions live in <home>/sessions/<sid>.json: {"turns": [{role, content, ts}]}.
The agent loop injects recent turns as context so the model remembers the
conversation. Frontends pass session_id in the payload; a default session
keeps single-shot usage unchanged.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

MAX_CONTEXT_TURNS = 12  # recent turns injected into the prompt


class Sessions:
    def __init__(self, home: Path):
        self.dir = Path(home) / "sessions"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file(self, sid: str) -> Path:
        if not sid or not sid.replace("-", "").replace("_", "").isalnum():
            sid = "default"
        return self.dir / f"{sid}.json"

    def load(self, sid: str) -> list[dict]:
        f = self._file(sid)
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8")).get("turns", [])
        return []

    def append(self, sid: str, role: str, content: str):
        f = self._file(sid)
        data = {"turns": self.load(sid)}
        data["turns"].append({"role": role, "content": content, "ts": time.time()})
        f.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    def context(self, sid: str) -> list[dict]:
        """Recent turns as chat messages (for the LLM)."""
        return [{"role": t["role"], "content": t["content"]}
                for t in self.load(sid)[-MAX_CONTEXT_TURNS:]]

    def reset(self, sid: str):
        self._file(sid).write_text('{"turns": []}', encoding="utf-8")

    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]
