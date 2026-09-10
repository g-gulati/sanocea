from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest

from sanocea.connectors.payments import SimulatedSettlementProvider
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    FinanceReconciliation,
    Merchant,
    Order,
    PaymentObservation,
    Refund,
    SettlementEntry,
)
from sanocea.packages.finance import FinanceOperationsService


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)


def test_phase3_finance_reconciliation_persists_and_is_tenant_scoped():
    suffix = uuid4().hex[:8]
    merchant_id = f"fin_mer_{suffix}"
    other_id = f"fin_other_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Finance A", display_name="Finance A"))
    store.put(Merchant(id=other_id, merchant_id=other_id, legal_name="Finance B", display_name="Finance B"))
    store.set_config(
        merchant_id,
        {
            "finance": {
                "tolerances": {"default": 0, "courier_charge": 25},
                "expected_charges": {"fee": -100, "courier_charge": -250},
            }
        },
    )

    order = Order(
        merchant_id=merchant_id,
        channel_id=f"{merchant_id}_shopify",
        order_number=f"FIN-{suffix}",
        status="PAID",
        payment_status="paid",
        total_amount=499900,
        currency="INR",
    )
    refund = Refund(
        merchant_id=merchant_id,
        order_id=order.id,
        amount=75000,
        currency="INR",
        reason="damaged_item",
        status="completed",
    )
    store.put(order)
    store.put(refund)

    service = FinanceOperationsService(store)
    observation = service.observe_payment(merchant_id, order, "razorpay_sim", 499900, "INR", "captured", "pay_live_like")
    payment_result = service.reconcile_payment(merchant_id, order, observation)
    assert payment_result.result == "MATCH"

    provider = SimulatedSettlementProvider()
    batch_payload = provider.build_batch(merchant_id, [order], [refund], {order.id: observation.external_payment_id}, include_faults=True)
    batch_payload["entries"].append(
        {
            "external_entry_id": f"fee-{suffix}",
            "entry_type": "fee",
            "amount": -175,
            "currency": "INR",
            "description": "gateway fee drift",
        }
    )
    batch = service.ingest_settlement_batch(merchant_id, "settlement_sim", batch_payload)
    results = service.reconcile_settlement_batch(merchant_id, batch.id)

    persisted = store.list(FinanceReconciliation, merchant_id)
    exceptions = store.list(ExceptionRecord, merchant_id)
    entries = store.list(SettlementEntry, merchant_id)
    assert len(entries) >= 2
    assert len(results) >= 2
    assert any(item.result == "MATCH" for item in persisted)
    assert any(item.result in {"DIVERGENCE", "UNRESOLVED_REFERENCE", "CANONICAL_ONLY", "PARTIAL_SETTLEMENT", "OVER_SETTLED"} for item in persisted)
    assert any(item.category in {"fee_discrepancy", "unresolved_settlement_reference", "duplicate_settlement_entry"} for item in exceptions)

    with pytest.raises(TenantAccessError):
        store.get(FinanceReconciliation, other_id, persisted[0].id)


def test_sequential_duplicate_payment_observation_is_database_enforced_idempotent():
    """Blocker 2 (sequential replay): a webhook retry of the same (merchant, provider,
    external_payment_id) must never persist a second row - proven here against real Postgres, not the
    in-memory store."""
    suffix = uuid4().hex[:8]
    merchant_id = f"fin_seq_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Seq Dup", display_name="Seq Dup"))
    order = Order(merchant_id=merchant_id, channel_id=f"{merchant_id}_shopify", order_number=f"SEQ-{suffix}", status="PAID", payment_status="paid", total_amount=42000, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)

    first = service.observe_payment(merchant_id, order, "gateway", 42000, "INR", "captured", f"webhook-{suffix}")
    for _ in range(5):
        replay = service.observe_payment(merchant_id, order, "gateway", 42000, "INR", "captured", f"webhook-{suffix}")
        assert replay.id == first.id

    persisted = store.list(PaymentObservation, merchant_id)
    assert len(persisted) == 1, f"expected exactly one persisted PaymentObservation after 6 deliveries of the same webhook, got {len(persisted)}"


