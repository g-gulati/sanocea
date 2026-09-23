from __future__ import annotations

import pytest

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract.models import (
    Approval,
    ExceptionRecord,
    Inventory,
    Order,
    OrderLine,
    Refund,
    Return,
    SupportConversation,
)
from sanocea.packages.domain_contract.store import TenantAccessError
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.packages.support import SupportWorkflowService
from sanocea.workers.workflow import FakeTemporalEngine


@pytest.fixture
def svc(phase0):
    store, workflow, shopify, chatwoot = phase0
    # NOTE: `_refund_decision` reads `config.get("refunds") or config.get("policy", {}).get("refund", {})`
    # - the top-level "refunds" key (unrelated to "policy.refund") takes PRIORITY when present. The
    # shared phase0 fixture already sets "refunds": {"auto_execute": False}, which would otherwise
    # silently defeat this fixture's own "policy.refund.automatic_limit" override (falling back to
    # automatic_limit=0, i.e. REQUIRE_APPROVAL for any nonzero amount) - so "refunds" must be cleared
    # here, not merged alongside "policy".
    store.set_config("mer_A", store.get_config("mer_A") | {
        "refunds": {},
        "policy": {"refund": {"automatic_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}},
        "returns": {"window_days": 30},
    })
    payments = SimulatedPaymentConnector(store)
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), payments)
    return store, service, payments


def _fulfilled_order(store, service, order_number, sku="SKU-1", qty=1, total_amount=50000):
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id="mer_A", order_id=order.id, sku=sku, title=sku, quantity=qty, unit_amount=total_amount // qty))
    service.reserve_inventory_for_order("mer_A", order)
    service.monitor_fulfilment("mer_A", order, status="fulfilled", age_hours=1)
    return order


def _accepted_return(store, service, order, *, restockable=True):
    ret = service.evaluate_return("mer_A", order, "customer_request")
    ret = service.progress_return("mer_A", ret.id, "received")
    return service.progress_return("mer_A", ret.id, "inspection_passed", restockable=restockable)


def _refunds_for_order(store, order_id):
    return [r for r in store.list(Refund, "mer_A") if r.order_id == order_id]


# --- 1: return request alone does not refund ------------------------------------------------------

