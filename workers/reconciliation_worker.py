from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    PurchaseOrder,
    Refund,
    WorkflowExecution,
    now_utc,
)
from sanocea.packages.exceptions import ExceptionService
from sanocea.packages.runtime import Services

"""Phase 4.5: the missing always-on recovery mechanism identified by the consolidation audit.

Required hierarchy, enforced here and nowhere else: READ/RECONCILE EXTERNAL TRUTH FIRST -> determine
whether the mutation actually occurred -> retry ONLY when genuinely safe (external truth confirms
nothing happened). Never blindly repeats an external mutation. Bounded retries with terminal escalation
- a human-required exception is never retried forever.

This is a plain callable class, not a Temporal workflow - it is meant to be invoked periodically (a
systemd timer / cron / simple `while True: sleep` loop calling run_once() per merchant is enough for
this phase; wiring an actual Temporal workflow around it is tracked debt, not built here).
"""


@dataclass
class RecoveryCounters:
    exceptions_scanned: int = 0
    reconciled_from_external_truth: int = 0
    retried_after_confirming_no_prior_effect: int = 0
    left_open_within_retry_bounds: int = 0
    escalated_terminal: int = 0
    stale_workflows_flagged: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "exceptions_scanned": self.exceptions_scanned,
            "reconciled_from_external_truth": self.reconciled_from_external_truth,
            "retried_after_confirming_no_prior_effect": self.retried_after_confirming_no_prior_effect,
            "left_open_within_retry_bounds": self.left_open_within_retry_bounds,
            "escalated_terminal": self.escalated_terminal,
            "stale_workflows_flagged": self.stale_workflows_flagged,
        }


