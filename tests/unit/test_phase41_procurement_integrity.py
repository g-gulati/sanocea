from __future__ import annotations

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector
from sanocea.packages.domain_contract.models import ExceptionRecord, PurchaseOrderLine
from sanocea.packages.procurement import ProcurementService


@pytest.fixture
def procurement(phase0):
    store, *_ = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    service = ProcurementService(store, SimulatedSupplierConnector(store))
    supplier = service.upsert_supplier("mer_A", "Acme Supplies", default_lead_time_days=5)
    service.ingest_supplier_offer("mer_A", supplier.id, sku="SKU-1", supplier_sku="ACME-1", cost=500, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    return store, service, supplier


def _submitted_po(store, service, supplier, sku="SKU-1", qty=100):
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": sku, "quantity_ordered": qty}])
    return service.submit_purchase_order("mer_A", po.id)


def _line(store, po_id, sku="SKU-1"):
    return next(l for l in store.list(PurchaseOrderLine, "mer_A") if l.purchase_order_id == po_id and l.sku == sku)


def test_partial_acknowledgement(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 60, "unit_cost": 500}], status="partially_confirmed")
    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "PARTIALLY_CONFIRMED"
    assert _line(store, po.id).quantity_confirmed == 60
    assert service.inventory_position("mer_A", "SKU-1")["confirmed_inbound"] == 60


def test_multiple_partials_reaching_exactly_ordered_quantity(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 60, "unit_cost": 500}], status="partially_confirmed")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a2", sequence=2, lines=[{"sku": "SKU-1", "quantity_confirmed": 40, "unit_cost": 500}], status="confirmed")
    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "CONFIRMED"
    assert _line(store, po.id).quantity_confirmed == 100
    assert service.inventory_position("mer_A", "SKU-1")["confirmed_inbound"] == 100


def test_over_acknowledgement_flags_exception_and_caps_confirmed_inbound(procurement):
    """Ordered 100 -> ACK 60 -> ACK +40 (100, CONFIRMED) -> ACK +20 (120, OVER_CONFIRMED)."""
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 60, "unit_cost": 500}], status="partially_confirmed")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a2", sequence=2, lines=[{"sku": "SKU-1", "quantity_confirmed": 40, "unit_cost": 500}], status="confirmed")
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="a3", sequence=3, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}], status="confirmed")

    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "OVER_CONFIRMED"
    line = _line(store, po.id)
    assert line.quantity_confirmed == 120, "true cumulative confirmed quantity must be visible, not silently capped"
    position = service.inventory_position("mer_A", "SKU-1")
    assert position["confirmed_inbound"] == 100, "confirmed_inbound must NEVER exceed the legitimately ordered quantity"
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "supplier_overconfirmation" for e in exceptions)


def test_two_full_acknowledgements_is_over_confirmed_duplicate_risk(procurement):
    """Ordered 100 -> ACK-1 100 -> ACK-2 100 (distinct external_ref, genuinely new event) -> OVER_CONFIRMED."""
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-first", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 100, "unit_cost": 500}], status="confirmed")
    po_mid = store.get(type(po), "mer_A", po.id)
    assert po_mid.status == "CONFIRMED"

    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-second-distinct", sequence=2, lines=[{"sku": "SKU-1", "quantity_confirmed": 100, "unit_cost": 500}], status="confirmed")
    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "OVER_CONFIRMED"
    assert _line(store, po.id).quantity_confirmed == 200
    assert service.inventory_position("mer_A", "SKU-1")["confirmed_inbound"] == 100


def test_exact_retransmission_is_idempotent_not_over_confirmed(procurement):
    """Exact retransmission (same external_ref) of a full acknowledgement must not increase confirmed
    quantity at all - this is different from a genuinely NEW duplicate-looking event."""
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier)
    first = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-retransmit", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 100, "unit_cost": 500}], status="confirmed")
    second = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-retransmit", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 100, "unit_cost": 500}], status="confirmed")
    assert first.id == second.id

    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "CONFIRMED", "exact retransmission must not push the PO into OVER_CONFIRMED"
    assert _line(store, po.id).quantity_confirmed == 100
    assert service.inventory_position("mer_A", "SKU-1")["confirmed_inbound"] == 100


