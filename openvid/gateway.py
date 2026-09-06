"""OPENVID Gateway — one interface, many messaging channels.

A channel is a thin adapter class with `poll() -> [(chat_id, text)]` and
`send(chat_id, text)`. Built-in: Telegram (long-poll), Discord (bot token,
REST polling via gateway-less simple mode), generic Webhook (inbound POST
-> /ask, reply as JSON).

Enable channels via env: OPENVID_TG_TOKEN / OPENVID_DISCORD_TOKEN /
OPENVID_WEBHOOK_PORT. Disabled channels are skipped silently.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request


def _http_json(url: str, payload: dict | None = None, timeout: int = 30) -> dict:
    if payload is None:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


class TelegramChannel:
    name = "telegram"

    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.offset = 0

    def poll(self):
        data = _http_json(f"{self.base}/getUpdates?timeout=25&offset={self.offset}",
                          timeout=35)
        out = []
        for u in data.get("result", []):
            self.offset = u["update_id"] + 1
            m = u.get("message") or {}
            text = (m.get("text") or "").strip()
            chat = m.get("chat", {}).get("id")
            if text and chat is not None:
                out.append((chat, text))
        return out

    def send(self, chat_id, text):
        _http_json(f"{self.base}/sendMessage",
                   {"chat_id": chat_id, "text": text[:4000]})


class DiscordChannel:
    """Simple REST polling mode: reads replies to the bot via /channels/<id>/messages.
    Requires OPENVID_DISCORD_CHANNEL_ID. (Full gateway bot = phase 2.)"""
    name = "discord"

    def __init__(self, token: str, channel_id: str):
        self.headers = {"Authorization": f"Bot {token}",
                        "Content-Type": "application/json"}
        self.channel = channel_id
        self.last_id = None

    def poll(self):
        url = (f"https://discord.com/api/v10/channels/{self.channel}/messages"
               f"?limit=5")
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            msgs = json.loads(r.read())
        out = []
        for m in reversed(msgs):
            if m["author"]["bot"]:
                continue
            if self.last_id and m["id"] <= self.last_id:
                continue
            self.last_id = m["id"]
            out.append((m["channel_id"], m["content"].strip()))
        return out

    def send(self, chat_id, text):
        url = f"https://discord.com/api/v10/channels/{chat_id}/messages"
        req = urllib.request.Request(url, data=json.dumps({"content": text[:2000]}).encode(),
                                     headers=self.headers)
        urllib.request.urlopen(req, timeout=15)


class WebhookChannel:
    """Inbound HTTP: POST /hook {chat_id, text} -> queued; replies collected
    via GET /hook/<chat_id>/reply. Zero dependencies, works with n8n/IFTTT."""
    name = "webhook"

    def __init__(self, port: int, inbound, outbound):
        self.port = port
        self._in = inbound    # callable(chat_id, text)
        self._out = outbound  # callable(chat_id) -> reply text or None
        self._replies: dict = {}

    def start(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        gw = self
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                if self.path != "/hook":
                    return self._code(404)
                n = int(self.headers.get("Content-Length", 0))
                d = json.loads(self.rfile.read(n) or b"{}")
                cid, text = d.get("chat_id"), (d.get("text") or "").strip()
                if not cid or not text:
                    return self._code(400)
                gw._in(cid, text)
                self._code(200)
            def do_GET(self):
                if self.path.startswith("/hook/"):
                    parts = self.path.strip("/").split("/")
                    cid = parts[1]
                    reply = gw._out(cid)
                    return self._code(200, {"reply": reply})
                self._code(404)
            def _code(self, c, body=None):
                b = json.dumps(body or {"ok": True}).encode()
                self.send_response(c)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            def log_message(self, *a): pass
        threading.Thread(
            target=lambda: ThreadingHTTPServer(("127.0.0.1", self.port), H).serve_forever(),
            daemon=True).start()


import threading  # noqa: E402


class Gateway:
    def __init__(self, ask_fn, session_of=None):
        self.ask = ask_fn                  # fn(text, session_id) -> answer
        self.channels = []
        self._pending: dict[str, str] = {}  # webhook replies

    def add(self, channel):
        self.channels.append(channel)
        if isinstance(channel, WebhookChannel):
            channel.start(self._webhook_in, self._webhook_out)

    def _webhook_in(self, cid, text):
        self._pending[f"webhook:{cid}"] = text

    def _webhook_out(self, cid):
        return self._pending.pop(f"webhook:{cid}", None)

    def run(self):
        print(f"gateway: {len(self.channels)} channel(s) active", flush=True)
        while True:
            for ch in self.channels:
                if isinstance(ch, WebhookChannel):
                    key = "webhook"
                    # webhook text arrives via HTTP thread; poll queue
                    for k in [k for k in list(self._pending) if k.startswith("webhook:")]:
                        continue  # replies consumed on GET; inbound handled inline
                    continue
                try:
                    for chat_id, text in ch.poll():
                        sid = f"{ch.name}:{chat_id}"
                        answer = self.ask(text, session_id=sid)
                        ch.send(chat_id, answer)
                except Exception as e:
                    print(f"gateway[{ch.name}]: {e}", flush=True)
                    time.sleep(3)
            time.sleep(0.3)


def run_gateway(ask_fn):
    g = Gateway(ask_fn)
    if os.environ.get("OPENVID_TG_TOKEN"):
        g.add(TelegramChannel(os.environ["OPENVID_TG_TOKEN"]))
    if os.environ.get("OPENVID_DISCORD_TOKEN") and os.environ.get("OPENVID_DISCORD_CHANNEL_ID"):
        g.add(DiscordChannel(os.environ["OPENVID_DISCORD_TOKEN"],
                             os.environ["OPENVID_DISCORD_CHANNEL_ID"]))
    if os.environ.get("OPENVID_WEBHOOK_PORT"):
        g.add(WebhookChannel(int(os.environ["OPENVID_WEBHOOK_PORT"]), None, None))
    if not g.channels:
        print("gateway: no channels configured (set OPENVID_TG_TOKEN etc.)")
        return
    g.run()
