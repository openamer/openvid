"""Tests: server kernel wiring (agent mode default / opt-out), trainer, learnloop."""
import importlib
import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("OPENVID_LLM_KEY", "test-dummy")

from openvid.server import _build_kernel
from openvid.bus import Bus
from openvid.sessions import Sessions


class TestServerWiring:
    def test_default_agent_mode(self, tmp_path):
        k = _build_kernel(tmp_path)
        assert "agent-loop" in k.workers and "llm" not in k.workers
        assert hasattr(k.workers["agent-loop"], "sessions")

    def test_opt_out_plain_chat(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENVID_AGENT_MODE", "0")
        import openvid.server as srv
        importlib.reload(srv)
        k = srv._build_kernel(tmp_path)
        assert "llm" in k.workers and "agent-loop" not in k.workers
        monkeypatch.delenv("OPENVID_AGENT_MODE")
        importlib.reload(srv)

    def test_all_workers_registered(self, tmp_path):
        k = _build_kernel(tmp_path)
        need = {"shell", "memory", "skills", "files", "web", "sys", "swarm", "agent-loop"}
        assert need <= set(k.workers)


class TestLearnLoop:
    def test_reject_on_regression(self, tmp_path, monkeypatch):
        from openvid.learnloop import LearnLoop
        import openvid.learnloop as llmod
        bus = Bus(tmp_path / "b.db")
        ll = LearnLoop(tmp_path, bus, min_pairs=1)
        ll._save_state({"runs": 2, "best_loss": 0.5, "active_adapter": None})
        monkeypatch.setattr(llmod, "export_sft",
                            lambda db, out, min_len=1: {"pairs": 10, "out": str(out)})
        import openvid.trainer as trmod
        orig = trmod.train
        monkeypatch.setattr(trmod, "train",
                            lambda m, r, epochs=1, **kw: {"pairs": 5, "last_loss": 0.9})
        r = ll.cycle()
        assert "rejected" in r

    def test_accept_on_improvement(self, tmp_path, monkeypatch):
        from openvid.learnloop import LearnLoop
        import openvid.learnloop as llmod
        bus = Bus(tmp_path / "b.db")
        ll = LearnLoop(tmp_path, bus, min_pairs=1)
        monkeypatch.setattr(llmod, "export_sft",
                            lambda db, out, min_len=1: {"pairs": 10, "out": str(out)})
        import openvid.trainer as trmod
        monkeypatch.setattr(trmod, "train",
                            lambda m, r, epochs=1, **kw: {"pairs": 5, "last_loss": 0.1})
        r = ll.cycle()
        assert r.get("accepted") and ll._state()["best_loss"] == 0.1

    def test_skip_below_min_pairs(self, tmp_path):
        from openvid.learnloop import LearnLoop
        ll = LearnLoop(tmp_path, Bus(tmp_path / "b.db"), min_pairs=50)
        assert "skipped" in ll.cycle()


class TestTrainer:
    def test_load_pairs(self):
        from openvid.trainer import load_pairs
        f = Path(REPO) / "examples" / "demo_sft.jsonl"
        pairs = load_pairs(f)
        assert len(pairs) >= 10
        assert all(set(p) == {"prompt", "completion"} for p in pairs)

    def test_load_pairs_empty(self, tmp_path):
        from openvid.trainer import train
        f = tmp_path / "empty.jsonl"
        f.write_text("", encoding="utf-8")
        with pytest.raises(SystemExit):
            train(f, tmp_path / "out")
