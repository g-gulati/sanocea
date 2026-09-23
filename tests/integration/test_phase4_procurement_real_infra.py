from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    Merchant,
    PurchaseOrder,
    SupplierAcknowledgement,
)
from sanocea.packages.procurement import ProcurementService


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"proc_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Procurement", display_name="Procurement"))
    store.set_config(merchant_id, {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    connector = SimulatedSupplierConnector(store)
    service = ProcurementService(store, connector)
    supplier = service.upsert_supplier(merchant_id, "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer(merchant_id, supplier.id, sku="SKU-1", supplier_sku="ACME-1", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return merchant_id, store, connector, service, supplier


def test_lost_response_then_retry_yields_exactly_one_external_po():
    """Phase 4's headline idempotency proof: submit -> supplier creates it -> response lost (timeout
    AFTER the mutation succeeded) -> Sanocea's own recovery path (find_purchase_order, mirroring
    Phase 2.1's refund pattern) reconciles from the supplier's truth without resubmitting."""
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}])
    assert po.status == "AUTO_APPROVED"

    po_after_lost_response = service.submit_purchase_order(merchant_id, po.id, simulate="timeout_after_mutation")
    assert po_after_lost_response.status == "SUBMITTED"
    assert po_after_lost_response.external_ref is not None

    # Explicit retry: call submit again exactly as an operator/retry-job would after observing the
    # apparent failure. Must be a pure no-op (early-returns once status has already moved past
    # AUTO_APPROVED/APPROVED) - never a second external PO.
    po_after_retry = service.submit_purchase_order(merchant_id, po.id)
    assert po_after_retry.external_ref == po_after_lost_response.external_ref

    assert len(connector.purchase_orders) == 1, f"expected exactly one external PO, got {len(connector.purchase_orders)}"


def test_concurrent_po_submission_yields_exactly_one_external_po():
    """Genuine concurrency (two threads, two Postgres connections, two connector instances sharing the
    same underlying idempotency_records table) racing submit_purchase_order() for the SAME PO id."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, _, setup_service, supplier = _setup(suffix)
    po = setup_service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}])
    assert po.status == "AUTO_APPROVED"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    winners: list[str | None] = []
    errors: list[str] = []

    def attempt() -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_connector = SimulatedSupplierConnector(thread_store)
            thread_service = ProcurementService(thread_store, thread_connector)
            barrier.wait(timeout=10)
            result = thread_service.submit_purchase_order(merchant_id, po.id)
            winners.append(result.external_ref)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent PO submission must not raise - got: {errors}"
    assert len(winners) == 2
    non_null = [w for w in winners if w]
    assert len(set(non_null)) <= 1, f"both concurrent submissions must resolve to the same (or no) external ref - got {winners}"

    final_po = setup_store.get(PurchaseOrder, merchant_id, po.id)
    assert final_po.status == "SUBMITTED"
    assert final_po.external_ref is not None


def test_duplicate_and_stale_acknowledgement_against_real_postgres():
    """Step 7A.1 correction: staleness is now exact-sequence-reuse, not "any lower sequence than the
    highest already applied" (see atomic_apply_acknowledgement's docstring). The "stale" case below
    resends sequence=5 again (a different external_ref) rather than a genuinely new, never-before-seen
    lower sequence - a genuinely new lower sequence is legitimate and must apply."""
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}])
    po = service.submit_purchase_order(merchant_id, po.id)

    first = service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-full", sequence=5, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    duplicate = service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-full", sequence=5, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    assert first.id == duplicate.id

    stale = service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-stale", sequence=5, lines=[{"sku": "SKU-1", "quantity_confirmed": 3, "unit_cost": 500}], status="partially_confirmed")
    assert stale.applied is False

    acks = [a for a in store.list(SupplierAcknowledgement, merchant_id) if a.purchase_order_id == po.id]
    assert len(acks) == 2  # the full ack + the (persisted-as-evidence-but-not-applied) stale one
    po_final = store.get(PurchaseOrder, merchant_id, po.id)
    assert po_final.status == "CONFIRMED"


def test_purchase_order_lifecycle_updates_survive_idempotency_key():
    """Regression test for a real bug found while running the Phase 4 workload: a PurchaseOrder created
    with idempotency_key set (to prevent duplicate DRAFT creation from a retried replenishment
    conversion) must still allow every subsequent lifecycle status update (validate/approve/submit) to
    persist - it must NOT be silently discarded because the business-key uniqueness path treats every
    later put() as 'already exists, skip'."""
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}], idempotency_key=f"idem-{suffix}")
    assert po.status == "AUTO_APPROVED"
    persisted_after_create = store.get(PurchaseOrder, merchant_id, po.id)
    assert persisted_after_create.status == "AUTO_APPROVED", "status change must have actually persisted, not silently reverted"

    submitted = service.submit_purchase_order(merchant_id, po.id)
    assert submitted.status == "SUBMITTED"
    persisted_after_submit = store.get(PurchaseOrder, merchant_id, po.id)
    assert persisted_after_submit.status == "SUBMITTED"
    assert persisted_after_submit.external_ref is not None


def test_concurrent_acknowledgement_delivery_does_not_lose_updates():
    """Phase 4.1/4.6: two genuinely concurrent contributions to the SAME PO line (each 40 units toward
    an order of 100) must both be reflected in the cumulative total (80) - not racing on a
    read-modify-write and losing one contribution. Proven against real Postgres with two separate
    connections, exercising the two atomic store primitives directly
    (atomic_apply_po_line_confirmation, atomic_adjust_inventory) that record_supplier_acknowledgement
    itself calls - this isolates the race-freedom guarantee from record_supplier_acknowledgement's
    separate, already-covered sequence-staleness business rule (which intentionally treats two
    acknowledgements sharing or regressing a PO-wide sequence number as one stale event, and would make
    a test driving genuine concurrency through two IDENTICAL or reordered sequence numbers flaky for an
    unrelated reason)."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, _, setup_service, supplier = _setup(suffix)
    po = setup_service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 100}])
    po = setup_service.submit_purchase_order(merchant_id, po.id)
    from sanocea.packages.domain_contract.models import PurchaseOrderLine

    po_line = next(l for l in setup_store.list(PurchaseOrderLine, merchant_id) if l.purchase_order_id == po.id)

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def contribute() -> None:
        try:
            thread_store = PostgresStore(dsn)
            barrier.wait(timeout=10)
            thread_store.atomic_apply_po_line_confirmation(merchant_id, po_line.id, 40)
            thread_store.atomic_adjust_inventory(merchant_id, "SKU-1", "default", confirmed_inbound_delta=40)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=contribute) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent contribution must not raise - got: {errors}"
    line = setup_store.get(PurchaseOrderLine, merchant_id, po_line.id)
    assert line.quantity_confirmed == 80, f"expected both concurrent contributions (40+40=80) to be reflected, got {line.quantity_confirmed} - a lost update would show 40"
    position = setup_service.inventory_position(merchant_id, "SKU-1")
    assert position["confirmed_inbound"] == 80


def test_procurement_records_remain_tenant_scoped():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    other_id = f"proc_other_{suffix}"
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Other", display_name="Other"))
    po = service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}])

    assert store.list(PurchaseOrder, other_id) == []
    with pytest.raises(TenantAccessError):
        store.get(PurchaseOrder, other_id, po.id)
