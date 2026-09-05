"""OPENVID Bus — durable SQLite event queue.

Every message is a row. Workers poll their subscribed topics. WAL mode keeps
readers and writers concurrent. Events are never deleted (audit trail) except
by explicit compaction.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    eid TEXT UNIQUE NOT NULL,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at REAL NOT NULL,
    claimed_by TEXT,
    claimed_at REAL,
    done INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_topic_done ON events(topic, done);
"""


class Bus:
    def __init__(self, path: str | Path = "openvid.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def publish(self, topic: str, payload: dict) -> str:
        eid = uuid.uuid4().hex[:16]
        with self._lock:
            self._db.execute(
                "INSERT INTO events (eid, topic, payload, created_at) VALUES (?,?,?,?)",
                (eid, topic, json.dumps(payload, ensure_ascii=False), time.time()),
            )
            self._db.commit()
        return eid

    def claim(self, topic: str, worker: str, limit: int = 1) -> list[dict]:
        """Atomically claim pending events for this worker."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, eid, payload FROM events "
                "WHERE topic=? AND done=0 AND (claimed_by IS NULL OR claimed_at < ?) "
                "ORDER BY id LIMIT ?",
                (topic, time.time() - 60, limit),
            ).fetchall()
            out = []
            for rid, eid, payload in rows:
                self._db.execute(
                    "UPDATE events SET claimed_by=?, claimed_at=? WHERE id=?",
                    (worker, time.time(), rid),
                )
                out.append({"id": rid, "eid": eid, "payload": json.loads(payload)})
            self._db.commit()
        return out

    def complete(self, event_id: int, result: dict | None = None):
        with self._lock:
            self._db.execute("UPDATE events SET done=1 WHERE id=?", (event_id,))
            self._db.commit()
        if result is not None:
            self.publish("worker.result", result)

    def pending(self, topic: str) -> int:
        row = self._db.execute(
            "SELECT COUNT(*) FROM events WHERE topic=? AND done=0", (topic,)
        ).fetchone()
        return row[0]

    def close(self):
        self._db.close()
