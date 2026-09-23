from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import (
    Approval,
    ExceptionRecord,
    WorkflowExecution,
)
from sanocea.packages.domain_contract.store import Phase0Store


@dataclass
class OrderWorkflow:
    merchant_id: str
    order_id: str
    workflow_id: str
    status: str = "running"
    step: str = "received"
    attempts: dict[str, int] = field(default_factory=dict)
    signals: list[dict[str, Any]] = field(default_factory=list)


class FakeTemporalEngine:
    """Small deterministic Temporal-shaped harness for Phase 0 tests.

    Production swaps this for Temporal workers; workflows keep durable IDs,
    signals, retries, timers, approval waits, and visible failure semantics.
    """

    def __init__(self, store: Phase0Store) -> None:
        self.store = store
        self.audit = AuditLedger(store)
        self._workflows: dict[str, OrderWorkflow] = {}

    def start_or_signal_order(self, merchant_id: str, order_id: str, event: dict[str, Any]) -> WorkflowExecution:
        business_key = f"order:{order_id}"
        existing = self.store.find_one(WorkflowExecution, merchant_id, business_key=business_key)
        if existing:
            self.signal(existing.temporal_workflow_id, event)
            return existing
        workflow_id = f"order-{merchant_id}-{order_id}"
        wf = OrderWorkflow(merchant_id=merchant_id, order_id=order_id, workflow_id=workflow_id)
        self._workflows[workflow_id] = wf
        execution = WorkflowExecution(
            merchant_id=merchant_id,
            workflow_type="order_lifecycle",
            business_key=business_key,
            temporal_workflow_id=workflow_id,
            status="running",
            current_step="received",
        )
        self.store.put(execution)
        self.audit.record(
            merchant_id=merchant_id,
            actor="workflow",
            source="temporal",
            action="workflow_started",
            object_type="Order",
            object_id=order_id,
            workflow_id=execution.id,
            result="running",
        )
        return execution

    def signal(self, workflow_id: str, event: dict[str, Any]) -> None:
        wf = self._workflows.get(workflow_id)
        if wf:
            wf.signals.append(event)

    def run_step_with_retry(self, workflow_id: str, step: str, fail_times: int = 0) -> str:
        wf = self._workflows[workflow_id]
        attempts = wf.attempts.get(step, 0) + 1
        wf.attempts[step] = attempts
        if attempts <= fail_times:
            self.audit.record(
                merchant_id=wf.merchant_id,
                actor="workflow",
                source="temporal",
                action=f"{step}_retry",
                object_type="Order",
                object_id=wf.order_id,
                result="retrying",
                error="simulated transient failure",
            )
            return "retrying"
        wf.step = step
        self.audit.record(
            merchant_id=wf.merchant_id,
            actor="workflow",
            source="temporal",
            action=step,
            object_type="Order",
            object_id=wf.order_id,
            result="completed",
        )
        return "completed"

    def wait_for_approval(self, merchant_id: str, workflow_id: str, action: str, object_id: str) -> Approval:
        wf = self._workflows[workflow_id]
        wf.status = "waiting_approval"
        approval = Approval(
            merchant_id=merchant_id,
            workflow_id=workflow_id,
            action=action,
            object_id=object_id,
            requested_by="workflow",
        )
        self.store.put(approval)
        self.audit.record(
            merchant_id=merchant_id,
            actor="workflow",
            source="temporal",
            action="approval_requested",
            object_type="Approval",
            object_id=approval.id,
            workflow_id=workflow_id,
            result="pending",
        )
        return approval

    def approve(self, merchant_id: str, approval_id: str, actor: str) -> None:
        approval = self.store.get(Approval, merchant_id, approval_id)
        approval.status = "approved"
        approval.decided_by = actor
        self.store.put(approval)
        if approval.workflow_id in self._workflows:
            self._workflows[approval.workflow_id].status = "running"
        self.audit.record(
            merchant_id=merchant_id,
            actor=actor,
            source="operator",
            action="approval_granted",
            object_type="Approval",
            object_id=approval.id,
            workflow_id=approval.workflow_id,
            result="approved",
        )

    def timer_fired(self, workflow_id: str, name: str) -> None:
        wf = self._workflows[workflow_id]
        self.audit.record(
            merchant_id=wf.merchant_id,
            actor="workflow",
            source="temporal",
            action=f"timer:{name}",
            object_type="Order",
            object_id=wf.order_id,
            result="fired",
        )

    def fail(self, workflow_id: str, message: str) -> ExceptionRecord:
        wf = self._workflows[workflow_id]
        wf.status = "failed"
        exc = ExceptionRecord(
            merchant_id=wf.merchant_id,
            severity="error",
            category="workflow_failure",
            message=message,
            object_id=wf.order_id,
        )
        self.store.put(exc)
        self.audit.record(
            merchant_id=wf.merchant_id,
            actor="workflow",
            source="temporal",
            action="workflow_failed",
            object_type="Exception",
            object_id=exc.id,
            result="failed",
            error=message,
        )
        return exc

    def snapshot(self) -> dict[str, OrderWorkflow]:
        return self._workflows

    def restore(self, snapshot: dict[str, OrderWorkflow]) -> None:
        self._workflows = snapshot

