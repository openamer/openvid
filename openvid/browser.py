"""OPENVID BrowserWorker — drives a real Chrome via CDP (port 9222).

Actions: browser.open (url -> title+text), browser.eval (js in page).
Reuses an existing Chrome with --remote-debugging-port if present; otherwise
reports a clear error (never launches a visible browser uninvited).
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


def _cdp_json(path: str, port: int = 9222):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read())


class BrowserWorker:
    name = "browser"
    topics = ["agent.action"]
    actions = {"browser.open", "browser.eval"}

    def __init__(self, port: int = 9222):
        self.port = port

    def handle(self, payload: dict) -> dict:
        action = payload.get("action", "")
        if action == "browser.open":
            return self._open(payload.get("url", ""))
        if action == "browser.eval":
            return self._eval(payload.get("expr", ""))
        return {"ok": False, "error": f"unsupported: {action}"}

    def _tabs(self):
        return _cdp_json("/json", self.port)

    def _open(self, url: str) -> dict:
        try:
            tabs = self._tabs()
        except Exception:
            return {"ok": False, "action": action, "error":
                    "no CDP browser on 127.0.0.1:9222 — start Chrome with "
                    "--remote-debugging-port=9222"}
        if not url:
            return {"ok": True, "action": "browser.open", "tabs": [
                {"title": t.get("title"), "url": t.get("url")} for t in tabs if t.get("type") == "page"]}
        tab = next((t for t in tabs if t.get("type") == "page"), None)
        if not tab:
            return {"ok": False, "error": "no page tab open"}
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/json/new?{urllib.parse.quote(url, safe='')}",
                method="PUT")
            with urllib.request.urlopen(req, timeout=10) as r:
                new = json.loads(r.read())
            return {"ok": True, "action": "browser.open", "url": new.get("url"),
                    "title": new.get("title")}
        except Exception as e:
            return {"ok": False, "action": "browser.open", "error": str(e)}

    def _eval(self, expr: str) -> dict:
        import websocket  # websocket-client
        try:
            tabs = self._tabs()
        except Exception:
            return {"ok": False, "action": "browser.eval", "error": "no CDP browser on 9222"}
        tab = next((t for t in tabs if t.get("type") == "page"), None)
        if not tab:
            return {"ok": False, "error": "no page tab"}
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=15)
        try:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": expr, "returnByValue": True}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    r = msg.get("result", {}).get("result", {})
                    return {"ok": True, "action": "browser.eval",
                            "value": r.get("value"), "type": r.get("type")}
        finally:
            ws.close()
