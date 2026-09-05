"""OPENVID CronWorker — durable scheduler on top of the bus.

Jobs live in <home>/cron.json: [{name, schedule, prompt, enabled}].
schedule: interval seconds (int) or "daily@HH:MM". Each tick publishes a
user.input event, so jobs flow through the same pipeline as chat.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path


class CronWorker:
    name = "cron"
    topics = []  # runs its own thread, not bus-driven

    def __init__(self, home: Path, bus):
        self.file = Path(home) / "cron.json"
        self.bus = bus
        self._next: dict[str, float] = {}
        self._stop = threading.Event()

    # -- job store -------------------------------------------------------
    def _load(self) -> list[dict]:
        if self.file.exists():
            return json.loads(self.file.read_text(encoding="utf-8"))
        return []

    def _save(self, jobs: list[dict]):
        self.file.write_text(json.dumps(jobs, indent=2, ensure_ascii=False),
                             encoding="utf-8")

    def handle_control(self, payload: dict) -> dict:
        """Direct API for the CLI/HTTP layer (not bus-routed)."""
        act = payload.get("action")
        jobs = self._load()
        if act == "cron.add":
            job = {"name": payload["name"], "schedule": payload["schedule"],
                   "prompt": payload["prompt"], "enabled": True,
                   "last_run": None}
            jobs = [j for j in jobs if j["name"] != job["name"]] + [job]
            self._save(jobs)
            return {"ok": True, "name": job["name"]}
        if act == "cron.remove":
            self._save([j for j in jobs if j["name"] != payload["name"]])
            return {"ok": True}
        if act == "cron.list":
            return {"ok": True, "jobs": jobs}
        if act == "cron.toggle":
            for j in jobs:
                if j["name"] == payload["name"]:
                    j["enabled"] = not j["enabled"]
            self._save(jobs)
            return {"ok": True}
        return {"ok": False, "error": f"unsupported: {act}"}

    # -- scheduler thread -------------------------------------------------
    def _parse(self, schedule) -> float:
        """Return interval seconds."""
        if isinstance(schedule, (int, float)):
            return float(schedule)
        m = re.match(r"daily@(\d{1,2}):(\d{2})$", str(schedule))
        if m:
            now = time.localtime()
            target = time.mktime((now.tm_year, now.tm_mon, now.tm_mday,
                                  int(m.group(1)), int(m.group(2)), 0, 0, 0, -1))
            return max(60.0, target - time.mktime(now) + 86400) % 86400 or 86400
        raise ValueError(f"bad schedule: {schedule}")

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.is_set():
            try:
                for job in self._load():
                    if not job.get("enabled"):
                        continue
                    nxt = self._next.get(job["name"], 0)
                    if time.time() >= nxt:
                        self.bus.publish("user.input", {
                            "text": job["prompt"], "_eid": "",
                            "cron": job["name"], "ts": time.time()})
                        self._next[job["name"]] = time.time() + self._parse(job["schedule"])
            except Exception:
                pass  # scheduler must never die; errors surface in results
            self._stop.wait(10)
