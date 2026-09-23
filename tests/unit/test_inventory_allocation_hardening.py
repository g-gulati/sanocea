from __future__ import annotations

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.packages.domain_contract.models import AuditEvent, Inventory, InventoryReservation, Order, OrderLine
from sanocea.packages.post_order import PostOrderOperationsService


def _order_with_lines(store, merchant_id: str, order_number: str, lines: list[tuple[str, int]], *, total_amount: int = 100000) -> Order:
    order = Order(merchant_id=merchant_id, channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    for sku, quantity in lines:
        store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=quantity, unit_amount=total_amount // max(quantity, 1)))
    return order


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory:
    return [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location][-1]


def _service(store, shopify):
    return PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))


# --- Part C/4: replay of the same order is idempotent, even after a fresh service/outer-command wipe ---

def test_allocation_replay_stays_at_the_originally_allocated_location(phase0):
    """A second, independent call into the ALLOCATOR directly (bypassing reserve_inventory_for_order's
    outer ConnectorCommand fast-path entirely) must still converge on the SAME location - proves the
    reservation-existence check inside `_allocate_and_reserve_order` itself is the true idempotency
    guard, not merely the outer cache."""
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-REPLAY", location_ref="Surat", quantity=5, available=5))
    order = _order_with_lines(store, "mer_A", "REPLAY-1", [("SKU-REPLAY", 2)])
    order_lines = [l for l in store.list(OrderLine, "mer_A") if l.order_id == order.id]
    first_results, first_shortfall = service._allocate_and_reserve_order("mer_A", order, order_lines)
    assert first_shortfall is False

    # Now add a SECOND location with ample stock - if the allocator were not idempotent, a naive replay
    # might now find Mumbai eligible too and create a duplicate/competing reservation there.
    store.put(Inventory(merchant_id="mer_A", sku="SKU-REPLAY", location_ref="Mumbai", quantity=100, available=100))
    second_results, second_shortfall = service._allocate_and_reserve_order("mer_A", order, order_lines)
    assert second_shortfall is False
    assert second_results == first_results

    surat = _inv(store, "mer_A", "SKU-REPLAY", "Surat")
    mumbai = _inv(store, "mer_A", "SKU-REPLAY", "Mumbai")
    assert surat.reserved == 2  # unchanged - not doubled
    assert mumbai.reserved == 0  # never touched by the replay
    reservations = [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id]
    assert len(reservations) == 1  # no duplicate reservation row


