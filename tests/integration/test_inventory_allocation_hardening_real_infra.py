from __future__ import annotations

import os
import threading
import time
from uuid import uuid4

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import Channel, Inventory, InventoryReservation, Merchant, Order, OrderLine
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.workers.workflow import FakeTemporalEngine


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"hard_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Hardening", display_name="Hardening"))
    store.put(Channel(id=f"chn_{merchant_id}", merchant_id=merchant_id, type="shopify", name="Shopify", capabilities={"ingest_order_webhook": True}))
    return merchant_id, store


def _order_with_lines(store, merchant_id: str, channel_id: str, order_number: str, lines: list[tuple[str, int]]) -> Order:
    order = Order(merchant_id=merchant_id, channel_id=channel_id, order_number=order_number, status="PAID", payment_status="paid", total_amount=10000, currency="INR")
    store.put(order)
    for sku, quantity in lines:
        store.put(OrderLine(merchant_id=merchant_id, order_id=order.id, sku=sku, title=sku, quantity=quantity, unit_amount=10000))
    return order


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory:
    return [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location][-1]


def _service(store):
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    return PostOrderOperationsService(store, shopify, SimulatedLogisticsConnector(store))


# --- Part B: deterministic lock ordering - reversed SKU line order must never deadlock -----------------

def test_reversed_line_order_does_not_deadlock_and_both_orders_succeed():
    """Two concurrent multi-line orders at the SAME location, ample stock for both, but with their
    order-lines listed in OPPOSITE SKU order (Order1: A then B; Order2: B then A). If lock acquisition
    followed each order's own line order instead of a deterministic global order (SKU ascending), this is
    the classic ABBA deadlock shape. `reserve_order_lines_atomic` locks `ORDER BY data->>'sku' ASC`
    regardless of input order, so both threads must complete without hanging or erroring, and both must
    fully succeed since aggregate stock covers both orders."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-LOCK-A", location_ref="Surat", quantity=2, available=2))
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-LOCK-B", location_ref="Surat", quantity=2, available=2))
    channel_id = f"chn_{merchant_id}"
    dsn = os.environ["SANOCEA_PG_DSN"]

    order1 = _order_with_lines(setup_store, merchant_id, channel_id, "LOCK-1", [("SKU-LOCK-A", 1), ("SKU-LOCK-B", 1)])
    order2 = _order_with_lines(setup_store, merchant_id, channel_id, "LOCK-2", [("SKU-LOCK-B", 1), ("SKU-LOCK-A", 1)])

    barrier = threading.Barrier(2)
    results: dict[str, dict] = {}
    errors: list[str] = []

    def attempt(order, key):
        try:
            thread_store = PostgresStore(dsn)
            service = _service(thread_store)
            barrier.wait(timeout=10)
            results[key] = service._reserve_order_lines_at_location(merchant_id, order, [l for l in thread_store.list(OrderLine, merchant_id) if l.order_id == order.id], "Surat")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc!r}")

    t1 = threading.Thread(target=attempt, args=(order1, "o1"))
    t2 = threading.Thread(target=attempt, args=(order2, "o2"))
    start = time.monotonic()
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)
    elapsed = time.monotonic() - start

    assert not t1.is_alive() and not t2.is_alive(), "a thread is still alive - deadlock/hang detected"
    assert elapsed < 15, "attempts took too long - possible lock contention stall"
    assert errors == [], f"unexpected errors (possible deadlock exception): {errors}"

    assert _inv(setup_store, merchant_id, "SKU-LOCK-A", "Surat").reserved == 2
    assert _inv(setup_store, merchant_id, "SKU-LOCK-B", "Surat").reserved == 2


# --- Part D: mid-allocation failure - injected on the SECOND line, must undo the FIRST line's work -----

def test_injected_failure_on_second_line_rolls_back_the_first_lines_reservation_too():
    """Simulates 'line 1 succeeds inside the transaction, then line 2 fails before commit' by pre-planting
    a reservation row whose idempotency_key collides with what THIS order's second line would use. The
    real transaction locks both rows, inserts line 1's reservation and mutates its inventory (uncommitted),
    then hits a UniqueViolation inserting line 2's reservation - and must roll back EVERYTHING, including
    line 1's already-executed-but-uncommitted work. No leak, no partial commit, safe retry afterward."""
    suffix = uuid4().hex[:8]
    merchant_id, store = _setup(suffix)
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-INJ-A", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-INJ-B", location_ref="Surat", quantity=5, available=5))
    channel_id = f"chn_{merchant_id}"
    order = _order_with_lines(store, merchant_id, channel_id, "INJ-1", [("SKU-INJ-A", 1), ("SKU-INJ-B", 1)])
    order_lines = sorted([l for l in store.list(OrderLine, merchant_id) if l.order_id == order.id], key=lambda l: l.sku)
    line_a, line_b = order_lines[0], order_lines[1]  # SKU-INJ-A locks first (ascending), then SKU-INJ-B

    colliding_key = f"reserve_inventory:{order.id}:{line_b.id}"
    store.reserve_inventory_atomic(
        merchant_id, "SKU-INJ-B", "Surat", quantity_requested=1,
        source_type="order", source_id="ord-precollision", idempotency_key=colliding_key,
    )

    service = _service(store)
    result = service._attempt_reserve_order_at_location(merchant_id, order, order_lines, "Surat")

    assert result["outcome"] == "conflict"  # UniqueViolation on line B's insert
    # Line A's reservation must NOT have survived - the whole transaction rolled back.
    line_a_reservations = [r for r in store.list(InventoryReservation, merchant_id) if r.source_id == order.id]
    assert line_a_reservations == []
    assert _inv(store, merchant_id, "SKU-INJ-A", "Surat").reserved == 0  # no leak from line 1
    assert _inv(store, merchant_id, "SKU-INJ-A", "Surat").available == 5
    # The pre-planted colliding reservation is untouched (still the only row for that key).
    assert _inv(store, merchant_id, "SKU-INJ-B", "Surat").reserved == 1

    # Safe retry: fix the collision away (simulate it being for a different order later) and confirm a
    # fresh order for just SKU-INJ-A still reserves correctly - no residue blocks future attempts.
    order2 = _order_with_lines(store, merchant_id, channel_id, "INJ-2", [("SKU-INJ-A", 1)])
    order2_lines = [l for l in store.list(OrderLine, merchant_id) if l.order_id == order2.id]
    retry = service._attempt_reserve_order_at_location(merchant_id, order2, order2_lines, "Surat")
    assert retry["outcome"] == "success"
    assert _inv(store, merchant_id, "SKU-INJ-A", "Surat").reserved == 1


