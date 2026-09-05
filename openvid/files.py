"""OPENVID FileWorker — full file access (the machine belongs to the agent).

Actions: file.read, file.write, file.list, file.delete.
No sandbox by design: relative paths resolve against the process cwd,
absolute paths are used as-is. Dangerous ops (file.delete) sit behind the
kernel's permission gate (confirm list), not behind path restrictions.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path


class FileWorker:
    name = "files"
    topics = ["agent.action"]
    actions = {"file.read", "file.write", "file.list", "file.delete"}

    def __init__(self, home: Path, extra_roots: list[str] | None = None):
        self.root = Path.cwd().resolve()  # relative paths anchor at cwd

    def _resolve(self, path: str) -> Path:
        return Path(path).expanduser().resolve()

    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        path = payload.get("path", "")
        if act == "file.list":
            root = self._resolve(path) if path else self.root
            items = []
            for f in sorted(root.rglob("*"))[:200]:
                st = f.stat()
                items.append({"path": str(f), "size": st.st_size,
                              "dir": f.is_dir(), "mtime": st.st_mtime})
            return {"ok": True, "files": items}
        f = self._resolve(path)
        if act == "file.read":
            if not f.exists():
                return {"ok": False, "error": "not found"}
            return {"ok": True, "content": f.read_text(encoding="utf-8", errors="replace")[:20000],
                    "size": f.stat().st_size}
        if act == "file.write":
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(payload.get("content", ""), encoding="utf-8")
            return {"ok": True, "path": str(f), "size": f.stat().st_size}
        if act == "file.delete":
            if not f.exists():
                return {"ok": False, "error": "not found"}
            if f.is_dir():
                shutil.rmtree(f)
            else:
                f.unlink()
            return {"ok": True, "deleted": str(f)}
        return {"ok": False, "error": f"unsupported: {act}"}
