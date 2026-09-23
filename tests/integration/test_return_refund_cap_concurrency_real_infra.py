from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import Approval, Channel, Merchant, Order, Refund, Return
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.workers.workflow import FakeTemporalEngine


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"capconc_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="CapConc", display_name="CapConc"))
    channel_id = f"chn_{merchant_id}"
    store.put(Channel(id=channel_id, merchant_id=merchant_id, type="shopify", name="Shopify", capabilities={"ingest_order_webhook": True}))
    store.set_config(merchant_id, {"refunds": {}, "policy": {"refund": {"automatic_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}}, "returns": {"window_days": 30}})
    return merchant_id, store, channel_id


def _service(store):
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    return PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), SimulatedPaymentConnector(store))


def _paid_order(store, merchant_id, channel_id, order_number, total_amount=1000):
    order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    return order


def _forced_accepted_return(store, merchant_id, order, reason):
    ret = Return(merchant_id=merchant_id, order_id=order.id, status="accepted", reason=reason, restockable=False)
    store.put(ret)
    return ret


# --- Items 1/2/3: two distinct accepted Returns race on one fully-refundable order ----------------------

def test_two_distinct_returns_race_never_exceed_order_refundable_amount_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id = _setup(suffix)
    setup_service = _service(setup_store)
    order = _paid_order(setup_store, merchant_id, channel_id, "XR-1", total_amount=1000)
    ret_a = _forced_accepted_return(setup_store, merchant_id, order, "a")
    ret_b = _forced_accepted_return(setup_store, merchant_id, order, "b")

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []
    results: dict[str, str | None] = {}

    def trigger(key: str, return_id: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store)
            barrier.wait(timeout=10)
            result = thread_service.evaluate_return_refund(merchant_id, return_id)
            results[key] = result.id if result else None
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=trigger, args=("a", ret_a.id))
    t2 = threading.Thread(target=trigger, args=("b", ret_b.id))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"unexpected errors: {errors}"

    verify_store = PostgresStore(dsn)
    refunds = [r for r in verify_store.list(Refund, merchant_id) if r.order_id == order.id]
    committed_total = sum(r.amount for r in refunds if r.status != "denied")
    assert committed_total <= order.total_amount, f"committed refund total {committed_total} exceeded the order's authoritative refundable amount {order.total_amount}"
    # Item 3 - exactly one full-order Refund owns capacity under current whole-order semantics: one
    # winner refunds the full 1000, the other gets nothing (not a partial split - whole-order model).
    non_denied = [r for r in refunds if r.status != "denied"]
    assert len(non_denied) == 1
    assert non_denied[0].amount == 1000
    assert non_denied[0].status == "completed"


def test_require_approval_race_reserves_capacity_only_once_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id = _setup(suffix)
    setup_store.set_config(merchant_id, setup_store.get_config(merchant_id) | {"policy": {"refund": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"}}})
    setup_service = _service(setup_store)
    order = _paid_order(setup_store, merchant_id, channel_id, "XR-2", total_amount=1000)
    ret_a = _forced_accepted_return(setup_store, merchant_id, order, "a")
    ret_b = _forced_accepted_return(setup_store, merchant_id, order, "b")

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def trigger(return_id: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store)
            barrier.wait(timeout=10)
            thread_service.evaluate_return_refund(merchant_id, return_id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=trigger, args=(ret_a.id,))
    t2 = threading.Thread(target=trigger, args=(ret_b.id,))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"unexpected errors: {errors}"
    verify_store = PostgresStore(dsn)
    refunds = [r for r in verify_store.list(Refund, merchant_id) if r.order_id == order.id]
    non_denied = [r for r in refunds if r.status != "denied"]
    assert len(non_denied) == 1, "only ONE of the two racing returns may reserve the order's approval-gated capacity"
    assert non_denied[0].status == "approval_required"
    approvals = [a for a in verify_store.list(Approval, merchant_id) if a.action == "refund" and a.object_id == order.id]
    assert len(approvals) == 1, f"expected exactly one Approval despite the race, got {len(approvals)}"

    # Item 6 - approving the surviving refund executes once.
    approved = verify_store.get(Refund, merchant_id, non_denied[0].id)
    approve_service = _service(verify_store)
    approve_service.approve_refund(merchant_id, approved.id, "operator_1")
    executed = approve_service.execute_refund(merchant_id, approved.id)
    assert executed.status == "completed"
    replay = approve_service.execute_refund(merchant_id, approved.id)
    assert replay.status == "completed"
    assert replay.id == executed.id


# --- Item 4 (real-PG): same-return replay remains idempotent under this new path ------------------------

def test_same_return_replay_still_idempotent_under_capacity_claim_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id = _setup(suffix)
    service = _service(store)
    order = _paid_order(store, merchant_id, channel_id, "XR-3", total_amount=1000)
    ret = _forced_accepted_return(store, merchant_id, order, "a")
    first = service.evaluate_return_refund(merchant_id, ret.id)
    second = service.evaluate_return_refund(merchant_id, ret.id)
    assert first.id == second.id
    refunds = [r for r in store.list(Refund, merchant_id) if r.order_id == order.id]
    assert len(refunds) == 1


# --- Item 12: concurrent Returns on DIFFERENT orders do not contaminate each other, no deadlock ---------

def test_concurrent_different_orders_no_contamination_no_deadlock_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id = _setup(suffix)
    setup_service = _service(setup_store)
    order1 = _paid_order(setup_store, merchant_id, channel_id, "XR-4A", total_amount=1000)
    order2 = _paid_order(setup_store, merchant_id, channel_id, "XR-4B", total_amount=2000)
    ret1 = _forced_accepted_return(setup_store, merchant_id, order1, "a")
    ret2 = _forced_accepted_return(setup_store, merchant_id, order2, "b")

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def trigger(return_id: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store)
            barrier.wait(timeout=10)
            thread_service.evaluate_return_refund(merchant_id, return_id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=trigger, args=(ret1.id,))
    t2 = threading.Thread(target=trigger, args=(ret2.id,))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"unexpected errors (a deadlock would show up as a timeout/lock-wait error here): {errors}"
    verify_store = PostgresStore(dsn)
    refunds1 = [r for r in verify_store.list(Refund, merchant_id) if r.order_id == order1.id]
    refunds2 = [r for r in verify_store.list(Refund, merchant_id) if r.order_id == order2.id]
    assert len(refunds1) == 1 and refunds1[0].amount == 1000
    assert len(refunds2) == 1 and refunds2[0].amount == 2000


# --- Failure injection: crash after Order lock acquired, before Refund commits --------------------------

def test_injected_failure_after_order_lock_before_refund_commit_is_safe_to_retry_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id = _setup(suffix)
    service = _service(store)
    order = _paid_order(store, merchant_id, channel_id, "XR-5", total_amount=1000)
    ret = _forced_accepted_return(store, merchant_id, order, "a")

    class _FailingCursor:
        def __init__(self, real_cursor):
            self._real = real_cursor

        def execute(self, sql, params=None):
            if "INSERT INTO refunds" in sql:
                raise RuntimeError("injected failure after order lock, before refund commit")
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._real.__exit__(*exc)

    class _FailingConnection:
        def __init__(self, real_conn):
            self._real = real_conn

        def cursor(self, *args, **kwargs):
            return _FailingCursor(self._real.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return self._real.__exit__(*exc)

    real_connect = store.connect
    store.connect = lambda: _FailingConnection(real_connect())
    try:
        with pytest.raises(RuntimeError, match="injected failure"):
            service.evaluate_return_refund(merchant_id, ret.id)
    finally:
        store.connect = real_connect

    verify_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    assert [r for r in verify_store.list(Refund, merchant_id) if r.order_id == order.id] == [], "the failed transaction must not leave a partial Refund row - the Order lock and the insert are one transaction"

    # Safe retry after the injected failure.
    retry_service = _service(verify_store)
    resumed = retry_service.evaluate_return_refund(merchant_id, ret.id)
    assert resumed.status == "completed"
    assert resumed.amount == 1000
    assert len([r for r in verify_store.list(Refund, merchant_id) if r.order_id == order.id]) == 1


# --- Tenant isolation ---------------------------------------------------------------------------------

def test_cross_return_cap_tenant_isolation_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id = _setup(suffix)
    other_id = f"capconc_other_{suffix}"
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Other", display_name="Other"))
    service = _service(store)
    order = _paid_order(store, merchant_id, channel_id, "XR-6", total_amount=1000)
    ret = _forced_accepted_return(store, merchant_id, order, "a")
    service.evaluate_return_refund(merchant_id, ret.id)

    assert store.list(Refund, other_id) == []
    with pytest.raises(TenantAccessError):
        store.get(Order, other_id, order.id)
