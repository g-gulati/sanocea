from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "lifecycle-test"
PG_BIN = Path(r"C:\Program Files\PostgreSQL\17\bin")
TEMPORAL_EXE = ROOT / ".local" / "bin" / "temporal" / "temporal.exe"
MINIO_EXE = ROOT / ".local" / "bin" / "minio.exe"


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int | None
    elapsed_seconds: float
    stdout_tail: str = ""
    stderr_tail: str = ""
    timed_out: bool = False


@dataclass
class ServiceResult:
    name: str
    pid: int | None = None
    started: bool = False
    healthy: bool = False
    stopped: bool = False
    exited: bool = False
    port_released: bool = False
    start_error: str | None = None
    stop_error: str | None = None


@dataclass
class CycleResult:
    cycle: int
    postgres: ServiceResult
    temporal: ServiceResult
    minio: ServiceResult
    validation_ok: bool = False
    postgres_recovery_detected: bool = False
    orphan_processes: list[dict[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0


@dataclass
class LifecycleReport:
    run_id: str
    ports: dict[str, int]
    direct_initdb: CommandResult
    error_87_seen: bool
    error_87_explanation: str
    cycles: list[CycleResult]
    postgres_recovery_occurrences: int
    verdict: str
    runtime_seconds: float


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=5)
    parser.add_argument("--report", default=str(ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "local_lifecycle_report.json"))
    args = parser.parse_args()
    started = time.perf_counter()
    run_id = uuid.uuid4().hex[:10]
    run_dir = RUNTIME / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ports = {"postgres": free_port(), "temporal": free_port(), "minio": free_port(), "minio_console": free_port()}
    pg_data = run_dir / "postgres"
    initdb = run([str(PG_BIN / "initdb.exe"), "-D", str(pg_data), "-U", "sanocea", "--auth=trust", "--encoding=UTF8"], timeout=90)
    error_87_seen = "error code 87" in initdb.stdout_tail or "error code 87" in initdb.stderr_tail
    cycles: list[CycleResult] = []
    if initdb.exit_code != 0:
        report = LifecycleReport(
            run_id=run_id,
            ports=ports,
            direct_initdb=initdb,
            error_87_seen=error_87_seen,
            error_87_explanation=error_87_explanation(error_87_seen, initdb.exit_code),
            cycles=[],
            postgres_recovery_occurrences=0,
            verdict="FAIL",
            runtime_seconds=round(time.perf_counter() - started, 3),
        )
        write_report(args.report, report)
        print(json.dumps(asdict(report), indent=2))
        return 1

    for cycle in range(1, args.cycles + 1):
        cycle_started = time.perf_counter()
        pg = PostgresService(pg_data, ports["postgres"], run_dir / f"postgres-{cycle}.log")
        temporal = ProcessService(
            "temporal",
            [
                str(TEMPORAL_EXE),
                "server",
                "start-dev",
                "--ip",
                "127.0.0.1",
                "--port",
                str(ports["temporal"]),
                "--db-filename",
                str(run_dir / "temporal.db"),
            ],
            ports["temporal"],
            run_dir / f"temporal-{cycle}.out.log",
            run_dir / f"temporal-{cycle}.err.log",
            lambda: run([str(TEMPORAL_EXE), "operator", "cluster", "health", "--address", f"127.0.0.1:{ports['temporal']}"], timeout=10).exit_code == 0,
        )
        minio_env = os.environ.copy()
        minio_env["MINIO_ROOT_USER"] = "sanocea-dev"
        minio_env["MINIO_ROOT_PASSWORD"] = "sanocea-dev-secret"
        minio = ProcessService(
            "minio",
            [
                str(MINIO_EXE),
                "server",
                str(run_dir / "minio"),
                "--address",
                f"127.0.0.1:{ports['minio']}",
                "--console-address",
                f"127.0.0.1:{ports['minio_console']}",
            ],
            ports["minio"],
            run_dir / f"minio-{cycle}.out.log",
            run_dir / f"minio-{cycle}.err.log",
            lambda: http_ok(f"http://127.0.0.1:{ports['minio']}/minio/health/live"),
            env=minio_env,
        )
        validation_ok = False
        recovery = False
        try:
            pg_result = pg.start()
            temporal_result = temporal.start()
            minio_result = minio.start()
            validation_ok = validate_postgres(ports["postgres"], cycle)
            recovery = pg.recovery_detected()
        finally:
            minio_result = minio.stop()
            temporal_result = temporal.stop()
            pg_result = pg.stop()
        cycle_result = CycleResult(
            cycle=cycle,
            postgres=pg_result,
            temporal=temporal_result,
            minio=minio_result,
            validation_ok=validation_ok,
            postgres_recovery_detected=recovery,
            orphan_processes=owned_children(os.getpid()),
            elapsed_seconds=round(time.perf_counter() - cycle_started, 3),
        )
        cycles.append(cycle_result)
        write_partial(args.report, run_id, ports, initdb, error_87_seen, cycles, started)

    failures = [
        cycle
        for cycle in cycles
        if not (
            cycle.postgres.healthy
            and cycle.postgres.stopped
            and cycle.postgres.exited
            and cycle.postgres.port_released
            and cycle.temporal.healthy
            and cycle.temporal.stopped
            and cycle.temporal.exited
            and cycle.temporal.port_released
            and cycle.minio.healthy
            and cycle.minio.stopped
            and cycle.minio.exited
            and cycle.minio.port_released
            and cycle.validation_ok
            and not cycle.postgres_recovery_detected
            and not cycle.orphan_processes
        )
    ]
    report = LifecycleReport(
        run_id=run_id,
        ports=ports,
        direct_initdb=initdb,
        error_87_seen=error_87_seen,
        error_87_explanation=error_87_explanation(error_87_seen, initdb.exit_code),
        cycles=cycles,
        postgres_recovery_occurrences=sum(1 for cycle in cycles if cycle.postgres_recovery_detected),
        verdict="PASS" if not failures else "FAIL",
        runtime_seconds=round(time.perf_counter() - started, 3),
    )
    write_report(args.report, report)
    print(json.dumps(asdict(report), indent=2))
    return 0 if report.verdict == "PASS" else 1


class PostgresService:
    def __init__(self, data_dir: Path, port: int, log: Path) -> None:
        self.data_dir = data_dir
        self.port = port
        self.log = log
        self.pid: int | None = None

    def start(self) -> ServiceResult:
        result = ServiceResult(name="postgres")
        cmd = [
            str(PG_BIN / "pg_ctl.exe"),
            "-D",
            str(self.data_dir),
            "-l",
            str(self.log),
            "-o",
            f"-p {self.port} -h 127.0.0.1",
            "start",
            "-w",
        ]
        started = run(cmd, timeout=45)
        result.started = started.exit_code == 0
        self.pid = read_postmaster_pid(self.data_dir)
        result.pid = self.pid
        result.healthy = wait_until(lambda: pg_ready(self.port) and validate_postgres(self.port, 0), timeout=30)
        if not result.started or not result.healthy:
            result.start_error = started.stderr_tail or started.stdout_tail
        return result

    def stop(self) -> ServiceResult:
        result = ServiceResult(name="postgres", pid=self.pid, started=True, healthy=False)
        stopped = run([str(PG_BIN / "pg_ctl.exe"), "-D", str(self.data_dir), "stop", "-m", "fast", "-w"], timeout=45)
        result.stopped = stopped.exit_code == 0
        result.exited = wait_until(lambda: not pid_alive(self.pid), timeout=20)
        result.port_released = wait_until(lambda: port_free(self.port), timeout=20)
        if not result.stopped:
            result.stop_error = stopped.stderr_tail or stopped.stdout_tail
        return result

    def recovery_detected(self) -> bool:
        if not self.log.exists():
            return False
        text = self.log.read_text(errors="ignore")
        return "automatic recovery in progress" in text or "database system was interrupted" in text


class ProcessService:
    def __init__(self, name: str, command: list[str], port: int, stdout: Path, stderr: Path, health, env: dict[str, str] | None = None) -> None:
        self.name = name
        self.command = command
        self.port = port
        self.stdout = stdout
        self.stderr = stderr
        self.health = health
        self.env = env
        self.process: subprocess.Popen | None = None

    def start(self) -> ServiceResult:
        result = ServiceResult(name=self.name)
        out = self.stdout.open("wb")
        err = self.stderr.open("wb")
        self.process = subprocess.Popen(self.command, stdout=out, stderr=err, cwd=str(ROOT), env=self.env)
        result.pid = self.process.pid
        result.started = True
        result.healthy = wait_until(self.health, timeout=45)
        if not result.healthy:
            result.start_error = tail(self.stderr) or tail(self.stdout)
        return result

    def stop(self) -> ServiceResult:
        pid = self.process.pid if self.process else None
        result = ServiceResult(name=self.name, pid=pid, started=True, healthy=False)
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                result.stop_error = "graceful terminate timed out; killed owned process"
                self.process.kill()
                self.process.wait(timeout=20)
        result.stopped = True
        result.exited = not pid_alive(pid)
        result.port_released = wait_until(lambda: port_free(self.port), timeout=20)
        return result


def validate_postgres(port: int, cycle: int) -> bool:
    sql = f"CREATE TABLE IF NOT EXISTS lifecycle_probe (cycle integer primary key, observed_at timestamptz default now()); INSERT INTO lifecycle_probe (cycle) VALUES ({cycle}) ON CONFLICT DO NOTHING; SELECT count(*) FROM lifecycle_probe;"
    return run([str(PG_BIN / "psql.exe"), "-h", "127.0.0.1", "-p", str(port), "-U", "sanocea", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", sql], timeout=15).exit_code == 0


def pg_ready(port: int) -> bool:
    return run([str(PG_BIN / "pg_isready.exe"), "-h", "127.0.0.1", "-p", str(port), "-U", "sanocea"], timeout=10).exit_code == 0


def run(command: list[str], timeout: int) -> CommandResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
        return CommandResult(command, completed.returncode, round(time.perf_counter() - started, 3), tail_text(completed.stdout), tail_text(completed.stderr), False)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(command, None, round(time.perf_counter() - started, 3), tail_text(exc.stdout or ""), tail_text(exc.stderr or ""), True)


def wait_until(fn, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(0.5)
    return False


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def port_free(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def http_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def read_postmaster_pid(data_dir: Path) -> int | None:
    path = data_dir / "postmaster.pid"
    if not path.exists():
        return None
    try:
        return int(path.read_text().splitlines()[0])
    except Exception:
        return None


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        result = run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], timeout=5)
        return result.exit_code == 0 and str(pid) in (result.stdout_tail or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def owned_children(parent_pid: int) -> list[dict[str, str]]:
    if sys.platform != "win32":
        return []
    result = run(["wmic", "process", "where", f"(ParentProcessId={parent_pid})", "get", "ProcessId,CommandLine", "/FORMAT:CSV"], timeout=5)
    rows = []
    for line in (result.stdout_tail or "").splitlines():
        if not line.strip() or line.startswith("Node,"):
            continue
        parts = line.split(",", 2)
        if len(parts) == 3:
            rows.append({"pid": parts[2].strip(), "command": parts[1].strip()})
    return rows


def tail(path: Path) -> str:
    if not path.exists():
        return ""
    return tail_text(path.read_text(errors="ignore"))


def tail_text(text: str | bytes, limit: int = 4000) -> str:
    if isinstance(text, bytes):
        text = text.decode(errors="ignore")
    return text[-limit:]


def error_87_explanation(seen: bool, exit_code: int | None) -> str:
    if not seen:
        return "No Windows restricted-token error observed in direct initdb run."
    if exit_code == 0:
        return "Direct initdb emitted Windows restricted-token error 87 while attempting PostgreSQL's privilege-drop re-exec, but initialization completed successfully under the current user token. It is noisy/non-fatal here; nested PowerShell is not required to reproduce it."
    return "Direct initdb emitted Windows restricted-token error 87 and failed; lifecycle cannot be certified on this host without resolving Windows token restrictions."


def write_partial(path: str, run_id: str, ports: dict[str, int], initdb: CommandResult, error_87_seen: bool, cycles: list[CycleResult], started: float) -> None:
    report = LifecycleReport(
        run_id=run_id,
        ports=ports,
        direct_initdb=initdb,
        error_87_seen=error_87_seen,
        error_87_explanation=error_87_explanation(error_87_seen, initdb.exit_code),
        cycles=cycles,
        postgres_recovery_occurrences=sum(1 for cycle in cycles if cycle.postgres_recovery_detected),
        verdict="RUNNING",
        runtime_seconds=round(time.perf_counter() - started, 3),
    )
    write_report(path, report)


def write_report(path: str, report: LifecycleReport) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
