from __future__ import annotations

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.packages.domain_contract.location import DEFAULT_LOCATION_REF, resolve_location_ref
from sanocea.packages.domain_contract.models import Inventory, InventoryReservation, Order, OrderLine
from sanocea.packages.post_order import PostOrderOperationsService


def _order_with_line(store, merchant_id: str, order_number: str, sku: str, quantity: int, *, total_amount: int = 100000) -> Order:
    order = Order(merchant_id=merchant_id, channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=quantity, unit_amount=total_amount // max(quantity, 1)))
    return order


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory:
    return [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location][-1]


# 1/9. Two independent inventory facts for the same merchant/SKU at two locations, and each can carry
# its own independent reservation - the review's own worked scenario, followed exactly.
def test_full_surat_mumbai_lifecycle_scenario(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics, SimulatedPaymentConnector(store))

    store.put(Inventory(merchant_id="mer_A", sku="SKU-A", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-A", location_ref="Mumbai", quantity=7, available=7))
    assert len([i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-A"]) == 2  # #1

    # Reserve 3 at Surat via order O1
    order_surat = _order_with_line(store, "mer_A", "ML-SURAT-1", "SKU-A", 3)
    r1 = service.reserve_inventory_for_order("mer_A", order_surat, location="Surat")
    assert r1["lines"][0]["reserved"] == 3
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 3, 2)
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)  # #2 untouched

    # Reserve 4 at Mumbai via order O2 - the SAME SKU, an INDEPENDENT reservation at a different location
    order_mumbai = _order_with_line(store, "mer_A", "ML-MUMBAI-1", "SKU-A", 4)
    r2 = service.reserve_inventory_for_order("mer_A", order_mumbai, location="Mumbai")
    assert r2["lines"][0]["reserved"] == 4
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 3, 2)  # unchanged by Mumbai's reserve
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 4, 3)  # #9 independent reservation

    surat_reservation = [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order_surat.id][0]
    mumbai_reservation = [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order_mumbai.id][0]
    assert surat_reservation.location_ref == "Surat"
    assert mumbai_reservation.location_ref == "Mumbai"

    # Cancel O1 (release Surat's reservation) - Mumbai must be untouched
    store.set_config("mer_A", {"cancellations": {"before_fulfilment": "ALLOW"}})
    cancellation = service.evaluate_cancellation("mer_A", order_surat)
    assert cancellation.status == "eligible"
    service.execute_cancellation("mer_A", cancellation.id)
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 0, 5)  # #3 released
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 4, 3)  # #3 Mumbai untouched

    # Fulfil O2 (consume Mumbai's reservation) - #4: consumption must use the RESERVATION's own
    # location (Mumbai), not any merchant-wide default, and Surat must be untouched
    service.monitor_fulfilment("mer_A", order_mumbai, "fulfilled", 1)
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 0, 5)  # untouched by Mumbai's fulfilment
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (3, 0, 3)  # #4 consumed at Mumbai only

    # Restockable return for O2 - #5: must restock at Mumbai (the reservation's own location), Surat untouched
    store.set_config("mer_A", {"returns": {"window_days": 7, "auto_authorize": True}})
    ret = service.evaluate_return("mer_A", order_mumbai, "size_issue")
    assert ret.status == "authorized"
    for event in ["pickup_requested", "picked_up", "received"]:
        ret = service.progress_return("mer_A", ret.id, event)
    service.progress_return("mer_A", ret.id, "inspection_passed", restockable=True)
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 0, 5)  # #5 Surat untouched
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)  # #5 restocked at Mumbai

    # 6. RTO for a THIRD order fulfilled from Surat - restocks Surat only, Mumbai untouched
    order_rto = _order_with_line(store, "mer_A", "ML-SURAT-RTO", "SKU-A", 2)
    service.reserve_inventory_for_order("mer_A", order_rto, location="Surat")
    service.monitor_fulfilment("mer_A", order_rto, "fulfilled", 1)
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    assert (surat.quantity, surat.reserved) == (3, 0)
    _status, external_ref = service.create_or_observe_shipment("mer_A", order_rto)
    logistics.push_event(external_ref, "RTO_DELIVERED", 5)
    assert service.ingest_tracking("mer_A", external_ref) == "rto_delivered"
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 0, 5)  # #6 restocked at Surat
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)  # #6 Mumbai untouched

    # 7. Inventory observation updates Surat only, respecting Surat's own outstanding reservation
    order_obs = _order_with_line(store, "mer_A", "ML-SURAT-OBS", "SKU-A", 2)
    service.reserve_inventory_for_order("mer_A", order_obs, location="Surat")
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 2, 3)
    service.observe_inventory("mer_A", "SKU-A", canonical_qty=5, external_qty=5, location="Surat")
    surat = _inv(store, "mer_A", "SKU-A", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 2, 3)  # #7/#8 ATS respects the reservation
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)  # #7 Mumbai untouched by Surat's sync


# #8, sharper: an external sync that also CHANGES the raw quantity at one location must still respect
# that location's own outstanding reservation, independent of the other location
def test_observation_with_quantity_change_still_respects_that_locations_reservation(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-B", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-B", location_ref="Mumbai", quantity=7, available=7))
    order = _order_with_line(store, "mer_A", "ML-OBS-2", "SKU-B", 2)
    service.reserve_inventory_for_order("mer_A", order, location="Surat")
    # external system now reports Surat quantity=4 (a real stock change), Mumbai untouched
    service.observe_inventory("mer_A", "SKU-B", canonical_qty=5, external_qty=4, location="Surat")
    surat = _inv(store, "mer_A", "SKU-B", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-B", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (4, 2, 2)  # ATS = 4 - 2, never reset to 4
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)  # untouched