class ReconciliationWorker:
    def __init__(
        self,
        store,
        services: Services,
        *,
        supplier_connector=None,
        payment_connector=None,
        max_attempts: int = 5,
        stale_workflow_after: timedelta = timedelta(hours=24),
    ) -> None:
        self.store = store
        self.services = services
        self.supplier_connector = supplier_connector
        self.payment_connector = payment_connector
        self.max_attempts = max_attempts
        self.stale_workflow_after = stale_workflow_after
        self.exceptions = ExceptionService(store)
        self.audit = AuditLedger(store)

    def run_once(self, merchant_id: str) -> RecoveryCounters:
        counters = RecoveryCounters()
        self._recover_uncertain_po_submissions(merchant_id, counters)
        self._recover_uncertain_refund_executions(merchant_id, counters)
        self._flag_stale_workflows(merchant_id, counters)
        return counters

    # --- Purchase order submission uncertainty -----------------------------------------------------

    def _recover_uncertain_po_submissions(self, merchant_id: str, counters: RecoveryCounters) -> None:
        open_exceptions = self.store.list_where(ExceptionRecord, merchant_id, category="po_submission_uncertain", status="open")
        # Process at most ONE PO per distinct object_id per run_once() call - a PO can have accumulated
        # several open exceptions from prior runs, but re-attempting it more than once in a single pass
        # would multiply mutation attempts artificially within one invocation.
        exceptions_by_po: dict[str, list[ExceptionRecord]] = {}
        for exc in open_exceptions:
            if exc.object_id:
                exceptions_by_po.setdefault(exc.object_id, []).append(exc)

        for po_id, exceptions_for_po in exceptions_by_po.items():
            counters.exceptions_scanned += len(exceptions_for_po)
            po = self.store.get(PurchaseOrder, merchant_id, po_id)
            if po.status == "SUBMITTED":
                # Already resolved by some other path (e.g. a direct retry that succeeded) - close out
                # every accumulated exception for this PO, not just one.
                for exc in exceptions_for_po:
                    self._resolve(exc)
                counters.reconciled_from_external_truth += 1
                continue
            attempts = self._attempt_count(merchant_id, "po_submission_uncertain", po_id)
            if attempts >= self.max_attempts:
                for exc in exceptions_for_po:
                    self._escalate_terminal(merchant_id, exc, f"PO submission recovery exhausted {attempts} attempts - human review required, will not retry again")
                counters.escalated_terminal += 1
                continue
            # READ EXTERNAL TRUTH FIRST.
            external = self.supplier_connector.find_purchase_order(merchant_id, po_id) if self.supplier_connector else None
            if external:
                po.external_ref = external["external_ref"]
                po.status = "SUBMITTED"
                self.store.put(po)
                for exc in exceptions_for_po:
                    self._resolve(exc)
                self.audit.record(merchant_id=merchant_id, actor="reconciliation_worker", source="recovery", action="po_submission_reconciled_from_external_truth", object_type="PurchaseOrder", object_id=po_id, result="SUBMITTED")
                counters.reconciled_from_external_truth += 1
                continue
            # External truth confirms nothing happened - retry is safe (submit_purchase_order's own
            # idempotency_key makes this a no-op if it somehow already succeeded elsewhere).
            result = self.services.procurement.submit_purchase_order(merchant_id, po_id)
            if result.status == "SUBMITTED":
                for exc in exceptions_for_po:
                    self._resolve(exc)
                counters.retried_after_confirming_no_prior_effect += 1
            else:
                # The retry itself will have created ONE fresh po_submission_uncertain exception (via
                # submit_purchase_order's own TimeoutError handling); resolve the OLDER ones already
                # accounted for by this attempt so they don't keep being recounted on every future run.
                for exc in exceptions_for_po:
                    self._resolve(exc)
                counters.left_open_within_retry_bounds += 1

    # --- Refund execution uncertainty ---------------------------------------------------------------

    def _recover_uncertain_refund_executions(self, merchant_id: str, counters: RecoveryCounters) -> None:
        refunds = [r for r in self.store.list(Refund, merchant_id) if r.status == "mutation_uncertain"]
        for refund in refunds:
            counters.exceptions_scanned += 1
            attempts = self._attempt_count(merchant_id, "external_mutation_uncertain", refund.id)
            open_exc = next((e for e in self.store.list_where(ExceptionRecord, merchant_id, category="external_mutation_uncertain", status="open") if e.object_id == refund.id), None)
            if attempts >= self.max_attempts:
                if open_exc:
                    self._escalate_terminal(merchant_id, open_exc, f"refund execution recovery exhausted {attempts} attempts - human review required")
                    counters.escalated_terminal += 1
                continue
            # READ EXTERNAL TRUTH FIRST.
            external = None
            if self.payment_connector is not None and hasattr(self.payment_connector, "find_refund"):
                external = self.payment_connector.find_refund(merchant_id, refund.order_id, refund.amount, refund.currency)
            if external:
                self.services.post_order.reconcile_refund(merchant_id, refund.id, external["external_ref"])
                if open_exc:
                    self._resolve(open_exc)
                self.audit.record(merchant_id=merchant_id, actor="reconciliation_worker", source="recovery", action="refund_reconciled_from_external_truth", object_type="Refund", object_id=refund.id, result="reconciled")
                counters.reconciled_from_external_truth += 1
                continue
            # Not found externally - safe to retry the mutation (idempotent business-key dedup at the
            # simulated connector, same as the original execute_refund call).
            result = self.services.post_order.execute_refund(merchant_id, refund.id)
            if result.status in {"reconciled", "completed", "external_confirmed"}:
                if open_exc:
                    self._resolve(open_exc)
                counters.retried_after_confirming_no_prior_effect += 1
            else:
                counters.left_open_within_retry_bounds += 1

    # --- Stale workflow detection --------------------------------------------------------------------

    def _flag_stale_workflows(self, merchant_id: str, counters: RecoveryCounters) -> None:
        cutoff = now_utc() - self.stale_workflow_after
        for wf in self.store.list(WorkflowExecution, merchant_id):
            if wf.status != "running":
                continue
            if wf.sync.updated_at and wf.sync.updated_at >= cutoff:
                continue
            already_flagged = any(
                e.object_id == wf.id and e.category == "stale_workflow_execution" and e.status == "open"
                for e in self.store.list_where(ExceptionRecord, merchant_id, category="stale_workflow_execution")
            )
            if already_flagged:
                continue
            self.exceptions.create(
                merchant_id=merchant_id, category="stale_workflow_execution",
                message=f"WorkflowExecution {wf.id} ({wf.workflow_type}) has been 'running' with no update since {wf.sync.updated_at} - stuck orchestration, needs review",
                object_id=wf.id, severity="warning", remediation_options=["inspect_workflow", "manual_advance", "terminate"],
            )
            counters.stale_workflows_flagged += 1

    # --- Helpers ---------------------------------------------------------------------------------------

    def _attempt_count(self, merchant_id: str, category: str, object_id: str) -> int:
        return len([e for e in self.store.list_where(ExceptionRecord, merchant_id, category=category) if e.object_id == object_id])

    def _resolve(self, exc: ExceptionRecord) -> None:
        exc.status = "resolved"
        self.store.put(exc)

    def _escalate_terminal(self, merchant_id: str, exc: ExceptionRecord, message: str) -> None:
        exc.severity = "critical"
        exc.remediation_options = ["human_review_required"]
        self.store.put(exc)
        self.audit.record(merchant_id=merchant_id, actor="reconciliation_worker", source="recovery", action="terminal_escalation", object_type="ExceptionRecord", object_id=exc.object_id, result="escalated", error=message)
