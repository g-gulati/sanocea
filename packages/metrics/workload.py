from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkloadCounters:
    products_processed: int = 0
    products_requiring_human_approval: int = 0
    products_requiring_corrective_work: int = 0
    orders_processed: int = 0
    orders_requiring_human_intervention: int = 0
    support_requests_processed: int = 0
    support_requests_automatically_resolved: int = 0
    support_requests_escalated: int = 0
    total_approvals_requested: int = 0
    total_exceptions: int = 0
    connector_failures: int = 0
    duplicate_mutations_observed: int = 0
    cross_tenant_violations: int = 0
    unresolved_workflow_failures: int = 0

    @property
    def automation_rate(self) -> float:
        total = self.products_processed + self.orders_processed + self.support_requests_processed
        automated = (
            max(self.products_processed - self.products_requiring_corrective_work, 0)
            + max(self.orders_processed - self.orders_requiring_human_intervention, 0)
            + self.support_requests_automatically_resolved
        )
        return automated / total if total else 0.0

    @property
    def human_intervention_rate(self) -> float:
        total = self.products_processed + self.orders_processed + self.support_requests_processed
        human = self.products_requiring_human_approval + self.products_requiring_corrective_work + self.orders_requiring_human_intervention + self.support_requests_escalated
        return human / total if total else 0.0

