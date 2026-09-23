from __future__ import annotations

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.packages.domain_contract.models import Order, OrderLine, Refund, Return
from sanocea.packages.post_order import PostOrderOperationsService


@pytest.fixture
def svc(phase0):
    store, workflow, shopify, chatwoot = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {
        "refunds": {},
        "policy": {"refund": {"automatic_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}},
        "returns": {"window_days": 30},
    })
    payments = SimulatedPaymentConnector(store)
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), payments)
    return store, service, payments


def _paid_order(store, order_number, total_amount=1000):
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    return order


def _forced_accepted_return(store, order, reason):
    ret = Return(merchant_id="mer_A", order_id=order.id, status="accepted", reason=reason, restockable=False)
    store.put(ret)
    return ret


def _refunds_for_order(store, order_id):
    return [r for r in store.list(Refund, "mer_A") if r.order_id == order_id]


# --- 7: denied Refund does not permanently consume capacity ------------------------------------------

def test_denied_refund_does_not_consume_capacity(svc):
    store, service, payments = svc
    order = _paid_order(store, "CAP-7", total_amount=1000)
    order.payment_status = "pending"  # forces DENY via the amount-independent path
    store.put(order)
    ret_a = _forced_accepted_return(store, order, "a")
    refund_a = service.evaluate_return_refund("mer_A", ret_a.id)
    assert refund_a.status == "denied"

    # Order becomes legitimately paid/refundable later - a second return must still see the FULL
    # authoritative capacity, unblocked by A's denied refund.
    order.payment_status = "paid"
    store.put(order)
    ret_b = _forced_accepted_return(store, order, "b")
    refund_b = service.evaluate_return_refund("mer_A", ret_b.id)
    assert refund_b is not None
    assert refund_b.status == "completed"
    assert refund_b.amount == 1000


# --- 8: mutation_uncertain (STILL_UNKNOWN - read-back itself fails) continues consuming capacity -------

def test_mutation_uncertain_continues_consuming_capacity(svc):
    """Step 9 correction: a bare timeout no longer stays "mutation_uncertain" forever - execute_refund's
    own inline read-back (payments.find_refund) now resolves timeout_before_mutation to a confirmed,
    retryable "permitted" (see test_runtime_error_confirmed_not_applied_still_reserves_capacity below for
    that case). To exercise the genuinely-STILL_UNKNOWN branch (the read-back mechanism itself is
    unavailable, not merely "not found"), this test injects a failure into find_refund directly - the
    correct failure-injection point for "provider cannot establish truth", per the Step 9 report."""
    store, service, payments = svc
    order = _paid_order(store, "CAP-8", total_amount=1000)
    ret_a = _forced_accepted_return(store, order, "a")
    refund_a = service.evaluate_refund("mer_A", order, order.total_amount, return_id=ret_a.id)

    original_find_refund = payments.find_refund
    payments.find_refund = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("read-back unavailable"))
    try:
        uncertain = service.execute_refund("mer_A", refund_a.id, simulate="timeout_before_mutation")
    finally:
        payments.find_refund = original_find_refund
    assert uncertain.status == "mutation_uncertain"

    ret_b = _forced_accepted_return(store, order, "b")
    refund_b = service.evaluate_return_refund("mer_A", ret_b.id)
    assert refund_b is None, "an uncertain refund must continue reserving the full capacity - no second refund may be created"
    assert len(_refunds_for_order(store, order.id)) == 1


# --- 9: definitive rejection (RuntimeError path) resolves via read-back, still reserves capacity -------

def test_runtime_error_confirmed_not_applied_still_reserves_capacity(svc):
    """Step 9 correction: execute_refund's RuntimeError branch now runs the SAME read-back as timeout
    (never trusting the exception type alone - see Step 9 report) and, since SimulatedPaymentConnector's
    429/500 errors are raised before any state write, resolves to CONFIRMED_NOT_APPLIED = "permitted"
    (a definitive rejection no longer masquerades as unresolved "mutation_submitted"). "permitted" is
    NOT "denied", so this method's capacity definition (everything except "denied" reserves) continues
    to reserve for it - proving the RuntimeError path is now BOTH more precise AND still capacity-safe."""
    store, service, payments = svc
    order = _paid_order(store, "CAP-9", total_amount=1000)
    ret_a = _forced_accepted_return(store, order, "a")
    refund_a = service.evaluate_refund("mer_A", order, order.total_amount, return_id=ret_a.id)
    resolved = service.execute_refund("mer_A", refund_a.id, simulate="500")
    assert resolved.status == "permitted", "a definitive rejection must resolve to a confirmed, retryable status, not stay stuck at mutation_submitted/mutation_uncertain"

    ret_b = _forced_accepted_return(store, order, "b")
    refund_b = service.evaluate_return_refund("mer_A", ret_b.id)
    assert refund_b is None
    assert len(_refunds_for_order(store, order.id)) == 1


# --- Item 6 (unit-level): approving the surviving Refund executes once ---------------------------------

def test_require_approval_surviving_refund_executes_once(svc):
    store, service, payments = svc
    store.set_config("mer_A", store.get_config("mer_A") | {"policy": {"refund": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"}}})
    order = _paid_order(store, "CAP-6", total_amount=1000)
    ret = _forced_accepted_return(store, order, "a")
    refund = service.evaluate_return_refund("mer_A", ret.id)
    assert refund.status == "approval_required"
    approved = service.approve_refund("mer_A", refund.id, "operator_1")
    assert approved.status == "approved"
    executed = service.execute_refund("mer_A", refund.id)
    assert executed.status == "completed"
    replay = service.execute_refund("mer_A", refund.id)
    assert replay.status == "completed"
    assert replay.id == executed.id


# --- Sequential cross-return over-refund prevention (deterministic, no threading needed) ---------------

def test_sequential_second_return_after_full_refund_creates_no_monetary_refund(svc):
    store, service, payments = svc
    order = _paid_order(store, "CAP-10", total_amount=1000)
    ret_a = _forced_accepted_return(store, order, "a")
    refund_a = service.evaluate_return_refund("mer_A", ret_a.id)
    assert refund_a.status == "completed"
    assert refund_a.amount == 1000

    ret_b = _forced_accepted_return(store, order, "b")
    refund_b = service.evaluate_return_refund("mer_A", ret_b.id)
    assert refund_b is None
    assert len(_refunds_for_order(store, order.id)) == 1
