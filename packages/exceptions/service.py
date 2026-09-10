from __future__ import annotations

from enum import Enum

from sanocea.packages.audit import AuditLedger, get_correlation_id
from sanocea.packages.domain_contract.models import ExceptionRecord, now_utc


class ExceptionCategory(str, Enum):
    AMBIGUOUS_PRODUCT_DATA = "ambiguous_product_data"
    MISSING_REQUIRED_ATTRIBUTE = "missing_required_attribute"
    CONFLICTING_PRODUCT_EVIDENCE = "conflicting_product_evidence"
    NON_PUBLISHABLE_ATTRIBUTE = "non_publishable_attribute"
    PUBLICATION_FAILED = "publication_failed"
    PUBLICATION_VERIFICATION_MISMATCH = "publication_verification_mismatch"
    INVENTORY_CONFLICT = "inventory_conflict"
    PAYMENT_INCONSISTENCY = "payment_inconsistency"
    FULFILMENT_DELAY = "fulfilment_delay"
    SHIPMENT_DELAY = "shipment_delay"
    NDR_DETECTED = "ndr_detected"
    REFUND_APPROVAL_REQUIRED = "refund_approval_required"
    UNSUPPORTED_CUSTOMER_REQUEST = "unsupported_customer_request"
    CONNECTOR_RATE_LIMITED = "connector_rate_limited"
    CONNECTOR_5XX = "connector_5xx"
    EXTERNAL_MUTATION_UNCERTAIN = "external_mutation_uncertain"


class ExceptionService:
    def __init__(self, store) -> None:
        self.store = store
        self.audit = AuditLedger(store)

    def create(
        self,
        *,
        merchant_id: str,
        category: ExceptionCategory | str,
        message: str,
        object_id: str | None,
        severity: str = "warning",
        evidence_ref: str | None = None,
        workflow_id: str | None = None,
        remediation_options: list[str] | None = None,
    ) -> ExceptionRecord:
        exc = ExceptionRecord(
            merchant_id=merchant_id,
            severity=severity,  # type: ignore[arg-type]
            category=str(category.value if isinstance(category, ExceptionCategory) else category),
            message=message,
            object_id=object_id,
            remediation_options=remediation_options or ["review"],
            correlation_id=get_correlation_id(),
        )
        self.store.put(exc)
        self.audit.record(
            merchant_id=merchant_id,
            actor="sanocea",
            source="exception_service",
            action="exception_created",
            object_type="Exception",
            object_id=exc.id,
            workflow_id=workflow_id,
            evidence_ref=evidence_ref,
            result="open",
            error=message,
        )
        return exc