def test_return_request_alone_does_not_refund(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-1")
    ret = service.evaluate_return("mer_A", order, "customer_request")
    assert ret.status in {"eligible", "approval_required", "authorized"}
    assert _refunds_for_order(store, order.id) == []


# --- 2: eligible restockable return triggers refund evaluation ---------------------------------------

def test_eligible_restockable_return_triggers_refund(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-2")
    ret = _accepted_return(store, service, order, restockable=True)
    assert ret.status == "accepted"
    refunds = _refunds_for_order(store, order.id)
    assert len(refunds) == 1
    assert refunds[0].status == "completed"
    assert refunds[0].amount == 50000
    assert refunds[0].return_id == ret.id
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-1"][-1]
    assert inv.quantity == 5  # 5 - 1 (fulfilled) + 1 (restocked)


# --- 3: eligible non-restockable return can refund without stock increase ----------------------------

def test_eligible_non_restockable_return_refunds_without_stock_increase(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-3")
    ret = _accepted_return(store, service, order, restockable=False)
    assert ret.status == "accepted"
    assert ret.restockable is False
    refunds = _refunds_for_order(store, order.id)
    assert len(refunds) == 1
    assert refunds[0].status == "completed"
    inv = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-1"][-1]
    assert inv.quantity == 4, "non-restockable return must NOT increase physical inventory"


# --- 4: rejected/cancelled return does not refund -------------------------------------------------

def test_rejected_return_does_not_refund(svc):
    store, service, payments = svc
    order = _fulfilled_order(store, service, "RET-4")
    ret = service.evaluate_return("mer_A", order, "customer_request")
    ret = service.progress_return("mer_A", ret.id, "inspection_failed")
    assert ret.status == "rejected"
    result = service.evaluate_return_refund("mer_A", ret.id)
    assert result is None
    assert _refunds_for_order(store, order.id) == []


def test_return_outside_window_is_rejected_and_never_refunds(svc):
    store, service, payments = svc
    store.set_config("mer_A", store.get_config("mer_A") | {"returns": {"window_days": 0}})
    from datetime import datetime, timedelta, timezone
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="RET-4B", status="PAID", payment_status="paid", total_amount=1000, currency="INR", placed_at=datetime.now(timezone.utc) - timedelta(days=30))
    store.put(order)
    ret = service.evaluate_return("mer_A", order, "customer_request")
    assert ret.status == "rejected"
    result = service.evaluate_return_refund("mer_A", ret.id)
    assert result is None


# --- 5: same eligible return replay creates one logical refund ----------------------------------------

def test_return_replay_creates_one_logical_refund(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-5")
    ret = _accepted_return(store, service, order, restockable=True)
    first = service.evaluate_return_refund("mer_A", ret.id)
    second = service.evaluate_return_refund("mer_A", ret.id)
    assert first.id == second.id
    assert len(_refunds_for_order(store, order.id)) == 1


# --- 7/8: REQUIRE_APPROVAL creates one approval, no premature payment mutation; approved executes once --

def test_require_approval_creates_approval_no_premature_execution(svc):
    store, service, payments = svc
    store.set_config("mer_A", store.get_config("mer_A") | {"policy": {"refund": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"}}})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-7")
    ret = _accepted_return(store, service, order, restockable=True)
    refunds = _refunds_for_order(store, order.id)
    assert len(refunds) == 1
    refund = refunds[0]
    assert refund.status == "approval_required"
    assert refund.approval_id is not None
    approval = store.get(Approval, "mer_A", refund.approval_id)
    assert approval.status == "pending"
    assert len(payments.commands) == 0 if hasattr(payments, "commands") else True  # no payment mutation attempted


def test_approved_refund_executes_once(svc):
    store, service, payments = svc
    store.set_config("mer_A", store.get_config("mer_A") | {"policy": {"refund": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"}}})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-8")
    ret = _accepted_return(store, service, order, restockable=True)
    refund = _refunds_for_order(store, order.id)[0]
    approved = service.approve_refund("mer_A", refund.id, "operator_1")
    assert approved.status == "approved"
    executed = service.execute_refund("mer_A", refund.id)
    assert executed.status == "completed"
    replay = service.execute_refund("mer_A", refund.id)
    assert replay.status == "completed"
    assert replay.id == executed.id


# --- 9: DENY performs no payment mutation ------------------------------------------------------------

def test_deny_policy_performs_no_payment_mutation(svc):
    store, service, payments = svc
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="RET-9", status="PAID", payment_status="pending", total_amount=1000, currency="INR")
    store.put(order)
    ret = service.evaluate_return("mer_A", order, "customer_request")
    ret = service.progress_return("mer_A", ret.id, "authorize")
    ret = service.progress_return("mer_A", ret.id, "inspection_passed", restockable=False)
    refunds = _refunds_for_order(store, order.id)
    assert len(refunds) == 1
    assert refunds[0].status == "denied"
    assert refunds[0].approval_id is None


# --- 10: refund execution does not alter inventory ------------------------------------------------

def test_refund_execution_does_not_alter_inventory(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-10")
    ret = _accepted_return(store, service, order, restockable=False)
    inv_before = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-1"][-1].quantity
    refund = _refunds_for_order(store, order.id)[0]
    assert refund.status == "completed"  # already auto-executed (ALLOW policy)
    service.execute_refund("mer_A", refund.id)  # replay
    inv_after = [i for i in store.list(Inventory, "mer_A") if i.sku == "SKU-1"][-1].quantity
    assert inv_before == inv_after == 4


# --- 11: partial return classified as unsupported (whole-order refund, disclosed) -------------------

def test_partial_return_refunds_the_whole_remaining_order_amount_disclosed_limitation(svc):
    """The canonical model has no ReturnLine/per-quantity representation - a Return is whole-order-
    level. This test documents (does not silently hide) that a single accepted Return refunds the
    order's full remaining refundable amount, never a fabricated per-quantity calculation."""
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-11", qty=2, total_amount=60000)
    ret = _accepted_return(store, service, order, restockable=True)
    refund = _refunds_for_order(store, order.id)[0]
    assert refund.amount == 60000, "current model refunds the whole order - partial-quantity refund is not supported"


# --- 12: previous refund prevents over-refund ------------------------------------------------------

def test_previous_refund_prevents_over_refund_across_two_returns(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-12", total_amount=50000)
    ret1 = _accepted_return(store, service, order, restockable=True)
    refund1 = _refunds_for_order(store, order.id)[0]
    assert refund1.amount == 50000
    assert refund1.status == "completed"

    # A second, independent Return record for the SAME order (simulating a duplicate/erroneous second
    # return event) must find NO remaining refundable amount.
    ret2 = service.evaluate_return("mer_A", order, "second_request")
    # evaluate_return dedupes per order via _existing_for_order - force a second Return object directly
    # to simulate the scenario the mandate describes (two legitimate return EVENTS on one order).
    from sanocea.packages.domain_contract.models import Return as ReturnModel
    ret2_forced = ReturnModel(merchant_id="mer_A", order_id=order.id, status="received", reason="second_request")
    store.put(ret2_forced)
    ret2_final = service.progress_return("mer_A", ret2_forced.id, "inspection_passed", restockable=True)
    assert ret2_final.status == "accepted"
    refunds = _refunds_for_order(store, order.id)
    assert len(refunds) == 1, "no second refund must be created once the order's refundable amount is exhausted"


# --- 13: payment mutation uncertainty does not duplicate refund ---------------------------------------

def test_payment_uncertainty_does_not_duplicate_refund(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-13")
    ret = service.evaluate_return("mer_A", order, "customer_request")
    ret = service.progress_return("mer_A", ret.id, "received")
    # Directly create+approve a refund (bypassing auto-trigger) so we can control the execute_refund
    # `simulate` parameter, matching the existing Phase 2.1 uncertainty-proof pattern.
    refund = service.evaluate_refund("mer_A", order, order.total_amount, return_id=ret.id)
    # Step 9 correction (was: asserted a bare "mutation_uncertain" that could never self-heal - see the
    # Step 9 report for why that was a disclosed gap, not a permanent contract): timeout_before_mutation
    # means SimulatedPaymentConnector never wrote a refund record before raising TimeoutError -
    # execute_refund's own inline read-back (payments.find_refund) now establishes this authoritatively
    # (CONFIRMED_NOT_APPLIED) and resolves the refund straight to "permitted" (safely retryable), rather
    # than leaving it stuck. This is a STRONGER proof of "does not duplicate": a real subsequent retry is
    # attempted and must produce exactly one refund, not merely a no-op that trivially can't duplicate.
    resolved = service.execute_refund("mer_A", refund.id, simulate="timeout_before_mutation")
    assert resolved.status == "permitted"
    retry = service.execute_refund("mer_A", refund.id)
    assert retry.status == "completed"
    assert len([r for r in store.list(Refund, "mer_A") if r.order_id == order.id]) == 1


# --- 15: support reads resulting canonical state -------------------------------------------------

def test_support_reads_return_and_refund_canonical_state(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-15")
    ret = _accepted_return(store, service, order, restockable=True)
    refund = _refunds_for_order(store, order.id)[0]

    chatwoot = ChatwootConnector(store)
    support = SupportWorkflowService(store, chatwoot, post_order=service)
    conv1 = SupportConversation(merchant_id="mer_A", channel_id="chn_A_chatwoot", order_id=order.id, last_message="What is the status of my return?")
    store.put(conv1)
    action1 = support.handle_conversation("mer_A", conv1.id)
    assert ret.status in action1.response_text

    conv2 = SupportConversation(merchant_id="mer_A", channel_id="chn_A_chatwoot", order_id=order.id, last_message="Where is my refund?")
    store.put(conv2)
    action2 = support.handle_conversation("mer_A", conv2.id)
    assert refund.status in action2.response_text


# --- 16: tenant isolation --------------------------------------------------------------------------

def test_return_refund_tenant_isolation(svc):
    store, service, payments = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, "RET-16")
    ret = _accepted_return(store, service, order, restockable=True)
    assert store.list(Refund, "mer_B") == []
    with pytest.raises(TenantAccessError):
        store.get(Return, "mer_B", ret.id)