def test_delayed_acknowledgement_still_applies_correctly(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier)
    # "Delayed" here means arriving later in real time but still the next legitimate sequence - must
    # apply normally, not be mistaken for stale.
    result = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-delayed", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 100, "unit_cost": 500}], status="confirmed")
    assert result.applied is True
    assert store.get(type(po), "mer_A", po.id).status == "CONFIRMED"


def test_stale_out_of_order_acknowledgement_does_not_affect_cumulative_total(procurement):
    store, service, supplier = procurement
    po = _submitted_po(store, service, supplier)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-seq5", sequence=5, lines=[{"sku": "SKU-1", "quantity_confirmed": 60, "unit_cost": 500}], status="partially_confirmed")
    stale = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-seq1-stale", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 999, "unit_cost": 500}], status="confirmed")
    assert stale.applied is False
    line = _line(store, po.id)
    assert line.quantity_confirmed == 60, "a stale event's quantity must never be added to the cumulative total"
    assert service.inventory_position("mer_A", "SKU-1")["confirmed_inbound"] == 60


def test_multi_line_po_over_confirmation_is_per_line(procurement):
    store, service, supplier = procurement
    service.ingest_supplier_offer("mer_A", supplier.id, sku="SKU-2", supplier_sku="ACME-2", cost=300, currency="INR", moq=1, pack_quantity=1, lead_time_days=5)
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 50}, {"sku": "SKU-2", "quantity_ordered": 50}])
    po = service.submit_purchase_order("mer_A", po.id)
    service.record_supplier_acknowledgement(
        "mer_A", po.id, external_ref="ack-multi", sequence=1,
        lines=[{"sku": "SKU-1", "quantity_confirmed": 70, "unit_cost": 500}, {"sku": "SKU-2", "quantity_confirmed": 50, "unit_cost": 300}],
        status="confirmed",
    )
    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "OVER_CONFIRMED", "one over-confirmed line must flag the whole PO"
    line_1 = _line(store, po.id, "SKU-1")
    line_2 = _line(store, po.id, "SKU-2")
    assert line_1.quantity_confirmed == 70
    assert line_2.quantity_confirmed == 50
    assert service.inventory_position("mer_A", "SKU-1")["confirmed_inbound"] == 50, "SKU-1's over-confirmed excess must not enter confirmed_inbound"
    assert service.inventory_position("mer_A", "SKU-2")["confirmed_inbound"] == 50, "SKU-2's exact match is unaffected by SKU-1's over-confirmation"


def test_two_different_pos_same_sku_do_not_cross_contaminate_confirmation(procurement):
    store, service, supplier = procurement
    supplier_2 = service.upsert_supplier("mer_A", "Beta Supply", default_lead_time_days=3)
    service.ingest_supplier_offer("mer_A", supplier_2.id, sku="SKU-1", supplier_sku="BETA-1", cost=520, currency="INR", moq=1, pack_quantity=1, lead_time_days=3)

    po_1 = _submitted_po(store, service, supplier, sku="SKU-1", qty=50)
    po_2 = service.submit_purchase_order("mer_A", service.create_purchase_order("mer_A", supplier_2.id, [{"sku": "SKU-1", "quantity_ordered": 50}]).id)

    service.record_supplier_acknowledgement("mer_A", po_1.id, external_ref="po1-ack", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 50, "unit_cost": 500}], status="confirmed")
    line_1 = _line(store, po_1.id)
    line_2 = _line(store, po_2.id)
    assert line_1.quantity_confirmed == 50
    assert line_2.quantity_confirmed == 0, "acknowledging PO 1 must never touch PO 2's line, even for the identical SKU"
    # Cumulative confirmed_inbound correctly reflects BOTH orders' contributions once both confirm.
    service.record_supplier_acknowledgement("mer_A", po_2.id, external_ref="po2-ack", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 50, "unit_cost": 500}], status="confirmed")
    assert service.inventory_position("mer_A", "SKU-1")["confirmed_inbound"] == 100
