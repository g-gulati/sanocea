from __future__ import annotations

from sanocea.connectors.payments import SimulatedSettlementProvider
from sanocea.packages.domain_contract.models import ExceptionRecord, FinanceReconciliation, Order, SettlementEntry
from sanocea.packages.finance import FinanceOperationsService


def _order(merchant_id: str, number: str, total_amount: int, currency: str = "INR") -> Order:
    return Order(
        merchant_id=merchant_id,
        channel_id=f"{merchant_id}_shopify",
        order_number=number,
        status="PAID",
        payment_status="paid",
        total_amount=total_amount,
        currency=currency,
    )


def _batch(
    merchant_id: str,
    provider: str,
    external_batch_id: str,
    entries: list[dict],
) -> dict:
    return {"external_batch_id": external_batch_id, "entries": entries}


def _payment_entry(external_entry_id: str, provider_order_reference: str, amount: int, currency: str = "INR") -> dict:
    return {
        "external_entry_id": external_entry_id,
        "entry_type": "payment",
        "provider_order_reference": provider_order_reference,
        "amount": amount,
        "currency": currency,
    }


# --- Cumulative, cross-batch settlement accounting (Phase 3.1 item 1) --------------------------------


def test_cumulative_settlement_matches_when_two_partial_batches_sum_to_expected(phase0):
    """expected 10000 -> 6000 + 4000 (two separate batches) = MATCH."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "CUM-1", 10000)
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 10000, "INR", "captured", "txn-cum-1")
    reference = observation.external_payment_id

    batch_1 = service.ingest_settlement_batch("mer_A", "gateway", _batch("mer_A", "gateway", "batch-1", [_payment_entry("entry-1a", reference, 6000)]))
    results_1 = service.reconcile_settlement_batch("mer_A", batch_1.id)
    cumulative_1 = next(r for r in results_1 if r.scope.startswith("cumulative_settlement") and r.object_id == order.id)
    assert cumulative_1.result == "PARTIAL_SETTLEMENT"
    assert cumulative_1.observed_amount == 6000

    batch_2 = service.ingest_settlement_batch("mer_A", "gateway", _batch("mer_A", "gateway", "batch-2", [_payment_entry("entry-1b", reference, 4000)]))
    results_2 = service.reconcile_settlement_batch("mer_A", batch_2.id)
    cumulative_2 = next(r for r in results_2 if r.scope.startswith("cumulative_settlement") and r.object_id == order.id)
    assert cumulative_2.result == "MATCH"
    assert cumulative_2.observed_amount == 10000
    assert cumulative_2.expected_amount == 10000

    # Two entries actually contributed - proof this is a genuine cross-batch SUM, not the last write winning.
    entries = [e for e in store.list(SettlementEntry, "mer_A") if e.order_id == order.id]
    assert len(entries) == 2
    assert sorted(e.amount for e in entries) == [4000, 6000]


def test_cumulative_settlement_over_settled_across_two_batches_flags_duplicate_risk(phase0):
    """expected 10000 -> 10000 + 10000 (two separate batches) = OVER_SETTLED with duplicate-risk flagged."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "CUM-2", 10000)
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 10000, "INR", "captured", "txn-cum-2")
    reference = observation.external_payment_id

    batch_1 = service.ingest_settlement_batch("mer_A", "gateway", _batch("mer_A", "gateway", "batch-1", [_payment_entry("entry-2a", reference, 10000)]))
    results_1 = service.reconcile_settlement_batch("mer_A", batch_1.id)
    cumulative_1 = next(r for r in results_1 if r.scope.startswith("cumulative_settlement") and r.object_id == order.id)
    assert cumulative_1.result == "MATCH"

    # A second, DIFFERENT settlement row (different external_entry_id / different batch) remits the
    # exact same amount again for the same order - this is the concealed-duplicate/over-settlement risk
    # the original defect could not detect.
    batch_2 = service.ingest_settlement_batch("mer_A", "gateway", _batch("mer_A", "gateway", "batch-2", [_payment_entry("entry-2b", reference, 10000)]))
    results_2 = service.reconcile_settlement_batch("mer_A", batch_2.id)
    cumulative_2 = next(r for r in results_2 if r.scope.startswith("cumulative_settlement") and r.object_id == order.id)
    assert cumulative_2.result == "OVER_SETTLED"
    assert cumulative_2.observed_amount == 20000
    assert cumulative_2.expected_amount == 10000
    assert cumulative_2.exception_id
    assert "over_settled_duplicate_risk" in cumulative_2.scope

    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(exc.category == "over_settled_duplicate_risk" and exc.object_id == order.id for exc in exceptions)


