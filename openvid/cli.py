"""OPENVID CLI — REPL front-end. Just a client of the kernel."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .kernel import Kernel
from .workers import LLMWorker, MemoryWorker, ShellWorker

BANNER = r"""
  ___             _  __     __
 / _ | ___  ___  (_)/ /__ _/ /_____ ____
/ __ |(_-<(_-< / // / _ `/ / __/ // /
/_/ |_/___/___//_//_/\_,_/_/\__/\_, /
                               /___/  ASI runtime
"""


def _llm_from_env():
    base = os.environ.get("OPENVID_LLM_BASE", "https://openrouter.ai/api/v1")
    key = os.environ.get("OPENVID_LLM_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("OPENVID_LLM_MODEL", "z-ai/glm-5.3-flash")
    return LLMWorker(base, key, model)


def main():
    ap = argparse.ArgumentParser(prog="openvid")
    ap.add_argument("--home", default=None, help="OPENVID home dir")
    ap.add_argument("-p", "--prompt", help="one-shot: run and exit")
    args = ap.parse_args()

    k = Kernel(home=args.home)
    k.register(ShellWorker())
    k.register(MemoryWorker(k.home))
    k.register(_llm_from_env())
    k.start()

    if args.prompt:
        print(k.ask(args.prompt))
        k.stop()
        return

    print(BANNER)
    print(f"home: {k.home}  |  workers: {', '.join(k.workers)}  |  /quit to exit")
    while True:
        try:
            text = input("openvid> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in ("/quit", "/exit"):
            break
        if text.startswith("/run "):
            # direct shell escape, gated like any agent action
            eid = k.bus.publish("agent.action", {"action": "shell.run", "cmd": text[5:]})
            import time as _t
            deadline = _t.time() + 120
            while _t.time() < deadline:
                for ev in k.bus.claim("worker.result", "cli"):
                    if ev["payload"].get("eid") == eid:
                        r = ev["payload"]
                        k.bus.complete(ev["id"])
                        print(r.get("stdout") or r.get("stderr") or "(no output)")
                        break
                else:
                    _t.sleep(0.1)
                    continue
                break
            continue
        if text.startswith("/remember "):
            k.bus.publish("agent.action", {"action": "memory.write",
                                           "data": {"note": text[10:], "ts": __import__("time").time()}})
            print("saved.")
            continue
        print(k.ask(text))
    k.stop()


if __name__ == "__main__":
    main()
