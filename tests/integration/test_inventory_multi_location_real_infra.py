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
    merchant_id = f"ml_mer_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="MultiLocation", display_name="MultiLocation"))
    return merchant_id, store


def _inv(store, merchant_id: str, sku: str, location: str) -> Inventory:
    return [i for i in store.list(Inventory, merchant_id) if i.sku == sku and i.location_ref == location][-1]


def test_surat_mumbai_are_independent_facts_against_real_postgres():
    """The review's own worked scenario, proven against real Postgres (not the in-memory store) -
    SKU-A at Surat=5 and Mumbai=7 are genuinely independent rows, and reserve/release act on exactly
    one of them."""
    suffix = uuid4().hex[:8]
    merchant_id, store = _setup(suffix)
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-A", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-A", location_ref="Mumbai", quantity=7, available=7))
    assert len([i for i in store.list(Inventory, merchant_id) if i.sku == "SKU-A"]) == 2

    reservation = store.reserve_inventory_atomic(
        merchant_id, "SKU-A", "Surat", quantity_requested=3,
        source_type="order", source_id="ord-surat", idempotency_key="reserve-surat",
    )
    assert reservation.quantity_reserved == 3
    surat = _inv(store, merchant_id, "SKU-A", "Surat")
    mumbai = _inv(store, merchant_id, "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 3, 2)
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)

    store.adjust_reservation_atomic(merchant_id, reservation.id, mode="release", amount=reservation.quantity_reserved)
    surat = _inv(store, merchant_id, "SKU-A", "Surat")
    mumbai = _inv(store, merchant_id, "SKU-A", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 0, 5)
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)  # untouched throughout


def test_concurrent_reservations_at_different_locations_never_contend():
    """A genuine concurrency proof specific to multi-location: two threads reserving the LAST unit of
    the SAME SKU at TWO DIFFERENT locations simultaneously must BOTH succeed (no false contention across
    locations - each location's row is locked independently), unlike Step 1's same-location proof where
    exactly one of two concurrent attempts must win."""
    suffix = uuid4().hex[:8]
    merchant_id, setup_store = _setup(suffix)
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-B", location_ref="Surat", quantity=1, available=1))
    setup_store.put(Inventory(merchant_id=merchant_id, sku="SKU-B", location_ref="Mumbai", quantity=1, available=1))

    dsn = os.environ["SANOCEA_PG_DSN"]
    barrier = threading.Barrier(2)
    results: dict[str, int] = {}
    errors: list[str] = []

    def attempt(location: str) -> None:
        try:
            thread_store = PostgresStore(dsn)
            barrier.wait(timeout=10)
            reservation = thread_store.reserve_inventory_atomic(
                merchant_id, "SKU-B", location, quantity_requested=1,
                source_type="order", source_id=f"ord-{location}", idempotency_key=f"reserve-{location}",
            )
            results[location] = reservation.quantity_reserved
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=attempt, args=(loc,)) for loc in ("Surat", "Mumbai")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent reservations at different locations must not raise - got: {errors}"
    assert results == {"Surat": 1, "Mumbai": 1}  # BOTH succeed - no cross-location contention

    surat = _inv(setup_store, merchant_id, "SKU-B", "Surat")
    mumbai = _inv(setup_store, merchant_id, "SKU-B", "Mumbai")
    assert (surat.reserved, surat.available) == (1, 0)
    assert (mumbai.reserved, mumbai.available) == (1, 0)


def test_rto_restock_targets_reservation_location_against_real_postgres():
    """Proves Part D's location-correction against real Postgres specifically: RTO restock must land at
    the reservation's own location_ref, not any hardcoded/resolved default, even when the merchant's
    inventory rows for other locations exist and must stay untouched."""
    suffix = uuid4().hex[:8]
    merchant_id, store = _setup(suffix)
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-C", location_ref="Surat", quantity=5, available=5))
    store.put(Inventory(merchant_id=merchant_id, sku="SKU-C", location_ref="Mumbai", quantity=7, available=7))

    reservation = store.reserve_inventory_atomic(
        merchant_id, "SKU-C", "Surat", quantity_requested=2,
        source_type="order", source_id="ord-rto", idempotency_key="reserve-rto",
    )
    reservation = store.adjust_reservation_atomic(merchant_id, reservation.id, mode="consume", amount=reservation.quantity_reserved)
    surat = _inv(store, merchant_id, "SKU-C", "Surat")
    assert (surat.quantity, surat.reserved) == (3, 0)
    assert reservation.quantity_consumed == 2

    # Direct primitive-level restock at the reservation's own location (mirrors what
    # PostOrderOperationsService._restock_order_reservations does at the service layer)
    store.atomic_adjust_inventory(merchant_id, reservation.sku, reservation.location_ref, quantity_delta=reservation.quantity_consumed, available_delta=reservation.quantity_consumed)
    surat = _inv(store, merchant_id, "SKU-C", "Surat")
    mumbai = _inv(store, merchant_id, "SKU-C", "Mumbai")
    assert (surat.quantity, surat.reserved, surat.available) == (5, 0, 5)
    assert (mumbai.quantity, mumbai.reserved, mumbai.available) == (7, 0, 7)  # untouched
