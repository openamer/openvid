"""OPENVID Telegram frontend — a plain bus client via long-polling.

Env: OPENVID_TG_TOKEN (from @BotFather). Each chat maps to one kernel.ask.
Runs standalone: python -m openvid.telegram
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from .kernel import Kernel
from .workers import LLMWorker, MemoryWorker, ShellWorker
from .skills import SkillWorker

API = "https://api.telegram.org/bot{token}/{method}"


def _tg(token: str, method: str, data: dict | None = None, timeout: int = 30):
    url = API.format(token=token, method=method)
    if data is None:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def run(home=None):
    token = os.environ.get("OPENVID_TG_TOKEN", "")
    if not token:
        raise SystemExit("set OPENVID_TG_TOKEN (from @BotFather)")
    k = Kernel(home=home)
    k.register(ShellWorker())
    k.register(MemoryWorker(k.home))
    k.register(SkillWorker(k.home))
    base = os.environ.get("OPENVID_LLM_BASE", "https://openrouter.ai/api/v1")
    key = os.environ.get("OPENVID_LLM_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENVID_LLM_MODEL", "z-ai/glm-5.3-flash")
    if key:
        k.register(LLMWorker(base, key, model))
    k.start()

    print("OPENVID Telegram frontend — long-polling…")
    offset = 0
    while True:
        try:
            updates = _tg(token, "getUpdates",
                          {"offset": offset, "timeout": 25}, timeout=35)
            for u in updates.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                text = (msg.get("text") or "").strip()
                chat = msg.get("chat", {}).get("id")
                if not text or chat is None:
                    continue
                answer = k.ask(text, timeout=230.0)
                _tg(token, "sendMessage",
                    {"chat_id": chat, "text": answer[:4000]})
        except KeyboardInterrupt:
            break
        except Exception as e:
            print("tg loop error:", e)
            time.sleep(3)
    k.stop()


if __name__ == "__main__":
    run()
