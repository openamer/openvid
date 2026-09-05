"""OPENVID FileWorker — sandboxed file operations.

Actions: file.read, file.write, file.list, file.delete.
Sandbox: relative paths resolve under <home>/files; absolute paths are
rejected unless under OPENVID_FILES_ROOT (extra roots, e.g. a project dir).
"""
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path


class FileWorker:
    name = "files"
    topics = ["agent.action"]
    actions = {"file.read", "file.write", "file.list", "file.delete"}

    def __init__(self, home: Path, extra_roots: list[str] | None = None):
        self.root = (Path(home) / "files").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        if extra_roots is None:
            env = os.environ.get("OPENVID_FILES_ROOT", "")
            extra_roots = [r.strip() for r in env.split(",") if r.strip()]
        self.roots = [self.root] + [Path(r).resolve() for r in extra_roots if str(r).strip()]

    def _resolve(self, path: str) -> Path | None:
        """Resolve path into an allowed root; None if outside.
        Tries each root in order (relative paths may belong to any root)."""
        if not path:
            return None
        p = Path(path)
        if p.is_absolute():
            try:
                cand = p.resolve()
            except (OSError, ValueError):
                return None
            return cand if any(str(cand).startswith(str(root)) for root in self.roots) else None
        for root in self.roots:
            try:
                cand = (root / p).resolve()
                if str(cand).startswith(str(root)) and cand.exists():
                    return cand
            except (OSError, ValueError):
                continue
        # not found in any root: return primary-root candidate (for write/list)
        return (self.root / p).resolve()

    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        path = payload.get("path", "")
        if act == "file.list":
            root = self._resolve(path) or self.root
            items = []
            for f in sorted(root.rglob("*"))[:200]:
                st = f.stat()
                items.append({"path": str(f.relative_to(self.root)) if f.is_relative_to(self.root) else str(f),
                              "size": st.st_size,
                              "dir": f.is_dir(),
                              "mtime": st.st_mtime})
            return {"ok": True, "files": items}
        f = self._resolve(path)
        if f is None:
            return {"ok": False, "error": f"path outside sandbox: {path}"}
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