def test_concurrent_duplicate_payment_observation_resolves_to_single_row():
    """Blocker 2 (genuine concurrency, not SELECT-before-INSERT): two independent Postgres connections
    racing to observe_payment() for the SAME (merchant, provider, external_payment_id) at the same
    instant must still leave exactly one row - the database's unique index is the final authority, not
    an application-level existence check that can lose a race."""
    suffix = uuid4().hex[:8]
    merchant_id = f"fin_race_{suffix}"
    setup_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    setup_store.migrate()
    setup_store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Race", display_name="Race"))
    order = Order(merchant_id=merchant_id, channel_id=f"{merchant_id}_shopify", order_number=f"RACE-{suffix}", status="PAID", payment_status="paid", total_amount=15000, currency="INR")
    setup_store.put(order)

    external_payment_id = f"webhook-race-{suffix}"
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []
    winners: list[str] = []

    def deliver() -> None:
        try:
            # Each thread gets its own PostgresStore -> its own real psycopg2 connection, so this is a
            # genuine two-connection race at the database, not two calls serialized through one
            # connection or resolved by an in-process lock.
            thread_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
            thread_service = FinanceOperationsService(thread_store)
            barrier.wait(timeout=10)
            observation = thread_service.observe_payment(merchant_id, order, "gateway", 15000, "INR", "captured", external_payment_id)
            winners.append(observation.id)
        except BaseException as exc:  # noqa: BLE001 - we want to fail the test on ANY thread exception
            errors.append(exc)

    threads = [threading.Thread(target=deliver) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent observe_payment() must not raise - got: {errors}"
    assert len(winners) == 2
    assert winners[0] == winners[1], "both concurrent deliveries must resolve to the same canonical observation id"

    persisted = setup_store.list(PaymentObservation, merchant_id)
    assert len(persisted) == 1, f"expected exactly one row surviving a genuine concurrent duplicate delivery, got {len(persisted)}"


def test_concurrent_settlement_entry_ingestion_does_not_duplicate():
    """Strengthened validation: two threads ingesting a batch containing the SAME external_entry_id at
    the same instant must not both succeed in creating a row, and must not crash the caller with an
    unhandled UniqueViolation - the database-level ON CONFLICT handling in PostgresStore.put() is the
    real safety net behind the (weaker, TOCTOU) application-level pre-check."""
    suffix = uuid4().hex[:8]
    merchant_id = f"fin_ste_race_{suffix}"
    setup_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    setup_store.migrate()
    setup_store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Entry Race", display_name="Entry Race"))
    order = Order(merchant_id=merchant_id, channel_id=f"{merchant_id}_shopify", order_number=f"STE-{suffix}", status="PAID", payment_status="paid", total_amount=20000, currency="INR")
    setup_store.put(order)

    batch_payload = {
        "external_batch_id": f"race-batch-{suffix}",
        "entries": [
            {
                "external_entry_id": f"race-entry-{suffix}",
                "entry_type": "payment",
                "order_id": order.id,
                "amount": 20000,
                "currency": "INR",
            }
        ],
    }
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def ingest() -> None:
        try:
            thread_store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
            thread_service = FinanceOperationsService(thread_store)
            barrier.wait(timeout=10)
            thread_service.ingest_settlement_batch(merchant_id, "gateway", batch_payload)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=ingest) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"concurrent settlement ingestion must not raise an unhandled error - got: {errors}"
    entries = setup_store.list(SettlementEntry, merchant_id)
    matching = [e for e in entries if e.external_entry_id == f"race-entry-{suffix}"]
    assert len(matching) == 1, f"expected exactly one settlement entry surviving a concurrent duplicate ingest, got {len(matching)}"


