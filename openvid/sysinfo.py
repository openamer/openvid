"""OPENVID SysWorker — machine introspection (CPU/RAM/disk/uptime)."""
from __future__ import annotations

import os
import shutil
import time


class SysWorker:
    name = "sys"
    topics = ["agent.action"]
    actions = {"sys.info"}

    def handle(self, payload: dict) -> dict:
        if payload.get("action") != "sys.info":
            return {"ok": False, "error": "unsupported"}
        info = {"ok": True, "platform": os.name,
                "cpus": os.cpu_count(),
                "uptime_s": round(time.time() - _BOOT, 1)}
        try:
            import psutil
            vm = psutil.virtual_memory()
            info["ram_total_gb"] = round(vm.total / 1e9, 1)
            info["ram_used_pct"] = vm.percent
            info["load"] = [round(x, 2) for x in psutil.getloadavg()] \
                if hasattr(psutil, "getloadavg") else None
        except ImportError:
            info["ram_total_gb"] = None
        du = shutil.disk_usage(os.getcwd())
        info["disk_free_gb"] = round(du.free / 1e9, 1)
        info["disk_total_gb"] = round(du.total / 1e9, 1)
        return info


_BOOT = time.time()
try:
    import psutil
    _BOOT = psutil.boot_time()
except ImportError:
    pass
