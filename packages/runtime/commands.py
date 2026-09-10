from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sanocea.packages.domain_contract.models import Order, ProductDraft, PurchaseOrder, Refund
from sanocea.packages.finance import FinanceOperationsService
from sanocea.packages.post_order.operations import PostOrderOperationsService
from sanocea.packages.procurement import ProcurementService
from sanocea.packages.product_onboarding import ProductOnboardingWorkflow

"""Phase 4.5/4.6 command layer - the ONLY thing apps/api routes call for state-changing operations.
Every function here does auth-independent dispatch into an existing domain service; it contains no
policy/business logic of its own (that stays in FinanceOperationsService/ProcurementService/
PostOrderOperationsService/ProductOnboardingWorkflow, exactly as before). Routes are responsible for
authentication/authorization/tenant-scoping BEFORE calling any of these; these functions trust the
merchant_id they are given.
"""


@dataclass
class Services:
    store: Any
    post_order: PostOrderOperationsService
    finance: FinanceOperationsService
    procurement: ProcurementService
    catalogue: ProductOnboardingWorkflow | None = None


# --- Post-order: refunds, returns, exchanges, cancellations -----------------------------------------

def request_refund(services: Services, merchant_id: str, order_id: str, amount: int) -> Refund:
    order = services.store.get(Order, merchant_id, order_id)
    return services.post_order.evaluate_refund(merchant_id, order, amount)


def approve_refund(services: Services, merchant_id: str, refund_id: str, approver_id: str) -> Refund:
    return services.post_order.approve_refund(merchant_id, refund_id, approver_id)


def execute_refund(services: Services, merchant_id: str, refund_id: str, reason: str = "customer_refund", simulate: str | None = None) -> Refund:
    return services.post_order.execute_refund(merchant_id, refund_id, reason=reason, simulate=simulate)


def request_return(services: Services, merchant_id: str, order_id: str, reason: str):
    order = services.store.get(Order, merchant_id, order_id)
    return services.post_order.evaluate_return(merchant_id, order, reason)


def progress_return(services: Services, merchant_id: str, return_id: str, event: str):
    return services.post_order.progress_return(merchant_id, return_id, event)


def request_exchange(services: Services, merchant_id: str, order_id: str, requested_variant_sku: str, simulate: str | None = None):
    order = services.store.get(Order, merchant_id, order_id)
    return services.post_order.evaluate_exchange(merchant_id, order, requested_variant_sku, simulate=simulate)


def complete_exchange(services: Services, merchant_id: str, exchange_id: str):
    return services.post_order.complete_exchange(merchant_id, exchange_id)


def request_cancellation(services: Services, merchant_id: str, order_id: str):
    order = services.store.get(Order, merchant_id, order_id)
    return services.post_order.evaluate_cancellation(merchant_id, order)


def execute_cancellation(services: Services, merchant_id: str, cancellation_id: str, simulate: str | None = None):
    return services.post_order.execute_cancellation(merchant_id, cancellation_id, simulate=simulate)


# --- Post-order: fulfilment, shipment, tracking, NDR (Journey B) --------------------------------------

def monitor_fulfilment(services: Services, merchant_id: str, order_id: str, status: str, age_hours: int) -> str:
    order = services.store.get(Order, merchant_id, order_id)
    return services.post_order.monitor_fulfilment(merchant_id, order, status, age_hours)


def create_or_observe_shipment(services: Services, merchant_id: str, order_id: str, simulate: str | None = None) -> dict[str, Any]:
    order = services.store.get(Order, merchant_id, order_id)
    # PostOrderOperationsService.create_or_observe_shipment returns (status_label, external_ref) - e.g.
    # ("created", "ship-abc123") or ("uncertain", None) - NOT (ref, error). Phase 4.6 fix: this was
    # swapped since Phase 4.5, silently wrong because nothing had ever called this route through the
    # real app until this phase's own integration workload exercised the shipment/tracking journey for
    # the first time and hit a KeyError trying to use the status label ("created") as a real shipment
    # reference.
    status, external_ref = services.post_order.create_or_observe_shipment(merchant_id, order, simulate=simulate)
    return {"status": status, "shipment_ref": external_ref}


