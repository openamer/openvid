"""OPENVID SkillWorker — markdown skills with YAML-ish frontmatter.

skills/<name>.md:
    ---
    description: one-line trigger description
    ---
    # body injected into prompts when invoked
"""
from __future__ import annotations

import re
from pathlib import Path


class SkillWorker:
    name = "skills"
    topics = ["agent.action"]

    def __init__(self, home: Path):
        self.dir = Path(home) / "skills"
        self.dir.mkdir(parents=True, exist_ok=True)

    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        if act == "skill.list":
            return {"ok": True, "skills": sorted(
                p.stem for p in self.dir.glob("*.md"))}
        if act == "skill.get":
            f = self._safe(payload.get("name", ""))
            if f is None or not f.exists():
                return {"ok": False, "error": "skill not found"}
            return {"ok": True, "name": f.stem, "content": f.read_text(encoding="utf-8")}
        if act == "skill.write":
            name = payload.get("name", "")
            f = self._safe(name)
            if f is None or not re.match(r"^[\w-]+$", name or ""):
                return {"ok": False, "error": "invalid skill name"}
            f.write_text(payload.get("content", ""), encoding="utf-8")
            return {"ok": True, "name": f.stem}
        return {"ok": False, "error": f"unsupported: {act}"}

    def _safe(self, name: str):
        """Path-traversal guard: only plain names under skills/."""
        if not re.match(r"^[\w-]+$", name or ""):
            return None
        return self.dir / f"{name}.md"
