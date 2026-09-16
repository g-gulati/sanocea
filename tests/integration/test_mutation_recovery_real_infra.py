from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import Channel, Inventory, Merchant, Order, OrderLine, Refund, Cancellation
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.workers.workflow import FakeTemporalEngine

# Step 9 - real-Postgres proof that atomic_transition_refund_status / atomic_transition_cancellation_status
# actually serialize concurrent recovery attempts (DB row locking, not merely the in-memory store's
# Python lock already proven in tests/unit/test_mutation_recovery.py).

pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"mutrec_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="MutRec", display_name="MutRec"))
    channel_id = f"chn_{merchant_id}"
    store.put(Channel(id=channel_id, merchant_id=merchant_id, type="shopify", name="Shopify", capabilities={"ingest_order_webhook": True}))
    store.set_config(merchant_id, {
        "refunds": {}, "policy": {"refund": {"automatic_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}},
        "returns": {"window_days": 30}, "cancellations": {"before_fulfilment": "ALLOW"},
    })
    return merchant_id, store, channel_id


def _service(store, logistics=None, payments=None):
    """`logistics`/`payments` are the SIMULATED EXTERNAL PLATFORM stand-ins - a real provider is one
    shared external system regardless of which app process talks to it, so concurrent threads sharing
    one connector instance (while each still gets its OWN PostgresStore connection, for a genuine
    DB-level row-locking proof) is the architecturally correct simulation, not per-thread-isolated fakes."""
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    return PostOrderOperationsService(store, shopify, logistics or SimulatedLogisticsConnector(store), payments or SimulatedPaymentConnector(store))


def _break_find_refund(payments):
    original = payments.find_refund
    payments.find_refund = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("read-back unavailable"))
    return original


def _break_fetch(logistics):
    original = logistics.fetch
    logistics.fetch = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("read-back unavailable"))
    return original


# --- Concurrent refund recovery: only one resolution wins, no duplicate money movement ------------------

def test_concurrent_refund_recovery_resolves_exactly_once_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id = _setup(suffix)
    setup_service = _service(setup_store)
    order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number="MRPG-1", status="PAID", payment_status="paid", total_amount=1000, currency="INR")
    setup_store.put(order)
    refund = setup_service.evaluate_refund(merchant_id, order, order.total_amount)
    # Drive it to a genuine "mutation_uncertain" using the setup service's own (unbroken) connector, by
    # temporarily breaking find_refund just for this one call.
    original_find_refund = _break_find_refund(setup_service.payments)
    try:
        uncertain = setup_service.execute_refund(merchant_id, refund.id, simulate="timeout_before_mutation")
    finally:
        setup_service.payments.find_refund = original_find_refund
    assert uncertain.status == "mutation_uncertain"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []
    results: dict[str, str] = {}

    def trigger(key: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store, payments=setup_service.payments)
            barrier.wait(timeout=10)
            result = thread_service.recover_refund_mutation(merchant_id, refund.id)
            results[key] = result.status
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=trigger, args=("a",))
    t2 = threading.Thread(target=trigger, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"unexpected errors: {errors}"

    verify_store = PostgresStore(dsn)
    refunds = [r for r in verify_store.list(Refund, merchant_id) if r.order_id == order.id]
    assert len(refunds) == 1, "recovery must never create a second Refund row"
    assert refunds[0].status == "completed"
    assert len(setup_service.payments.refunds) == 1, "exactly one external refund must exist despite two concurrent recovery attempts"


# --- Concurrent cancellation recovery: reservation released exactly once, real Postgres row locking -------

def test_concurrent_cancellation_recovery_releases_reservation_once_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id = _setup(suffix)
    setup_service = _service(setup_store)
    order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number="MRPG-2", status="PAID", payment_status="paid", total_amount=1000, currency="INR")
    setup_store.put(order)
    setup_store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku="SKU-1", title="SKU-1", quantity=1, unit_amount=500))
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    setup_service.reserve_inventory_for_order(merchant_id, order)
    setup_service.logistics.seed_shipment(merchant_id, order.id, "CREATED")
    cancellation = setup_service.evaluate_cancellation(merchant_id, order)
    assert cancellation.status == "eligible"

    original_fetch = _break_fetch(setup_service.logistics)
    try:
        uncertain = setup_service.execute_cancellation(merchant_id, cancellation.id, simulate="timeout_after_mutation")
    finally:
        setup_service.logistics.fetch = original_fetch
    assert uncertain.status == "mutation_uncertain"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []
    results: dict[str, str] = {}

    def trigger(key: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store, logistics=setup_service.logistics)
            barrier.wait(timeout=10)
            result = thread_service.recover_cancellation_mutation(merchant_id, cancellation.id)
            results[key] = result.status
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=trigger, args=("a",))
    t2 = threading.Thread(target=trigger, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"unexpected errors: {errors}"

    verify_store = PostgresStore(dsn)
    final = verify_store.get(Cancellation, merchant_id, cancellation.id)
    assert final.status == "completed"
    releases = [e for e in verify_store.list_audit(merchant_id) if e.action == "inventory_reservation_released" and e.object_id == cancellation.id]
    assert len(releases) == 1, f"reservation must be released exactly once under real concurrent recovery, got {len(releases)}"
