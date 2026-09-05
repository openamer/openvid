"""OPENVID Swarm — multi-machine mesh over HTTP.

Each node runs the HTTP API (phase 5). A swarm node forwards actions to peer
nodes when local workers can't or shouldn't handle them. Peers are plain URLs:
    OPENVID_PEERS=http://192.168.178.23:8765,http://laptop:8765

Design: no central coordinator. Any node can fan out; results carry
`node` so answers are attributable. Dead peers are skipped with a health
probe, not retried blindly.
"""
from __future__ import annotations

import json
import os
import urllib.request


class SwarmWorker:
    name = "swarm"
    topics = ["agent.action"]
    actions = {"swarm.status", "swarm.ask", "swarm.run"}

    def __init__(self, peers: list[str] | None = None):
        if peers is None:
            raw = os.environ.get("OPENVID_PEERS", "")
            peers = [p.strip() for p in raw.split(",") if p.strip()]
        self.peers = [p.rstrip("/") for p in peers]

    def _post(self, url: str, path: str, payload: dict, timeout: float = 90.0):
        req = urllib.request.Request(
            url + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def _health(self, url: str, timeout: float = 4.0) -> bool:
        try:
            with urllib.request.urlopen(url + "/health", timeout=timeout) as r:
                return json.loads(r.read()).get("status") == "alive"
        except Exception:
            return False

    def handle(self, payload: dict) -> dict:
        action = payload.get("action", "")
        if action == "swarm.status":
            return {"ok": True, "peers": [
                {"url": p, "alive": self._health(p)} for p in self.peers]}
        if action in ("swarm.ask", "swarm.run"):
            path = "/ask" if action == "swarm.ask" else "/action"
            last = "unknown"
            for peer in self.peers:
                if not self._health(peer):
                    continue
                try:
                    r = self._post(peer, path, payload.get("payload", payload))
                    r["node"] = peer
                    return {"ok": True, "result": r}
                except Exception as e:
                    last = str(e)
            return {"ok": False, "error": f"no peer reachable ({last})" if self.peers
                    else "no peers configured (OPENVID_PEERS)"}
        return {"ok": False, "error": f"unsupported: {action}"}
