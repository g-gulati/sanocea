from __future__ import annotations

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    GoodsReceiptLine,
    Inventory,
    Order,
    OrderLine,
    PurchaseOrderLine,
    SupplierAcknowledgement,
)
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.packages.procurement import ProcurementService


@pytest.fixture
def procurement(phase0):
    store, *_ = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    service = ProcurementService(store, SimulatedSupplierConnector(store))
    supplier = service.upsert_supplier("mer_A", "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer("mer_A", supplier.id, sku="SKU-1", supplier_sku="ACME-1", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return store, service, supplier


def _submitted_po(store, service, supplier, *, sku="SKU-1", qty=10, location_ref=None):
    lines = [{"sku": sku, "quantity_ordered": qty}]
    if location_ref is not None:
        lines[0]["location_ref"] = location_ref
    po = service.create_purchase_order("mer_A", supplier.id, lines)
    return service.submit_purchase_order("mer_A", po.id)


def _line(store, po_id, sku="SKU-1"):
    return next(l for l in store.list(PurchaseOrderLine, "mer_A") if l.purchase_order_id == po_id and l.sku == sku)


# --- Part C: location-specific replenishment - high stock elsewhere never masks a real shortage --------

def test_high_stock_at_mumbai_does_not_mask_low_stock_at_surat(procurement):
    store, service, supplier = procurement
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {
        "spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"},
        "replenishment": {"SKU-1": {"safety_stock": 2, "reorder_point": 3}},
    }})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="Surat", quantity=2, reserved=1, available=1))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="Mumbai", quantity=20, reserved=0, available=20))

    rec_surat = service.recommend_replenishment("mer_A", "SKU-1", location_ref="Surat")
    assert rec_surat.location_ref == "Surat"
    assert rec_surat.reasoning["needs_reorder"] is True
    assert rec_surat.recommended_quantity > 0

    rec_mumbai = service.recommend_replenishment("mer_A", "SKU-1", location_ref="Mumbai")
    assert rec_mumbai.location_ref == "Mumbai"
    assert rec_mumbai.reasoning["needs_reorder"] is False
    assert rec_mumbai.recommended_quantity == 0


def test_legacy_no_location_replenishment_still_works(procurement):
    """Part I - a caller that never passes location_ref must keep resolving to the legacy 'default'
    location exactly as before Step 5."""
    store, service, supplier = procurement
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=500, available=500))
    rec = service.recommend_replenishment("mer_A", "SKU-1")
    assert rec.location_ref == "default"
    assert rec.recommended_quantity == 0


# --- Part D: PO line retains its destination location through the whole lifecycle -----------------------

def test_po_line_retains_destination_location_through_lifecycle(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, location_ref="Surat")
    line = _line(store, po.id)
    assert line.location_ref == "Surat"

    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    assert _line(store, po.id).location_ref == "Surat"

    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    assert _line(store, po.id).location_ref == "Surat"

    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])
    assert _line(store, po.id).location_ref == "Surat"


def test_different_lines_on_the_same_po_may_resolve_to_different_locations(procurement):
    store, service, supplier = procurement
    service.ingest_supplier_offer("mer_A", supplier.id, sku="SKU-2", supplier_sku="ACME-2", cost=300, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    po = service.create_purchase_order("mer_A", supplier.id, [
        {"sku": "SKU-1", "quantity_ordered": 10, "location_ref": "Surat"},
        {"sku": "SKU-2", "quantity_ordered": 10, "location_ref": "Mumbai"},
    ])
    line_1 = _line(store, po.id, "SKU-1")
    line_2 = _line(store, po.id, "SKU-2")
    assert line_1.location_ref == "Surat"
    assert line_2.location_ref == "Mumbai"


def test_never_received_into_mumbai_merely_because_it_became_merchant_default(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, location_ref="Surat")
    # Merchant default location changes AFTER the PO line was created.
    store.set_config("mer_A", store.get_config("mer_A") | {"inventory": {"default_location_ref": "Mumbai"}})
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["on_hand"] == 10
    assert service.inventory_position("mer_A", "SKU-1", "Mumbai")["on_hand"] == 0


# --- Part E: confirmed inbound is location-specific ------------------------------------------------------

def test_confirmed_inbound_is_location_specific(procurement):
    store, service, supplier = procurement
    po_surat = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po_surat.id, external_ref="ack-surat", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")

    surat_pos = service.inventory_position("mer_A", "SKU-1", "Surat")
    mumbai_pos = service.inventory_position("mer_A", "SKU-1", "Mumbai")
    assert surat_pos["confirmed_inbound"] == 10
    assert mumbai_pos["confirmed_inbound"] == 0, "confirmed inbound must not leak onto another location"


def test_acknowledgement_preserves_line_location_across_partial_events(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=100, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 60, "unit_cost": 500}], status="partially_confirmed")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a2", sequence=2, lines=[{"sku": "SKU-1", "quantity_confirmed": 40, "unit_cost": 500}], status="confirmed")
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["confirmed_inbound"] == 100
    assert service.inventory_position("mer_A", "SKU-1", "Mumbai")["confirmed_inbound"] == 0


