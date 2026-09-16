from __future__ import annotations

import pytest

from sanocea.connectors.chatwoot import ChatwootConnector  # noqa: F401 - not used, kept for fixture parity
from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.packages.domain_contract.models import (
    ConnectorCommand,
    Inventory,
    InventoryReservation,
    Order,
    OrderLine,
    Refund,
)
from sanocea.packages.post_order import PostOrderOperationsService

# Step 9 - CONSEQUENTIAL MUTATION READ-BACK + RECOVERY, refund + cancellation only.
#
# Core rule under test throughout: UNKNOWN RESULT != FAILED RESULT. A lost response
# (TimeoutError/RuntimeError) must never be silently retried while genuinely unknown, and must never be
# assumed failed/succeeded without authoritative external read-back (payments.find_refund /
# logistics.fetch("shipment", ...)).


@pytest.fixture
def svc(phase0):
    store, workflow, shopify, chatwoot = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {
        "refunds": {},
        "policy": {"refund": {"automatic_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}},
        "returns": {"window_days": 30},
        "cancellations": {"before_fulfilment": "ALLOW"},
    })
    payments = SimulatedPaymentConnector(store)
    logistics = SimulatedLogisticsConnector(store)
    service = PostOrderOperationsService(store, shopify, logistics, payments)
    return store, service, payments, logistics


def _paid_order(store, order_number, total_amount=1000):
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    return order


def _cancellable_order(store, service, logistics, order_number, sku="SKU-1", qty=1):
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=1000, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id="mer_A", order_id=order.id, sku=sku, title=sku, quantity=qty, unit_amount=500))
    store.put(Inventory(merchant_id="mer_A", sku=sku, location_ref="default", quantity=5, available=5))
    service.reserve_inventory_for_order("mer_A", order)
    logistics.seed_shipment("mer_A", order.id, "CREATED")
    return order


def _break_find_refund(payments):
    original = payments.find_refund
    payments.find_refund = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("read-back unavailable"))
    return original


def _break_fetch(logistics):
    original = logistics.fetch
    logistics.fetch = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("read-back unavailable"))
    return original


# =========================================================================================================
# REFUND
# =========================================================================================================

# --- 1: timeout + provider confirms success -------------------------------------------------------------

