from __future__ import annotations

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.packages.domain_contract.models import ExceptionRecord, Inventory, InventoryReservation, Order, OrderLine
from sanocea.packages.post_order import PostOrderOperationsService


def _fulfil(service: PostOrderOperationsService, merchant_id: str, order: Order) -> None:
    """Drives an order through the real `monitor_fulfilment` path with the storefront platform's own
    "fulfilled" signal - the corrected (2026-09) authoritative inventory-consume trigger, replacing the
    earlier DELIVERED-tracking-event choice. Mirrors how a genuine Shopify/WooCommerce/BigCommerce
    fulfilment-status poll/webhook would arrive, not a direct call to the internal consume helper."""
    service.monitor_fulfilment(merchant_id, order, "fulfilled", 1)


def _order_with_line(store, merchant_id: str, order_number: str, sku: str, quantity: int, *, total_amount: int = 100000) -> Order:
    order = Order(merchant_id=merchant_id, channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=quantity, unit_amount=total_amount // max(quantity, 1)))
    return order


# 1. reserve success
def test_reserve_success(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R1", location_ref="default", quantity=10, available=10))
    order = _order_with_line(store, "mer_A", "RSV-1", "SKU-R1", 4)
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    assert result["lines"][0]["reserved"] == 4
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R1"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (10, 4, 6)


# 2. insufficient ATS
def test_reserve_insufficient_ats_creates_exception_and_partial_reservation(phase0):
    """Step 3: partial reservation on shortfall is the EXPLICIT-location path's behavior specifically
    (unchanged from Step 1/2 - "explicit means explicit", no allocation, no rollback). Passes
    `location="default"` explicitly to exercise that path; see
    test_allocator_reports_full_shortfall_with_no_partial_reservation_when_no_location_specified for the
    NEW automatic-allocation behavior when no location is given at all."""
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R2", location_ref="default", quantity=2, available=2))
    order = _order_with_line(store, "mer_A", "RSV-2", "SKU-R2", 5)
    result = service.reserve_inventory_for_order("mer_A", order, location="default")
    assert result["reserved"] is False
    assert result["lines"][0] == {"sku": "SKU-R2", "requested": 5, "reserved": 2, "shortfall": 3}
    assert any(e.category == "inventory_conflict" for e in store.list(ExceptionRecord, "mer_A"))
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R2"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (2, 2, 0)


# Step 3: the NEW automatic-allocation behavior for the same scenario, no explicit location - no single
# eligible location can satisfy the full requirement, so the allocator reports a FULL shortfall (0
# reserved) rather than partially reserving anywhere, per Scenario D's no-split boundary.
def test_allocator_reports_full_shortfall_with_no_partial_reservation_when_no_location_specified(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R2B", location_ref="default", quantity=2, available=2))
    order = _order_with_line(store, "mer_A", "RSV-2B", "SKU-R2B", 5)
    result = service.reserve_inventory_for_order("mer_A", order)  # no location argument
    assert result["reserved"] is False
    assert result["lines"][0] == {"sku": "SKU-R2B", "requested": 5, "reserved": 0, "shortfall": 5}
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R2B"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (2, 0, 2)  # never partially reserved


# 3. duplicate reserve - both the operations-level outer guard and the DB-level primitive itself
def test_reserve_inventory_for_order_is_idempotent(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R3", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "RSV-3", "SKU-R3", 3)
    first = service.reserve_inventory_for_order("mer_A", order)
    second = service.reserve_inventory_for_order("mer_A", order)
    assert first["already_done"] is False
    assert second["already_done"] is True
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R3"][-1]
    assert inv.reserved == 3


def test_reserve_inventory_atomic_is_idempotent_at_the_primitive_level(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    store.put(Inventory(merchant_id="mer_A", sku="SKU-IDEMP", location_ref="default", quantity=5, available=5))
    r1 = store.reserve_inventory_atomic("mer_A", "SKU-IDEMP", "default", quantity_requested=3, source_type="order", source_id="ord-i", idempotency_key="dup-key")
    r2 = store.reserve_inventory_atomic("mer_A", "SKU-IDEMP", "default", quantity_requested=3, source_type="order", source_id="ord-i", idempotency_key="dup-key")
    assert r1.id == r2.id
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-IDEMP"][-1]
    assert inv.reserved == 3  # not 6 - the SAME idempotency_key must never reserve twice


# 4. cancel release
def test_cancellation_releases_exact_reserved_quantity(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"cancellations": {"before_fulfilment": "ALLOW"}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R4", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "RSV-4", "SKU-R4", 3)
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    assert cancellation.status == "eligible"
    service.execute_cancellation("mer_A", cancellation.id)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R4"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (5, 0, 5)


# 5. duplicate release
def test_duplicate_release_is_a_noop(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"cancellations": {"before_fulfilment": "ALLOW"}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R5", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "RSV-5", "SKU-R5", 3)
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    service.execute_cancellation("mer_A", cancellation.id)
    reservation = [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id][0]
    # execute_cancellation itself early-returns once status=="completed"; call the release primitive
    # directly a second time to prove ITS OWN idempotency, not just the outer status guard.
    store.adjust_reservation_atomic("mer_A", reservation.id, mode="release", amount=reservation.quantity_reserved)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R5"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (5, 0, 5)  # unchanged - not double-released


# 6. partial reservation then cancellation releases only owned quantity (EXPLICIT-location path - the
# automatic allocator never leaves a partial reservation to release, by design)
def test_partial_reservation_then_cancellation_releases_only_owned_quantity(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"cancellations": {"before_fulfilment": "ALLOW"}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R6", location_ref="default", quantity=3, available=3))
    order = _order_with_line(store, "mer_A", "RSV-6", "SKU-R6", 5)  # requests 5, only 3 ever available
    result = service.reserve_inventory_for_order("mer_A", order, location="default")
    assert result["lines"][0]["reserved"] == 3
    cancellation = service.evaluate_cancellation("mer_A", order)
    service.execute_cancellation("mer_A", cancellation.id)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R6"][-1]
    # releasing the REQUESTED quantity (5) instead of the OWNED quantity (3) would push reserved
    # negative - this is the exact bug Correction 2 exists to prevent.
    assert (inv.quantity, inv.reserved, inv.available) == (3, 0, 3)


# 7. consume-on-fulfilment (the raw primitive, and the real integration wiring via exchange completion -
# no order-fulfilment trigger point exists anywhere in the current codebase, confirmed by direct grep;
# see the Step 1 report for this disclosed, deliberately out-of-scope gap)
def test_consume_reservation_primitive_decrements_quantity_and_reserved_together(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    store.put(Inventory(merchant_id="mer_A", sku="SKU-R7", location_ref="default", quantity=10, available=10))
    reservation = store.reserve_inventory_atomic("mer_A", "SKU-R7", "default", quantity_requested=4, source_type="order", source_id="ord-x", idempotency_key="k-r7")
    store.adjust_reservation_atomic("mer_A", reservation.id, mode="consume", amount=reservation.quantity_reserved)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-R7"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (6, 0, 6)  # ATS stays economically consistent (6 before and after)


# 8. exchange reservation + cancellation release
def test_exchange_reservation_and_cancellation_release(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), SimulatedPaymentConnector(store))
    order = _order_with_line(store, "mer_A", "EXG-1", "SKU-ORIG", 1)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EXG", location_ref="default", quantity=2, available=2))
    exchange = service.evaluate_exchange("mer_A", order, "SKU-EXG")
    assert exchange.status == "reserved"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-EXG"][-1]
    assert (inv.reserved, inv.available) == (1, 1)
    cancelled = service.cancel_exchange("mer_A", exchange.id)
    assert cancelled.status == "cancelled"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-EXG"][-1]
    assert (inv.reserved, inv.available) == (0, 2)


def test_exchange_completion_consumes_its_reservation(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), SimulatedPaymentConnector(store))
    order = _order_with_line(store, "mer_A", "EXG-2", "SKU-ORIG2", 1)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-EXG2", location_ref="default", quantity=2, available=2))
    exchange = service.evaluate_exchange("mer_A", order, "SKU-EXG2")
    completed = service.complete_exchange("mer_A", exchange.id)
    assert completed.status == "completed"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-EXG2"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (1, 0, 1)  # consumed: quantity permanently reduced


# 9. restockable return
def test_restockable_return_restores_sellable_inventory(phase0):
    """Step 2 correction: restock is now RESERVATION-driven (restocks exactly what was CONSUMED at
    dispatch, at the location it was consumed from), not OrderLine-quantity-driven - so the realistic
    setup reserves and fulfils the order FIRST (a return can only happen after real fulfilment)."""
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"returns": {"window_days": 7, "auto_authorize": True}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), SimulatedPaymentConnector(store))
    order = _order_with_line(store, "mer_A", "RET-1", "SKU-RESTOCK", 2)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-RESTOCK", location_ref="default", quantity=5, available=5))
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    inv_after_fulfil = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RESTOCK"][-1]
    assert (inv_after_fulfil.quantity, inv_after_fulfil.reserved) == (3, 0)
    ret = service.evaluate_return("mer_A", order, "size_issue")
    assert ret.status == "authorized"
    for event in ["pickup_requested", "picked_up", "received"]:
        ret = service.progress_return("mer_A", ret.id, event)
    ret = service.progress_return("mer_A", ret.id, "inspection_passed", restockable=True)
    assert ret.status == "accepted"
    assert ret.restockable is True
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RESTOCK"][-1]
    assert (inv.quantity, inv.available) == (5, 5)  # the 2 consumed units are back
    # replaying the same terminal event must not double-restock
    service.progress_return("mer_A", ret.id, "inspection_passed", restockable=True)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RESTOCK"][-1]
    assert (inv.quantity, inv.available) == (5, 5)


# 10. non-restockable return
def test_non_restockable_return_does_not_increase_sellable_inventory(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"returns": {"window_days": 7, "auto_authorize": True}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), SimulatedPaymentConnector(store))
    order = _order_with_line(store, "mer_A", "RET-2", "SKU-DAMAGED", 2)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DAMAGED", location_ref="default", quantity=5, available=5))
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    ret = service.evaluate_return("mer_A", order, "damaged")
    for event in ["pickup_requested", "picked_up", "received"]:
        ret = service.progress_return("mer_A", ret.id, event)
    ret = service.progress_return("mer_A", ret.id, "inspection_passed", restockable=False)
    assert ret.status == "accepted"
    assert ret.restockable is False
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-DAMAGED"][-1]
    assert (inv.quantity, inv.available) == (3, 3)  # stays at post-fulfilment level, not restocked


# 11. refund does not restock
def test_refund_does_not_change_inventory(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    payments = SimulatedPaymentConnector(store)
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), payments)
    store.set_config("mer_A", {"refunds": {"automatic_limit": 100000, "above_limit": "REQUIRE_APPROVAL"}})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-REFUND", location_ref="default", quantity=5, available=5))
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="REF-1", status="PAID", payment_status="paid", total_amount=90000, currency="INR")
    store.put(order)
    refund = service.evaluate_refund("mer_A", order, 50000)
    assert refund.status == "permitted"
    completed = service.execute_refund("mer_A", refund.id, "customer_request")
    assert completed.status == "completed"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-REFUND"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (5, 0, 5)  # untouched by a pure financial event


# 12. inventory sync preserves outstanding reservations
def test_inventory_sync_preserves_outstanding_reservations(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-SYNC", location_ref="default", quantity=10, available=10))
    order = _order_with_line(store, "mer_A", "SYN-1", "SKU-SYNC", 4)
    service.reserve_inventory_for_order("mer_A", order)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-SYNC"][-1]
    assert (inv.reserved, inv.available) == (4, 6)
    # external system reports the SAME quantity - a routine sync, not a real stock change - must NOT
    # reset available to the raw synced quantity and discard the outstanding reservation.
    service.observe_inventory("mer_A", "SKU-SYNC", canonical_qty=10, external_qty=10)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-SYNC"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (10, 4, 6)


# 13. reserved never negative
def test_reserved_never_negative_even_when_releasing_more_than_owned(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    store.put(Inventory(merchant_id="mer_A", sku="SKU-FLOOR", location_ref="default", quantity=5, available=5))
    reservation = store.reserve_inventory_atomic("mer_A", "SKU-FLOOR", "default", quantity_requested=2, source_type="order", source_id="ord-f", idempotency_key="k-floor")
    store.adjust_reservation_atomic("mer_A", reservation.id, mode="release", amount=999)  # far more than ever reserved
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-FLOOR"][-1]
    assert inv.reserved == 0
    assert inv.reserved >= 0
    assert inv.available == 5  # released only the 2 actually owned, not 999


# 14. ATS invariant maintained across the full lifecycle
def test_ats_invariant_available_equals_quantity_minus_reserved_across_lifecycle(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    store.put(Inventory(merchant_id="mer_A", sku="SKU-ATS", location_ref="default", quantity=10, available=10))

    def _assert_invariant() -> Inventory:
        inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-ATS"][-1]
        assert inv.available == inv.quantity - inv.reserved, (inv.quantity, inv.reserved, inv.available)
        return inv

    _assert_invariant()
    r = store.reserve_inventory_atomic("mer_A", "SKU-ATS", "default", quantity_requested=4, source_type="order", source_id="ord-ats", idempotency_key="k-ats")
    _assert_invariant()
    store.adjust_reservation_atomic("mer_A", r.id, mode="consume", amount=2)
    _assert_invariant()
    store.reserve_inventory_atomic("mer_A", "SKU-ATS", "default", quantity_requested=3, source_type="order", source_id="ord-ats2", idempotency_key="k-ats2")
    _assert_invariant()
    store.adjust_reservation_atomic("mer_A", r.id, mode="release", amount=r.quantity_reserved)
    inv = _assert_invariant()
    assert inv.quantity == 8  # 10 - 2 consumed; the other 3 (reserved by ord-ats2) never left quantity


# --- Step 1A: order-fulfilment consumption -------------------------------------------------------


# 15. same-SKU multiple order lines do not collide (the traceability ambiguity found during Step 1A
# review: a sku-only idempotency key would treat the second line's reservation attempt as a replay of
# the first, silently reserving nothing for the second line's own quantity)
def test_multiple_order_lines_with_the_same_sku_each_reserve_their_own_quantity(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DUP", location_ref="default", quantity=10, available=10))
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="DUP-1", status="PAID", payment_status="paid", total_amount=200000, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id="mer_A", order_id=order.id, sku="SKU-DUP", title="line 1", quantity=2, unit_amount=50000))
    store.put(OrderLine(merchant_id="mer_A", order_id=order.id, sku="SKU-DUP", title="line 2", quantity=3, unit_amount=50000))
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is True
    reserved_amounts = sorted(l["reserved"] for l in result["lines"])
    assert reserved_amounts == [2, 3]  # each line reserved its OWN quantity, not one colliding with the other
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-DUP"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (10, 5, 5)  # 2 + 3, not just 2 or just 3
    reservations = [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id]
    assert len(reservations) == 2
    assert {r.order_line_id for r in reservations} == {l.id for l in store.list(OrderLine, "mer_A") if l.order_id == order.id}


# 1/3/4. fulfilment (dispatch) consumes reservation BEFORE final delivery; quantity+reserved move
# together; ATS invariant holds
def test_fulfilled_order_consumes_its_reservation_before_delivery(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DLV", location_ref="default", quantity=10, available=10))
    order = _order_with_line(store, "mer_A", "DLV-1", "SKU-DLV", 3)
    service.reserve_inventory_for_order("mer_A", order)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-DLV"][-1]
    assert (inv.reserved, inv.available) == (3, 7)
    _fulfil(service, "mer_A", order)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-DLV"][-1]
    # consumed at FULFILMENT, before any delivery/tracking event has even been observed
    assert (inv.quantity, inv.reserved, inv.available) == (7, 0, 7)
    order_after = store.get(Order, "mer_A", order.id)
    assert order_after.fulfillment_status == "fulfilled"  # the previously-dead field, now maintained


# 2. final DELIVERED does not consume again
def test_delivered_tracking_event_after_fulfilment_does_not_consume_again(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DLV2", location_ref="default", quantity=10, available=10))
    order = _order_with_line(store, "mer_A", "DLV2-1", "SKU-DLV2", 3)
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    inv_after_fulfil = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-DLV2"][-1]
    assert (inv_after_fulfil.quantity, inv_after_fulfil.reserved) == (7, 0)
    _status, external_ref = service.create_or_observe_shipment("mer_A", order)
    logistics.push_event(external_ref, "OUT_FOR_DELIVERY", 5)
    logistics.push_event(external_ref, "DELIVERED", 9)
    assert service.ingest_tracking("mer_A", external_ref) == "observed"  # purely observational now
    inv_after_delivery = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-DLV2"][-1]
    assert (inv_after_delivery.quantity, inv_after_delivery.reserved, inv_after_delivery.available) == (7, 0, 7)  # unchanged


# 3. duplicate dispatch/fulfilment does not double-consume
def test_duplicate_fulfilment_signal_does_not_double_consume(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-DUP2", location_ref="default", quantity=10, available=10))
    order = _order_with_line(store, "mer_A", "DUP2-1", "SKU-DUP2", 4)
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    # a repeated poll reporting "fulfilled" again (e.g. the storefront connector re-syncing the same
    # status) - guarded both by `order.fulfillment_status != "fulfilled"` and the underlying clamp
    service.monitor_fulfilment("mer_A", store.get(Order, "mer_A", order.id), "fulfilled", 1)
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-DUP2"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (6, 0, 6)  # consumed exactly once, not twice


# 7. cancellation is denied/blocked after canonical fulfilment (the previously-dead field, now real)
def test_cancellation_denied_after_fulfilment(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"cancellations": {"before_fulfilment": "ALLOW"}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-POSTDLV", location_ref="default", quantity=10, available=10))
    order = _order_with_line(store, "mer_A", "PDLV-1", "SKU-POSTDLV", 4)
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    order_after_fulfil = store.get(Order, "mer_A", order.id)
    cancellation = service.evaluate_cancellation("mer_A", order_after_fulfil)
    assert cancellation.status == "denied"  # evaluate_cancellation's existing check, now actually fed
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-POSTDLV"][-1]
    assert (inv.quantity, inv.reserved) == (6, 0)
    # Directly exercise the release primitive against the now-fully-consumed reservation too (proves the
    # INVENTORY-level invariant independently of the workflow-level denial above).
    reservation = [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id][0]
    store.adjust_reservation_atomic("mer_A", reservation.id, mode="release", amount=reservation.quantity_reserved)
    inv_after_release_attempt = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-POSTDLV"][-1]
    assert (inv_after_release_attempt.quantity, inv_after_release_attempt.reserved, inv_after_release_attempt.available) == (6, 0, 6)


# 8. refund still does not restock
def test_refund_after_fulfilment_does_not_restock(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    payments = SimulatedPaymentConnector(store)
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), payments)
    store.set_config("mer_A", {"refunds": {"automatic_limit": 100000, "above_limit": "REQUIRE_APPROVAL"}})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-REFDLV", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "REFDLV-1", "SKU-REFDLV", 2, total_amount=90000)
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    inv_after_fulfil = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-REFDLV"][-1]
    assert (inv_after_fulfil.quantity, inv_after_fulfil.reserved) == (3, 0)
    refund = service.evaluate_refund("mer_A", order, 50000)
    completed = service.execute_refund("mer_A", refund.id, "customer_request")
    assert completed.status == "completed"
    inv_after_refund = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-REFDLV"][-1]
    assert (inv_after_refund.quantity, inv_after_refund.reserved, inv_after_refund.available) == (3, 0, 3)  # unchanged


# fulfilment consumes only the reservation owned by that order/SKU
def test_fulfilment_of_one_order_does_not_consume_another_orders_reservation(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-ISO-A", location_ref="default", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-ISO-B", location_ref="default", quantity=5, available=5))
    order_a = _order_with_line(store, "mer_A", "ISO-A", "SKU-ISO-A", 2)
    order_b = _order_with_line(store, "mer_A", "ISO-B", "SKU-ISO-B", 3)
    service.reserve_inventory_for_order("mer_A", order_a)
    service.reserve_inventory_for_order("mer_A", order_b)
    _fulfil(service, "mer_A", order_a)
    inv_a = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-ISO-A"][-1]
    inv_b = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-ISO-B"][-1]
    assert (inv_a.quantity, inv_a.reserved) == (3, 0)  # order A's SKU: consumed
    assert (inv_b.quantity, inv_b.reserved, inv_b.available) == (5, 3, 2)  # order B's SKU: untouched


# NDR/DELIVERY_FAILED never consume or restock (unchanged invariant, re-verified under the new trigger)
def test_ndr_and_delivery_failure_do_not_change_inventory(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-NDR", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "NDR-1", "SKU-NDR", 2)
    service.reserve_inventory_for_order("mer_A", order)
    _status, external_ref = service.create_or_observe_shipment("mer_A", order)
    logistics.push_event(external_ref, "OUT_FOR_DELIVERY", 5)
    logistics.push_event(external_ref, "NDR", 6)
    assert service.ingest_tracking("mer_A", external_ref) == "ndr"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-NDR"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (5, 2, 3)  # unchanged - reservation still stands
    logistics.push_event(external_ref, "DELIVERY_FAILED", 7)
    assert service.ingest_tracking("mer_A", external_ref) == "exception"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-NDR"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (5, 2, 3)  # still unchanged


# 5. RTO detected does not restock
def test_rto_detected_does_not_restock(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-RTO1", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "RTO1-1", "SKU-RTO1", 2)
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    inv_after_fulfil = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RTO1"][-1]
    assert (inv_after_fulfil.quantity, inv_after_fulfil.reserved) == (3, 0)
    _status, external_ref = service.create_or_observe_shipment("mer_A", order)
    logistics.push_event(external_ref, "RTO_INITIATED", 5)
    assert service.ingest_tracking("mer_A", external_ref) == "rto"
    inv_after_rto_initiated = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RTO1"][-1]
    assert (inv_after_rto_initiated.quantity, inv_after_rto_initiated.reserved) == (3, 0)  # NOT restocked yet


# 6. RTO physically received back can later become a restock event - the received state (RTO_DELIVERED)
# already exists in the current model (confirmed via run_phase2_workload.py), so this is implemented,
# not merely documented as missing. Restocks exactly what was CONSUMED at dispatch.
def test_rto_delivered_restocks_exactly_what_was_consumed(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-RTO2", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "RTO2-1", "SKU-RTO2", 2)
    service.reserve_inventory_for_order("mer_A", order)
    _fulfil(service, "mer_A", order)
    _status, external_ref = service.create_or_observe_shipment("mer_A", order)
    logistics.push_event(external_ref, "RTO_INITIATED", 5)
    service.ingest_tracking("mer_A", external_ref)
    assert service.ingest_tracking("mer_A", external_ref) in {"observed", "rto"}  # already-processed events are stale/no-op on replay
    logistics.push_event(external_ref, "RTO_DELIVERED", 6)
    assert service.ingest_tracking("mer_A", external_ref) == "rto_delivered"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RTO2"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (5, 0, 5)  # the 2 consumed units are back

    # duplicate RTO_DELIVERED (e.g. a fresh service instance re-processing history) must not double-restock
    fresh_service = PostOrderOperationsService(store, shopify, logistics)
    fresh_service.ingest_tracking("mer_A", external_ref)
    inv_after_replay = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RTO2"][-1]
    assert (inv_after_replay.quantity, inv_after_replay.reserved, inv_after_replay.available) == (5, 0, 5)


def test_rto_delivered_without_prior_fulfilment_restocks_nothing(phase0):
    """An order that was never actually dispatched (monitor_fulfilment never observed "fulfilled") has
    nothing CONSUMED yet - RTO_DELIVERED must not inflate stock that was never removed."""
    store, _workflow, shopify, _chatwoot = phase0
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-RTO3", location_ref="default", quantity=5, available=5))
    order = _order_with_line(store, "mer_A", "RTO3-1", "SKU-RTO3", 2)
    service.reserve_inventory_for_order("mer_A", order)  # reserved, but never fulfilled/consumed
    _status, external_ref = service.create_or_observe_shipment("mer_A", order)
    logistics.push_event(external_ref, "RTO_DELIVERED", 5)
    assert service.ingest_tracking("mer_A", external_ref) == "rto_delivered"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-RTO3"][-1]
    assert (inv.quantity, inv.reserved, inv.available) == (5, 2, 3)  # unchanged - nothing was ever consumed
