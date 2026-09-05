"""Tests for files (full access), web, skills, agent-loop logic."""
import json
from pathlib import Path

import pytest

from openvid.files import FileWorker
from openvid.web import WebWorker
from openvid.skills import SkillWorker
from openvid.agent_loop import AgentLoopWorker, TOOL_SPECS
from openvid.bus import Bus
from openvid.sessions import Sessions


@pytest.fixture
def fw():
    return FileWorker(Path(tempfile_root()))


def tempfile_root():
    import tempfile
    return tempfile.mkdtemp(prefix="openvid-test-")


class TestFilesFullAccess:
    def test_absolute_anywhere(self, fw, tmp_path):
        f = tmp_path / "outside.txt"
        f.write_text("free", encoding="utf-8")
        r = fw.handle({"action": "file.read", "path": str(f)})
        assert r["ok"] and "free" in r["content"]

    def test_write_outside(self, fw, tmp_path):
        f = tmp_path / "w.txt"
        r = fw.handle({"action": "file.write", "path": str(f), "content": "x"})
        assert r["ok"] and f.exists()

    def test_list_arbitrary(self, fw, tmp_path):
        r = fw.handle({"action": "file.list", "path": str(tmp_path)})
        assert r["ok"] and isinstance(r["files"], list)

    def test_delete(self, fw, tmp_path):
        f = tmp_path / "del.txt"
        f.write_text("x", encoding="utf-8")
        assert fw.handle({"action": "file.delete", "path": str(f)})["ok"]
        assert not f.exists()


class TestWeb:
    def test_fetch_real(self):
        r = WebWorker().handle({"action": "web.fetch", "url": "https://example.com"})
        assert r["ok"] and "Example" in r["content"]

    def test_reject_file_scheme(self):
        assert not WebWorker().handle({"action": "web.fetch", "url": "file:///x"})["ok"]


class TestSkills:
    def test_roundtrip_and_guards(self, tmp_path):
        s = SkillWorker(tmp_path)
        s.handle({"action": "skill.write", "name": "t", "content": "body"})
        assert "body" in s.handle({"action": "skill.get", "name": "t"})["content"]
        assert not s.handle({"action": "skill.get", "name": "../../x"}).get("ok")


class TestAgentLoopLogic:
    def test_tool_specs_complete(self):
        need = {"shell.run", "file.write", "web.search", "memory.read",
                "browser.open", "sys.info", "skill.get", "swarm.status"}
        assert need <= set(TOOL_SPECS)

    def test_fake_llm_tool_then_answer(self, tmp_path):
        class FakeW(AgentLoopWorker):
            def __init__(self):
                self.calls = 0; self.max_steps = 6
                self.bus = Bus(tmp_path / "b.db")
                self.sessions = Sessions(tmp_path)
            def _chat(self, messages):
                self.calls += 1
                if self.calls == 1:
                    return '{"tool": "memory.write", "args": {"data": {"k": "v"}}}'
                return '{"answer": "FINAL"}'
            def _call_tool(self, bus, tool, args, eid):
                return {"ok": True}
        out = FakeW().handle({"text": "go", "_eid": "E1", "session_id": "s"})
        assert out["ok"] and out["reply_to"] == "E1" and out["text"] == "FINAL"
        assert len(out["trace"]) == 1 and out["trace"][0]["result"]["ok"]

    def test_error_path_returns_reply_to(self, tmp_path):
        class DeadW(AgentLoopWorker):
            def __init__(self):
                self.max_steps = 2
                self.bus = Bus(tmp_path / "b.db")
                self.sessions = Sessions(tmp_path)
            def _chat(self, messages):
                raise ConnectionError("dead endpoint")
        out = DeadW().handle({"text": "x", "_eid": "E9"})
        assert "agent error" in out["text"] and out["reply_to"] == "E9"

    def test_max_steps_termination(self, tmp_path):
        class LoopW(AgentLoopWorker):
            def __init__(self):
                self.calls = 0; self.max_steps = 2
                self.bus = Bus(tmp_path / "b.db")
                self.sessions = Sessions(tmp_path)
            def _chat(self, messages):
                self.calls += 1
                return '{"tool": "sys.info", "args": {}}'
            def _call_tool(self, bus, tool, args, eid):
                return {"ok": True}
        out = LoopW().handle({"text": "x"})
        assert "max steps" in out["text"]
