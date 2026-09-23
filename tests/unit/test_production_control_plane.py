from __future__ import annotations

import pytest

from sanocea.packages.approvals import ApprovalService
from sanocea.packages.domain_contract.models import (
    Approval,
    ApprovalState,
    FinancialReconciliationState,
    Inventory,
    InvalidStateTransitionError,
    Location,
    OperationalRefundState,
    Order,
    OrderState,
    Product,
    ProductDraft,
    Refund,
    Return,
    ReturnState,
    Variant,
    ORDER_TRANSITIONS,
    RETURN_TRANSITIONS,
    APPROVAL_TRANSITIONS,
    validate_state_transition,
)
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.policy_engine import Decision, PolicyEngine


def test_location_canonical_entity_lifecycle():
    store = Phase0Store()
    loc1 = Location(
        merchant_id="mer_test",
        code="WH-MUM-01",
        name="Mumbai Central Fulfillment Center",
        fulfillment_types=["standard", "express"],
        priority=10,
    )
    store.put(loc1)

    fetched = store.get(Location, "mer_test", loc1.id)
    assert fetched.code == "WH-MUM-01"
    assert fetched.priority == 10
    assert "express" in fetched.fulfillment_types

    # Deduplication by (merchant_id, code)
    loc2 = Location(
        merchant_id="mer_test",
        code="WH-MUM-01",
        name="Duplicate Mumbai Center",
    )
    deduped = store.put(loc2)
    assert deduped.id == loc1.id
    assert len(store.list(Location, "mer_test")) == 1


def test_inventory_location_scoped_ats_and_quarantine():
    store = Phase0Store()
    inv = Inventory(
        merchant_id="mer_test",
        sku="SKU-CASHEW-500",
        location_ref="WH-MUM-01",
        quantity=100,
        sellable=100,
        reserved=0,
        quarantine=0,
        in_transit=0,
    )
    store.put(inv)

    assert inv.ats == 100

    # 1. Atomic reservation
    res1 = store.reserve_inventory_atomic(
        "mer_test", "SKU-CASHEW-500", "WH-MUM-01",
        quantity_requested=25, source_type="order", source_id="ord_1", idempotency_key="idemp_1"
    )
    assert res1.quantity_reserved == 25
    inv_after_res = store.get(Inventory, "mer_test", inv.id)
    assert inv_after_res.reserved == 25
    assert inv_after_res.ats == 75

    # 2. Quarantine damaged goods (10 units)
    inv_quarantine = store.quarantine_inventory_atomic(
        "mer_test", "SKU-CASHEW-500", "WH-MUM-01", quantity=10, reason="damaged_packaging"
    )
    assert inv_quarantine.quarantine == 10
    assert inv_quarantine.sellable == 90
    assert inv_quarantine.reserved == 25
    assert inv_quarantine.ats == 65  # 90 sellable - 25 reserved = 65

    # 3. Attempting to quarantine more than ATS raises ValueError
    with pytest.raises(ValueError, match="Insufficient available stock to quarantine"):
        store.quarantine_inventory_atomic(
            "mer_test", "SKU-CASHEW-500", "WH-MUM-01", quantity=70, reason="excess_damage"
        )

    # 4. Release partial quarantine back to sellable (4 units)
    inv_released = store.release_quarantine_atomic(
        "mer_test", "SKU-CASHEW-500", "WH-MUM-01", quantity=4
    )
    assert inv_released.quarantine == 6
    assert inv_released.sellable == 94
    assert inv_released.ats == 69  # 94 sellable - 25 reserved = 69


def test_explicit_state_machine_validations():
    # Order State Transitions
    validate_state_transition("Order", OrderState.DRAFT.value, OrderState.CONFIRMED.value, ORDER_TRANSITIONS)
    validate_state_transition("Order", OrderState.CONFIRMED.value, OrderState.FULFILLED.value, ORDER_TRANSITIONS)

    with pytest.raises(InvalidStateTransitionError, match="Invalid state transition for Order"):
        # Cannot jump from COMPLETED back to DRAFT or CONFIRMED
        validate_state_transition("Order", OrderState.COMPLETED.value, OrderState.DRAFT.value, ORDER_TRANSITIONS)

    with pytest.raises(InvalidStateTransitionError, match="Invalid state transition for Order"):
        # Cannot jump from CANCELLED to FULFILLED
        validate_state_transition("Order", OrderState.CANCELLED.value, OrderState.FULFILLED.value, ORDER_TRANSITIONS)

    # Return State Transitions
    validate_state_transition("Return", ReturnState.REQUESTED.value, ReturnState.AUTHORIZED.value, RETURN_TRANSITIONS)
    validate_state_transition("Return", ReturnState.RECEIVED.value, ReturnState.INSPECTED.value, RETURN_TRANSITIONS)
    validate_state_transition("Return", ReturnState.INSPECTED.value, ReturnState.ACCEPTED.value, RETURN_TRANSITIONS)

    with pytest.raises(InvalidStateTransitionError, match="Invalid state transition for Return"):
        # Cannot jump from CLOSED to REQUESTED
        validate_state_transition("Return", ReturnState.CLOSED.value, ReturnState.REQUESTED.value, RETURN_TRANSITIONS)


