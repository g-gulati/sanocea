from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import Merchant
from sanocea.workers.workflow.temporal_runtime import TASK_QUEUE, RealOrderWorkflow, TemporalRuntime


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN") or not os.environ.get("SANOCEA_RUN_TEMPORAL_TESTS"),
    reason="requires real Postgres DSN and SANOCEA_RUN_TEMPORAL_TESTS=1",
)


def _terminate_owned_process(process: subprocess.Popen, timeout: int = 10) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def test_real_temporal_retry_timer_signal_and_replay():
    asyncio.run(_run_real_temporal_retry_timer_signal_and_replay())


async def _run_real_temporal_retry_timer_signal_and_replay():
    pg = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    pg.migrate()
    suffix = uuid4().hex
    state_dir = Path("sanocea/tests/fixtures/phase11_merchant/generated/temporal_state") / suffix
    state_dir.mkdir(parents=True, exist_ok=True)
    merchant_id = f"tmp_mer_A_{suffix}"
    order_id = f"tmp_ord_{suffix}"
    pg.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="A", display_name="A"))

    runtime = TemporalRuntime(os.environ["SANOCEA_TEMPORAL_TARGET"], TASK_QUEUE)
    client = await runtime.connect()
    worker = await runtime.start_worker(client)
    async with worker:
        workflow_id = f"tmp-order-workflow-{suffix}"
        handle_id = await runtime.start_or_signal_order(
            client,
            workflow_id,
            {
                "dsn": os.environ["SANOCEA_PG_DSN"],
                "merchant_id": merchant_id,
                "order_id": order_id,
                "state_dir": str(state_dir),
                "timer_seconds": 2,
                "fail_times": 1,
            },
        )
        await runtime.start_or_signal_order(
            client,
            workflow_id,
            {
                "dsn": os.environ["SANOCEA_PG_DSN"],
                "merchant_id": merchant_id,
                "order_id": order_id,
                "state_dir": str(state_dir),
            },
        )
        handle = client.get_workflow_handle(handle_id)
        await asyncio.sleep(3)
        await handle.signal(RealOrderWorkflow.approve, "operator")
        result = await handle.result()
        assert result["status"] == "completed"
        actions = [a.action for a in pg.list_audit(merchant_id)]
        assert "workflow_started" in actions
        assert "timer_fired" in actions
        assert "approval_resumed" in actions


def test_temporal_worker_process_restart_preserves_workflow():
    asyncio.run(_run_temporal_worker_process_restart_preserves_workflow())


async def _run_temporal_worker_process_restart_preserves_workflow():
    pg = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    pg.migrate()
    suffix = uuid4().hex
    state_dir = Path("sanocea/tests/fixtures/phase11_merchant/generated/temporal_state") / suffix
    state_dir.mkdir(parents=True, exist_ok=True)
    merchant_id = f"restart_mer_{suffix}"
    order_id = f"restart_ord_{suffix}"
    pg.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Restart", display_name="Restart"))
    runtime = TemporalRuntime(os.environ["SANOCEA_TEMPORAL_TARGET"], TASK_QUEUE)
    client = await runtime.connect()
    first_worker = None

    env = os.environ.copy()
    env["SANOCEA_TEMPORAL_TARGET"] = os.environ["SANOCEA_TEMPORAL_TARGET"]
    try:
        first_worker = subprocess.Popen(
            [sys.executable, "-m", "sanocea.workers.workflow.worker_process"],
            cwd=str(Path(__file__).parents[3]),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        await asyncio.sleep(2)
        workflow_id = f"restart-workflow-{suffix}"
        handle_id = await runtime.start_or_signal_order(
            client,
            workflow_id,
            {
                "dsn": os.environ["SANOCEA_PG_DSN"],
                "merchant_id": merchant_id,
                "order_id": order_id,
                "state_dir": str(state_dir),
                "timer_seconds": 5,
                "fail_times": 0,
            },
        )
        await asyncio.sleep(1)
        _terminate_owned_process(first_worker)
        second_worker = subprocess.Popen(
            [sys.executable, "-m", "sanocea.workers.workflow.worker_process"],
            cwd=str(Path(__file__).parents[3]),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            await asyncio.sleep(6)
            handle = client.get_workflow_handle(handle_id)
            await handle.signal(RealOrderWorkflow.approve, "operator")
            result = await handle.result()
            assert result["status"] == "completed"
            actions = [a.action for a in pg.list_audit(merchant_id)]
            assert "workflow_started" in actions
            assert "timer_fired" in actions
            assert "approval_resumed" in actions
        finally:
            _terminate_owned_process(second_worker)
    finally:
        if first_worker is not None:
            _terminate_owned_process(first_worker)
