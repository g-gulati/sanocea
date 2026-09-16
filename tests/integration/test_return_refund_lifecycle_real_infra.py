from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import Channel, Inventory, Merchant, Order, OrderLine, Refund, Return
from sanocea.packages.finance import FinanceOperationsService
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.workers.workflow import FakeTemporalEngine


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"retref_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="RetRef", display_name="RetRef"))
    channel_id = f"chn_{merchant_id}"
    store.put(Channel(id=channel_id, merchant_id=merchant_id, type="shopify", name="Shopify", capabilities={"ingest_order_webhook": True}))
    store.set_config(merchant_id, {
        "refunds": {},
        "policy": {"refund": {"automatic_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}},
        "returns": {"window_days": 30},
    })
    payments = SimulatedPaymentConnector(store)
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    service = PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), payments)
    return merchant_id, store, channel_id, service, payments


def _fulfilled_order(store, service, merchant_id, channel_id, order_number, sku="SKU-1", total_amount=50000):
    order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number=order_number, status="PAID", payment_status="paid", total_amount=total_amount, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=1, unit_amount=total_amount))
    service.reserve_inventory_for_order(merchant_id, order)
    service.monitor_fulfilment(merchant_id, order, status="fulfilled", age_hours=1)
    return order


def _inv(store, merchant_id, sku, location="default"):
    rows = [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location]
    return rows[-1] if rows else None


def _service(store, payments=None):
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    return PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store), payments or SimulatedPaymentConnector(store))


# --- Item 6: concurrent trigger creates one logical refund ---------------------------------------------

