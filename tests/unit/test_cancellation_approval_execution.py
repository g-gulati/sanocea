from __future__ import annotations

import pytest

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract.models import (
    Approval,
    Cancellation,
    ExceptionRecord,
    Inventory,
    InventoryReservation,
    Order,
    OrderLine,
    SupportConversation,
)
from sanocea.packages.domain_contract.store import TenantAccessError
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.packages.support import SupportWorkflowService


@pytest.fixture
def svc(phase0):
    store, workflow, shopify, chatwoot = phase0
    store.set_config("mer_A", store.get_config("mer_A") | {"cancellations": {"before_fulfilment": "REQUIRE_APPROVAL"}})
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))
    return store, service


def _order(store, merchant_id, order_number, sku="SKU-1", qty=1):
    order = Order(merchant_id=merchant_id, channel_id="chn_A_shopify", order_number=order_number, status="PAID", payment_status="paid", total_amount=1000, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=qty, unit_amount=500))
    return order


def _inv(store, merchant_id, sku, location="default"):
    rows = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location]
    return rows[-1] if rows else None


# --- 1: approval of a valid pending cancellation executes -------------------------------------------

def test_approval_of_valid_pending_cancellation_executes(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-1")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    assert cancellation.status == "approval_required"
    result = service.approve_cancellation("mer_A", cancellation.id, "op_1")
    assert result.status == "completed"
    assert store.get(Order, "mer_A", order.id).status == "CANCELLED"
    assert _inv(store, "mer_A", "SKU-1").reserved == 0


# --- 2: rejection performs no mutation ----------------------------------------------------------------

def test_rejection_performs_no_mutation(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-2")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    result = service.reject_cancellation("mer_A", cancellation.id, "op_1", reason="customer changed mind")
    assert result.status == "rejected"
    assert store.get(Order, "mer_A", order.id).status == "PAID"
    assert _inv(store, "mer_A", "SKU-1").reserved == 1
    approval = store.get(Approval, "mer_A", cancellation.approval_id)
    assert approval.status == "denied"
    exceptions_before = len(store.list(ExceptionRecord, "mer_A"))
    result2 = service.reject_cancellation("mer_A", cancellation.id, "op_1")
    assert result2.status == "rejected"
    assert len(store.list(ExceptionRecord, "mer_A")) == exceptions_before  # no new exception on replay


# --- 3: duplicate approval is idempotent ---------------------------------------------------------------

def test_duplicate_approval_is_idempotent(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-3")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    first = service.approve_cancellation("mer_A", cancellation.id, "op_1")
    second = service.approve_cancellation("mer_A", cancellation.id, "op_2")
    assert first.status == second.status == "completed"
    releases = [e for e in store.list_audit("mer_A") if e.action == "inventory_reservation_released" and e.object_id == cancellation.id]
    assert len(releases) == 1, "reservation must be released exactly once despite the duplicate approval call"
    completions = [e for e in store.list_audit("mer_A") if e.action == "cancellation_completed" and e.object_id == cancellation.id]
    assert len(completions) == 1, "success audit must not be duplicated on replay"


# --- 4: concurrent approval is idempotent (real-Postgres version in the integration suite) -------------

def test_sequential_double_approve_call_releases_reservation_exactly_once(svc):
    """In-memory precursor to the real-Postgres concurrent proof - two approve calls back to back must
    still leave the reservation released exactly once, never negative, never double-released."""
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=3, available=3))
    order = _order(store, "mer_A", "CAN-4", qty=2)
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    service.approve_cancellation("mer_A", cancellation.id, "op_1")
    service.approve_cancellation("mer_A", cancellation.id, "op_2")
    inv = _inv(store, "mer_A", "SKU-1")
    assert inv.reserved == 0
    assert inv.quantity == 3
    assert inv.available == 3


# --- 5: stale approval after fulfilment does not cancel -------------------------------------------------

def test_stale_approval_after_fulfilment_does_not_cancel(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-5")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    assert cancellation.status == "approval_required"

    # Order becomes fulfilled WHILE the approval is pending.
    service.monitor_fulfilment("mer_A", order, status="fulfilled", age_hours=1)
    inv_after_fulfil = _inv(store, "mer_A", "SKU-1")
    assert inv_after_fulfil.quantity == 4 and inv_after_fulfil.reserved == 0  # consumed, not reserved

    result = service.approve_cancellation("mer_A", cancellation.id, "op_1")
    assert result.status == "stale_not_executable"
    order_after = store.get(Order, "mer_A", order.id)
    assert order_after.status != "CANCELLED"
    inv_after_approve = _inv(store, "mer_A", "SKU-1")
    assert inv_after_approve.quantity == 4 and inv_after_approve.reserved == 0, "no reservation corruption from the stale approval attempt"
    exceptions = store.list_audit("mer_A")
    assert any(e.action == "cancellation_execution_not_allowed" and e.object_id == cancellation.id for e in exceptions)

    # Replay must remain deterministic (still stale, never flips to completed).
    replay = service.approve_cancellation("mer_A", cancellation.id, "op_1")
    assert replay.status == "stale_not_executable"


# --- 6: approval belonging to another merchant is refused -----------------------------------------------

def test_approval_belonging_to_another_merchant_is_refused(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-6")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    with pytest.raises(TenantAccessError):
        service.approve_cancellation("mer_B", cancellation.id, "op_1")
    with pytest.raises(TenantAccessError):
        service.reject_cancellation("mer_B", cancellation.id, "op_1")


# --- 7: approval/action/order mismatch is refused --------------------------------------------------------

def test_approval_action_mismatch_is_refused(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-7")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    # Corrupt the linked approval's action/object_id to simulate a data-integrity mismatch.
    approval = store.get(Approval, "mer_A", cancellation.approval_id)
    approval.action = "some_other_action"
    store.put(approval)

    result = service.approve_cancellation("mer_A", cancellation.id, "op_1")
    assert result.status == "approval_required", "must refuse, not silently approve, on a mismatched linked approval"
    order_after = store.get(Order, "mer_A", order.id)
    assert order_after.status != "CANCELLED"
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "cancellation_approval_mismatch" for e in exceptions)


# --- 8/9: releases only outstanding owned reservation; already-consumed reservation not released --------

def test_cancellation_releases_only_the_outstanding_shortfall_amount(svc):
    """A shortfall at reservation time means quantity_reserved < requested - cancellation must release
    only what was ACTUALLY reserved, never the originally-requested amount."""
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=1, available=1))
    order = _order(store, "mer_A", "CAN-8", qty=3)  # requests 3, only 1 available
    service.reserve_inventory_for_order("mer_A", order, location="default")
    reservation = next(r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id)
    assert reservation.quantity_reserved == 1

    cancellation = service.evaluate_cancellation("mer_A", order)
    service.approve_cancellation("mer_A", cancellation.id, "op_1")
    inv = _inv(store, "mer_A", "SKU-1")
    assert inv.reserved == 0
    assert inv.quantity == 1  # never released more than was actually reserved


def test_already_consumed_reservation_is_not_released_by_cancellation_attempt(svc):
    """A cancellation attempted on an order that has ALREADY been fulfilled (consumed, not reserved)
    must never release/restock anything - covered by the stale-approval path, verified here explicitly
    against the underlying reservation object itself."""
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-9")
    service.reserve_inventory_for_order("mer_A", order)
    reservation_before = next(r for r in store.list(InventoryReservation, "mer_A") if r.source_id == order.id)
    cancellation = service.evaluate_cancellation("mer_A", order)
    service.monitor_fulfilment("mer_A", order, status="fulfilled", age_hours=1)
    reservation_after_fulfil = store.get(InventoryReservation, "mer_A", reservation_before.id)
    assert reservation_after_fulfil.quantity_consumed == 1
    assert reservation_after_fulfil.quantity_released == 0

    service.approve_cancellation("mer_A", cancellation.id, "op_1")
    reservation_after_cancel_attempt = store.get(InventoryReservation, "mer_A", reservation_before.id)
    assert reservation_after_cancel_attempt.quantity_released == 0, "an already-consumed reservation must never be released by a stale cancellation"
    assert reservation_after_cancel_attempt.quantity_consumed == 1


# --- 10: support -> approval -> execution -> support-readback works --------------------------------------

def test_support_to_approval_to_execution_to_support_readback(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-10")
    service.reserve_inventory_for_order("mer_A", order)

    chatwoot = ChatwootConnector(store)
    support = SupportWorkflowService(store, chatwoot, post_order=service)
    conv1 = SupportConversation(merchant_id="mer_A", channel_id="chn_A_chatwoot", order_id=order.id, last_message="Please cancel my order")
    store.put(conv1)
    action1 = support.handle_conversation("mer_A", conv1.id)
    assert action1.handling_mode == "APPROVAL-GATED"
    cancellation = next(c for c in store.list(Cancellation, "mer_A") if c.order_id == order.id)
    assert cancellation.status == "approval_required"

    service.approve_cancellation("mer_A", cancellation.id, "operator")
    order_after = store.get(Order, "mer_A", order.id)
    assert order_after.status == "CANCELLED"
    assert _inv(store, "mer_A", "SKU-1").reserved == 0

    conv2 = SupportConversation(merchant_id="mer_A", channel_id="chn_A_chatwoot", order_id=order.id, last_message="What is the status of my order?")
    store.put(conv2)
    action2 = support.handle_conversation("mer_A", conv2.id)
    assert action2.handling_mode == "AUTOMATIC"
    assert "CANCELLED" in action2.response_text


# --- 11: explicit DENY policy never creates executable approval --------------------------------------------

def test_explicit_deny_policy_never_creates_executable_approval(svc):
    store, service = svc
    store.set_config("mer_A", store.get_config("mer_A") | {"cancellations": {"before_fulfilment": "DENY"}})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-11")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    assert cancellation.status == "denied"
    assert cancellation.approval_id is None
    result = service.execute_cancellation("mer_A", cancellation.id)
    assert result.status == "denied"
    assert store.get(Order, "mer_A", order.id).status != "CANCELLED"


# --- 12: ALLOW path still executes without unnecessary approval ---------------------------------------------

def test_allow_path_still_executes_without_approval(svc):
    store, service = svc
    store.set_config("mer_A", store.get_config("mer_A") | {"cancellations": {"before_fulfilment": "ALLOW"}})
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-12")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    assert cancellation.status == "eligible"
    assert cancellation.approval_id is None
    result = service.execute_cancellation("mer_A", cancellation.id)
    assert result.status == "completed"
    assert store.get(Order, "mer_A", order.id).status == "CANCELLED"


# --- Additional: audit/evidence distinguishes every named state ------------------------------------------

def test_audit_evidence_distinguishes_every_lifecycle_state(svc):
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-AUDIT")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    service.approve_cancellation("mer_A", cancellation.id, "op_1")
    events = [e for e in store.list_audit("mer_A") if e.object_id == cancellation.id]
    actions = {e.action for e in events}
    assert "cancellation_approved" in actions
    assert "cancellation_completed" in actions
    assert "inventory_reservation_released" in actions


def test_success_audit_never_written_before_mutation_succeeds(svc):
    """A rejected cancellation must never produce a 'completed'-flavoured audit event."""
    store, service = svc
    store.put(Inventory(merchant_id="mer_A", sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, "mer_A", "CAN-AUDIT-2")
    service.reserve_inventory_for_order("mer_A", order)
    cancellation = service.evaluate_cancellation("mer_A", order)
    service.reject_cancellation("mer_A", cancellation.id, "op_1")
    events = [e for e in store.list_audit("mer_A") if e.object_id == cancellation.id]
    assert all(e.action != "cancellation_completed" for e in events)
    assert store.get(Order, "mer_A", order.id).status != "CANCELLED"
