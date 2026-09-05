"""Core tests: bus, kernel gate, dispatcher routing, sessions."""
import time

import pytest

from openvid.bus import Bus
from openvid.kernel import Kernel
from openvid.sessions import Sessions
from openvid.workers import ShellWorker, MemoryWorker
from openvid.files import FileWorker


@pytest.fixture
def bus(tmp_path):
    return Bus(tmp_path / "bus.db")


@pytest.fixture
def kernel(tmp_path):
    k = Kernel(home=tmp_path)
    k.register(ShellWorker())
    k.register(MemoryWorker(k.home))
    k.register(FileWorker(k.home))
    k.start()
    yield k
    k.stop()


def wait_result(bus, pred, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for ev in bus.claim("worker.result", "test"):
            p = ev["payload"]
            bus.complete(ev["id"])
            if pred(p):
                return p
        time.sleep(0.05)
    return None


class TestBus:
    def test_publish_claim_complete(self, bus):
        eid = bus.publish("t", {"a": 1})
        evs = bus.claim("t", "w")
        assert len(evs) == 1 and evs[0]["payload"] == {"a": 1}
        bus.complete(evs[0]["id"])
        assert bus.pending("t") == 0

    def test_complete_with_result_publishes(self, bus):
        eid = bus.publish("t", {"x": 1})
        ev = bus.claim("t", "w")[0]
        bus.complete(ev["id"], {"ok": True, "val": 42})
        res = bus.claim("worker.result", "w2")
        assert res and res[0]["payload"]["val"] == 42

    def test_events_survive_reopen(self, bus, tmp_path):
        bus.publish("durable", {"n": 1})
        bus.close()
        bus2 = Bus(tmp_path / "bus.db")
        assert bus2.pending("durable") == 1


class TestGate:
    def test_free_action_allowed(self, kernel):
        assert kernel._gate_check("shell.run") is True

    def test_confirm_action_denied_by_default(self, kernel):
        assert kernel._gate_check("file.delete") is False
        assert kernel._gate_check("shell.sudo") is False

    def test_deny_wins_over_everything(self, kernel):
        kernel.gate["deny"] = ["shell.run"]
        assert kernel._gate_check("shell.run") is False


class TestDispatcher:
    def test_routes_to_right_worker(self, kernel):
        kernel.bus.publish("agent.action", {"action": "shell.run", "cmd": "echo ROUTE_OK"})
        p = wait_result(kernel.bus, lambda p: "ROUTE_OK" in str(p.get("stdout", "")))
        assert p and p["ok"]

    def test_gate_denial_reaches_result(self, kernel):
        kernel.bus.publish("agent.action", {"action": "file.delete", "path": "x"})
        p = wait_result(kernel.bus, lambda p: "denied by gate" in str(p.get("error", "")))
        assert p is not None

    def test_unknown_action_reported(self, kernel):
        kernel.bus.publish("agent.action", {"action": "nonexistent.tool"})
        p = wait_result(kernel.bus, lambda p: "no worker" in str(p.get("error", "")))
        assert p is not None


class TestSessions:
    def test_append_context_roundtrip(self, tmp_path):
        s = Sessions(tmp_path)
        s.append("a", "user", "hi")
        s.append("a", "assistant", "hello")
        ctx = s.context("a")
        assert ctx[0]["role"] == "user" and ctx[1]["content"] == "hello"

    def test_reset(self, tmp_path):
        s = Sessions(tmp_path)
        s.append("a", "user", "x")
        s.reset("a")
        assert s.load("a") == []

    def test_evil_sid_falls_back(self, tmp_path):
        s = Sessions(tmp_path)
        s.append("../evil", "user", "x")
        assert (tmp_path / "sessions" / "default.json").exists()


class TestShellMemoryFlow:
    def test_memory_write_read(self, kernel):
        kernel.bus.publish("agent.action",
                           {"action": "memory.write", "data": {"note": "pytest-marker"}})
        time.sleep(0.5)
        kernel.bus.publish("agent.action",
                           {"action": "memory.read", "query": "pytest-marker"})
        p = wait_result(kernel.bus, lambda p: p.get("hits") is not None)
        assert p and any("pytest-marker" in str(h) for h in p["hits"])