# --- Part E: candidate retry under real concurrent contention leaves no residue at the losing location -

def test_candidate_loses_surat_under_real_contention_and_retries_cleanly_to_mumbai():
    """Surat has ATS=1 for the SKU (so it ranks ahead of Mumbai's lower priority in this setup - see
    below), Mumbai has ample stock. A genuinely concurrent order - its own connection, its own real
    committed Postgres transaction - drains Surat's single unit in the exact window between our order's
    heuristic ATS read (ranking) and its actual locked atomic attempt: the precise race Part E must
    survive. The window is opened deterministically here (via a thin wrapper around the real store call,
    so the moment of injection is controlled while every actual reservation/rollback still runs as real
    Postgres SQL) rather than left to OS thread scheduling, which Part E's other requirement - a
    DISTINGUISHABLE failed Surat attempt in the trace - needs to observe reliably rather than
    intermittently. True simultaneous-thread races are separately proven in Parts B/F/G above.

    Surat is configured as the merchant's priority location so ranking tries it FIRST despite Mumbai
    having more raw stock - otherwise highest-ATS-first would simply never attempt Surat at all."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-RETRY", location_ref="Surat", quantity=1, available=1))
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-RETRY", location_ref="Mumbai", quantity=5, available=5))
    setup_store.set_config(merchant_id, {"inventory": {"location_priority": ["Surat", "Mumbai"]}})
    channel_id = f"chn_{merchant_id}"
    dsn = os.environ["SANOCEA_PG_DSN"]

    order = _order_with_lines(setup_store, merchant_id, channel_id, "RETRY-1", [("SKU-RETRY", 1)])

    errors: list[str] = []
    outcome: dict = {}

    def our_order():
        try:
            thread_store = PostgresStore(dsn)
            service = _service(thread_store)
            order_lines = [l for l in thread_store.list(OrderLine, merchant_id) if l.order_id == order.id]

            real_atomic = thread_store.reserve_order_lines_atomic
            drained = {"done": False}

            def draining_atomic(*args, **kwargs):
                if not drained["done"]:
                    drained["done"] = True
                    competitor_store = PostgresStore(dsn)
                    reservation = competitor_store.reserve_inventory_atomic(
                        merchant_id, "SKU-RETRY", "Surat", quantity_requested=1,
                        source_type="order", source_id="ord-competitor", idempotency_key="k-competitor-retry",
                    )
                    assert reservation.quantity_reserved == 1
                return real_atomic(*args, **kwargs)

            thread_store.reserve_order_lines_atomic = draining_atomic
            outcome["result"] = service._allocate_and_reserve_order(merchant_id, order, order_lines)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"our_order: {exc!r}")

    t = threading.Thread(target=our_order)
    t.start()
    t.join(timeout=15)

    assert errors == [], f"unexpected errors: {errors}"

    verify_store = PostgresStore(dsn)
    surat_reservations = [r for r in verify_store.list(InventoryReservation, merchant_id) if r.location_ref == "Surat" and r.source_id == order.id]
    assert surat_reservations == []  # no residue at the losing candidate

    mumbai = _inv(verify_store, merchant_id, "SKU-RETRY", "Mumbai")
    surat = _inv(verify_store, merchant_id, "SKU-RETRY", "Surat")
    assert surat.reserved == 1  # only the competitor's reservation
    assert mumbai.reserved == 1  # our order landed fully at Mumbai
    line_results, any_shortfall = outcome["result"]
    assert any_shortfall is False

    events = [e for e in verify_store.list_audit(merchant_id) if e.action == "location_allocation_decision" and e.object_id == order.id]
    assert len(events) == 1
    assert events[0].result == "allocated"
    assert events[0].requested_mutation["selected_location"] == "Mumbai"
    attempts = events[0].requested_mutation["attempts"]
    assert any(a["location"] == "Surat" and a["outcome"] == "insufficient" for a in attempts)
    assert any(a["location"] == "Mumbai" and a["outcome"] == "success" for a in attempts)


# --- Part F: concurrent replay of the SAME order must converge on one allocation, no duplicates --------

def test_concurrent_replay_of_the_same_order_produces_exactly_one_allocation():
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-SAMEORD", location_ref="Surat", quantity=1, available=1))
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-SAMEORD", location_ref="Mumbai", quantity=1, available=1))
    channel_id = f"chn_{merchant_id}"
    dsn = os.environ["SANOCEA_PG_DSN"]
    order = _order_with_lines(setup_store, merchant_id, channel_id, "SAMEORD-1", [("SKU-SAMEORD", 1)])

    barrier = threading.Barrier(2)
    results: dict[str, dict] = {}
    errors: list[str] = []

    def attempt(key):
        try:
            thread_store = PostgresStore(dsn)
            service = _service(thread_store)
            order_lines = [l for l in thread_store.list(OrderLine, merchant_id) if l.order_id == order.id]
            barrier.wait(timeout=10)
            line_results, any_shortfall = service._allocate_and_reserve_order(merchant_id, order, order_lines)
            results[key] = {"line_results": line_results, "any_shortfall": any_shortfall}
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc!r}")

    threads = [threading.Thread(target=attempt, args=(f"t{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert errors == [], f"unexpected errors: {errors}"
    assert results["t0"]["any_shortfall"] is False
    assert results["t1"]["any_shortfall"] is False
    assert results["t0"]["line_results"] == results["t1"]["line_results"]  # both callers see a consistent result

    verify_store = PostgresStore(dsn)
    reservations = [r for r in verify_store.list(InventoryReservation, merchant_id) if r.source_id == order.id]
    assert len(reservations) == 1  # no duplicate reservation despite two concurrent allocation attempts
    locations_touched = {r.location_ref for r in reservations}
    assert len(locations_touched) == 1  # never split across locations

    surat = _inv(verify_store, merchant_id, "SKU-SAMEORD", "Surat")
    mumbai = _inv(verify_store, merchant_id, "SKU-SAMEORD", "Mumbai")
    assert surat.reserved + mumbai.reserved == 1  # exactly one unit reserved total, at exactly one location


# --- Part G: concurrent competing whole multi-line orders - never split a single order across locations -

def test_concurrent_competing_multiline_orders_never_split_a_single_order():
    """Order1(A=1,B=1) and Order2(A=1,B=1) compete for Surat(A=1,B=1) and Mumbai(A=1,B=1). Whichever
    order wins a location must get BOTH its lines there - never A-at-Surat-B-at-Mumbai for the same
    order. Both orders should ultimately succeed (one per location), with no oversell."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    for loc in ("Surat", "Mumbai"):
        setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-GA", location_ref=loc, quantity=1, available=1))
        setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-GB", location_ref=loc, quantity=1, available=1))
    channel_id = f"chn_{merchant_id}"
    dsn = os.environ["SANOCEA_PG_DSN"]

    order1 = _order_with_lines(setup_store, merchant_id, channel_id, "MULTI-1", [("SKU-GA", 1), ("SKU-GB", 1)])
    order2 = _order_with_lines(setup_store, merchant_id, channel_id, "MULTI-2", [("SKU-GA", 1), ("SKU-GB", 1)])

    barrier = threading.Barrier(2)
    errors: list[str] = []

    def attempt(order):
        try:
            thread_store = PostgresStore(dsn)
            service = _service(thread_store)
            order_lines = [l for l in thread_store.list(OrderLine, merchant_id) if l.order_id == order.id]
            barrier.wait(timeout=10)
            service._allocate_and_reserve_order(merchant_id, order, order_lines)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{order.order_number}: {exc!r}")

    t1 = threading.Thread(target=attempt, args=(order1,))
    t2 = threading.Thread(target=attempt, args=(order2,))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert errors == [], f"unexpected errors: {errors}"

    verify_store = PostgresStore(dsn)
    for order in (order1, order2):
        reservations = [r for r in verify_store.list(InventoryReservation, merchant_id) if r.source_id == order.id]
        locations_touched = {r.location_ref for r in reservations}
        assert len(locations_touched) <= 1, f"order {order.order_number} was split across locations: {locations_touched}"

    all_reservations = [r for r in verify_store.list(InventoryReservation, merchant_id) if r.source_id in (order1.id, order2.id)]
    surat_orders = {r.source_id for r in all_reservations if r.location_ref == "Surat"}
    mumbai_orders = {r.source_id for r in all_reservations if r.location_ref == "Mumbai"}
    assert surat_orders.isdisjoint(mumbai_orders) or not (surat_orders and mumbai_orders)
    # No oversell: each location's SKUs never exceed quantity 1 reserved.
    for loc in ("Surat", "Mumbai"):
        assert _inv(verify_store, merchant_id, "SKU-GA", loc).reserved <= 1
        assert _inv(verify_store, merchant_id, "SKU-GB", loc).reserved <= 1


