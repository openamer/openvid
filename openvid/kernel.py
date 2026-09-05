"""OPENVID Kernel — event loop + worker registry + permission gate."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from .bus import Bus


class Kernel:
    def __init__(self, home: str | Path | None = None):
        self.home = Path(home) if home else Path.home() / ".openvid"
        self.home.mkdir(parents=True, exist_ok=True)
        self.bus = Bus(self.home / "bus.db")
        self.workers: dict[str, object] = {}
        self._threads: list[threading.Thread] = []
        self._running = False
        self.gate = self._load_gate()

    def _load_gate(self) -> dict:
        cfg = self.home / "gate.json"
        if cfg.exists():
            return json.loads(cfg.read_text(encoding="utf-8"))
        default = {
            "allow": ["shell.run", "memory.read", "memory.write", "llm.chat"],
            "confirm": ["shell.rm", "shell.sudo"],
            "deny": []
        }
        cfg.write_text(json.dumps(default, indent=2), encoding="utf-8")
        return default

    def register(self, worker):
        self.workers[worker.name] = worker
        for topic in worker.topics:
            t = threading.Thread(target=self._pump, args=(worker, topic), daemon=True)
            self._threads.append(t)
        return worker

    def _gate_check(self, action: str) -> bool:
        if action in self.gate.get("deny", []):
            return False
        return action in self.gate.get("allow", []) or action not in self.gate.get("confirm", [])

    def _pump(self, worker, topic: str):
        while self._running:
            events = self.bus.claim(topic, worker.name)
            if not events:
                time.sleep(0.15)
                continue
            for ev in events:
                # permission gate for actions
                if topic == "agent.action":
                    action = ev["payload"].get("action", "")
                    if not self._gate_check(action):
                        self.bus.complete(ev["id"], {
                            "eid": ev["eid"], "worker": worker.name,
                            "ok": False, "error": f"denied by gate: {action}",
                        })
                        continue
                try:
                    result = worker.handle(ev["payload"])
                    self.bus.complete(ev["id"], result if isinstance(result, dict) else {"ok": True})
                except Exception as e:  # worker crash must not kill the loop
                    self.bus.complete(ev["id"], {
                        "ok": False, "worker": worker.name,
                        "error": f"{type(e).__name__}: {e}",
                    })

    def start(self):
        self._running = True
        for t in self._threads:
            t.start()

    def stop(self):
        self._running = False

    def ask(self, text: str, timeout: float = 120.0) -> str:
        """Full turn: user.input -> llm -> answer (matched via reply_to)."""
        eid = self.bus.publish("user.input", {"text": text, "_eid": "", "ts": time.time()})
        # stamp eid into the pending event so the llm worker echoes it back
        evs = self.bus.claim("user.input", "kernel-stamp")
        for ev in evs:
            payload = ev["payload"]
            payload["_eid"] = ev["eid"]
            self.bus.complete(ev["id"])
            self.bus.publish("user.input", payload)
        deadline = time.time() + timeout
        while time.time() < deadline:
            for ev in self.bus.claim("worker.result", "kernel"):
                p = ev["payload"]
                self.bus.complete(ev["id"])
                if p.get("reply_to") == eid:
                    return p.get("text", "")
            time.sleep(0.1)
        return "(timeout — no answer in %.0fs)" % timeout
