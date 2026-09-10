from __future__ import annotations

import pytest

from sanocea.connectors.suppliers import SimulatedSupplierConnector, SupplierSimulator
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    GoodsReceiptLine,
    Inventory,
    Order,
    OrderLine,
    PurchaseOrderLine,
    now_utc,
)
from sanocea.packages.procurement import ProcurementService


@pytest.fixture
def procurement(phase0):
    store, *_ = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}})
    service = ProcurementService(store, SimulatedSupplierConnector(store))
    supplier = service.upsert_supplier("mer_A", "Acme Supplies", default_lead_time_days=5)
    return store, service, supplier


def _seed_offer(store, service, supplier, sku="SKU-1", supplier_sku="ACME-1", cost=500, moq=10, pack=5, lead_time=5):
    return service.ingest_supplier_offer("mer_A", supplier.id, sku=sku, supplier_sku=supplier_sku, cost=cost, currency="INR", moq=moq, pack_quantity=pack, lead_time_days=lead_time)


# --- Supplier ingestion: never invents cost/MOQ/lead time -------------------------------------------


def test_supplier_offer_requires_all_fields_never_invents(procurement):
    store, service, supplier = procurement
    offer = _seed_offer(store, service, supplier)
    assert offer.cost == 500
    assert offer.moq == 10
    assert offer.lead_time_days == 5


def test_po_line_without_supplier_offer_is_refused_not_invented(procurement):
    store, service, supplier = procurement
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "UNKNOWN-SKU", "quantity_ordered": 10}])
    assert po.status == "BLOCKED"
    lines = [l for l in store.list(PurchaseOrderLine, "mer_A") if l.purchase_order_id == po.id]
    assert lines == []
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "po_line_missing_supplier_offer" for e in exceptions)


# --- Inventory position / confirmed-inbound-not-sellable invariant ----------------------------------


def test_inventory_position_distinguishes_all_dimensions(procurement):
    store, service, supplier = procurement
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=10, reserved=3, available=7, confirmed_inbound=5))
    position = service.inventory_position("mer_A", "SKU-1")
    assert position == {
        "sku": "SKU-1", "on_hand": 10, "reserved": 3, "confirmed_inbound": 5,
        "available_to_sell": 7, "inventory_position": 12,  # 10 - 3 + 5
    }


def test_confirmed_inbound_never_becomes_sellable_until_goods_receipt(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=2, available=2))
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    assert po.status == "AUTO_APPROVED"
    po = service.submit_purchase_order("mer_A", po.id)
    assert po.status == "SUBMITTED"

    ack = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}], status="confirmed")
    assert ack.applied
    position = service.inventory_position("mer_A", "SKU-1")
    assert position["confirmed_inbound"] == 20
    assert position["available_to_sell"] == 2, "confirmed inbound must NOT be sellable"

    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 20}])
    position = service.inventory_position("mer_A", "SKU-1")
    assert position["available_to_sell"] == 2, "dispatch must NOT be sellable either"

    service.record_goods_receipt("mer_A", po.id, external_receipt_ref="rcpt-1", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 20}])
    position = service.inventory_position("mer_A", "SKU-1")
    assert position["confirmed_inbound"] == 0
    assert position["available_to_sell"] == 22


# --- State-machine guards: an event cannot drive a PO that never legitimately reached that state -----


def test_acknowledgement_refused_for_po_never_submitted(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    assert po.status == "AUTO_APPROVED"
    ack = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="premature", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}], status="confirmed")
    assert ack.applied is False
    po_after = store.get(type(po), "mer_A", po.id)
    assert po_after.status == "AUTO_APPROVED"


def test_goods_receipt_refused_before_shipment(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    po = service.submit_purchase_order("mer_A", po.id)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}], status="confirmed")
    # never dispatched - PO is CONFIRMED, not INBOUND/PARTIALLY_RECEIVED
    receipt = service.record_goods_receipt("mer_A", po.id, external_receipt_ref="too-early", lines=[{"raw_sku_reference": "SKU-1", "quantity_received": 20}])
    assert receipt.status == "received_with_exceptions"
    position = service.inventory_position("mer_A", "SKU-1")
    assert position["on_hand"] == 0, "inventory must not move on a refused receipt"


# --- Stale / out-of-order / duplicate events ----------------------------------------------------------