def test_concurrent_orders_with_insufficient_aggregate_capacity_never_split_either_order():
    """Only ONE location exists with capacity for exactly ONE order's demand (A=1,B=1); no second
    location exists at all. Two concurrent orders each need (A=1,B=1). Exactly one must succeed fully;
    the other must fail cleanly with ZERO reservations anywhere - never a partial/split reservation for
    the losing order."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-AGG-A", location_ref="Surat", quantity=1, available=1))
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-AGG-B", location_ref="Surat", quantity=1, available=1))
    channel_id = f"chn_{merchant_id}"
    dsn = os.environ["SANOCEA_PG_DSN"]

    order1 = _order_with_lines(setup_store, merchant_id, channel_id, "AGG-1", [("SKU-AGG-A", 1), ("SKU-AGG-B", 1)])
    order2 = _order_with_lines(setup_store, merchant_id, channel_id, "AGG-2", [("SKU-AGG-A", 1), ("SKU-AGG-B", 1)])

    barrier = threading.Barrier(2)
    outcomes: dict[str, tuple] = {}
    errors: list[str] = []

    def attempt(order, key):
        try:
            thread_store = PostgresStore(dsn)
            service = _service(thread_store)
            order_lines = [l for l in thread_store.list(OrderLine, merchant_id) if l.order_id == order.id]
            barrier.wait(timeout=10)
            outcomes[key] = service._allocate_and_reserve_order(merchant_id, order, order_lines)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}: {exc!r}")

    t1 = threading.Thread(target=attempt, args=(order1, "o1"))
    t2 = threading.Thread(target=attempt, args=(order2, "o2"))
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert errors == [], f"unexpected errors: {errors}"

    verify_store = PostgresStore(dsn)
    reservations_o1 = [r for r in verify_store.list(InventoryReservation, merchant_id) if r.source_id == order1.id]
    reservations_o2 = [r for r in verify_store.list(InventoryReservation, merchant_id) if r.source_id == order2.id]

    winners = [k for k, (lr, shortfall) in outcomes.items() if not shortfall]
    losers = [k for k, (lr, shortfall) in outcomes.items() if shortfall]
    assert len(winners) == 1 and len(losers) == 1

    winner_reservations, loser_reservations = (reservations_o1, reservations_o2) if winners[0] == "o1" else (reservations_o2, reservations_o1)
    assert len(winner_reservations) == 2  # both lines reserved for the winner
    assert loser_reservations == []  # zero reservations for the loser - no partial/split leftover

    assert _inv(verify_store, merchant_id, "SKU-AGG-A", "Surat").reserved == 1
    assert _inv(verify_store, merchant_id, "SKU-AGG-B", "Surat").reserved == 1
