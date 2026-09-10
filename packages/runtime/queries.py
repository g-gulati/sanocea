from __future__ import annotations

from typing import Any

from sanocea.packages.domain_contract.models import (
    Approval,
    AuditEvent,
    Cancellation,
    ConnectorCommand,
    CustomerSupportAction,
    Exchange,
    ExceptionRecord,
    FinanceReconciliation,
    GoodsReceipt,
    Inventory,
    ListingVerification,
    Order,
    PaymentObservation,
    ProductDraft,
    Publication,
    PurchaseOrder,
    Refund,
    Return,
    Shipment,
    Supplier,
    SupportConversation,
)

"""Phase 4.5 read-only application layer. Every function here is a thin dispatch into store.list()/
list_where() - no business logic. This is the ONLY thing apps/api routes and the operator control
plane call for reads; it exists so 'what an operator can see' is defined once, not re-derived ad hoc
per route or duplicated between the API and the dashboard.
"""


def get_order(store, merchant_id: str, order_id: str) -> Order:
    return store.get(Order, merchant_id, order_id)


def list_orders(store, merchant_id: str) -> list[Order]:
    return store.list(Order, merchant_id)


def get_refund_full_state(store, merchant_id: str, refund_id: str) -> dict[str, Any]:
    """The ONLY place both refund truth dimensions are read together - operational execution status
    (Phase 2.1) and financial reconciliation status (Phase 3/3.1/4.5). Support and the operator
    dashboard MUST use this, never `Refund.status` alone, or the canonical-truth split this phase closed
    reopens itself at the read layer."""
    refund = store.get(Refund, merchant_id, refund_id)
    return {
        "refund_id": refund.id,
        "order_id": refund.order_id,
        "amount": refund.amount,
        "currency": refund.currency,
        "operational_status": refund.status,
        "financial_reconciliation_status": refund.financial_reconciliation_status,
        "financial_reconciliation_ref": refund.financial_reconciliation_ref,
        "financial_reconciliation_updated_at": refund.financial_reconciliation_updated_at.isoformat() if refund.financial_reconciliation_updated_at else None,
        "requires_attention": refund.financial_reconciliation_status == "discrepancy",
    }


def list_refunds_full_state(store, merchant_id: str) -> list[dict[str, Any]]:
    return [get_refund_full_state(store, merchant_id, r.id) for r in store.list(Refund, merchant_id)]


def list_inventory(store, merchant_id: str) -> list[Inventory]:
    return store.list(Inventory, merchant_id)


def list_shipments(store, merchant_id: str) -> list[Shipment]:
    return store.list(Shipment, merchant_id)


def list_returns(store, merchant_id: str) -> list[Return]:
    return store.list(Return, merchant_id)


def list_exchanges(store, merchant_id: str) -> list[Exchange]:
    return store.list(Exchange, merchant_id)


def list_cancellations(store, merchant_id: str) -> list[Cancellation]:
    return store.list(Cancellation, merchant_id)


def list_payments(store, merchant_id: str) -> list[PaymentObservation]:
    return store.list(PaymentObservation, merchant_id)


def list_finance_reconciliations(store, merchant_id: str) -> list[FinanceReconciliation]:
    return store.list(FinanceReconciliation, merchant_id)


def list_suppliers(store, merchant_id: str) -> list[Supplier]:
    return store.list(Supplier, merchant_id)


def list_purchase_orders(store, merchant_id: str) -> list[PurchaseOrder]:
    return store.list(PurchaseOrder, merchant_id)


def list_purchase_orders_requiring_approval(store, merchant_id: str) -> list[PurchaseOrder]:
    return store.list_where(PurchaseOrder, merchant_id, status="REQUIRES_APPROVAL")


def list_goods_receipts(store, merchant_id: str) -> list[GoodsReceipt]:
    return store.list(GoodsReceipt, merchant_id)


def list_open_approvals(store, merchant_id: str) -> list[Approval]:
    return store.list_where(Approval, merchant_id, status="pending")


def list_open_exceptions(store, merchant_id: str) -> list[ExceptionRecord]:
    return store.list_where(ExceptionRecord, merchant_id, status="open")


def list_uncertain_connector_commands(store, merchant_id: str) -> list[ConnectorCommand]:
    return store.list_where(ConnectorCommand, merchant_id, status="uncertain")


def list_failed_connector_commands(store, merchant_id: str) -> list[ConnectorCommand]:
    return store.list_where(ConnectorCommand, merchant_id, status="failed")


def list_product_drafts(store, merchant_id: str) -> list[ProductDraft]:
    return store.list(ProductDraft, merchant_id)


def get_product_draft(store, merchant_id: str, draft_id: str) -> ProductDraft:
    return store.get(ProductDraft, merchant_id, draft_id)


def list_publications(store, merchant_id: str) -> list[Publication]:
    return store.list(Publication, merchant_id)


def get_publication(store, merchant_id: str, publication_id: str) -> Publication:
    return store.get(Publication, merchant_id, publication_id)


def list_listing_verifications(store, merchant_id: str) -> list[ListingVerification]:
    return store.list(ListingVerification, merchant_id)


def list_support_conversations(store, merchant_id: str) -> list[SupportConversation]:
    return store.list(SupportConversation, merchant_id)


def list_support_actions(store, merchant_id: str) -> list[CustomerSupportAction]:
    return store.list(CustomerSupportAction, merchant_id)


def get_audit_trail(store, merchant_id: str, *, correlation_id: str | None = None) -> list[AuditEvent]:
    events = store.list_audit(merchant_id)
    if correlation_id:
        events = [e for e in events if e.correlation_id == correlation_id]
    return events


def operator_summary(store, merchant_id: str) -> dict[str, Any]:
    """Answers "what needs attention right now, for which merchant, and why" in one call - the exact
    question Phase 4.5 requires the operator to be able to answer."""
    open_exceptions = list_open_exceptions(store, merchant_id)
    open_approvals = list_open_approvals(store, merchant_id)
    uncertain = list_uncertain_connector_commands(store, merchant_id)
    failed = list_failed_connector_commands(store, merchant_id)
    discrepant_refunds = [r for r in list_refunds_full_state(store, merchant_id) if r["requires_attention"]]
    return {
        "merchant_id": merchant_id,
        "open_exceptions": len(open_exceptions),
        "open_exceptions_by_category": _count_by(open_exceptions, "category"),
        "open_approvals": len(open_approvals),
        "uncertain_connector_commands": len(uncertain),
        "failed_connector_commands": len(failed),
        "refunds_with_financial_discrepancy": len(discrepant_refunds),
        "needs_attention": bool(open_exceptions or open_approvals or uncertain or failed or discrepant_refunds),
    }


def _count_by(items: list[Any], attr: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, attr, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return counts
