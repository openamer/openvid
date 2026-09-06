"""OPENVID LongMemoryWorker — episodic long-term memory with scoring.

Extends the basic memory worker:
    long.write {text, tags}   -> episode stored with timestamp + tags
    long.search {query, k}    -> keyword-scored top-k episodes
    long.stats                -> episode count, tag histogram
Store: <home>/memory/episodes.jsonl (compatible with basic memory.write).
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path


class LongMemoryWorker:
    name = "long-memory"
    topics = ["agent.action"]
    actions = {"long.write", "long.search", "long.stats"}

    def __init__(self, home: Path):
        self.file = Path(home) / "memory" / "episodes.jsonl"
        self.file.parent.mkdir(parents=True, exist_ok=True)

    def _all(self) -> list[dict]:
        if not self.file.exists():
            return []
        out = []
        for line in self.file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        if act == "long.write":
            ep = {"text": payload.get("text", ""),
                  "tags": payload.get("tags", []),
                  "ts": time.time()}
            with self.file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ep, ensure_ascii=False) + "\n")
            return {"ok": True, "total": len(self._all())}
        if act == "long.search":
            q = (payload.get("query") or "").lower()
            k = int(payload.get("k", 5))
            scored = []
            for i, ep in enumerate(self._all()):
                text = (ep.get("text", "") or "").lower()
                tags = " ".join(ep.get("tags", [])).lower()
                score = sum(1 for w in q.split() if w and w in text) \
                        + 2 * sum(1 for w in q.split() if w and w in tags)
                if score:
                    scored.append((score, i, ep))
            scored.sort(key=lambda x: (-x[0], -x[1]))
            return {"ok": True, "hits": [ep for _, _, ep in scored[:k]]}
        if act == "long.stats":
            eps = self._all()
            tags = Counter(t for ep in eps for t in ep.get("tags", []))
            return {"ok": True, "episodes": len(eps),
                    "tags": tags.most_common(10)}
        return {"ok": False, "error": f"unsupported: {act}"}