def test_stale_acknowledgement_does_not_regress_state(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    po = service.submit_purchase_order("mer_A", po.id)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-2", sequence=2, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}], status="confirmed")
    po_after_full = store.get(type(po), "mer_A", po.id)
    assert po_after_full.status == "CONFIRMED"
    position_after_full = service.inventory_position("mer_A", "SKU-1")

    stale = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1-stale", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 5, "unit_cost": 500}], status="partially_confirmed")
    assert stale.applied is False
    po_after_stale = store.get(type(po), "mer_A", po.id)
    assert po_after_stale.status == "CONFIRMED", "a stale (lower-sequence) event must not regress PO state"
    assert service.inventory_position("mer_A", "SKU-1") == position_after_full
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "stale_acknowledgement_ignored" for e in exceptions)


def test_duplicate_acknowledgement_event_is_idempotent(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    po = service.submit_purchase_order("mer_A", po.id)
    first = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="dup-ack", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}], status="confirmed")
    second = service.record_supplier_acknowledgement("mer_A", po.id, external_ref="dup-ack", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}], status="confirmed")
    assert first.id == second.id
    line = next(l for l in store.list(PurchaseOrderLine, "mer_A") if l.purchase_order_id == po.id)
    assert line.quantity_confirmed == 20, "duplicate ack must not double-count confirmed quantity"


# --- Cost controls: unknown cost never becomes expected cost (Phase 3 lesson) ------------------------


def test_unknown_supplier_cost_never_silently_accepted(procurement):
    store, service, supplier = procurement
    decision, info = service._cost_decision("mer_A", None, 999)
    from sanocea.packages.policy_engine.engine import Decision
    assert decision == Decision.DENY
    assert info["reason"] == "no_known_supplier_offer_cost"


def test_cost_change_on_acknowledgement_is_flagged(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier, cost=500)
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}, "cost_tolerance": {"pct": 0.02, "above_tolerance": "REQUIRE_APPROVAL"}}})
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    po = service.submit_purchase_order("mer_A", po.id)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-cost", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 650}], status="confirmed")
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "po_cost_variance" for e in exceptions)


# --- Procurement authority: ALLOW / REQUIRE_APPROVAL / DENY -------------------------------------------


def test_po_above_spending_threshold_requires_approval(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier, cost=500)
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000, "above_limit": "REQUIRE_APPROVAL"}}})
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])  # value 10000 > 1000
    assert po.status == "REQUIRES_APPROVAL"
    assert po.approval_id


def test_po_approval_unblocks_submission(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier, cost=500)
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000, "above_limit": "REQUIRE_APPROVAL"}}})
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    assert po.status == "REQUIRES_APPROVAL"
    still_blocked = service.submit_purchase_order("mer_A", po.id)
    assert still_blocked.status == "REQUIRES_APPROVAL", "must not submit before approval"
    approved = service.approve_purchase_order("mer_A", po.id)
    assert approved.status == "APPROVED"
    submitted = service.submit_purchase_order("mer_A", approved.id)
    assert submitted.status == "SUBMITTED"


def test_approving_a_po_resolves_its_requires_approval_exception(procurement):
    """A PO that needed approval and then got approved must not be permanently blocked from closing by
    its own now-stale 'requires approval' notice - that would make reconcile_purchase_order's
    open-exception guard fire forever on every legitimately-approved order."""
    store, service, supplier = procurement
    _seed_offer(store, service, supplier, cost=500)
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000, "above_limit": "REQUIRE_APPROVAL"}}})
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    assert po.status == "REQUIRES_APPROVAL"
    open_before = [e for e in store.list(ExceptionRecord, "mer_A") if e.object_id == po.id and e.status == "open"]
    assert len(open_before) == 1

    service.approve_purchase_order("mer_A", po.id)
    open_after = [e for e in store.list(ExceptionRecord, "mer_A") if e.object_id == po.id and e.status == "open"]
    assert open_after == []
    resolved = [e for e in store.list(ExceptionRecord, "mer_A") if e.object_id == po.id and e.status == "resolved"]
    assert len(resolved) == 1


def test_low_reliability_supplier_requires_approval_regardless_of_value(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier, cost=500)
    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}, "supplier_reliability_threshold": 0.8}})
    supplier.reliability_score = 0.5
    store.put(supplier)
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 5}])
    assert po.status == "REQUIRES_APPROVAL"


# --- Goods receipt discrepancies ----------------------------------------------------------------------


