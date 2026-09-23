from __future__ import annotations

import asyncio
import os
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker


TASK_QUEUE = "sanocea-phase05"


@activity.defn
async def audit_transition(input: dict[str, Any]) -> dict[str, Any]:
    from sanocea.packages.audit import AuditLedger
    from sanocea.packages.domain_contract.postgres_store import PostgresStore

    store = PostgresStore(input["dsn"])
    event = AuditLedger(store).record(
        merchant_id=input["merchant_id"],
        actor="workflow",
        source="temporal",
        action=input["action"],
        object_type=input["object_type"],
        object_id=input.get("object_id"),
        workflow_id=input.get("workflow_id"),
        result=input.get("result", "completed"),
        error=input.get("error"),
    )
    return {"audit_event_id": event.id}


@activity.defn
async def create_exception(input: dict[str, Any]) -> dict[str, Any]:
    from sanocea.packages.audit import AuditLedger
    from sanocea.packages.domain_contract.models import ExceptionRecord
    from sanocea.packages.domain_contract.postgres_store import PostgresStore

    store = PostgresStore(input["dsn"])
    exc = ExceptionRecord(
        merchant_id=input["merchant_id"],
        severity="error",
        category=input["category"],
        message=input["message"],
        object_id=input.get("object_id"),
    )
    store.put(exc)
    AuditLedger(store).record(
        merchant_id=input["merchant_id"],
        actor="workflow",
        source="temporal",
        action="exception_created",
        object_type="Exception",
        object_id=exc.id,
        result="open",
        error=input["message"],
    )
    return {"exception_id": exc.id}


@activity.defn
async def flaky_activity(input: dict[str, Any]) -> str:
    marker = input["marker"]
    path = input["state_dir"] + "/" + marker + ".attempts"
    from pathlib import Path

    p = Path(path)
    attempts = int(p.read_text() if p.exists() else "0") + 1
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(attempts))
    if attempts <= int(input.get("fail_times", 0)):
        raise RuntimeError("simulated transient activity failure")
    return "ok"


@workflow.defn
class RealOrderWorkflow:
    def __init__(self) -> None:
        self.approved = False
        self.external_events: list[dict[str, Any]] = []

    @workflow.run
    async def run(self, input: dict[str, Any]) -> dict[str, Any]:
        retry = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=5)
        await workflow.execute_activity(
            audit_transition,
            input | {"action": "workflow_started", "object_type": "Order", "object_id": input["order_id"]},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )
        await workflow.execute_activity(
            flaky_activity,
            {
                "state_dir": input["state_dir"],
                "marker": input["workflow_id"],
                "fail_times": input.get("fail_times", 0),
            },
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )
        await workflow.sleep(timedelta(seconds=input.get("timer_seconds", 1)))
        await workflow.execute_activity(
            audit_transition,
            input | {"action": "timer_fired", "object_type": "Order", "object_id": input["order_id"]},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )
        await workflow.wait_condition(lambda: self.approved)
        await workflow.execute_activity(
            audit_transition,
            input | {"action": "approval_resumed", "object_type": "Order", "object_id": input["order_id"]},
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )
        return {"status": "completed", "events": len(self.external_events)}

    @workflow.signal
    async def approve(self, actor: str) -> None:
        self.approved = True

    @workflow.signal
    async def external_event(self, event: dict[str, Any]) -> None:
        self.external_events.append(event)


class TemporalRuntime:
    """Phase 4.6 decision (see docs/architecture/phase4.6-commerce-core-completion.md, "Real Temporal
    decision"): NOT wired into the live order/support/finance/procurement paths. This class - and
    RealOrderWorkflow above - remain a validated CAPABILITY PROOF (a real Temporal worker connecting to
    a real server, executing real activities/timers/signals/retries) kept for the day a genuinely
    long-running, durable, multi-day workflow actually appears in Sanocea's scope (e.g. a multi-week B2B
    procurement SLA with real wall-clock waits spanning process restarts). Every operational workflow
    Sanocea runs today is either a short synchronous sequence (order intake, refund/return/cancellation
    approval) or an already-solved bounded-retry-with-terminal-escalation background job
    (workers/reconciliation_worker.py) - neither needs a durable orchestration engine. Do not read
    apps/api/app.py's optional /health Temporal check as evidence Temporal is authoritative for any
    order/business state - it only proves connectivity to a Temporal server when SANOCEA_TEMPORAL_TARGET
    is configured, entirely independent of whether anything routes through it."""

    def __init__(self, target_host: str = "127.0.0.1:7233", task_queue: str = TASK_QUEUE) -> None:
        self.target_host = target_host
        self.task_queue = task_queue

    async def connect(self) -> Client:
        return await Client.connect(self.target_host)

    async def start_worker(self, client: Client) -> Worker:
        return Worker(
            client,
            task_queue=self.task_queue,
            workflows=[RealOrderWorkflow],
            activities=[audit_transition, create_exception, flaky_activity],
        )

    async def start_or_signal_order(self, client: Client, workflow_id: str, input: dict[str, Any]) -> str:
        try:
            handle = await client.start_workflow(
                RealOrderWorkflow.run,
                input | {"workflow_id": workflow_id},
                id=workflow_id,
                task_queue=self.task_queue,
            )
            return handle.id
        except WorkflowAlreadyStartedError:
            handle = client.get_workflow_handle(workflow_id)
            await handle.signal(RealOrderWorkflow.external_event, {"type": "duplicate_or_later_event"})
            return handle.id

    async def health(self) -> dict[str, str]:
        client = await self.connect()
        await client.service_client.check_health()
        return {"temporal": "ok"}


async def run_worker_until_cancelled(target_host: str = "127.0.0.1:7233") -> None:
    runtime = TemporalRuntime(target_host)
    client = await runtime.connect()
    worker = await runtime.start_worker(client)
    await worker.run()


def main() -> None:
    asyncio.run(run_worker_until_cancelled(os.environ.get("SANOCEA_TEMPORAL_TARGET", "127.0.0.1:7233")))


if __name__ == "__main__":
    main()
