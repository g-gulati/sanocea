from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import Channel, Inventory, Merchant, Order, OrderLine
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.workers.workflow import FakeTemporalEngine


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"alloc_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Allocation", display_name="Allocation"))
    store.put(Channel(id=f"chn_{merchant_id}", merchant_id=merchant_id, type="shopify", name="Shopify", capabilities={"ingest_order_webhook": True}))
    return merchant_id, store


def _order(store, merchant_id: str, channel_id: str, order_number: str, sku: str, quantity: int) -> Order:
    order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number=order_number, status="PAID", payment_status="paid", total_amount=10000, currency="INR")
    store.put(order)
    store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=quantity, unit_amount=10000))
    return order


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory:
    return [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location][-1]


def test_concurrent_orders_bounded_reevaluation_allocates_to_different_locations():
    """The mandate's exact concurrency proof: Surat ATS=1, Mumbai ATS=1, two concurrent one-unit orders
    for the SAME SKU. Both threads will initially rank the SAME first-choice candidate (ATS tied at 1
    each, so ranking falls through to the alphabetical tie-break - both pick the same location first).
    Exactly one atomic reserve at that location succeeds; the other comes back short, is rolled back, and
    - per Step 3's bounded re-evaluation requirement - the LOSING allocator must move to the next ranked
    candidate rather than incorrectly reporting a global stock failure. Both orders must succeed, one at
    each location, with no oversell."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-CONC", location_ref="Surat", quantity=1, available=1))
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-CONC", location_ref="Mumbai", quantity=1, available=1))
    channel_id = f"chn_{merchant_id}"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    results: dict[str, bool] = {}
    errors: list[str] = []

    def attempt(order_number: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            workflow = FakeTemporalEngine(thread_store)
            shopify = ShopifyConnector(thread_store, workflow)
            service = PostOrderOperationsService(thread_store, shopify, SimulatedLogisticsConnector(thread_store))
            order = _order(thread_store, merchant_id, channel_id, order_number, "SKU-CONC", 1)
            barrier.wait(timeout=10)
            result = service.reserve_inventory_for_order(merchant_id, order)  # no explicit location - allocator runs
            results[order_number] = result["reserved"]
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=attempt, args=(f"CONC-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent allocation must not raise - got: {errors}"
    assert results == {"CONC-0": True, "CONC-1": True}, f"both orders must succeed via bounded re-evaluation - got {results}"

    surat = _inv(setup_store, merchant_id, "SKU-CONC", "Surat")
    mumbai = _inv(setup_store, merchant_id, "SKU-CONC", "Mumbai")
    assert surat.reserved == 1
    assert mumbai.reserved == 1
    assert surat.available == 0
    assert mumbai.available == 0  # no oversell at either location


def test_concurrent_orders_at_the_only_stocked_location_exactly_one_succeeds():
    """Only Surat has stock (Mumbai has none) - the allocator's candidate list has exactly one member for
    both threads, so when one wins the atomic reserve, the loser has NO other candidate to retry and must
    correctly report a genuine allocation failure, not a phantom success."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-SOLE", location_ref="Surat", quantity=1, available=1))
    channel_id = f"chn_{merchant_id}"

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    results: dict[str, bool] = {}
    errors: list[str] = []

    def attempt(order_number: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            workflow = FakeTemporalEngine(thread_store)
            shopify = ShopifyConnector(thread_store, workflow)
            service = PostOrderOperationsService(thread_store, shopify, SimulatedLogisticsConnector(thread_store))
            order = _order(thread_store, merchant_id, channel_id, order_number, "SKU-SOLE", 1)
            barrier.wait(timeout=10)
            result = service.reserve_inventory_for_order(merchant_id, order)
            results[order_number] = result["reserved"]
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=attempt, args=(f"SOLE-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent allocation must not raise - got: {errors}"
    outcomes = list(results.values())
    assert outcomes.count(True) == 1, f"exactly one of two concurrent orders must succeed - got {results}"
    assert outcomes.count(False) == 1

    surat = _inv(setup_store, merchant_id, "SKU-SOLE", "Surat")
    assert surat.reserved == 1  # never 2 - no oversell
    assert surat.available == 0