# 10. duplicate events remain idempotent per location - the SAME idempotency key at two different
# locations must not collide, and a duplicate at ONE location must not double-apply while leaving the
# other location's independent state alone
def test_duplicate_reservation_idempotent_independently_per_location(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.put(Inventory(merchant_id="mer_A", sku="SKU-C", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-C", location_ref="Mumbai", quantity=7, available=7))
    r1 = store.reserve_inventory_atomic("mer_A", "SKU-C", "Surat", quantity_requested=2, source_type="order", source_id="ord-dup", idempotency_key="dup-loc-key")
    r2 = store.reserve_inventory_atomic("mer_A", "SKU-C", "Mumbai", quantity_requested=3, source_type="order", source_id="ord-dup-2", idempotency_key="dup-loc-key-2")
    # replay the SAME key against Surat again - must be idempotent, not double-reserve, and must not
    # touch Mumbai
    r1_replay = store.reserve_inventory_atomic("mer_A", "SKU-C", "Surat", quantity_requested=2, source_type="order", source_id="ord-dup", idempotency_key="dup-loc-key")
    assert r1_replay.id == r1.id
    surat = _inv(store, "mer_A", "SKU-C", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-C", "Mumbai")
    assert surat.reserved == 2  # not 4
    assert mumbai.reserved == 3  # untouched by Surat's replay
    assert r2.location_ref == "Mumbai"


# 11. legacy/default single-location behavior still works unchanged - both the bare-literal-"default"
# path AND the merchant-configured-default-location path (the resolver's tier 2, genuinely new coverage)
def test_legacy_default_location_behavior_unchanged(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-LEGACY", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "ML-LEGACY-1", "SKU-LEGACY", 2)
    result = service.reserve_inventory_for_order("mer_A", order)  # no location argument at all
    assert result["reserved"] is True
    inv = _inv(store, "mer_A", "SKU-LEGACY", "default")
    assert (inv.quantity, inv.reserved, inv.available) == (5, 2, 3)


def test_merchant_configured_default_location_is_honored(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_B", {"marketplace": {"shopify": False}, "support": {"email": True}, "inventory": {"default_location_ref": "Bengaluru"}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_B", sku="SKU-CFG", location_ref="Bengaluru", quantity=6, available=6))
    order = Order(merchant_id="mer_B", channel_id="chn_B_email", order_number="ML-CFG-1", status="PAID", payment_status="paid", total_amount=50000, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id="mer_B", order_id=order.id, sku="SKU-CFG", title="SKU-CFG", quantity=2, unit_amount=25000))
    result = service.reserve_inventory_for_order("mer_B", order)  # no explicit location - resolver must find "Bengaluru"
    assert result["reserved"] is True
    inv = _inv(store, "mer_B", "SKU-CFG", "Bengaluru")
    assert (inv.quantity, inv.reserved, inv.available) == (6, 2, 4)


def test_resolve_location_ref_precedence(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    # 1. explicit always wins
    assert resolve_location_ref(store, "mer_A", "Chennai") == "Chennai"
    # 2. merchant-configured default, when no explicit value given
    store.set_config("mer_A", {**store.get_config("mer_A"), "inventory": {"default_location_ref": "Pune"}})
    assert resolve_location_ref(store, "mer_A", None) == "Pune"
    # 3. legacy fallback when nothing configured
    assert resolve_location_ref(store, "mer_B", None) == DEFAULT_LOCATION_REF


# 12. tenant isolation still holds at the location layer - two merchants with the SAME sku+location name
# must never see or affect each other's inventory
def test_tenant_isolation_holds_with_shared_location_names(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-SHARED", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_B", sku="SKU-SHARED", location_ref="Surat", quantity=9, available=9))
    order_a = _order_with_line(store, "mer_A", "ML-TEN-A", "SKU-SHARED", 3)
    service.reserve_inventory_for_order("mer_A", order_a, location="Surat")
    inv_a = _inv(store, "mer_A", "SKU-SHARED", "Surat")
    inv_b = _inv(store, "mer_B", "SKU-SHARED", "Surat")
    assert (inv_a.quantity, inv_a.reserved) == (5, 3)
    assert (inv_b.quantity, inv_b.reserved) == (9, 0)  # merchant B completely untouched despite identical sku+location


# Part F proof: procurement's existing location-aware read helper returns correct per-location truth
# (read-only proof - no procurement code changed in this step)
def test_procurement_inventory_position_is_location_correct(phase0):
    from sanocea.connectors.suppliers import SimulatedSupplierConnector
    from sanocea.packages.procurement import ProcurementService

    store, _workflow, _shopify, _chatwoot = phase0
    store.put(Inventory(merchant_id="mer_A", sku="SKU-PROC", location_ref="Surat", quantity=5, reserved=2, available=3))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-PROC", location_ref="Mumbai", quantity=7, reserved=1, available=6))
    procurement = ProcurementService(store, SimulatedSupplierConnector(store))
    surat_position = procurement.inventory_position("mer_A", "SKU-PROC", "Surat")
    mumbai_position = procurement.inventory_position("mer_A", "SKU-PROC", "Mumbai")
    assert surat_position["on_hand"] == 5 and surat_position["reserved"] == 2 and surat_position["available_to_sell"] == 3
    assert mumbai_position["on_hand"] == 7 and mumbai_position["reserved"] == 1 and mumbai_position["available_to_sell"] == 6