def test_cross_batch_cumulative_settlement_against_real_postgres():
    """Phase 3.1 item 1, proven against real Postgres (not the in-memory store): the same order settled
    under two different external entry ids across two SEPARATE batches must be summed cumulatively, not
    independently matched twice."""
    suffix = uuid4().hex[:8]
    merchant_id = f"fin_cum_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Cumulative", display_name="Cumulative"))
    order = Order(merchant_id=merchant_id, channel_id=f"{merchant_id}_shopify", order_number=f"CUM-{suffix}", status="PAID", payment_status="paid", total_amount=10000, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)
    observation = service.observe_payment(merchant_id, order, "gateway", 10000, "INR", "captured", f"txn-cum-{suffix}")
    reference = observation.external_payment_id

    batch_1 = service.ingest_settlement_batch(merchant_id, "gateway", {"external_batch_id": f"cum-batch-1-{suffix}", "entries": [
        {"external_entry_id": f"cum-entry-1a-{suffix}", "entry_type": "payment", "provider_order_reference": reference, "amount": 6000, "currency": "INR"},
    ]})
    partial_results = service.reconcile_settlement_batch(merchant_id, batch_1.id)
    partial = next(r for r in partial_results if r.object_id == order.id and r.scope.startswith("cumulative_settlement"))
    assert partial.result == "PARTIAL_SETTLEMENT"

    batch_2 = service.ingest_settlement_batch(merchant_id, "gateway", {"external_batch_id": f"cum-batch-2-{suffix}", "entries": [
        {"external_entry_id": f"cum-entry-1b-{suffix}", "entry_type": "payment", "provider_order_reference": reference, "amount": 4000, "currency": "INR"},
    ]})
    complete_results = service.reconcile_settlement_batch(merchant_id, batch_2.id)
    complete = next(r for r in complete_results if r.object_id == order.id and r.scope.startswith("cumulative_settlement"))
    assert complete.result == "MATCH"
    assert complete.observed_amount == 10000

    entries = [e for e in store.list(SettlementEntry, merchant_id) if e.order_id == order.id]
    assert len(entries) == 2, "both settlement entries (from two different batches) must be persisted and both must contribute to the sum"


def test_external_reference_resolution_against_real_postgres():
    """Phase 3.1 item 2, proven against real Postgres: settlement entries carry a provider reference,
    not Sanocea's order.id, and resolution goes through external_id_mappings."""
    suffix = uuid4().hex[:8]
    merchant_id = f"fin_ext_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="ExtRef", display_name="ExtRef"))
    order = Order(merchant_id=merchant_id, channel_id=f"{merchant_id}_shopify", order_number=f"EXT-{suffix}", status="PAID", payment_status="paid", total_amount=7500, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)
    observation = service.observe_payment(merchant_id, order, "gateway", 7500, "INR", "captured", f"txn-ext-{suffix}")

    mapping = store.get_external_mapping(merchant_id, "gateway", "order", observation.external_payment_id)
    assert mapping is not None and mapping.sanocea_id == order.id, "observe_payment must register a resolvable external_id_mappings row"

    batch = service.ingest_settlement_batch(merchant_id, "gateway", {"external_batch_id": f"ext-batch-{suffix}", "entries": [
        {"external_entry_id": f"ext-entry-valid-{suffix}", "entry_type": "payment", "provider_order_reference": observation.external_payment_id, "amount": 7500, "currency": "INR"},
        {"external_entry_id": f"ext-entry-unknown-{suffix}", "entry_type": "payment", "provider_order_reference": f"never-seen-{suffix}", "amount": 1234, "currency": "INR"},
    ]})
    results = service.reconcile_settlement_batch(merchant_id, batch.id)
    valid = next(r for r in results if r.object_id == order.id and r.scope.startswith("cumulative_settlement"))
    assert valid.result == "MATCH"
    unresolved = [r for r in results if r.result == "UNRESOLVED_REFERENCE"]
    assert len(unresolved) == 1

    entries = store.list(SettlementEntry, merchant_id)
    resolved_entry = next(e for e in entries if e.external_entry_id == f"ext-entry-valid-{suffix}")
    unresolved_entry = next(e for e in entries if e.external_entry_id == f"ext-entry-unknown-{suffix}")
    assert resolved_entry.order_id == order.id
    assert unresolved_entry.order_id is None
    assert unresolved_entry.provider_order_reference == f"never-seen-{suffix}", "raw provider reference must be kept as evidence even when unresolved"