def test_concurrent_return_refund_trigger_creates_one_logical_refund_real_postgres():
    """Two genuinely concurrent observations of the SAME refund-eligible return (e.g. two workers both
    reacting to the 'accepted' transition) must converge on exactly one Refund row, one Approval (if
    required), and one payment execution - via uq_refund_return_id's DB-unique partial index, not a
    Python lock."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id, setup_service, _ = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(setup_store, setup_service, merchant_id, channel_id, "RETPG-1")
    ret = setup_service.evaluate_return(merchant_id, order, "customer_request")
    ret = setup_service.progress_return(merchant_id, ret.id, "received")
    ret = setup_service.progress_return(merchant_id, ret.id, "inspection_passed", restockable=True)
    assert ret.status == "accepted"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []
    results: dict[str, str] = {}

    def observe(key: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store)
            barrier.wait(timeout=10)
            result = thread_service.evaluate_return_refund(merchant_id, ret.id)
            results[key] = result.id if result else None
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{key}: {type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=observe, args=("a",))
    t2 = threading.Thread(target=observe, args=("b",))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"concurrent trigger must not raise - got: {errors}"
    assert results["a"] == results["b"], "both concurrent observations must resolve to the SAME refund id"

    verify_store = PostgresStore(dsn)
    refunds = [r for r in verify_store.list(Refund, merchant_id) if r.return_id == ret.id]
    assert len(refunds) == 1, f"expected exactly one logical Refund for this return, got {len(refunds)}"
    assert refunds[0].status == "completed"
    assert refunds[0].amount == 50000


def test_concurrent_trigger_with_require_approval_creates_one_approval_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, setup_store, channel_id, setup_service, _ = _setup(suffix)
    setup_store.set_config(merchant_id, setup_store.get_config(merchant_id) | {"policy": {"refund": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"}}})
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(setup_store, setup_service, merchant_id, channel_id, "RETPG-2")
    ret = setup_service.evaluate_return(merchant_id, order, "customer_request")
    ret = setup_service.progress_return(merchant_id, ret.id, "received")
    ret = setup_service.progress_return(merchant_id, ret.id, "inspection_passed", restockable=True)

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def observe() -> None:
        try:
            thread_store = PostgresStore(dsn)
            thread_service = _service(thread_store)
            barrier.wait(timeout=10)
            thread_service.evaluate_return_refund(merchant_id, ret.id)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=observe) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"unexpected errors: {errors}"
    verify_store = PostgresStore(dsn)
    refunds = [r for r in verify_store.list(Refund, merchant_id) if r.return_id == ret.id]
    assert len(refunds) == 1
    assert refunds[0].status == "approval_required"
    from sanocea.packages.domain_contract.models import Approval
    approvals = [a for a in verify_store.list(Approval, merchant_id) if a.action == "refund" and a.object_id == order.id]
    assert len(approvals) == 1, f"expected exactly one Approval, got {len(approvals)}"


# --- Failure injection: crash between Refund creation and execute_refund -------------------------------

def test_safe_retry_after_crash_between_refund_creation_and_execution_real_postgres():
    """Simulates the exact crash window the mandate names: the Refund row is created (durably, via
    return_id ownership) but the process crashes before execute_refund ever runs. A later retry of
    evaluate_return_refund must find and resume the SAME Refund - never create a second one."""
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id, service, payments = _setup(suffix)
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, merchant_id, channel_id, "RETPG-3")
    ret = service.evaluate_return(merchant_id, order, "customer_request")
    ret = service.progress_return(merchant_id, ret.id, "received")

    # Manually reach the "accepted" state WITHOUT the automatic trigger, to isolate the crash window:
    # simulate the refund having been CREATED (return_id ownership established) but never executed.
    ret_record = store.get(Return, merchant_id, ret.id)
    ret_record.status = "accepted"
    ret_record.restockable = True
    store.put(ret_record)
    crashed_refund = service.evaluate_refund(merchant_id, order, order.total_amount, return_id=ret.id)
    assert crashed_refund.status == "permitted"

    # "Retry" - a fresh call as if a new process/worker picked this up after the crash.
    retry_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    retry_service = _service(retry_store, payments)
    resumed = retry_service.evaluate_return_refund(merchant_id, ret.id)
    assert resumed.id == crashed_refund.id
    assert resumed.status == "completed"

    verify_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    refunds = [r for r in verify_store.list(Refund, merchant_id) if r.return_id == ret.id]
    assert len(refunds) == 1, "the retry must resume the SAME refund, never create a duplicate ownership row"


# --- Finance feedback: return -> refund -> settlement -> reconciliation --------------------------------

def test_return_refund_finance_reconciliation_chain_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id, service, payments = _setup(suffix)
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, merchant_id, channel_id, "RETPG-4")

    finance = FinanceOperationsService(store)
    observation = finance.observe_payment(merchant_id, order, provider=payments.name, amount=order.total_amount, currency=order.currency, status="paid", external_payment_id=f"pay-{order.id}")
    finance.reconcile_payment(merchant_id, order, observation)

    ret = service.evaluate_return(merchant_id, order, "customer_request")
    ret = service.progress_return(merchant_id, ret.id, "received")
    ret = service.progress_return(merchant_id, ret.id, "inspection_passed", restockable=True)
    refund = next(r for r in store.list(Refund, merchant_id) if r.return_id == ret.id)
    assert refund.status == "completed"

    from sanocea.packages.domain_contract.models import ConnectorCommand
    refund_command = next(c for c in store.list(ConnectorCommand, merchant_id) if c.action == "create_refund" and c.object_id == refund.id)
    refund_external_ref = refund_command.external_ref
    assert refund_external_ref is not None

    batch = finance.ingest_settlement_batch(merchant_id, payments.name, {
        "external_batch_id": f"batch-{order.id}",
        "currency": "INR",
        "entries": [
            {"external_entry_id": f"pay-entry-{order.id}", "entry_type": "payment", "provider_order_reference": f"pay-{order.id}", "amount": order.total_amount, "currency": "INR"},
            {"external_entry_id": f"refund-entry-{order.id}", "entry_type": "refund", "provider_refund_reference": refund_external_ref, "amount": -abs(refund.amount), "currency": "INR"},
        ],
    })
    reconciliations = finance.reconcile_settlement_batch(merchant_id, batch.id, final_orders={order.id})
    results = sorted({r.result for r in reconciliations})
    assert results == ["MATCH"], f"expected clean MATCH reconciliation for both payment and refund entries, got {results}"

    refund_after = store.get(Refund, merchant_id, refund.id)
    assert refund_after.financial_reconciliation_status == "matched"


# --- DENY / rejected paths against real Postgres -----------------------------------------------------

def test_deny_policy_and_rejected_return_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id, service, payments = _setup(suffix)
    unpaid_order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number="RETPG-5", status="PAID", payment_status="pending", total_amount=1000, currency="INR")
    store.put(unpaid_order)
    ret = service.evaluate_return(merchant_id, unpaid_order, "customer_request")
    ret = service.progress_return(merchant_id, ret.id, "authorize")
    ret = service.progress_return(merchant_id, ret.id, "inspection_passed", restockable=False)
    refunds = [r for r in store.list(Refund, merchant_id) if r.return_id == ret.id]
    assert len(refunds) == 1
    assert refunds[0].status == "denied"

    order2 = Order(merchant_id=merchant_id, channel_id=channel_id, order_number="RETPG-6", status="PAID", payment_status="paid", total_amount=1000, currency="INR")
    store.put(order2)
    ret2 = service.evaluate_return(merchant_id, order2, "customer_request")
    ret2 = service.progress_return(merchant_id, ret2.id, "inspection_failed")
    assert ret2.status == "rejected"
    result = service.evaluate_return_refund(merchant_id, ret2.id)
    assert result is None
    assert [r for r in store.list(Refund, merchant_id) if r.order_id == order2.id] == []


# --- Tenant isolation ---------------------------------------------------------------------------------

def test_return_refund_tenant_isolation_real_postgres():
    suffix = uuid4().hex[:8]
    merchant_id, store, channel_id, service, payments = _setup(suffix)
    other_id = f"retref_other_{suffix}"
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Other", display_name="Other"))
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=5, available=5))
    order = _fulfilled_order(store, service, merchant_id, channel_id, "RETPG-7")
    ret = service.evaluate_return(merchant_id, order, "customer_request")
    ret = service.progress_return(merchant_id, ret.id, "received")
    ret = service.progress_return(merchant_id, ret.id, "inspection_passed", restockable=True)

    assert store.list(Refund, other_id) == []
    with pytest.raises(TenantAccessError):
        store.get(Return, other_id, ret.id)
