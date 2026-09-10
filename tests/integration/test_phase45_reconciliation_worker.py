from __future__ import annotations

import os
from uuid import uuid4

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import ExceptionRecord, Merchant, PurchaseOrder
from sanocea.packages.finance import FinanceOperationsService
from sanocea.packages.post_order.operations import PostOrderOperationsService
from sanocea.packages.procurement import ProcurementService
from sanocea.packages.runtime import Services
from sanocea.workers.reconciliation_worker import ReconciliationWorker

pytestmark = pytest.mark.skipif(not os.environ.get("SANOCEA_PG_DSN"), reason="requires real Postgres DSN in SANOCEA_PG_DSN")


def _setup(suffix: str):
    merchant_id = f"recovery_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Recovery", display_name="Recovery"))
    store.set_config(merchant_id, {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    connector = SimulatedSupplierConnector(store)
    procurement = ProcurementService(store, connector)
    post_order = PostOrderOperationsService(store, None, None, None)
    finance = FinanceOperationsService(store)
    services = Services(store=store, post_order=post_order, finance=finance, procurement=procurement)
    supplier = procurement.upsert_supplier(merchant_id, "Recovery Supplier", default_lead_time_days=5)
    procurement.ingest_supplier_offer(merchant_id, supplier.id, sku="SKU-1", supplier_sku="REC-1", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return merchant_id, store, connector, services


def test_worker_reconciles_when_supplier_processed_it_out_of_band_not_blind_retry():
    """A genuinely uncertain PO (Sanocea never even attempted the mutation - simulate=
    timeout_before_mutation) where the supplier LATER processes it out-of-band (e.g. a human ops action
    on the supplier's side, discovered only via find_purchase_order). The worker must discover this by
    reading external truth FIRST and never call submit_purchase_order again - proven by asserting
    exactly one external PO exists afterward, matching the one seeded directly on the connector, not a
    second one minted by a retry."""
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, services = _setup(suffix)
    from sanocea.packages.domain_contract.models import Supplier

    supplier = store.list(Supplier, merchant_id)[0]
    po = services.procurement.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}])
    po = services.procurement.submit_purchase_order(merchant_id, po.id, simulate="timeout_before_mutation")
    assert po.status != "SUBMITTED"
    assert len(connector.purchase_orders) == 0

    # Out-of-band: the supplier's own system now has it, discoverable only via find_purchase_order.
    connector.purchase_orders["simpo-manual"] = {"merchant_id": merchant_id, "external_ref": "simpo-manual", "supplier_id": supplier.id, "lines": [], "currency": "INR", "status": "received"}
    connector.purchase_orders_by_key[f"{merchant_id}:{po.id}"] = "simpo-manual"

    worker = ReconciliationWorker(store, services, supplier_connector=connector)
    counters = worker.run_once(merchant_id)

    assert counters.reconciled_from_external_truth >= 1
    final_po = store.get(PurchaseOrder, merchant_id, po.id)
    assert final_po.status == "SUBMITTED"
    assert final_po.external_ref == "simpo-manual"
    assert len(connector.purchase_orders) == 1, "worker must NOT have minted a second external PO via a blind retry"
    remaining_open = [e for e in store.list(ExceptionRecord, merchant_id) if e.category == "po_submission_uncertain" and e.status == "open"]
    assert remaining_open == []


def test_worker_retries_only_when_external_truth_confirms_nothing_happened():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, services = _setup(suffix)
    from sanocea.packages.domain_contract.models import Supplier

    supplier = store.list(Supplier, merchant_id)[0]
    po = services.procurement.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}])
    po = services.procurement.submit_purchase_order(merchant_id, po.id, simulate="timeout_before_mutation")
    assert po.status != "SUBMITTED"
    assert len(connector.purchase_orders) == 0, "the supplier never actually received this PO"

    worker = ReconciliationWorker(store, services, supplier_connector=connector)
    counters = worker.run_once(merchant_id)

    assert counters.retried_after_confirming_no_prior_effect >= 1
    final_po = store.get(PurchaseOrder, merchant_id, po.id)
    assert final_po.status == "SUBMITTED"
    assert len(connector.purchase_orders) == 1, "exactly one external PO after the safe retry"


class _AlwaysUncertainConnector:
    """A connector that can NEVER succeed and NEVER has external truth to discover - models a
    genuinely, permanently stuck integration (e.g. a misconfigured endpoint), not a transient fault.
    Used to prove the worker terminally escalates instead of retrying forever."""

    name = "always_uncertain"

    def __init__(self) -> None:
        self.purchase_orders: dict = {}

    def find_purchase_order(self, merchant_id: str, purchase_order_id: str):
        return None

    def execute_mutation(self, request):
        raise TimeoutError("permanently uncertain - simulated broken integration")


def test_worker_escalates_terminally_instead_of_looping_forever():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, services = _setup(suffix)
    from sanocea.packages.domain_contract.models import Supplier

    supplier = store.list(Supplier, merchant_id)[0]
    po = services.procurement.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}])

    stuck_connector = _AlwaysUncertainConnector()
    services.procurement.supplier_connector = stuck_connector  # both the direct call below and the
    # worker's internal retries go through this SAME attribute, so both consistently fail forever.
    services.procurement.submit_purchase_order(merchant_id, po.id)

    worker = ReconciliationWorker(store, services, supplier_connector=stuck_connector, max_attempts=2)
    for _ in range(4):
        po = store.get(PurchaseOrder, merchant_id, po.id)
        if po.status == "SUBMITTED":
            break
        worker.run_once(merchant_id)

    exceptions = store.list(ExceptionRecord, merchant_id)
    escalated = [e for e in exceptions if e.category == "po_submission_uncertain" and e.severity == "critical"]
    assert escalated, "an exhausted-retries exception must be escalated to critical, not silently retried forever"
