from __future__ import annotations

from sanocea.connectors.payments import SimulatedSettlementProvider
from sanocea.packages.domain_contract.models import ExceptionRecord, FinanceReconciliation, Order, PaymentObservation, Refund, SettlementEntry
from sanocea.packages.finance import FinanceOperationsService


def test_payment_observation_reconciles_deterministically(phase0):
    store, *_ = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="F-1", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)
    observation = service.observe_payment("mer_A", order, "razorpay", 100000, "INR", "captured", "pay_1")
    result = service.reconcile_payment("mer_A", order, observation)
    assert result.result == "MATCH"
    assert store.list(FinanceReconciliation, "mer_A")[0].result == "MATCH"


def test_payment_amount_mismatch_creates_finance_exception(phase0):
    store, *_ = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="F-2", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)
    observation = service.observe_payment("mer_A", order, "razorpay", 99000, "INR", "captured", "pay_2")
    result = service.reconcile_payment("mer_A", order, observation)
    assert result.result == "DIVERGENCE"
    assert result.exception_id


def test_settlement_reconciliation_detects_duplicates_missing_refunds_and_unmatched_entries(phase0):
    store, *_ = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="F-3", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    refund = Refund(merchant_id="mer_A", order_id=order.id, amount=25000, currency="INR", status="completed")
    store.put(refund)
    service = FinanceOperationsService(store)
    observation = service.observe_payment("mer_A", order, "gateway", 100000, "INR", "captured", "pay_f3")
    batch = SimulatedSettlementProvider().build_batch("mer_A", [order], [refund], {order.id: observation.external_payment_id}, include_faults=True)
    settlement = service.ingest_settlement_batch("mer_A", "gateway", batch)
    results = service.reconcile_settlement_batch("mer_A", settlement.id)
    scopes = {result.scope for result in results}
    assert any("missing_refund_settlement" in scope for scope in scopes)
    # The fault-injected entry referencing a provider transaction Sanocea never observed must not
    # resolve to any order - Phase 3.1 no longer accepts a raw order_id shortcut for this.
    assert any(result.result == "UNRESOLVED_REFERENCE" and "unresolved_settlement_reference" in result.scope for result in results)
    assert any(item.category == "duplicate_settlement_entry" for item in store.list(ExceptionRecord, "mer_A"))


def test_finance_records_remain_tenant_scoped(phase0):
    store, *_ = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="F-4", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)
    observation = service.observe_payment("mer_A", order, "gateway", 100000, "INR", "settled", "pay_4")
    result = service.reconcile_payment("mer_A", order, observation)
    assert store.list(FinanceReconciliation, "mer_B") == []
    assert store.get(FinanceReconciliation, "mer_A", result.id).id == result.id


# --- Phase 3 hardening regression tests (blockers from the independent audit) -----------------------


def test_sequential_duplicate_payment_observation_produces_exactly_one_business_effect(phase0):
    """Blocker 2: repeated delivery of the same (merchant, provider, external_payment_id) - e.g. a
    gateway webhook retry - must persist as exactly one PaymentObservation and reconcile to exactly
    one FinanceReconciliation record, not one per delivery."""
    store, *_ = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="F-DUP-1", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)

    first = service.observe_payment("mer_A", order, "gateway", 100000, "INR", "captured", "webhook-retry-77")
    second = service.observe_payment("mer_A", order, "gateway", 100000, "INR", "captured", "webhook-retry-77")
    assert first.id == second.id, "duplicate webhook delivery must resolve to the same canonical observation"
    assert len(store.list(PaymentObservation, "mer_A")) == 1

    result_a = service.reconcile_payment("mer_A", order, first)
    result_b = service.reconcile_payment("mer_A", order, second)
    assert result_a.id == result_b.id, "reconciling the same observation twice must not double-book"
    assert len(store.list(FinanceReconciliation, "mer_A")) == 1


def test_missing_refund_settlement_creates_visible_finance_exception(phase0):
    """Blocker 3: a completed refund with no matching settlement entry must produce a real
    ExceptionRecord (category=missing_refund_settlement) with an exception_id wired onto the
    FinanceReconciliation row - not a silent CANONICAL_ONLY row nobody sees."""
    store, *_ = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="F-MISS-1", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    refund = Refund(merchant_id="mer_A", order_id=order.id, amount=25000, currency="INR", status="completed")
    store.put(refund)
    service = FinanceOperationsService(store)
    # a batch with no entries at all for this refund
    batch = service.ingest_settlement_batch("mer_A", "gateway", {"external_batch_id": "no-refund-batch", "entries": []})
    results = service.reconcile_settlement_batch("mer_A", batch.id)

    missing = [r for r in results if r.result == "CANONICAL_ONLY" and "missing_refund_settlement" in r.scope]
    assert len(missing) == 1
    assert missing[0].exception_id, "missing-refund reconciliation must be linked to a real ExceptionRecord"

    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(exc.category == "missing_refund_settlement" and exc.object_id == refund.id for exc in exceptions)


def test_unconfigured_charge_type_never_uses_observed_as_expected(phase0):
    """Blocker 4: a settlement charge entry (fee/courier_charge/marketplace_deduction) whose type has
    no merchant expected_charges configuration must never silently MATCH itself - it must come back as
    an explicit REQUIRES_CONFIGURATION result, not a fabricated match."""
    store, *_ = phase0
    order = Order(merchant_id="mer_A", channel_id="chn_A_shopify", order_number="F-UNK-1", status="PAID", payment_status="paid", total_amount=100000, currency="INR")
    store.put(order)
    service = FinanceOperationsService(store)
    # deliberately configure finance WITHOUT a marketplace_deduction entry
    config = store.get_config("mer_A")
    config["finance"] = {"tolerances": {"default": 0}, "expected_charges": {"fee": -120}}
    store.set_config("mer_A", config)

    batch = service.ingest_settlement_batch(
        "mer_A",
        "gateway",
        {
            "external_batch_id": "unknown-charge-batch",
            "entries": [
                {
                    "external_entry_id": "mkt-ded-1",
                    "entry_type": "marketplace_deduction",
                    "order_id": order.id,
                    "amount": -777,
                    "currency": "INR",
                }
            ],
        },
    )
    results = service.reconcile_settlement_batch("mer_A", batch.id)
    assert len(results) == 1
    assert results[0].result == "REQUIRES_CONFIGURATION"
    assert results[0].result != "MATCH"
    assert results[0].exception_id
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(exc.category == "marketplace_deduction_requires_configuration" for exc in exceptions)