def ingest_tracking(services: Services, merchant_id: str, shipment_ref: str) -> str:
    return services.post_order.ingest_tracking(merchant_id, shipment_ref)


def request_ndr_reattempt(services: Services, merchant_id: str, shipment_ref: str) -> str:
    return services.post_order.request_ndr_reattempt(merchant_id, shipment_ref)


# --- Finance ------------------------------------------------------------------------------------------

def observe_payment(services: Services, merchant_id: str, order_id: str, provider: str, amount: int, currency: str, status: str, external_payment_id: str | None = None):
    order = services.store.get(Order, merchant_id, order_id)
    return services.finance.observe_payment(merchant_id, order, provider, amount, currency, status, external_payment_id)


def reconcile_payment_observation(services: Services, merchant_id: str, order_id: str, observation):
    order = services.store.get(Order, merchant_id, order_id)
    return services.finance.reconcile_payment(merchant_id, order, observation)


def ingest_settlement_batch(services: Services, merchant_id: str, provider: str, batch_payload: dict[str, Any]):
    return services.finance.ingest_settlement_batch(merchant_id, provider, batch_payload)


def reconcile_settlement_batch(services: Services, merchant_id: str, batch_id: str, final_orders: set[str] | None = None):
    return services.finance.reconcile_settlement_batch(merchant_id, batch_id, final_orders=final_orders)


# --- Procurement ---------------------------------------------------------------------------------------

def recommend_replenishment(services: Services, merchant_id: str, sku: str):
    return services.procurement.recommend_replenishment(merchant_id, sku)


def create_purchase_order(services: Services, merchant_id: str, supplier_id: str, lines: list[dict[str, Any]], idempotency_key: str | None = None) -> PurchaseOrder:
    return services.procurement.create_purchase_order(merchant_id, supplier_id, lines, idempotency_key=idempotency_key)


def approve_purchase_order(services: Services, merchant_id: str, po_id: str, approver_id: str) -> PurchaseOrder:
    return services.procurement.approve_purchase_order(merchant_id, po_id, approver_id)


def submit_purchase_order(services: Services, merchant_id: str, po_id: str, simulate: str | None = None) -> PurchaseOrder:
    return services.procurement.submit_purchase_order(merchant_id, po_id, simulate=simulate)


def record_supplier_acknowledgement(services: Services, merchant_id: str, po_id: str, external_ref: str, sequence: int, lines: list[dict[str, Any]], status: str):
    return services.procurement.record_supplier_acknowledgement(merchant_id, po_id, external_ref=external_ref, sequence=sequence, lines=lines, status=status)


def record_inbound_shipment(services: Services, merchant_id: str, po_id: str, external_shipment_ref: str, sequence: int, lines: list[dict[str, Any]]):
    return services.procurement.record_inbound_shipment(merchant_id, po_id, external_shipment_ref=external_shipment_ref, sequence=sequence, lines=lines)


def record_goods_receipt(services: Services, merchant_id: str, po_id: str, external_receipt_ref: str, lines: list[dict[str, Any]], inbound_shipment_id: str | None = None):
    return services.procurement.record_goods_receipt(merchant_id, po_id, external_receipt_ref=external_receipt_ref, lines=lines, inbound_shipment_id=inbound_shipment_id)


# --- Catalogue (Journey A, Phase 4.6) -----------------------------------------------------------------

def ingest_product_file(services: Services, merchant_id: str, tmp_path: Path, content_type: str) -> list[ProductDraft]:
    return services.catalogue.ingest_file(merchant_id, tmp_path, content_type)


def approve_product_facts(services: Services, merchant_id: str, draft_id: str, approver_id: str) -> ProductDraft:
    return services.catalogue.approve_product_facts(merchant_id, draft_id, approver_id)


def request_publication(services: Services, merchant_id: str, draft_id: str, channel_id: str, requested_by: str) -> dict[str, Any]:
    return services.catalogue.request_publication(merchant_id, draft_id, channel_id, requested_by)


def approve_publication(services: Services, merchant_id: str, draft_id: str, channel_id: str, approver_id: str) -> dict[str, Any]:
    return services.catalogue.approve_publication(merchant_id, draft_id, channel_id, approver_id)


def reverify_publication(services: Services, merchant_id: str, publication_id: str):
    return services.catalogue.reverify(merchant_id, publication_id)
