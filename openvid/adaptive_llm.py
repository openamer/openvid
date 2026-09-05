"""OPENVID LocalLLM with hot-swappable LoRA adapters.

The model stays resident; adapters load/unload via peft without reloading
weights. learnloop activates the newest accepted adapter automatically.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


class AdaptiveLocalLLM:
    """Ollama-compatible fast path + optional local LoRA-tuned path.

    Strategy: if an accepted adapter exists (learning/state.json), serve with
    the tuned model; else fall back to Ollama. Hot-swaps on adapter change.
    """
    name = "local-llm"
    topics = ["user.input"]

    def __init__(self, home: Path, ollama_url: str = "http://127.0.0.1:11434",
                 ollama_model: str = "qwen3.5:2b", torch_pref: bool = True):
        self.home = Path(home)
        self.ollama_url = ollama_url.rstrip("/")
        self.ollama_model = ollama_model
        self.torch_pref = torch_pref
        self._tuned = None          # peft model, resident
        self._tok = None
        self._active_adapter = None
        self._lock = threading.Lock()

    # -- adapter management ------------------------------------------------
    def _state(self) -> dict:
        f = self.home / "learning" / "state.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        return {}

    def _ensure_adapter(self):
        """Load/reload the adapter if state points somewhere new."""
        st = self._state()
        adapter = st.get("active_adapter")
        if not adapter or adapter == self._active_adapter:
            return
        if not Path(adapter).exists():
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from peft import PeftModel
        base = "Qwen/Qwen2.5-0.5B-Instruct"
        with self._lock:
            self._tok = AutoTokenizer.from_pretrained(base)
            model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float32)
            self._tuned = PeftModel.from_pretrained(model, adapter).eval()
            self._active_adapter = adapter
            print(f"[local-llm] adapter live: {adapter}", flush=True)

    def active(self) -> str:
        return self._active_adapter or f"ollama:{self.ollama_model}"

    # -- serving ------------------------------------------------------------
    def handle(self, payload: dict) -> dict:
        eid = payload.get("_eid")
        text = payload.get("text", "")
        if self.torch_pref:
            try:
                self._ensure_adapter()
            except Exception as e:
                print(f"[local-llm] adapter load failed: {e}", flush=True)
        if self._tuned is not None:
            out = self._serve_tuned(text)
        else:
            out = self._serve_ollama(text)
        if eid:
            out["reply_to"] = eid
        return out

    def _serve_tuned(self, text: str) -> dict:
        import torch
        ids = self._tok(f"User: {text}\nAssistant:", return_tensors="pt")
        with torch.no_grad():
            out = self._tuned.generate(**ids, max_new_tokens=200, do_sample=False,
                                       pad_token_id=self._tok.eos_token_id)
        return {"ok": True, "worker": self.name,
                "text": self._tok.decode(out[0][ids["input_ids"].shape[1]:],
                                         skip_special_tokens=True).strip()}

    def _serve_ollama(self, text: str) -> dict:
        import urllib.request
        try:
            body = json.dumps({"model": self.ollama_model, "stream": False,
                               "messages": [{"role": "user", "content": text}]}).encode()
            req = urllib.request.Request(self.ollama_url + "/api/chat", data=body,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read())
            return {"ok": True, "worker": self.name,
                    "text": (d.get("message", {}).get("content") or "").strip()}
        except Exception as e:
            return {"ok": False, "worker": self.name, "text": f"local-llm offline: {e}"}
