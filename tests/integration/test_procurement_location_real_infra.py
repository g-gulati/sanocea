from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import Inventory, Merchant, PurchaseOrderLine
from sanocea.packages.procurement import ProcurementService


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"procloc_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="ProcLoc", display_name="ProcLoc"))
    store.set_config(merchant_id, {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    connector = SimulatedSupplierConnector(store)
    service = ProcurementService(store, connector)
    supplier = service.upsert_supplier(merchant_id, "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer(merchant_id, supplier.id, sku="SKU-1", supplier_sku="ACME-1", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return merchant_id, store, connector, service, supplier


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory | None:
    rows = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location]
    return rows[-1] if rows else None


def test_po_line_destination_survives_full_lifecycle_against_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10, "location_ref": "Surat"}])
    po = service.submit_purchase_order(merchant_id, po.id)
    line = next(l for l in store.list(PurchaseOrderLine, merchant_id) if l.purchase_order_id == po.id)
    assert line.location_ref == "Surat"

    service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment(merchant_id, po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])

    assert service.inventory_position(merchant_id, "SKU-1", "Surat")["on_hand"] == 10
    assert service.inventory_position(merchant_id, "SKU-1", "Mumbai")["on_hand"] == 0


def test_concurrent_cumulative_acknowledgement_at_a_specific_location_does_not_lose_updates():
    """Real-Postgres extension of Phase 4.1's concurrent-acknowledgement proof, now location-scoped: two
    genuinely concurrent 40-unit contributions to the SAME PO line (ordered 100, destination Surat) must
    both land in confirmed_inbound at Surat (80 total), and Mumbai's Inventory row for the same SKU must
    remain completely untouched by either thread."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, _, setup_service, supplier = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="Mumbai", quantity=50, available=50))
    po = setup_service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 100, "location_ref": "Surat"}])
    po = setup_service.submit_purchase_order(merchant_id, po.id)
    po_line = next(l for l in setup_store.list(PurchaseOrderLine, merchant_id) if l.purchase_order_id == po.id)
    assert po_line.location_ref == "Surat"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def contribute() -> None:
        try:
            thread_store = PostgresStore(dsn)
            barrier.wait(timeout=10)
            thread_store.atomic_apply_po_line_confirmation(merchant_id, po_line.id, 40)
            thread_store.atomic_adjust_inventory(merchant_id, "SKU-1", po_line.location_ref, confirmed_inbound_delta=40)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=contribute) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent contribution must not raise - got: {errors}"
    line = setup_store.get(PurchaseOrderLine, merchant_id, po_line.id)
    assert line.quantity_confirmed == 80, f"expected both concurrent contributions (40+40=80), got {line.quantity_confirmed} - a lost update would show 40"
    surat_pos = setup_service.inventory_position(merchant_id, "SKU-1", "Surat")
    mumbai_pos = setup_service.inventory_position(merchant_id, "SKU-1", "Mumbai")
    assert surat_pos["confirmed_inbound"] == 80
    assert mumbai_pos["confirmed_inbound"] == 0
    assert mumbai_pos["on_hand"] == 50, "Mumbai's on-hand stock must be completely untouched by Surat's contributions"


def test_concurrent_duplicate_receipt_against_real_postgres_does_not_double_receive_or_cross_locations():
    """Two threads attempt to record the SAME external_receipt_ref (a realistic retried-webhook shape)
    for a PO whose line destination is Surat. Real Postgres's DB-unique idempotency on external_receipt_ref
    (the existing Phase 4 mechanism, reused unchanged) must ensure exactly one receipt is actually applied
    - no double-increment of on_hand at Surat, and Mumbai's Inventory row for the same SKU is never
    created or touched by either thread."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, _, setup_service, supplier = _setup(suffix)
    po = setup_service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10, "location_ref": "Surat"}])
    po = setup_service.submit_purchase_order(merchant_id, po.id)
    setup_service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    setup_service.record_inbound_shipment(merchant_id, po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []
    results: list[str] = []

    def attempt_receipt() -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_connector = SimulatedSupplierConnector(thread_store)
            thread_service = ProcurementService(thread_store, thread_connector)
            barrier.wait(timeout=10)
            receipt = thread_service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-concurrent-dup", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])
            results.append(receipt.id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=attempt_receipt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent duplicate receipt must not raise - got: {errors}"
    assert len(results) == 2
    assert len(set(results)) == 1, "both concurrent attempts must resolve to the SAME receipt id (idempotent), not two"

    verify_store = PostgresStore(dsn)
    surat = _inv(verify_store, merchant_id, "SKU-1", "Surat")
    mumbai = _inv(verify_store, merchant_id, "SKU-1", "Mumbai")
    assert surat.quantity == 10, f"expected exactly one receipt applied (10), got {surat.quantity} - a lost idempotency guard would show 20"
    assert mumbai is None, "Mumbai must never have gained an Inventory row from Surat-destined receipts"


def test_procurement_location_records_remain_tenant_scoped_against_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    other_id = f"procloc_other_{suffix}"
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Other", display_name="Other"))
    po = service.create_purchase_order(merchant_id, supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10, "location_ref": "Surat"}])

    assert store.list(PurchaseOrderLine, other_id) == []
    with pytest.raises(TenantAccessError):
        store.get(type(po), other_id, po.id)
