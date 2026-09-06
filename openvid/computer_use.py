"""OPENVID ComputerUseWorker — desktop control via cua-driver MCP.

Actions:
    cu.screenshot            -> {path} screenshot of frontmost app
    cu.click {element}       -> click SOM element index from last capture
    cu.type {text}           -> type text
    cu.key {keys}            -> key combo (e.g. "ctrl+s")

Talks to the cua-driver HTTP/MCP bridge already proven on this machine
(same stack the OpenAmer desktop uses). Falls back with a clear error if
the driver is not running.
"""
from __future__ import annotations

import json
import subprocess
import time


class ComputerUseWorker:
    name = "computer-use"
    topics = ["agent.action"]
    actions = {"cu.screenshot", "cu.click", "cu.type", "cu.key"}

    def __init__(self, driver_cmd: str | None = None):
        # cua-driver is invoked through the OpenAmer bridge; a direct CLI is
        # assumed available on PATH (`cua-driver`). Override via env.
        import os
        self.cmd = driver_cmd or os.environ.get("OPENVID_CUA_CMD", "cua-driver")

    def _call(self, *args) -> dict:
        try:
            p = subprocess.run([self.cmd, *args], capture_output=True,
                               text=True, timeout=30, encoding="utf-8",
                               errors="replace")
            out = (p.stdout or p.stderr or "").strip()
            try:
                return json.loads(out)
            except json.JSONDecodeError:
                return {"ok": p.returncode == 0, "raw": out[:2000]}
        except FileNotFoundError:
            return {"ok": False, "error": "cua-driver not on PATH — install "
                                          "or set OPENVID_CUA_CMD"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        if act == "cu.screenshot":
            return self._call("capture", "--mode", "som")
        if act == "cu.click":
            el = payload.get("element")
            if el is None:
                return {"ok": False, "error": "element index required"}
            return self._call("click", "--element", str(el))
        if act == "cu.type":
            text = payload.get("text", "")
            if not text:
                return {"ok": False, "error": "text required"}
            return self._call("type", "--text", text)
        if act == "cu.key":
            keys = payload.get("keys", "")
            if not keys:
                return {"ok": False, "error": "keys required"}
            return self._call("key", "--keys", keys)
        return {"ok": False, "error": f"unsupported: {act}"}