def test_policy_engine_threshold_evaluations():
    engine = PolicyEngine()
    policy = {
        "refund": {
            "automatic_limit": 100000,  # ₹1000.00 in paise
            "max_order_percent": 50.0,
            "above_limit": "REQUIRE_APPROVAL",
        },
        "price_change": {
            "automatic_limit_percent": 15.0,
            "require_approval_for_live": True,
            "above_limit": "REQUIRE_APPROVAL",
        },
        "catalog_unpublish": {
            "require_approval": True,
        },
    }

    # 1. Refund within limits (₹500 on ₹2000 order)
    dec, reason, ev = engine.evaluate_with_reason(policy, "refund", {"amount": 50000, "order_total": 200000})
    assert dec == Decision.ALLOW

    # 2. Refund exceeding amount threshold (₹1500)
    dec, reason, ev = engine.evaluate_with_reason(policy, "refund", {"amount": 150000, "order_total": 500000})
    assert dec == Decision.REQUIRE_APPROVAL
    assert "exceeds automatic limit" in reason

    # 3. Refund exceeding order percentage threshold (₹800 on ₹1000 order = 80%)
    dec, reason, ev = engine.evaluate_with_reason(policy, "refund", {"amount": 80000, "order_total": 100000})
    assert dec == Decision.REQUIRE_APPROVAL
    assert "exceeding allowed 50.0%" in reason

    # 4. Price change on draft product under limit (10% drop)
    dec, reason, ev = engine.evaluate_with_reason(
        policy, "price_change", {"old_price": 1000, "new_price": 900, "is_published": False}
    )
    assert dec == Decision.ALLOW

    # 5. Price change on published product requiring approval
    dec, reason, ev = engine.evaluate_with_reason(
        policy, "price_change", {"old_price": 1000, "new_price": 950, "is_published": True}
    )
    assert dec == Decision.REQUIRE_APPROVAL
    assert "live published product" in reason

    # 6. Catalog unpublishing
    dec, reason, ev = engine.evaluate_with_reason(
        policy, "catalog_unpublish", {"product_id": "prd_123", "channel": "shopify"}
    )
    assert dec == Decision.REQUIRE_APPROVAL
    assert "Catalog unpublishing" in reason


def test_approval_workflow_and_execution_dispatch():
    store = Phase0Store()
    app_svc = ApprovalService(store)

    # 1. Setup a product draft
    draft = ProductDraft(
        merchant_id="mer_test",
        sku="ND-ALM-0500G",
        title="Roasted Almonds 500g",
        price=80000,  # ₹800
    )
    store.put(draft)

    # 2. Request price change approval
    approval = app_svc.request_approval(
        "mer_test",
        action="price_change",
        object_id=draft.id,
        requested_by="operator_test",
        summary="Price reduction on Roasted Almonds from ₹800 to ₹650",
        evidence={"old_price": 80000, "new_price": 65000, "sku": "ND-ALM-0500G"},
    )
    assert approval.status == "pending"
    assert len(app_svc.get_pending("mer_test")) == 1

    # 3. Resolve approval (APPROVE)
    res = app_svc.resolve(
        "mer_test", approval.id, decision="approved", resolved_via="command_center", decided_by="admin_user"
    )
    assert res["status"] == "approved"
    assert res["already_resolved"] is False

    # 4. Verify the price change was applied
    updated_draft = store.get(ProductDraft, "mer_test", draft.id)
    assert updated_draft.price == 65000

    # 5. Idempotent re-resolution test
    re_res = app_svc.resolve(
        "mer_test", approval.id, decision="approved", resolved_via="command_center", decided_by="admin_user"
    )
    assert re_res["already_resolved"] is True


def test_operational_vs_financial_status_separation():
    # Demonstrates non-negotiable principle: Operational delivery status != Financial status
    order = Order(
        merchant_id="mer_test",
        channel_id="shopify",
        order_number="1042",
        status="DELIVERED",  # Physical goods delivered
        payment_status="pending_cod_remittance",
        total_amount=245000,
        currency="INR",
    )
    assert order.status == "DELIVERED"
    assert order.payment_status != "paid"

    refund = Refund(
        merchant_id="mer_test",
        order_id=order.id,
        amount=50000,
        currency="INR",
        status=OperationalRefundState.COMPLETED.value,  # Gateway accepted mutation
        financial_reconciliation_status=FinancialReconciliationState.PENDING.value,  # Bank/Settlement statement not yet matched
    )
    assert refund.status == "completed"
    assert refund.financial_reconciliation_status == "pending"
    # State cannot silently collapse into one status
    assert refund.status != refund.financial_reconciliation_status