def test_refund_timeout_provider_confirms_success(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-1")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    resolved = service.execute_refund("mer_A", refund.id, simulate="timeout_after_mutation")
    assert resolved.status == "completed"
    commands = [c for c in store.list(ConnectorCommand, "mer_A") if c.object_id == refund.id]
    assert commands[-1].status == "succeeded"
    assert commands[-1].external_ref is not None


# --- 2: timeout + provider proves not applied -> safe controlled retry -----------------------------------

def test_refund_timeout_provider_proves_not_applied_safe_retry(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-2")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    resolved = service.execute_refund("mer_A", refund.id, simulate="timeout_before_mutation")
    assert resolved.status == "permitted", "provider proved nothing was applied - must resolve to a confirmed, retryable state"
    retried = service.execute_refund("mer_A", refund.id)
    assert retried.status == "completed"
    assert len(payments.refunds) == 1, "exactly one external refund must exist after the confirmed-not-applied retry"


# --- 3: timeout + provider still unknown -> no retry ------------------------------------------------------

def test_refund_timeout_still_unknown_no_retry(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-3")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    original = _break_find_refund(payments)
    try:
        resolved = service.execute_refund("mer_A", refund.id, simulate="timeout_before_mutation")
    finally:
        payments.find_refund = original
    assert resolved.status == "mutation_uncertain"
    replay = service.execute_refund("mer_A", refund.id)
    assert replay.status == "mutation_uncertain", "a plain call must never retry while genuinely unknown"
    assert len(payments.refunds) == 0


# --- 4: definitive rejection does not masquerade as uncertainty --------------------------------------------

def test_refund_definitive_rejection_does_not_masquerade_as_uncertainty(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-4")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    resolved = service.execute_refund("mer_A", refund.id, simulate="500")
    assert resolved.status not in {"mutation_uncertain", "mutation_submitted"}
    assert resolved.status == "permitted"


# --- 5: uncertain refund never causes duplicate money movement --------------------------------------------

def test_refund_uncertain_never_duplicates_money_movement(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-5")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    # First attempt is lost to a timeout AFTER the connector actually applied the mutation.
    resolved = service.execute_refund("mer_A", refund.id, simulate="timeout_after_mutation")
    assert resolved.status == "completed"
    # A caller retries anyway (e.g. a naive client unaware the first call already resolved) - the
    # guard (status not in the executable set) makes this a safe no-op, and even if it were not, the
    # connector's OWN business-key dedup (order_id:amount:currency:reason) would prevent a duplicate.
    replay = service.execute_refund("mer_A", refund.id)
    assert replay.status == "completed"
    assert len(payments.refunds) == 1


# --- 6: recovery replay is idempotent -----------------------------------------------------------------------

def test_refund_recovery_replay_is_idempotent(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-6")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    original = _break_find_refund(payments)
    try:
        uncertain = service.execute_refund("mer_A", refund.id, simulate="timeout_before_mutation")
    finally:
        payments.find_refund = original
    assert uncertain.status == "mutation_uncertain"

    first_recovery = service.recover_refund_mutation("mer_A", refund.id)
    assert first_recovery.status == "completed"
    assert len(payments.refunds) == 1

    second_recovery = service.recover_refund_mutation("mer_A", refund.id)
    assert second_recovery.status == "completed"
    assert second_recovery.id == first_recovery.id
    assert len(payments.refunds) == 1, "replaying recovery on an already-resolved refund must never re-attempt anything"


# =========================================================================================================
# CANCELLATION
# =========================================================================================================

# --- 7: uncertain cancellation + external read-back confirms cancelled -------------------------------------

def test_cancellation_recovery_confirms_cancelled(svc):
    store, service, payments, logistics = svc
    order = _cancellable_order(store, service, logistics, "MR-7")
    cancellation = service.evaluate_cancellation("mer_A", order)
    assert cancellation.status == "eligible"

    original = _break_fetch(logistics)
    try:
        # The connector genuinely applies the cancel (pushes a CANCELLED event) before raising - our
        # own read-back is what is broken here, not the provider's actual mutation.
        uncertain = service.execute_cancellation("mer_A", cancellation.id, simulate="timeout_after_mutation")
    finally:
        logistics.fetch = original
    assert uncertain.status == "mutation_uncertain"

    recovered = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert recovered.status == "completed"
    assert store.get(Order, "mer_A", order.id).status == "CANCELLED"
    reservation = next(r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id)
    assert reservation.quantity_released == reservation.quantity_reserved


# --- 8: provider proves cancellation not applied -> controlled retry ---------------------------------------

def test_cancellation_recovery_confirms_not_applied_then_retries(svc):
    store, service, payments, logistics = svc
    order = _cancellable_order(store, service, logistics, "MR-8")
    cancellation = service.evaluate_cancellation("mer_A", order)

    original = _break_fetch(logistics)
    try:
        uncertain = service.execute_cancellation("mer_A", cancellation.id, simulate="timeout_before_mutation")
    finally:
        logistics.fetch = original
    assert uncertain.status == "mutation_uncertain"

    recovered = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert recovered.status == "completed"
    assert store.get(Order, "mer_A", order.id).status == "CANCELLED"
    shipment_ref = logistics.shipments_by_order[order.id]
    cancelled_events = [e for e in logistics.shipments[shipment_ref]["events"] if e["status"] == "CANCELLED"]
    assert len(cancelled_events) == 1, "the confirmed-not-applied retry must produce exactly one real cancellation, not zero or two"


# --- 9: still unknown -> no retry ---------------------------------------------------------------------------

def test_cancellation_recovery_still_unknown_no_retry(svc):
    store, service, payments, logistics = svc
    order = _cancellable_order(store, service, logistics, "MR-9")
    cancellation = service.evaluate_cancellation("mer_A", order)

    _break_fetch(logistics)  # left broken for both the inline attempt and the recovery attempt below
    uncertain = service.execute_cancellation("mer_A", cancellation.id, simulate="timeout_before_mutation")
    assert uncertain.status == "mutation_uncertain"

    recovered = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert recovered.status == "mutation_uncertain"
    assert store.get(Order, "mer_A", order.id).status != "CANCELLED"


# --- 10: recovery never releases reservation twice -----------------------------------------------------------

def test_cancellation_recovery_never_releases_reservation_twice(svc):
    store, service, payments, logistics = svc
    order = _cancellable_order(store, service, logistics, "MR-10")
    cancellation = service.evaluate_cancellation("mer_A", order)

    original = _break_fetch(logistics)
    try:
        uncertain = service.execute_cancellation("mer_A", cancellation.id, simulate="timeout_after_mutation")
    finally:
        logistics.fetch = original
    assert uncertain.status == "mutation_uncertain"

    first = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert first.status == "completed"
    second = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert second.status == "completed"

    releases = [e for e in store.list_audit("mer_A") if e.action == "inventory_reservation_released" and e.object_id == cancellation.id]
    assert len(releases) == 1


# --- 11: stale/fulfilled order remains protected ----------------------------------------------------------

def test_cancellation_recovery_respects_stale_fulfilled_order(svc):
    store, service, payments, logistics = svc
    order = _cancellable_order(store, service, logistics, "MR-11")
    cancellation = service.evaluate_cancellation("mer_A", order)

    original = _break_fetch(logistics)
    try:
        uncertain = service.execute_cancellation("mer_A", cancellation.id, simulate="timeout_before_mutation")
    finally:
        logistics.fetch = original
    assert uncertain.status == "mutation_uncertain"

    # The order becomes fulfilled WHILE the cancellation sits uncertain.
    service.monitor_fulfilment("mer_A", order, status="fulfilled", age_hours=1)

    recovered = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert recovered.status == "stale_not_executable", "confirmed-not-applied must still re-validate current order state before retrying, never force a cancel on a now-fulfilled order"
    assert store.get(Order, "mer_A", order.id).status != "CANCELLED"


# --- 12: recovery replay is idempotent ------------------------------------------------------------------------

def test_cancellation_recovery_replay_is_idempotent(svc):
    store, service, payments, logistics = svc
    order = _cancellable_order(store, service, logistics, "MR-12")
    cancellation = service.evaluate_cancellation("mer_A", order)

    original = _break_fetch(logistics)
    try:
        uncertain = service.execute_cancellation("mer_A", cancellation.id, simulate="timeout_before_mutation")
    finally:
        logistics.fetch = original
    assert uncertain.status == "mutation_uncertain"

    first = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert first.status == "completed"
    second = service.recover_cancellation_mutation("mer_A", cancellation.id)
    third = service.recover_cancellation_mutation("mer_A", cancellation.id)
    assert second.status == third.status == "completed"
    assert second.id == third.id == first.id


# =========================================================================================================
# CROSS-CUTTING
# =========================================================================================================

# --- 13: tenant isolation --------------------------------------------------------------------------------

def test_recovery_tenant_isolation(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-13")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    from sanocea.packages.domain_contract.store import TenantAccessError
    with pytest.raises(TenantAccessError):
        service.recover_refund_mutation("mer_B", refund.id)

    order_c = _cancellable_order(store, service, logistics, "MR-13B")
    cancellation = service.evaluate_cancellation("mer_A", order_c)
    with pytest.raises(TenantAccessError):
        service.recover_cancellation_mutation("mer_B", cancellation.id)


# --- 14: persisted recovery evidence ----------------------------------------------------------------------

def test_recovery_persists_evidence(svc):
    store, service, payments, logistics = svc
    order = _paid_order(store, "MR-14")
    refund = service.evaluate_refund("mer_A", order, order.total_amount)
    original = _break_find_refund(payments)
    try:
        service.execute_refund("mer_A", refund.id, simulate="timeout_before_mutation")
    finally:
        payments.find_refund = original
    service.recover_refund_mutation("mer_A", refund.id)

    events = [e for e in store.list_audit("mer_A") if e.object_id == refund.id]
    actions = {e.action for e in events}
    assert "refund_mutation_still_unknown" in actions
    assert "refund_mutation_confirmed_not_applied" in actions
    commands = [c for c in store.list(ConnectorCommand, "mer_A") if c.object_id == refund.id]
    assert commands, "the last attempted mutation must remain persisted as evidence"
    assert any(c.action == "create_refund" for c in commands)
