from __future__ import annotations

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    GoodsReceiptLine,
    PurchaseOrderLine,
)
from sanocea.packages.procurement import ProcurementService


@pytest.fixture
def procurement(phase0):
    store, *_ = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    service = ProcurementService(store, SimulatedSupplierConnector(store))
    supplier = service.upsert_supplier("mer_A", "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer("mer_A", supplier.id, sku="SKU-A", supplier_sku="ACME-A", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return store, service, supplier


def _po_lines(store, po_id):
    return [l for l in store.list(PurchaseOrderLine, "mer_A") if l.purchase_order_id == po_id]


def _to_shippable(store, service, po):
    """Move a freshly-created PO into a state where record_goods_receipt is legal (INBOUND), without
    relying on per-line acknowledgement correctness - that is a SEPARATE, pre-existing, disclosed
    limitation (record_supplier_acknowledgement/_po_line still resolve by SKU only) which Step 5A's
    mandate explicitly does NOT ask to fix; only goods-receipt line identity is in scope here. A single
    small acknowledgement is enough to flip PO status to PARTIALLY_CONFIRMED (guaranteed whenever a PO
    has more than one line for the same SKU, since at least one line's quantity_confirmed necessarily
    stays below its own quantity_ordered), then a shipment event unconditionally advances any
    CONFIRMED/PARTIALLY_CONFIRMED PO to INBOUND regardless of per-line confirmation accuracy."""
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref=f"ack-{po.id}", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 1, "unit_cost": 500}], status="partially_confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref=f"ship-{po.id}", sequence=1, lines=[{"sku": "SKU-A", "quantity_shipped": 1}])
    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "INBOUND"
    return po_after


# --- Same SKU, different locations: exact po_line_id disambiguates correctly ----------------------------

def test_same_sku_different_locations_receipt_by_exact_po_line_id(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    line_surat = next(l for l in lines if l.location_ref == "Surat")
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(store, service, po)

    receipt_mumbai = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-mumbai", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 5}])
    assert receipt_mumbai.status == "received_with_exceptions"  # a partial receipt (5 of 20 ordered) is a genuine shortage, not a resolution failure
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 5
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_received == 5
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_received == 0
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt_mumbai.id)
    assert grl.purchase_order_line_id == line_mumbai.id
    assert grl.location_ref == "Mumbai"

    # Then receive line-A1 (Surat) separately.
    receipt_surat = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-surat", lines=[{"po_line_id": line_surat.id, "quantity_received": 4}])
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 4
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 5, "the earlier Mumbai receipt must remain unchanged"
    assert store.get(PurchaseOrderLine, "mer_A", line_surat.id).quantity_received == 4
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_received == 5, "line-A2 must not be affected by line-A1's receipt"


def test_legacy_sku_only_receipt_fails_closed_when_two_locations_match(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    _to_shippable(store, service, po)

    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-ambiguous", lines=[{"raw_sku_reference": "SKU-A", "quantity_received": 5}])
    assert receipt.status == "received_with_exceptions"
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id)
    assert grl.disposition == "ambiguous_po_line"
    assert grl.purchase_order_line_id is None
    assert grl.location_ref is None
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 0
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "goods_receipt_ambiguous_po_line" for e in exceptions)


# --- Same SKU, SAME location: the harder identity case ---------------------------------------------------