def test_goods_receipt_detects_shortage_excess_and_wrong_sku(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier, sku="SKU-1")
    _seed_offer(store, service, supplier, sku="SKU-2", supplier_sku="ACME-2")
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 10}, {"sku": "SKU-2", "quantity_ordered": 10}])
    po = service.submit_purchase_order("mer_A", po.id)
    service.record_supplier_acknowledgement("mer_A", po.id, external_ref="ack-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_confirmed": 10, "unit_cost": 500}, {"sku": "SKU-2", "quantity_confirmed": 10, "unit_cost": 500}], status="confirmed")
    service.record_inbound_shipment("mer_A", po.id, external_shipment_ref="ship-1", sequence=1, lines=[{"sku": "SKU-1", "quantity_shipped": 10}, {"sku": "SKU-2", "quantity_shipped": 10}])

    receipt = service.record_goods_receipt(
        "mer_A", po.id, external_receipt_ref="rcpt-mixed",
        lines=[
            {"raw_sku_reference": "SKU-1", "quantity_received": 7},   # shortage
            {"raw_sku_reference": "SKU-2", "quantity_received": 12},  # excess
            {"raw_sku_reference": "SKU-UNKNOWN", "quantity_received": 3},  # wrong sku / unresolved
        ],
    )
    assert receipt.status == "received_with_exceptions"
    lines = [l for l in store.list(GoodsReceiptLine, "mer_A") if l.goods_receipt_id == receipt.id]
    dispositions = {l.disposition for l in lines}
    assert dispositions == {"shortage", "excess", "wrong_sku"}
    unresolved_line = next(l for l in lines if l.disposition == "wrong_sku")
    assert unresolved_line.sku is None
    assert unresolved_line.raw_sku_reference == "SKU-UNKNOWN"

    # Only the resolvable SKUs move inventory, and only by the ACTUAL counted amount.
    pos_1 = service.inventory_position("mer_A", "SKU-1")
    pos_2 = service.inventory_position("mer_A", "SKU-2")
    assert pos_1["on_hand"] == 7
    assert pos_2["on_hand"] == 12


# --- Deterministic supplier selection: no universal "best supplier" -----------------------------------


def test_supplier_selection_is_deterministic_by_configured_priority(procurement):
    store, service, supplier_a = procurement
    _seed_offer(store, service, supplier_a, sku="SKU-1", supplier_sku="A-1", cost=600, moq=1, lead_time=10)
    supplier_b = service.upsert_supplier("mer_A", "Beta Supply", default_lead_time_days=3)
    service.ingest_supplier_offer("mer_A", supplier_b.id, sku="SKU-1", supplier_sku="B-1", cost=550, currency="INR", moq=1, pack_quantity=1, lead_time_days=3)

    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"supplier_priority": ["cost"]}})
    chosen = service.select_supplier_offer("mer_A", "SKU-1")
    assert chosen.supplier_id == supplier_b.id, "cheapest supplier must win when priority=cost"

    store.set_config("mer_A", store.get_config("mer_A") | {"procurement": {"supplier_priority": ["lead_time_days"]}})
    chosen = service.select_supplier_offer("mer_A", "SKU-1")
    assert chosen.supplier_id == supplier_b.id, "fastest supplier must win when priority=lead_time_days"


# --- Replenishment reasoning must be explicit ----------------------------------------------------------


def test_replenishment_recommendation_explains_itself(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=1, available=1))
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="O-VEL", status="PAID", payment_status="paid", total_amount=1000, currency="INR", placed_at=now_utc())
    store.put(order)
    store.put(OrderLine(merchant_id="mer_A", order_id=order.id, title="x", sku="SKU-1", quantity=30, unit_amount=50))

    rec = service.recommend_replenishment("mer_A", "SKU-1")
    assert rec.recommended_quantity > 0
    assert "reorder_point_formula" in rec.reasoning
    assert "explanation" in rec.reasoning
    assert rec.chosen_supplier_id == supplier.id


def test_no_replenishment_recommended_when_above_reorder_point(procurement):
    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=500, available=500))
    rec = service.recommend_replenishment("mer_A", "SKU-1")
    assert rec.recommended_quantity == 0
    assert rec.reasoning["needs_reorder"] is False


# --- Tenant isolation ------------------------------------------------------------------------------


def test_purchase_orders_remain_tenant_scoped(procurement):
    from sanocea.packages.domain_contract.store import TenantAccessError

    store, service, supplier = procurement
    _seed_offer(store, service, supplier)
    po = service.create_purchase_order("mer_A", supplier.id, [{"sku": "SKU-1", "quantity_ordered": 20}])
    assert store.list(type(po), "mer_B") == []
    with pytest.raises(TenantAccessError):
        store.get(type(po), "mer_B", po.id)
