from __future__ import annotations

import os
from uuid import uuid4

import pytest

from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.models import ExternalIdMapping, Merchant, Order, Refund, SettlementEntry
from sanocea.packages.finance import FinanceOperationsService


pytestmark = pytest.mark.skipif(not os.environ.get("SANOCEA_PG_DSN"), reason="requires real Postgres DSN in SANOCEA_PG_DSN")


def _setup(suffix: str, store: PostgresStore) -> tuple[str, Order, Refund]:
    merchant_id = f"rr_mer_{suffix}"
    store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="Refund Ref", display_name="Refund Ref"))
    order = Order(merchant_id=merchant_id, channel_id=f"{merchant_id}_shopify", order_number=f"RR-{suffix}", status="PAID", payment_status="paid", total_amount=8000, currency="INR")
    store.put(order)
    refund = Refund(merchant_id=merchant_id, order_id=order.id, amount=8000, currency="INR", status="completed")
    store.put(refund)
    return merchant_id, order, refund


def test_refund_external_reference_resolution_against_real_postgres():
    """Real Postgres proof (not the in-memory store) that a refund settlement entry resolves through
    external_id_mappings - closing the Phase 3.1 debt where refund_id was trusted directly off the
    incoming settlement payload."""
    suffix = uuid4().hex[:8]
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    merchant_id, order, refund = _setup(suffix, store)
    service = FinanceOperationsService(store)

    store.put_external_mapping(ExternalIdMapping(merchant_id=merchant_id, sanocea_entity_type="Refund", sanocea_id=refund.id, external_system="gateway", external_entity_type="refund", external_id=f"rf-{suffix}"))

    valid_batch = service.ingest_settlement_batch(merchant_id, "gateway", {"external_batch_id": f"b-valid-{suffix}", "entries": [
        {"external_entry_id": f"e-valid-{suffix}", "entry_type": "refund", "provider_refund_reference": f"rf-{suffix}", "amount": -8000, "currency": "INR"},
    ]})
    valid_entry = next(e for e in store.list(SettlementEntry, merchant_id) if e.batch_id == valid_batch.id)
    assert valid_entry.refund_id == refund.id
    results = service.reconcile_settlement_batch(merchant_id, valid_batch.id)
    assert results[0].result == "MATCH"

    unknown_batch = service.ingest_settlement_batch(merchant_id, "gateway", {"external_batch_id": f"b-unknown-{suffix}", "entries": [
        {"external_entry_id": f"e-unknown-{suffix}", "entry_type": "refund", "provider_refund_reference": f"rf-never-observed-{suffix}", "amount": -8000, "currency": "INR"},
    ]})
    unknown_entry = next(e for e in store.list(SettlementEntry, merchant_id) if e.batch_id == unknown_batch.id)
    assert unknown_entry.refund_id is None
    unknown_results = service.reconcile_settlement_batch(merchant_id, unknown_batch.id)
    assert unknown_results[0].result == "UNRESOLVED_REFERENCE"


def test_cross_merchant_refund_reference_isolated_against_real_postgres():
    suffix = uuid4().hex[:8]
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    merchant_a, order_a, refund_a = _setup(f"{suffix}a", store)
    merchant_b, order_b, refund_b = _setup(f"{suffix}b", store)
    service = FinanceOperationsService(store)

    shared_reference = f"rf-shared-{suffix}"
    store.put_external_mapping(ExternalIdMapping(merchant_id=merchant_a, sanocea_entity_type="Refund", sanocea_id=refund_a.id, external_system="gateway", external_entity_type="refund", external_id=shared_reference))

    batch_b = service.ingest_settlement_batch(merchant_b, "gateway", {"external_batch_id": f"b-xtenant-{suffix}", "entries": [
        {"external_entry_id": f"e-xtenant-{suffix}", "entry_type": "refund", "provider_refund_reference": shared_reference, "amount": -8000, "currency": "INR"},
    ]})
    entry_b = next(e for e in store.list(SettlementEntry, merchant_b) if e.batch_id == batch_b.id)
    assert entry_b.refund_id is None, "merchant A's mapping must never resolve inside merchant B's ingestion"
    assert entry_b.refund_id != refund_a.id