def test_full_reserve_inventory_for_order_replay_via_public_api(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-REPLAY2", location_ref="Surat", quantity=5, available=5))
    order = _order_with_lines(store, "mer_A", "REPLAY-2", [("SKU-REPLAY2", 2)])
    first = service.reserve_inventory_for_order("mer_A", order)
    assert first["already_done"] is False
    second = service.reserve_inventory_for_order("mer_A", order)
    assert second["already_done"] is True
    assert second["lines"] == first["lines"]
    assert _inv(store, "mer_A", "SKU-REPLAY2", "Surat").reserved == 2


# --- Part I: failure taxonomy ------------------------------------------------------------------------

def test_failure_reason_no_eligible_location(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    # zero Inventory rows at all for this SKU - the ranked candidate list starts empty
    order = _order_with_lines(store, "mer_A", "TAX-NOELIG", [("SKU-NOELIG", 3)])
    service.reserve_inventory_for_order("mer_A", order)
    events = [e for e in store.list_audit("mer_A") if e.action == "location_allocation_decision" and e.object_id == order.id]
    assert len(events) == 1
    assert events[0].result == "failed"
    assert events[0].requested_mutation["reason"] == "NO_ELIGIBLE_LOCATION"


def test_failure_reason_contention_exhausted(phase0):
    """The candidate looks eligible at the heuristic ATS read (ranking), but by the time the atomic
    attempt actually runs, a concurrent reservation has drained the stock - CONTENTION_EXHAUSTED, not
    NO_ELIGIBLE_LOCATION. The race window between ranking-read and atomic-attempt is simulated here by
    wrapping the store's atomic method to drain stock on its first invocation (single-threaded proof of
    the classification logic; true concurrent draining is proven separately with real Postgres)."""
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-CONTEND", location_ref="Surat", quantity=2, available=2))
    order = _order_with_lines(store, "mer_A", "TAX-CONTEND", [("SKU-CONTEND", 2)])

    real_atomic = store.reserve_order_lines_atomic
    call_count = {"n": 0}

    def draining_atomic(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # a concurrent order steals the stock between this order's ranking read and its own attempt
            store.reserve_inventory_atomic(
                "mer_A", "SKU-CONTEND", "Surat", quantity_requested=2,
                source_type="order", source_id="ord-other", idempotency_key="k-other-contend",
            )
        return real_atomic(*args, **kwargs)

    store.reserve_order_lines_atomic = draining_atomic
    try:
        service.reserve_inventory_for_order("mer_A", order)
    finally:
        store.reserve_order_lines_atomic = real_atomic

    events = [e for e in store.list_audit("mer_A") if e.action == "location_allocation_decision" and e.object_id == order.id]
    assert len(events) == 1
    assert events[0].result == "failed"
    assert events[0].requested_mutation["reason"] == "CONTENTION_EXHAUSTED"
    assert events[0].requested_mutation["attempts"][0]["outcome"] == "insufficient"


def test_failure_reason_already_allocated(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-ALREADY", location_ref="Surat", quantity=5, available=5))
    order = _order_with_lines(store, "mer_A", "TAX-ALREADY", [("SKU-ALREADY", 2)])
    order_lines = [l for l in store.list(OrderLine, "mer_A") if l.order_id == order.id]
    service._allocate_and_reserve_order("mer_A", order, order_lines)  # direct call, bypassing outer cache
    service._allocate_and_reserve_order("mer_A", order, order_lines)  # second direct call - hits the replay path
    events = [e for e in store.list_audit("mer_A") if e.action == "location_allocation_decision" and e.object_id == order.id]
    assert len(events) == 2
    assert events[0].result == "allocated"
    assert events[1].result == "already_allocated"


# --- Part H: audit truth - success is written only for a committed allocation -------------------------

def test_no_allocated_audit_event_exists_when_allocation_ultimately_fails(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-NOFALSE", location_ref="Surat", quantity=1, available=1))
    order = _order_with_lines(store, "mer_A", "TAX-NOFALSE", [("SKU-NOFALSE", 5)])
    service.reserve_inventory_for_order("mer_A", order)
    events = [e for e in store.list_audit("mer_A") if e.action == "location_allocation_decision" and e.object_id == order.id]
    assert all(e.result != "allocated" for e in events)  # never manufactured success evidence
    assert _inv(store, "mer_A", "SKU-NOFALSE", "Surat").reserved == 0


def test_allocated_audit_event_reflects_the_actual_committed_location(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-TRUTH", location_ref="Surat", quantity=1, available=1))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-TRUTH", location_ref="Mumbai", quantity=5, available=5))
    order = _order_with_lines(store, "mer_A", "TAX-TRUTH", [("SKU-TRUTH", 3)])  # only Mumbai can satisfy
    service.reserve_inventory_for_order("mer_A", order)
    events = [e for e in store.list_audit("mer_A") if e.action == "location_allocation_decision" and e.object_id == order.id]
    allocated_events = [e for e in events if e.result == "allocated"]
    assert len(allocated_events) == 1
    assert allocated_events[0].requested_mutation["selected_location"] == "Mumbai"
    assert _inv(store, "mer_A", "SKU-TRUTH", "Mumbai").reserved == 3


# --- Part G: impossible cross-location split fails cleanly (no real concurrency needed for this proof) -

def test_impossible_cross_location_split_fails_with_zero_reservations(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-GA", location_ref="Surat", quantity=1, available=1))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-GB", location_ref="Surat", quantity=0, available=0))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-GA", location_ref="Mumbai", quantity=0, available=0))
    store.put(Inventory(merchant_id="mer_A", sku="SKU-GB", location_ref="Mumbai", quantity=1, available=1))
    order = _order_with_lines(store, "mer_A", "TAX-SPLIT", [("SKU-GA", 1), ("SKU-GB", 1)])
    result = service.reserve_inventory_for_order("mer_A", order)
    assert result["reserved"] is False
    assert _inv(store, "mer_A", "SKU-GA", "Surat").reserved == 0
    assert _inv(store, "mer_A", "SKU-GB", "Mumbai").reserved == 0
    assert [r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id] == []


# --- Part J.13: tenant isolation, extended to the new whole-order-atomic + idempotent-replay path -----

def test_tenant_isolation_holds_for_allocation_and_replay(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    service = _service(store, shopify)
    store.put(Inventory(merchant_id="mer_A", sku="SKU-TEN", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id="mer_B", sku="SKU-TEN", location_ref="Surat", quantity=9, available=9))
    order_a = _order_with_lines(store, "mer_A", "TEN-A", [("SKU-TEN", 3)])
    service.reserve_inventory_for_order("mer_A", order_a)
    inv_a = _inv(store, "mer_A", "SKU-TEN", "Surat")
    inv_b = _inv(store, "mer_B", "SKU-TEN", "Surat")
    assert inv_a.reserved == 3
    assert inv_b.reserved == 0
    reservations_a = [r for r in store.list(InventoryReservation, "mer_A") if r.sku == "SKU-TEN"]
    reservations_b = [r for r in store.list(InventoryReservation, "mer_B") if r.sku == "SKU-TEN"]
    assert len(reservations_a) == 1
    assert len(reservations_b) == 0
