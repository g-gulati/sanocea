from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import ExceptionRecord, Inventory, Merchant, PurchaseOrderLine
from sanocea.packages.procurement import ProcurementService


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"polup_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="POLineUpstream", display_name="POLineUpstream"))
    store.set_config(merchant_id, {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    connector = SimulatedSupplierConnector(store)
    service = ProcurementService(store, connector)
    supplier = service.upsert_supplier(merchant_id, "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer(merchant_id, supplier.id, sku="SKU-A", supplier_sku="ACME-A", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return merchant_id, store, connector, service, supplier


def _dual_location_po(store, service, merchant_id, supplier):
    po = service.create_purchase_order(merchant_id, supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 100, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order(merchant_id, po.id)
    lines = [l for l in store.list(PurchaseOrderLine, merchant_id) if l.purchase_order_id == po.id]
    line_surat = next(l for l in lines if l.location_ref == "Surat")
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    return po, line_surat, line_mumbai


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory | None:
    rows = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location]
    return rows[-1] if rows else None


def test_exact_identity_survives_the_full_po_to_ack_to_inbound_to_receipt_chain_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)

    service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-a2-p1", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 12, "unit_cost": 500, "line_ref": line_mumbai.id}], status="partially_confirmed")
    assert service.inventory_position(merchant_id, "SKU-A", "Mumbai")["confirmed_inbound"] == 12
    assert service.inventory_position(merchant_id, "SKU-A", "Surat")["confirmed_inbound"] == 0

    service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-a2-p2", sequence=2, lines=[{"sku": "SKU-A", "quantity_confirmed": 88, "unit_cost": 500, "line_ref": line_mumbai.id}], status="confirmed")
    assert store.get(PurchaseOrderLine, merchant_id, line_mumbai.id).quantity_confirmed == 100
    assert service.inventory_position(merchant_id, "SKU-A", "Mumbai")["confirmed_inbound"] == 100

    service.record_inbound_shipment(merchant_id, po.id, external_shipment_ref="ship-a2", sequence=1, lines=[{"sku": "SKU-A", "quantity_shipped": 100, "line_ref": line_mumbai.id}])
    assert store.get(PurchaseOrderLine, merchant_id, line_mumbai.id).quantity_shipped == 100
    assert store.get(PurchaseOrderLine, merchant_id, line_surat.id).quantity_shipped == 0

    service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-a2", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 100}])
    assert _inv(store, merchant_id, "SKU-A", "Mumbai").quantity == 100
    assert _inv(store, merchant_id, "SKU-A", "Surat") is None or _inv(store, merchant_id, "SKU-A", "Surat").quantity == 0

    service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-a1", sequence=3, lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500, "line_ref": line_surat.id}], status="confirmed")
    service.record_inbound_shipment(merchant_id, po.id, external_shipment_ref="ship-a1", sequence=2, lines=[{"sku": "SKU-A", "quantity_shipped": 10, "line_ref": line_surat.id}])
    service.record_goods_receipt(merchant_id, po.id, external_receipt_ref="rcpt-a1", lines=[{"po_line_id": line_surat.id, "quantity_received": 10}])
    assert _inv(store, merchant_id, "SKU-A", "Surat").quantity == 10
    assert _inv(store, merchant_id, "SKU-A", "Mumbai").quantity == 100, "A2's completed lifecycle must remain unaffected by A1's independent receipt"


def test_sku_only_ambiguous_acknowledgement_fails_closed_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)

    service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-ambiguous", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 5, "unit_cost": 500}], status="partially_confirmed")
    assert store.get(PurchaseOrderLine, merchant_id, line_surat.id).quantity_confirmed == 0
    assert store.get(PurchaseOrderLine, merchant_id, line_mumbai.id).quantity_confirmed == 0
    exceptions = store.list(ExceptionRecord, merchant_id)
    assert any(e.category == "acknowledgement_ambiguous_po_line" for e in exceptions)


def test_concurrent_cumulative_acknowledgement_for_duplicate_sku_lines_against_real_postgres():
    """Two genuinely concurrent contributions (60 + 40 = 100) to the EXACT SAME po_line (A2 = Mumbai)
    on a PO that has a SIBLING line sharing the same SKU (A1 = Surat, ordered 10). Must prove: the
    correct PO line (A2) is updated to exactly 100 with no lost update; the sibling line (A1) is
    completely untouched; Mumbai's confirmed_inbound reaches exactly 100 (no over-confirmation, no
    under-count from a lost race); Surat's confirmed_inbound stays at 0; no duplicate quantity is ever
    applied to either line."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, _, setup_service, supplier = _setup(suffix)
    po, line_surat, line_mumbai = _dual_location_po(setup_store, setup_service, merchant_id, supplier)

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def contribute(amount: int, seq: int) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_connector = SimulatedSupplierConnector(thread_store)
            thread_service = ProcurementService(thread_store, thread_connector)
            barrier.wait(timeout=10)
            thread_service.record_supplier_acknowledgement(
                merchant_id, po.id, external_ref=f"ack-conc-{seq}", sequence=seq,
                lines=[{"sku": "SKU-A", "quantity_confirmed": amount, "unit_cost": 500, "line_ref": line_mumbai.id}],
                status="partially_confirmed" if amount < 100 else "confirmed",
            )
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=contribute, args=(60, 1))
    t2 = threading.Thread(target=contribute, args=(40, 2))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"concurrent contribution must not raise - got: {errors}"

    verify_store = PostgresStore(dsn)
    line_mumbai_after = verify_store.get(PurchaseOrderLine, merchant_id, line_mumbai.id)
    line_surat_after = verify_store.get(PurchaseOrderLine, merchant_id, line_surat.id)
    assert line_mumbai_after.quantity_confirmed == 100, f"expected both concurrent contributions (60+40=100) reflected, got {line_mumbai_after.quantity_confirmed} - a lost update would show 60 or 40"
    assert line_surat_after.quantity_confirmed == 0, "the sibling line must never be touched by A2's concurrent acknowledgements"

    mumbai_pos = ProcurementService(verify_store, SimulatedSupplierConnector(verify_store)).inventory_position(merchant_id, "SKU-A", "Mumbai")
    surat_pos = ProcurementService(verify_store, SimulatedSupplierConnector(verify_store)).inventory_position(merchant_id, "SKU-A", "Surat")
    assert mumbai_pos["confirmed_inbound"] == 100, f"expected exactly 100 (no over/under-confirmation race), got {mumbai_pos['confirmed_inbound']}"
    assert surat_pos["confirmed_inbound"] == 0

    po_after = verify_store.get(type(po), merchant_id, po.id)
    assert po_after.status != "OVER_CONFIRMED", "60+40=100 against an ordered quantity of 100 must not be misclassified as over-confirmed"


def test_upstream_identity_tenant_isolation_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, connector, service, supplier = _setup(suffix)
    other_id = f"polup_other_{suffix}"
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Other", display_name="Other"))
    po, line_surat, line_mumbai = _dual_location_po(store, service, merchant_id, supplier)
    service.record_supplier_acknowledgement(merchant_id, po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 100, "unit_cost": 500, "line_ref": line_mumbai.id}], status="confirmed")
    assert store.list(PurchaseOrderLine, other_id) == []
    assert [i for i in store.list(Inventory, other_id) if i.sku == "SKU-A"] == []
