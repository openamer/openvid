"""OPENVID FineTune — export bus history as an SFT dataset.

Turns the audit trail (user.input -> answer results) into JSONL
{"messages":[{role,content},...]} ready for any trainer (TRL, axolotl, our own).
Every conversation the system has becomes training fuel — with the user's
data, on the user's machine.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def export_sft(bus_db: Path, out: Path, min_len: int = 1) -> dict:
    """Pair each answered user.input with its result text."""
    db = sqlite3.connect(str(bus_db))
    inputs = {r[0]: r[1] for r in db.execute(
        "SELECT eid, payload FROM events WHERE topic='user.input' AND done=1")}
    pairs = []
    for (payload,) in db.execute(
            "SELECT payload FROM events WHERE topic='worker.result' AND done=1"):
        p = json.loads(payload)
        eid = p.get("reply_to")
        if not eid or eid not in inputs:
            continue
        user = json.loads(inputs[eid]).get("text", "")
        answer = p.get("text", "")
        if len(user) >= min_len and answer and not answer.startswith("("):
            pairs.append({"messages": [
                {"role": "user", "content": user},
                {"role": "assistant", "content": answer}]})
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    return {"pairs": len(pairs), "out": str(out)}
