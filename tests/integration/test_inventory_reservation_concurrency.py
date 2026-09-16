from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import Inventory, InventoryReservation, Merchant


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def _setup(suffix: str):
    merchant_id = f"rsv_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Reservation", display_name="Reservation"))
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-1", location_ref="default", quantity=1, available=1))
    return merchant_id, store


def test_concurrent_last_unit_reservation_exactly_one_succeeds():
    """Step 1 Correction 1's required proof: two concurrent attempts to reserve the LAST remaining unit
    of the same (merchant, sku, location) must not both succeed. Genuine concurrency (two threads, two
    separate real Postgres connections, synchronized with a barrier so both attempts race the SAME row)
    exercising `reserve_inventory_atomic` directly - the exact operation Correction 1 required be made
    database-atomic (SELECT ... FOR UPDATE + check + increment in one transaction), replacing the old
    check-then-update pattern (read available in Python, then a separate write) that plain additive
    deltas cannot make safe for reservation CREATION. Mirrors
    test_phase4_procurement_real_infra.test_concurrent_po_submission_yields_exactly_one_external_po's
    established two-thread/barrier/separate-connection pattern.
    """
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    results: list[int] = []
    errors: list[str] = []

    def attempt(order_id: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            barrier.wait(timeout=10)
            reservation = thread_store.reserve_inventory_atomic(
                merchant_id, "SKU-1", "default",
                quantity_requested=1, source_type="order", source_id=order_id,
                idempotency_key=f"reserve:{order_id}",
            )
            results.append(reservation.quantity_reserved)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=attempt, args=(f"ord-{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent reservation must not raise - got: {errors}"
    assert len(results) == 2
    # EXACTLY one of the two concurrent attempts gets the last unit; the other gets a deterministic
    # shortfall (0 reserved) - never both reserving the same physical unit.
    assert sorted(results) == [0, 1], f"expected exactly one winner (1) and one shortfall (0), got {results}"

    final_inv = [i for i in setup_store.list(Inventory, merchant_id) if i.sku == "SKU-1"][-1]
    assert final_inv.reserved == 1, "final reserved must never exceed the single unit that actually existed"
    assert final_inv.quantity == 1
    assert final_inv.available == 0
    assert final_inv.available == final_inv.quantity - final_inv.reserved

    reservations = setup_store.list(InventoryReservation, merchant_id)
    assert len(reservations) == 2
    reserved_amounts = sorted(r.quantity_reserved for r in reservations)
    assert reserved_amounts == [0, 1]


def test_concurrent_release_and_consume_on_same_reservation_never_double_applies():
    """A second, related concurrency proof: two threads racing RELEASE and CONSUME against the SAME
    already-created reservation (e.g. a retried cancellation racing a retried fulfilment-consume signal)
    must never apply more than the reservation actually owns. `adjust_reservation_atomic`'s
    `SELECT ... FOR UPDATE` on the reservation row serializes this; without it, both threads could read
    the same `quantity_reserved` and each apply the full amount, double-counting the effect on
    `Inventory.reserved`."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-2", location_ref="default", quantity=5, available=5))
    reservation = setup_store.reserve_inventory_atomic(
        merchant_id, "SKU-2", "default", quantity_requested=5,
        source_type="order", source_id="ord-race", idempotency_key="reserve-race",
    )
    assert reservation.quantity_reserved == 5

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    errors: list[str] = []

    def apply(mode: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            barrier.wait(timeout=10)
            thread_store.adjust_reservation_atomic(merchant_id, reservation.id, mode=mode, amount=5)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=apply, args=(mode,)) for mode in ("release", "consume")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent release/consume must not raise - got: {errors}"
    final_reservation = setup_store.get(InventoryReservation, merchant_id, reservation.id)
    # Together, release + consume must never exceed the 5 units this reservation actually owns -
    # whichever ran first gets its full amount, the second is clamped to whatever remained (0).
    assert final_reservation.quantity_released + final_reservation.quantity_consumed == 5

    final_inv = [i for i in setup_store.list(Inventory, merchant_id) if i.sku == "SKU-2"][-1]
    assert final_inv.reserved == 0
    assert final_inv.available == final_inv.quantity - final_inv.reserved
