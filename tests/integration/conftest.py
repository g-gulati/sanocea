from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

from sanocea.tests.unit.conftest import phase0


def pytest_sessionfinish(session, exitstatus) -> None:
    if os.environ.get("SANOCEA_TEST_DIAGNOSTICS") != "1":
        return
    diagnostics = {
        "exitstatus": int(exitstatus),
        "threads": [
            {"name": thread.name, "daemon": thread.daemon, "alive": thread.is_alive()}
            for thread in threading.enumerate()
        ],
        "asyncio_tasks": [],
        "child_processes": _child_processes(),
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            diagnostics["asyncio_tasks"] = [repr(task) for task in asyncio.all_tasks(loop)]
    except RuntimeError:
        diagnostics["asyncio_tasks"] = []
    path = Path(os.environ.get("SANOCEA_TEST_DIAGNOSTICS_PATH", "sanocea/tests/fixtures/phase11_merchant/generated/integration_diagnostics.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")


def _child_processes() -> list[dict[str, object]]:
    if sys.platform != "win32":
        return []
    try:
        output = subprocess.check_output(
            [
                "wmic",
                "process",
                "where",
                f"(ParentProcessId={os.getpid()})",
                "get",
                "ProcessId,CommandLine",
                "/FORMAT:CSV",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        return []
    rows = []
    for line in output.splitlines():
        if not line.strip() or line.startswith("Node,"):
            continue
        parts = line.split(",", 2)
        if len(parts) == 3:
            rows.append({"pid": parts[2].strip(), "command": parts[1].strip()})
    return rows
