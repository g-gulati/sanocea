from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--diagnostics-path", default="sanocea/tests/fixtures/phase11_merchant/generated/pytest_bounded_diagnostics.json")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    pytest_args = args.pytest_args
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    if not pytest_args:
        pytest_args = ["sanocea/tests/integration", "-q"]

    diagnostics_path = Path(args.diagnostics_path)
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SANOCEA_TEST_DIAGNOSTICS"] = "1"
    env["SANOCEA_TEST_DIAGNOSTICS_PATH"] = str(diagnostics_path.with_name(diagnostics_path.stem + "_sessionfinish.json"))
    command = [sys.executable, "-m", "pytest", *pytest_args]
    started = time.perf_counter()
    process = subprocess.Popen(command, env=env)
    try:
        exit_code = process.wait(timeout=args.timeout_seconds)
    except subprocess.TimeoutExpired:
        snapshot = {
            "status": "timeout",
            "timeout_seconds": args.timeout_seconds,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "pid": process.pid,
            "command": command,
            "child_processes": child_processes(process.pid),
        }
        diagnostics_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=15)
        print(json.dumps(snapshot, indent=2))
        return 124

    result = {
        "status": "completed",
        "exit_code": exit_code,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "pid": process.pid,
        "command": command,
    }
    diagnostics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return int(exit_code)


def child_processes(parent_pid: int) -> list[dict[str, str]]:
    if sys.platform != "win32":
        return []
    try:
        output = subprocess.check_output(
            [
                "wmic",
                "process",
                "where",
                f"(ParentProcessId={parent_pid})",
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


if __name__ == "__main__":
    raise SystemExit(main())
