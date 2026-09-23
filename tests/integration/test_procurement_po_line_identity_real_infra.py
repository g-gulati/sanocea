from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import ExceptionRecord, GoodsReceiptLine, Inventory, Merchant, PurchaseOrderLine
from sanocea.packages.procurement import ProcurementService


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"polid_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="POLineIdentity", display_name="POLineIdentity"))
    store.set_config(merchant_id, {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    connector = SimulatedSupplierConnector(store)
    service = ProcurementService(store, connector)
    supplier = service.upsert_supplier(merchant_id, "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer(merchant_id, supplier.id, sku="SKU-A", supplier_sku="ACME-A", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return merchant_id, store, connector, service, supplier


def _po_lines(store, merchant_id, po_id):
    return [l for l in store.list(PurchaseOrderLine, merchant_id) if l.purchase_order_id == po_id]


def _to_shippable(store, service, merchant_id, po):
    service.record_supplier_acknowledgement(merchant_id, po.id, external_ref=f"ack-{po.id}", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 1, "unit_cost": 500}], status="partially_confirmed")
    service.record_inbound_shipment(merchant_id, po.id, external_shipment_ref=f"ship-{po.id}", sequence=1, lines=[{"sku": "SKU-A", "quantity_shipped": 1}])
    po_after = store.get(type(po), merchant_id, po.id)
    assert po_after.status == "INBOUND"
    return po_after


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory | None:
    rows = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location]
    return rows[-1] if rows else None


def _on_hand(store, merchant_id: str, sku: str, location: str) -> int:
    """`_to_shippable`'s acknowledgement step is a real (pre-existing, disclosed, out-of-Step-5A-scope)
    side effect that can create a confirmed-inbound-only Inventory row at whichever line the ambiguous
    SKU-only ack resolution happens to pick - so "untouched by receipt" must be asserted via on-hand
    quantity, not via "no Inventory row exists at all"."""
    inv = _inv(store, merchant_id, sku, location)
    return inv.quantity if inv else 0


def test_same_sku_different_locations_exact_line_identity_against_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order(merchant_id, po.id)
    lines = _po_lines(store, merchant_id, po.id)
    line_surat = next(l for l in lines if l.location_ref == "Surat")
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(store, service, merchant_id, po)

    service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-mumbai", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 20}])
    assert _inv(store, merchant_id, "SKU-A", "Mumbai").quantity == 20
    assert _on_hand(store, merchant_id, "SKU-A", "Surat") == 0

    service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-surat", lines=[{"po_line_id": line_surat.id, "quantity_received": 10}])
    assert _inv(store, merchant_id, "SKU-A", "Surat").quantity == 10
    assert _inv(store, merchant_id, "SKU-A", "Mumbai").quantity == 20, "the Mumbai line's earlier receipt must remain unaffected"

    assert store.get(PurchaseOrderLine, merchant_id, line_mumbai.id).quantity_received == 20
    assert store.get(PurchaseOrderLine, merchant_id, line_surat.id).quantity_received == 10


def test_same_sku_same_location_exact_line_identity_against_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Surat"},
    ])
    po = service.submit_purchase_order(merchant_id, po.id)
    lines = _po_lines(store, merchant_id, po.id)
    assert len(lines) == 2
    assert {l.location_ref for l in lines} == {"Surat"}
    line_1, line_2 = lines[0], lines[1]
    _to_shippable(store, service, merchant_id, po)

    service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-line2", lines=[{"po_line_id": line_2.id, "quantity_received": 20}])
    assert _inv(store, merchant_id, "SKU-A", "Surat").quantity == 20
    assert store.get(PurchaseOrderLine, merchant_id, line_2.id).quantity_received == 20
    assert store.get(PurchaseOrderLine, merchant_id, line_1.id).quantity_received == 0, "line 1 must be untouched by a receipt naming line 2's exact id"


def test_legacy_sku_only_receipt_with_multiple_candidates_fails_closed_against_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order(merchant_id, po.id)
    _to_shippable(store, service, merchant_id, po)

    receipt = service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-ambiguous", lines=[{"raw_sku_reference": "SKU-A", "quantity_received": 5}])
    assert receipt.status == "received_with_exceptions"
    grl = next(l for l in store.list(GoodsReceiptLine, merchant_id) if l.goods_receipt_id == receipt.id)
    assert grl.disposition == "ambiguous_po_line"
    assert grl.purchase_order_line_id is None
    assert _on_hand(store, merchant_id, "SKU-A", "Surat") == 0
    assert _on_hand(store, merchant_id, "SKU-A", "Mumbai") == 0
    exceptions = store.list(ExceptionRecord, merchant_id)
    assert any(e.category == "goods_receipt_ambiguous_po_line" for e in exceptions)


def test_concurrent_duplicate_receipt_for_the_exact_line_against_real_postgres():
    """Two threads race to record the SAME external_receipt_ref against the SAME exact po_line_id, on a
    PO that has TWO lines sharing a SKU. Exactly one receipt must be applied (existing DB-unique
    external_receipt_ref idempotency, unchanged), only the named line's quantity_received advances, and
    the sibling line/location is never touched by either thread."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, _, setup_service, supplier = _setup(suffix)
    po = setup_service.create_purchase_order(merchant_id, supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = setup_service.submit_purchase_order(merchant_id, po.id)
    lines = _po_lines(setup_store, merchant_id, po.id)
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(setup_store, setup_service, merchant_id, po)

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
            receipt = thread_service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-concurrent-exact", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 20}])
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
    assert len(set(results)) == 1, "both attempts must resolve to the SAME receipt id"

    verify_store = PostgresStore(dsn)
    assert verify_store.get(PurchaseOrderLine, merchant_id, line_mumbai.id).quantity_received == 20, "duplicate receipt must not double-increment the exact line"
    mumbai = _inv(verify_store, merchant_id, "SKU-A", "Mumbai")
    assert mumbai.quantity == 20, f"expected exactly one receipt applied (20), got {mumbai.quantity} - a lost idempotency guard would show 40"
    assert _on_hand(verify_store, merchant_id, "SKU-A", "Surat") == 0, "the sibling Surat line/location must never gain on-hand stock from Mumbai's receipts"


def test_wrong_location_claim_on_exact_line_does_not_mutate_claimed_location_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po = service.create_purchase_order(merchant_id, supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order(merchant_id, po.id)
    lines = _po_lines(store, merchant_id, po.id)
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(store, service, merchant_id, po)

    receipt = service.record_goods_receipt(
        merchant_id, po.id, external_receipt_ref="rcpt-wrongloc",
        lines=[{"po_line_id": line_mumbai.id, "quantity_received": 20, "location_ref": "Surat"}],
    )
    assert receipt.status == "received_with_exceptions"
    assert _inv(store, merchant_id, "SKU-A", "Mumbai").quantity == 20
    assert _on_hand(store, merchant_id, "SKU-A", "Surat") == 0
    exceptions = store.list(ExceptionRecord, merchant_id)
    assert any(e.category == "goods_receipt_wrong_location_attempted" for e in exceptions)