# --- Part F: goods receipt mutates ONLY the destination location -----------------------------------------

def test_full_goods_receipt_updates_only_destination_location(procurement):
    store, service, supplier = procurement
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="Surat", quantity=3, reserved=1, available=2))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="Mumbai", quantity=20, reserved=0, available=20))
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])

    surat = service.inventory_position("mer_A", "SKU-1", "Surat")
    mumbai = service.inventory_position("mer_A", "SKU-1", "Mumbai")
    assert surat == {"sku": "SKU-1", "on_hand": 13, "reserved": 1, "confirmed_inbound": 0, "available_to_sell": 12, "inventory_position": 12}
    assert mumbai == {"sku": "SKU-1", "on_hand": 20, "reserved": 0, "confirmed_inbound": 0, "available_to_sell": 20, "inventory_position": 20}


def test_outstanding_reservation_at_destination_still_affects_ats_after_receipt(procurement):
    """Part J-adjacent - a reservation held at the destination location before receipt must still be
    correctly reflected in available_to_sell after the receipt increases on-hand."""
    store, service, supplier = procurement
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="Surat", quantity=5, reserved=3, available=2))
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])
    pos = service.inventory_position("mer_A", "SKU-1", "Surat")
    assert pos["on_hand"] == 15
    assert pos["reserved"] == 3, "the pre-existing reservation must be untouched by the receipt"
    assert pos["available_to_sell"] == 12


# --- Part G: partial and cumulative receipt still work, now location-scoped ------------------------------

def test_partial_receipt_then_cumulative_second_receipt_location_scoped(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])

    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-partial", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 4}])
    line_after_first = _line(store, po.id)
    assert line_after_first.quantity_received == 4
    pos_after_first = service.inventory_position("mer_A", "SKU-1", "Surat")
    assert pos_after_first["on_hand"] == 4
    assert pos_after_first["confirmed_inbound"] == 6

    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-remainder", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 6}])
    line_after_second = _line(store, po.id)
    assert line_after_second.quantity_received == 10
    pos_after_second = service.inventory_position("mer_A", "SKU-1", "Surat")
    assert pos_after_second["on_hand"] == 10
    assert pos_after_second["confirmed_inbound"] == 0
    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "RECEIVED"


def test_duplicate_receipt_is_idempotent_location_scoped(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])

    first = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-dup", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])
    second = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-dup", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])
    assert first.id == second.id
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["on_hand"] == 10, "duplicate receipt must not double-increment on_hand"


# --- Part H: over-receipt / wrong-location / duplicate / unknown-line handling ----------------------------

def test_over_receipt_does_not_corrupt_inventory_at_the_correct_location(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-excess", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 15}])
    assert receipt.status == "received_with_exceptions"
    lines = [l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id]
    assert lines[0].disposition == "excess"
    assert lines[0].location_ref == "Surat"
    # The actual physical count is real and applied - but ONLY at the correct location.
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["on_hand"] == 15
    assert service.inventory_position("mer_A", "SKU-1", "Mumbai")["on_hand"] == 0
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "goods_receipt_excess" for e in exceptions)


def test_wrong_location_receipt_does_not_mutate_the_claimed_wrong_location(procurement):
    """The PO line's canonical destination is Surat. The receiving payload claims Mumbai. Step 5 does
    NOT allow overrides: inventory must be applied at Surat only, Mumbai must remain untouched, and the
    mismatch must be flagged as an exception rather than silently ignored or silently honored."""
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])

    receipt = service.record_goods_receipt(
        "mer_A", po.id, external_receipt_ref="rcpt-wrongloc",
        lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10, "location_ref": "Mumbai"}],
    )
    assert receipt.status == "received_with_exceptions"
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["on_hand"] == 10
    assert service.inventory_position("mer_A", "SKU-1", "Mumbai")["on_hand"] == 0, "the claimed wrong location must never be mutated"
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "goods_receipt_wrong_location_attempted" for e in exceptions)
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id)
    assert grl.location_ref == "Surat", "the receipt line's recorded location is the canonical one actually used"