def test_cumulative_settlement_partial_vs_under_settled_depends_on_final_flag(phase0):
    """expected 10000 -> 6000 only: PARTIAL_SETTLEMENT while more may still arrive, UNDER_SETTLED once
    the caller explicitly closes the settlement window for that order."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "CUM-3", 10000)
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 10000, "INR", "captured", "txn-cum-3")
    reference = observation.external_payment_id

    batch = service.ingest_settlement_batch("mer_A", "gateway", _batch("mer_A", "gateway", "batch-1", [_payment_entry("entry-3a", reference, 6000)]))
    results = service.reconcile_settlement_batch("mer_A", batch.id)
    cumulative = next(r for r in results if r.scope.startswith("cumulative_settlement") and r.object_id == order.id)
    assert cumulative.result == "PARTIAL_SETTLEMENT"

    # No new settlement entries arrive; the same underlying facts, but now explicitly closed as final.
    closing = service.reconcile_cumulative_settlement("mer_A", order.id, final=True)
    assert closing.result == "UNDER_SETTLED"
    assert closing.observed_amount == 6000
    assert closing.expected_amount == 10000
    assert closing.exception_id


def test_retransmission_of_same_provider_entry_does_not_change_cumulative_total(phase0):
    """Retransmitting the exact same provider settlement entry must remain idempotent: the cumulative
    total (and verdict) must not change, and no second SettlementEntry row is persisted."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "CUM-4", 10000)
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 10000, "INR", "captured", "txn-cum-4")
    reference = observation.external_payment_id

    payload = _batch("mer_A", "gateway", "batch-retransmit", [_payment_entry("entry-4a", reference, 6000)])
    batch = service.ingest_settlement_batch("mer_A", "gateway", payload)
    service.reconcile_settlement_batch("mer_A", batch.id)

    # Retransmit the identical batch payload (same external_batch_id, same external_entry_id).
    batch_again = service.ingest_settlement_batch("mer_A", "gateway", payload)
    assert batch_again.id == batch.id
    results_again = service.reconcile_settlement_batch("mer_A", batch_again.id)
    cumulative_again = next(r for r in results_again if r.scope.startswith("cumulative_settlement") and r.object_id == order.id)

    assert cumulative_again.observed_amount == 6000  # unchanged, not 12000
    assert cumulative_again.result == "PARTIAL_SETTLEMENT"
    entries = [e for e in store.list(SettlementEntry, "mer_A") if e.order_id == order.id]
    assert len(entries) == 1


# --- External-ID resolution (Phase 3.1 item 2) --------------------------------------------------------


def test_valid_provider_reference_resolves_and_reconciles(phase0):
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "EXT-1", 5000)
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 5000, "INR", "captured", "txn-ext-1")

    batch = service.ingest_settlement_batch("mer_A", "gateway", _batch("mer_A", "gateway", "batch-ext-1", [_payment_entry("entry-ext-1", observation.external_payment_id, 5000)]))
    results = service.reconcile_settlement_batch("mer_A", batch.id)
    cumulative = next(r for r in results if r.scope.startswith("cumulative_settlement") and r.object_id == order.id)
    assert cumulative.result == "MATCH"


