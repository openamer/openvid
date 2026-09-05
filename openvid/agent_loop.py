"""OPENVID AgentLoopWorker — the heart: LLM decides which tools to use.

Protocol: the model receives a tool list and answers either
    {"tool": "<name>", "args": {...}}        -> kernel dispatches agent.action,
                                                result is appended, loop continues
    {"answer": "..."}                         -> final answer, loop ends
Anything unparseable is treated as the answer (robust to chatty models).

This is a plain worker: it claims user.input, runs the loop synchronously,
and publishes the final result with reply_to so kernel.ask()/frontends see it.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request

TOOLS_PROMPT = """You are OPENVID, an autonomous agent. You can use tools.

Available tools:
{tools}

Respond with ONLY one JSON object, nothing else:
  {{"tool": "<tool-name>", "args": {{...}}}}   to call a tool
  {{"answer": "<final answer to the user>"}}   when you are done

Tool results will be given to you as JSON after each call.
User request:
{user}
"""

TOOL_SPECS = {
    "shell.run": {"args": {"cmd": "shell command to execute"},
                  "desc": "Run a shell command and get stdout/stderr/rc."},
    "browser.open": {"args": {"url": "url to open (empty = list tabs)"},
                     "desc": "Open a URL in Chrome (CDP) or list tabs."},
    "browser.eval": {"args": {"expr": "JavaScript to run in the page"},
                     "desc": "Evaluate JavaScript in the active Chrome tab."},
    "memory.write": {"args": {"data": "object to remember"},
                     "desc": "Persist a fact/episode to memory."},
    "memory.read": {"args": {"query": "search text"},
                    "desc": "Search episodic memory."},
    "skill.get": {"args": {"name": "skill name"},
                  "desc": "Load a skill's instructions."},
    "skill.list": {"args": {}, "desc": "List available skills."},
    "file.read": {"args": {"path": "relative or allowed-absolute path"},
                  "desc": "Read a text file (max 20k chars)."},
    "file.write": {"args": {"path": "file path", "content": "text to write"},
                   "desc": "Create/overwrite a text file."},
    "file.list": {"args": {"path": "directory (empty = root)"},
                  "desc": "List files recursively."},
    "file.delete": {"args": {"path": "file or dir"},
                    "desc": "Delete a file or directory (sandboxed)."},
    "web.fetch": {"args": {"url": "http(s) url"},
                  "desc": "Fetch a web page, returns readable text."},
    "web.search": {"args": {"query": "search terms"},
                   "desc": "Web search (DuckDuckGo), returns top results."},
    "sys.info": {"args": {}, "desc": "CPU/RAM/disk/uptime snapshot of this machine."},
}


class AgentLoopWorker:
    name = "agent-loop"
    topics = ["user.input"]

    def __init__(self, base_url: str, api_key: str, model: str,
                 max_steps: int = 6, step_timeout: float = 90.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_steps = max_steps
        self.step_timeout = step_timeout

    # -- llm ---------------------------------------------------------------
    def _chat(self, messages: list[dict]) -> str:
        body = json.dumps({"model": self.model, "messages": messages}).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=self.step_timeout) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]

    # -- tool dispatch via the kernel bus (gate applies!) -------------------
    def _call_tool(self, bus, tool: str, args: dict, eid: str) -> dict:
        rid = f"al-{eid}-{time.time_ns()}"
        bus.publish("agent.action", {"action": tool, "_rid": rid, **args})
        deadline = time.time() + 60
        while time.time() < deadline:
            for ev in bus.claim("worker.result", "agent-loop"):
                p = ev["payload"]
                bus.complete(ev["id"])
                if p.get("_rid") == rid:
                    return p
                # unrelated result: re-publish so it isn't lost
                bus.publish("worker.result", p)
            time.sleep(0.1)
        return {"ok": False, "error": "tool timeout"}

    # -- the loop ------------------------------------------------------------
    def handle(self, payload: dict) -> dict:
        from .bus import Bus  # injected via .attach(bus) by bootstrap
        bus = self.bus
        eid = payload.get("_eid") or ""
        user = payload.get("text", "")

        tool_list = "\n".join(
            f'- {t}: {s["desc"]} args: {json.dumps(s["args"])}'
            for t, s in TOOL_SPECS.items())
        system = TOOLS_PROMPT.format(tools=tool_list, user=user)
        messages = [{"role": "user", "content": system}]
        sid = payload.get("session_id", "default")
        if getattr(self, "sessions", None):
            history = self.sessions.context(sid)
            if history:
                # compact history into one context block to keep the tool prompt first
                hist = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in history)
                messages.append({"role": "user",
                                 "content": "Conversation so far:\n" + hist})
        trace = []

        try:
            out = self._run_loop(messages, bus, eid, user, sid, trace)
        except Exception as e:
            out = {"ok": False, "worker": self.name,
                   "text": f"agent error: {type(e).__name__}: {e}"}
        if eid:
            out["reply_to"] = eid
        return out

    def _run_loop(self, messages, bus, eid, user, sid, trace):
        for step in range(self.max_steps):
            raw = self._chat(messages)
            m = re.search(r"\{.*\}", raw, re.S)
            try:
                decision = json.loads(m.group(0)) if m else {"answer": raw}
            except json.JSONDecodeError:
                decision = {"answer": raw}

            if "answer" in decision and "tool" not in decision:
                out = {"ok": True, "worker": self.name, "text": decision["answer"],
                       "steps": step + 1, "trace": trace}
                if getattr(self, "sessions", None):
                    self.sessions.append(sid, "user", user)
                    self.sessions.append(sid, "assistant", decision["answer"])
                return out

            tool = decision.get("tool", "")
            if tool not in TOOL_SPECS:
                result = {"ok": False, "error": f"unknown tool: {tool}"}
            else:
                result = self._call_tool(bus, tool, decision.get("args", {}), eid)
            result_slim = {k: result.get(k) for k in ("ok", "stdout", "stderr",
                                                      "rc", "error", "value", "text", "hits")
                           if k in result}
            trace.append({"tool": tool, "args": decision.get("args", {}),
                          "result": result_slim})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user",
                             "content": "Tool result:\n" + json.dumps(result_slim, ensure_ascii=False)})
        else:
            out = {"ok": False, "worker": self.name,
                   "text": "(max steps reached without final answer)",
                   "steps": self.max_steps, "trace": trace}
        return out

    def attach(self, bus):
        self.bus = bus
        return self

    def attach_sessions(self, sessions):
        from .sessions import Sessions
        self.sessions: Sessions = sessions
        return self