def test_same_sku_same_location_receipt_by_exact_po_line_id_distinguishes_lines(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Surat"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    assert len(lines) == 2
    assert {l.location_ref for l in lines} == {"Surat"}  # both at the SAME location - (sku, location) is NOT unique
    line_1, line_2 = lines[0], lines[1]
    _to_shippable(store, service, po)

    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-exact-2", lines=[{"po_line_id": line_2.id, "quantity_received": 7}])
    assert receipt.status == "received_with_exceptions"  # a partial receipt (7 of 20 ordered) is a genuine shortage, not a resolution failure
    assert store.get(PurchaseOrderLine, "mer_A", line_2.id).quantity_received == 7
    assert store.get(PurchaseOrderLine, "mer_A", line_1.id).quantity_received == 0, "line 1 must be completely untouched by a receipt naming line 2's exact id"
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 7


def test_legacy_sku_only_receipt_fails_closed_even_when_locations_are_identical(procurement):
    """The harder case the mandate specifically calls out: (sku, location) is NOT a reliable
    disambiguator, so a legacy SKU-only receipt must fail closed here too, not just across locations."""
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Surat"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    _to_shippable(store, service, po)

    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-ambiguous-sameloc", lines=[{"raw_sku_reference": "SKU-A", "quantity_received": 3}])
    assert receipt.status == "received_with_exceptions"
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id)
    assert grl.disposition == "ambiguous_po_line"
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0

    # Even supplying the (matching) claimed location must NOT be used to disambiguate/select a line.
    receipt2 = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-ambiguous-sameloc-2", lines=[{"raw_sku_reference": "SKU-A", "quantity_received": 3, "location_ref": "Surat"}])
    grl2 = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt2.id)
    assert grl2.disposition == "ambiguous_po_line", "a claimed location must never be used to pick a line among ambiguous candidates"
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0


# --- Backward compatibility: unambiguous legacy SKU-only input still resolves -----------------------------

def test_legacy_sku_only_receipt_still_resolves_when_unambiguous(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"}])
    po = service.submit_purchase_order("mer_A", po.id)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-A", "quantity_shipped": 10}])

    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-legacy-ok", lines=[{"raw_sku_reference": "SKU-A", "quantity_received": 10}])
    assert receipt.status == "received"
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 10
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id)
    line = _po_lines(store, po.id)[0]
    assert grl.purchase_order_line_id == line.id


def test_unknown_po_line_id_is_refused_not_guessed(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"}])
    po = service.submit_purchase_order("mer_A", po.id)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-A", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-A", "quantity_shipped": 10}])

    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-badid", lines=[{"po_line_id": "pol_does_not_exist", "quantity_received": 10}])
    assert receipt.status == "received_with_exceptions"
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id)
    assert grl.disposition == "unknown_po_line"
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "goods_receipt_unknown_po_line" for e in exceptions)


# --- Cumulative/duplicate integrity, per EXACT line -------------------------------------------------------

def test_partial_then_cumulative_receipt_operates_on_the_exact_line_only(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(store, service, po)

    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-partial-a2", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 8}])
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_received == 8
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 8

    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-cumulative-a2", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 12}])
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_received == 20
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 20
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0, "the other line must never be consumed by line-A2's receipts"


def test_duplicate_receipt_ref_is_idempotent_for_the_exact_line(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(store, service, po)

    first = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-dup-a2", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 20}])
    second = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-dup-a2", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 20}])
    assert first.id == second.id
    assert store.get(PurchaseOrderLine, "mer_A", line_mumbai.id).quantity_received == 20, "duplicate receipt must not double-increment"
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 20


def test_over_receipt_classification_still_applies_per_exact_line(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(store, service, po)

    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-excess-a2", lines=[{"po_line_id": line_mumbai.id, "quantity_received": 25}])
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id)
    assert grl.disposition == "excess"
    assert grl.purchase_order_line_id == line_mumbai.id
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 25
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0


# --- Wrong location, now scoped to an exact resolved line --------------------------------------------------

def test_wrong_location_claim_on_an_exact_line_does_not_mutate_claimed_location(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-A", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-A", "quantity_ordered": 20, "location_ref": "Mumbai"},
    ])
    po = service.submit_purchase_order("mer_A", po.id)
    lines = _po_lines(store, po.id)
    line_mumbai = next(l for l in lines if l.location_ref == "Mumbai")
    _to_shippable(store, service, po)

    receipt = service.record_goods_receipt(
        "mer_A", po.id, external_receipt_ref="rcpt-wrongloc-exact",
        lines=[{"po_line_id": line_mumbai.id, "quantity_received": 5, "location_ref": "Surat"}],
    )
    assert receipt.status == "received_with_exceptions"
    assert service.inventory_position("mer_A", "SKU-A", "Mumbai")["on_hand"] == 5, "the canonical Mumbai destination remains authoritative"
    assert service.inventory_position("mer_A", "SKU-A", "Surat")["on_hand"] == 0, "Surat must not be mutated simply because the payload claimed it"
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "goods_receipt_wrong_location_attempted" for e in exceptions)
