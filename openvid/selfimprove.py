"""OPENVID SelfImprovement — nightly loop that mines failed results.

Scans worker.result events with ok=false, clusters by error signature,
and proposes skill patches (written to skills/_proposals/ for human review
unless auto_approve is set in config).
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import Counter
from pathlib import Path


def _sig(error: str) -> str:
    """Normalize an error to a cluster signature."""
    e = re.sub(r"[0-9a-f]{8,}", "<id>", str(error))
    e = re.sub(r"\d+", "N", e)
    return e[:120]


class SelfImprovement:
    def __init__(self, home: Path, bus, auto_approve: bool = False):
        self.home = Path(home)
        self.bus = bus
        self.auto_approve = auto_approve
        self.proposals = self.home / "skills" / "_proposals"
        self.proposals.mkdir(parents=True, exist_ok=True)
        self.report = self.home / "improvement_report.json"
        self._stop = threading.Event()

    def scan_once(self) -> dict:
        """Claim failed results, cluster, write proposals."""
        fails = []
        for ev in self.bus.claim("worker.result", "selfimprove", limit=200):
            p = ev["payload"]
            self.bus.complete(ev["id"])
            if not p.get("ok", True) and p.get("error"):
                fails.append(p)
        clusters = Counter(_sig(f["error"]) for f in fails)
        proposals = []
        for sig, n in clusters.most_common(10):
            if n < 2:
                continue  # one-off errors are noise
            name = re.sub(r"[^\w]+", "_", sig)[:40].strip("_") or "err"
            skill = (f"---\ndescription: auto-proposal for recurring error "
                     f"(seen {n}x)\n---\n# Error pattern\n\n{sig}\n\n"
                     f"# Proposed handling\n1. Detect this error signature.\n"
                     f"2. Retry once with backoff.\n3. If persisting, "
                     f"escalate to user with context.\n")
            target = self.proposals / f"{name}.md"
            if not target.exists():  # never overwrite human edits
                target.write_text(skill, encoding="utf-8")
                proposals.append(name)
        report = {"scanned": len(fails), "clusters": len(clusters),
                  "proposed": proposals, "ts": time.time()}
        self.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if self.auto_approve and proposals:
            sk = self.home / "skills"
            for name in proposals:
                (self.proposals / f"{name}.md").rename(sk / f"{name}.md")
        return report

    def start(self, interval: float = 3600.0):
        def loop():
            while not self._stop.is_set():
                try:
                    self.scan_once()
                except Exception:
                    pass
                self._stop.wait(interval)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._stop.set()