def test_unknown_provider_reference_never_matches(phase0):
    """A settlement entry referencing a provider transaction Sanocea never observed (no
    external_id_mappings row exists at all) must resolve to UNRESOLVED_REFERENCE, never MATCH."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    batch = service.ingest_settlement_batch(
        "mer_A", "gateway", _batch("mer_A", "gateway", "batch-unknown-ref", [_payment_entry("entry-unknown-1", "never-observed-reference-xyz", 5000)])
    )
    results = service.reconcile_settlement_batch("mer_A", batch.id)
    assert len(results) == 1
    assert results[0].result == "UNRESOLVED_REFERENCE"
    assert results[0].result != "MATCH"
    assert results[0].exception_id


def test_incorrect_provider_reference_never_matches(phase0):
    """A corrupted/mistyped reference that superficially resembles a real one but does not exactly match
    any external_id_mappings row must also resolve to UNRESOLVED_REFERENCE, never MATCH against the
    order the correct reference would have pointed to."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "EXT-2", 5000)
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 5000, "INR", "captured", "txn-ext-2")
    corrupted_reference = observation.external_payment_id + "-typo"

    batch = service.ingest_settlement_batch("mer_A", "gateway", _batch("mer_A", "gateway", "batch-incorrect-ref", [_payment_entry("entry-incorrect-1", corrupted_reference, 5000)]))
    results = service.reconcile_settlement_batch("mer_A", batch.id)
    assert len(results) == 1
    assert results[0].result == "UNRESOLVED_REFERENCE"
    # Confirm the order itself was NOT touched - no cumulative reconciliation was produced for it.
    assert not any(r.object_id == order.id for r in results)


def test_ambiguous_reference_currency_mismatch_never_matches(phase0):
    """A reference resolves to a real order, but the settlement entry's currency does not match that
    order's currency (a form of "ambiguous" resolution) - must not silently MATCH."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "EXT-3", 5000, currency="INR")
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 5000, "INR", "captured", "txn-ext-3")

    batch = service.ingest_settlement_batch(
        "mer_A", "gateway",
        _batch("mer_A", "gateway", "batch-ambiguous-ref", [_payment_entry("entry-ambiguous-1", observation.external_payment_id, 5000, currency="USD")]),
    )
    results = service.reconcile_settlement_batch("mer_A", batch.id)
    assert len(results) == 1
    assert results[0].result != "MATCH"
    assert "currency_mismatch" in results[0].scope
    assert results[0].exception_id


def test_duplicate_external_entry_result_is_explicitly_duplicate(phase0):
    """Retransmitting the same external_entry_id (a business-level duplicate, not a race) must now be
    tagged with the explicit DUPLICATE result, not the generic DIVERGENCE bucket."""
    store, *_ = phase0
    service = FinanceOperationsService(store)
    order = _order("mer_A", "EXT-4", 5000)
    store.put(order)
    observation = service.observe_payment("mer_A", order, "gateway", 5000, "INR", "captured", "txn-ext-4")

    payload = _batch("mer_A", "gateway", "batch-dup-entry", [_payment_entry("entry-dup-1", observation.external_payment_id, 5000)])
    payload["entries"].append(dict(payload["entries"][0]))  # exact duplicate row within the same batch
    batch = service.ingest_settlement_batch("mer_A", "gateway", payload)
    duplicate_exceptions = [exc for exc in store.list(ExceptionRecord, "mer_A") if exc.category == "duplicate_settlement_entry"]
    assert duplicate_exceptions
    duplicate_reconciliations = [
        r for r in store.list(FinanceReconciliation, "mer_A")
        if r.exception_id in {exc.id for exc in duplicate_exceptions}
    ]
    assert duplicate_reconciliations
    assert all(r.result == "DUPLICATE" for r in duplicate_reconciliations)
    entries = [e for e in store.list(SettlementEntry, "mer_A") if e.order_id == order.id]
    assert len(entries) == 1


def test_adjustment_entry_is_recorded_not_silently_unknown(phase0):
    store, *_ = phase0
    service = FinanceOperationsService(store)
    batch = service.ingest_settlement_batch(
        "mer_A", "gateway",
        _batch("mer_A", "gateway", "batch-adjustment", [
            {"external_entry_id": "adj-1", "entry_type": "adjustment", "amount": -50, "currency": "INR"},
        ]),
    )
    results = service.reconcile_settlement_batch("mer_A", batch.id)
    assert len(results) == 1
    assert results[0].result == "ADJUSTMENT_RECORDED"
