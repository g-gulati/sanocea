from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import Channel, Inventory, InventoryReservation, Merchant, Order, OrderLine
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.workers.workflow import FakeTemporalEngine


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"canexec_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="CanExec", display_name="CanExec"))
    channel_id = f"chn_{merchant_id}"
    store.put(Channel(id=channel_id, merchant_id=merchant_id, type="shopify", name="Shopify", capabilities={"ingest_order_webhook": True}))
    store.set_config(merchant_id, {"cancellations": {"before_fulfilment": "REQUIRE_APPROVAL"}})
    return merchant_id, store, channel_id


def _order(store, merchant_id, channel_id, order_number, sku="SKU-1", qty=1):
    order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number=order_number, status="PAID", payment_status="paid", total_amount=1000, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=qty, unit_amount=500))
    return order


def _inv(store, merchant_id, sku, location="default"):
    rows = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location]
    return rows[-1] if rows else None


def _service(store):
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    return PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))


def test_concurrent_double_approval_executes_cancellation_exactly_once_real_postgres():
    """Two genuinely concurrent operators approving the SAME cancellation (two real Postgres
    connections, two threads, synchronized to the same instant) must produce exactly one logical
    execution: the reservation released exactly once (never negative, never double-released), exactly
    one 'cancellation_completed' success audit event, and a consistent final Order/Inventory state."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=3, available=3))
    order = _order(setup_store, merchant_id, channel_id, "CANPG-1", qty=2)
    setup_service = _service(setup_store)
    setup_service.reserve_inventory_for_order(merchant_id, order)
    cancellation = setup_service.evaluate_cancellation(merchant_id, order)
    assert cancellation.status == "approval_required"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []
    results: dict[str, str] = {}

    def approve(key: str, approver: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store)
            barrier.wait(timeout=10)
            result = thread_service.approve_cancellation(merchant_id, cancellation.id, approver)
            results[key] = result.status
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=approve, args=("op1", "operator_1"))
    t2 = threading.Thread(target=approve, args=("op2", "operator_2"))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"concurrent approval must not raise - got: {errors}"
    assert results["op1"] == "completed"
    assert results["op2"] == "completed"

    verify_store = PostgresStore(dsn)
    order_after = verify_store.get(Order, merchant_id, order.id)
    assert order_after.status == "CANCELLED"
    inv = _inv(verify_store, merchant_id, "SKU-1")
    assert inv.reserved == 0, "reservation must be released exactly once - a lost double-release guard would show reserved go negative or stay positive"
    assert inv.quantity == 3
    assert inv.available == 3

    completions = [e for e in verify_store.list_audit(merchant_id) if e.action == "cancellation_completed" and e.object_id == cancellation.id]
    assert len(completions) == 1, f"expected exactly one success audit record despite two concurrent approvals, got {len(completions)}"
    releases = [e for e in verify_store.list_audit(merchant_id) if e.action == "inventory_reservation_released" and e.object_id == cancellation.id]
    assert len(releases) == 1, f"expected exactly one reservation-release audit record, got {len(releases)}"


def test_stale_approval_after_fulfilment_against_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id = _setup(suffix)
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, merchant_id, channel_id, "CANPG-STALE")
    service = _service(store)
    service.reserve_inventory_for_order(merchant_id, order)
    cancellation = service.evaluate_cancellation(merchant_id, order)

    service.monitor_fulfilment(merchant_id, order, status="fulfilled", age_hours=1)
    result = service.approve_cancellation(merchant_id, cancellation.id, "operator_1")
    assert result.status == "stale_not_executable"

    order_after = store.get(Order, merchant_id, order.id)
    assert order_after.status != "CANCELLED"
    inv = _inv(store, merchant_id, "SKU-1")
    assert inv.quantity == 4 and inv.reserved == 0  # consumed by fulfilment, untouched by the stale attempt


def test_reservation_release_correctness_under_shortfall_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id = _setup(suffix)
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=1, available=1))
    order = _order(store, merchant_id, channel_id, "CANPG-SHORTFALL", qty=3)
    service = _service(store)
    service.reserve_inventory_for_order(merchant_id, order, location="default")
    reservation = next(r for r in store.list(InventoryReservation, merchant_id) if r.source_id == order.id)
    assert reservation.quantity_reserved == 1

    cancellation = service.evaluate_cancellation(merchant_id, order)
    service.approve_cancellation(merchant_id, cancellation.id, "operator_1")
    inv = _inv(store, merchant_id, "SKU-1")
    assert inv.reserved == 0
    assert inv.quantity == 1


def test_cancellation_approval_tenant_isolation_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id = _setup(suffix)
    other_id = f"canexec_other_{suffix}"
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Other", display_name="Other"))
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _order(store, merchant_id, channel_id, "CANPG-TENANT")
    service = _service(store)
    service.reserve_inventory_for_order(merchant_id, order)
    cancellation = service.evaluate_cancellation(merchant_id, order)

    with pytest.raises(TenantAccessError):
        service.approve_cancellation(other_id, cancellation.id, "operator_1")
    with pytest.raises(TenantAccessError):
        service.reject_cancellation(other_id, cancellation.id, "operator_1")
