"""OPENVID LearnLoop — the closing loop: traffic -> SFT -> LoRA -> live model.

Nightly worker: exports verified conversations, fine-tunes a fresh adapter,
and atomically points the local model worker at the newest adapter that beat
its predecessor on the training loss (guard: loss must improve, else keep old).
"""
from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

from .finetune import export_sft


class LearnLoop:
    def __init__(self, home: Path, bus, min_pairs: int = 8,
                 epochs: int = 40, interval: float = 86400.0):
        self.home = Path(home)
        self.bus = bus
        self.min_pairs = min_pairs
        self.epochs = epochs
        self.interval = interval
        self.dir = self.home / "learning"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.dir / "state.json"
        self._stop = threading.Event()

    def _state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        return {"runs": 0, "best_loss": None, "active_adapter": None}

    def _save_state(self, s: dict):
        self.state_file.write_text(json.dumps(s, indent=2), encoding="utf-8")

    def cycle(self) -> dict:
        from .trainer import train
        state = self._state()
        # 1. export fresh verified traffic
        sft = self.dir / f"sft_run{state['runs'] + 1}.jsonl"
        exp = export_sft(self.home / "bus.db", sft)
        if exp["pairs"] < self.min_pairs:
            return {"skipped": f"only {exp['pairs']} pairs (< {self.min_pairs})"}
        # 2. train on a merged dataset (old + new)
        merged = self.dir / "sft_merged.jsonl"
        old = state.get("last_sft")
        with merged.open("w", encoding="utf-8") as out:
            seen = set()
            for f in ([old] if old else []) + [str(sft)]:
                if f and Path(f).exists():
                    for line in Path(f).read_text(encoding="utf-8").splitlines():
                        if line and line not in seen:
                            seen.add(line); out.write(line + "\n")
        run = self.dir / f"adapter_run{state['runs'] + 1}"
        report = train(merged, run, epochs=self.epochs)
        # 3. accept only if loss improved on best
        best = state.get("best_loss")
        if best is not None and report["last_loss"] >= best:
            shutil.rmtree(run, ignore_errors=True)
            state["runs"] += 1; state["last_sft"] = str(sft)
            self._save_state(state)
            return {"rejected": f"loss {report['last_loss']:.3f} >= best {best:.3f}"}
        state.update({"runs": state["runs"] + 1, "best_loss": report["last_loss"],
                      "active_adapter": str(run), "last_sft": str(sft)})
        self._save_state(state)
        return {"accepted": True, "adapter": str(run),
                "loss": report["last_loss"], "pairs": report["pairs"]}

    def start(self):
        def loop():
            while not self._stop.is_set():
                try:
                    r = self.cycle()
                    (self.dir / "last_cycle.json").write_text(
                        json.dumps(r, indent=2), encoding="utf-8")
                except Exception:
                    pass
                self._stop.wait(self.interval)
        threading.Thread(target=loop, daemon=True).start()

    def stop(self):
        self._stop.set()