def test_unknown_po_line_reference_never_touches_any_location(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-unknown", lines=[{"raw_sku_reference": "SKU-UNKNOWN", "quantity_received": 5}])
    assert receipt.status == "received_with_exceptions"
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["on_hand"] == 0
    grl = next(l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id)
    assert grl.location_ref is None


# --- Part I: legacy default-location compatibility --------------------------------------------------------

def test_legacy_single_location_procurement_flow_still_works_end_to_end(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10)  # no location_ref anywhere
    assert _line(store, po.id).location_ref == "default"
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}])
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 10}])
    assert service.inventory_position("mer_A", "SKU-1")["on_hand"] == 10


# --- Tenant isolation ---------------------------------------------------------------------------------

def test_procurement_location_records_remain_tenant_scoped(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier, sku="SKU-1", qty=10, location_ref="Surat")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    assert store.list(PurchaseOrderLine, "mer_B") == []
    assert store.list(SupplierAcknowledgement, "mer_B") == []
    assert [i for i in store.list(Inventory, "mer_B") if i.sku == "SKU-1"] == []


# --- Part J: cross-domain proof - procurement truth and order-allocation truth share the same location- #
#            scoped canonical inventory --------------------------------------------------------------------

def test_cross_domain_procurement_to_allocation_chain(procurement):
    """Surat stock low -> replenishment recommendation for Surat -> PO line created for Surat ->
    supplier acknowledgement -> confirmed inbound appears at Surat only -> goods received at Surat ->
    Surat quantity increases -> Mumbai unchanged -> the ORDER ALLOCATION ENGINE (Step 3/4) can
    subsequently see the newly received Surat ATS and choose it for an order it could not have
    satisfied before the receipt."""
    store, service, supplier = procurement
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {
        "spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"},
        "replenishment": {"SKU-1": {"safety_stock": 2, "reorder_point": 3}},
    }})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="Surat", quantity=1, available=1))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="Mumbai", quantity=1, available=1))

    rec = service.recommend_replenishment("mer_A", "SKU-1", location_ref="Surat")
    assert rec.location_ref == "Surat"
    assert rec.recommended_quantity > 0

    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": rec.recommended_quantity, "location_ref": "Surat"}])
    po = service.submit_purchase_order("mer_A", po.id)
    assert _line(store, po.id).location_ref == "Surat"

    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": rec.recommended_quantity, "unit_cost": 500}], status="confirmed")
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["confirmed_inbound"] == rec.recommended_quantity
    assert service.inventory_position("mer_A", "SKU-1", "Mumbai")["confirmed_inbound"] == 0

    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": rec.recommended_quantity}])
    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": rec.recommended_quantity}])

    surat_on_hand = service.inventory_position("mer_A", "SKU-1", "Surat")["on_hand"]
    assert surat_on_hand == 1 + rec.recommended_quantity
    assert service.inventory_position("mer_A", "SKU-1", "Mumbai")["on_hand"] == 1, "Mumbai must be completely unaffected"

    # Now prove the ALLOCATION engine (Step 3/4) sees the newly received Surat ATS: build an order that
    # requires more than Surat's ORIGINAL stock (1) but fits within its POST-RECEIPT stock.
    order_qty = 1 + rec.recommended_quantity  # exactly Surat's new total - impossible before the receipt
    _workflow, shopify, _chatwoot = None, None, None
    from sanocea.connectors.shopify import ShopifyConnector
    from sanocea.workers.workflow import FakeTemporalEngine
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    post_order_service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))

    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="CROSS-1", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id="mer_A", order_id=order.id, sku="SKU-1", title="SKU-1", quantity=order_qty, unit_amount=100000 // order_qty))

    result = post_order_service.reserve_inventory_for_order("mer_A", order, location="Surat")
    assert result["reserved"] is True, "the allocation/reservation engine must see the newly received Surat stock"
    assert service.inventory_position("mer_A", "SKU-1", "Surat")["reserved"] == order_qty
