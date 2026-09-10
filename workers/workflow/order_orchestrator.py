from __future__ import annotations

from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import Order

from .engine import FakeTemporalEngine


class OrderOrchestrator:
    """Phase 4.5: replaces the dead end at workflow bookkeeping.

    Drop-in replacement for FakeTemporalEngine wherever a `workflow` object with
    start_or_signal_order()/signal() is expected (ShopifyConnector, apps/api). It does NOT contain
    business logic itself - it only SEQUENCES a call into the existing PostOrderOperationsService after
    the underlying workflow engine records the event, and advances WorkflowExecution.current_step to
    reflect ORCHESTRATION PROGRESS. Business truth (was inventory actually reserved, for how much)
    lives on the canonical Order/Inventory/ExceptionRecord rows the domain service writes - never on
    the workflow record itself. This is the explicit distinction Phase 4.5 requires: workflow state
    describes orchestration progress, canonical entities describe business truth.
    """

    def __init__(self, store, engine: FakeTemporalEngine, post_order_service) -> None:
        self.store = store
        self.engine = engine
        self.post_order = post_order_service
        self.audit = AuditLedger(store)

    def start_or_signal_order(self, merchant_id: str, order_id: str, event: dict[str, Any]):
        execution = self.engine.start_or_signal_order(merchant_id, order_id, event)
        self._advance(merchant_id, order_id, execution)
        return execution

    def signal(self, workflow_id: str, event: dict[str, Any]) -> None:
        return self.engine.signal(workflow_id, event)

    def _advance(self, merchant_id: str, order_id: str, execution) -> None:
        order = self.store.get(Order, merchant_id, order_id)
        if order.payment_status != "paid" or self.post_order is None:
            return
        result = self.post_order.reserve_inventory_for_order(merchant_id, order)
        execution.current_step = "inventory_shortfall" if result.get("any_shortfall") else "inventory_reserved"
        self.store.put(execution)
        self.audit.record(
            merchant_id=merchant_id, actor="workflow", source="order_orchestrator",
            action="inventory_reservation_step", object_type="Order", object_id=order_id,
            workflow_id=execution.id, result=execution.current_step,
        )
