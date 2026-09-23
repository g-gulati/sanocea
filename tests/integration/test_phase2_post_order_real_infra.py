from __future__ import annotations

import os
from uuid import uuid4

import pytest

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import ExceptionRecord, Order, Shipment
from sanocea.packages.onboarding import MerchantOnboardingService
from sanocea.packages.post_order import PostOrderOperationsService
from sanocea.workers.workflow import FakeTemporalEngine


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres settings",
)


def test_phase2_post_order_persistence_and_duplicate_shipment_safety():
    suffix = uuid4().hex[:8]
    merchant_id = f"p2_mer_{suffix}"
    other_id = f"p2_other_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    MerchantOnboardingService(store).onboard_phase1(merchant_id, "Phase 2 Merchant")
    MerchantOnboardingService(store).onboard_phase1(other_id, "Other Merchant")
    order = Order(
        merchant_id=merchant_id,
        channel_id=f"{merchant_id}_shopify",
        order_number=f"P2-{suffix}",
        status="PAID",
        payment_status="paid",
        total_amount=150000,
        currency="INR",
    )
    store.put(order)
    logistics = SimulatedLogisticsConnector(store)
    operations = PostOrderOperationsService(store, ShopifyConnector(store, FakeTemporalEngine(store)), logistics)

    assert operations.observe_inventory(merchant_id, f"SKU-{suffix}", 5, 2) == "exception"
    assert any(item.category == "inventory_conflict" for item in store.list(ExceptionRecord, merchant_id))

    first_status, first_ref = operations.create_or_observe_shipment(merchant_id, order)
    second_status, second_ref = operations.create_or_observe_shipment(merchant_id, order, simulate="timeout_after_mutation")
    assert first_status == "created"
    assert second_status == "existing"
    assert first_ref == second_ref
    assert len([shipment for shipment in store.list(Shipment, merchant_id) if shipment.order_id == order.id]) == 1

    logistics.push_event(first_ref, "NDR", 2, description="Customer unreachable")
    assert operations.ingest_tracking(merchant_id, first_ref) == "ndr"
    assert operations.request_ndr_reattempt(merchant_id, first_ref) == "accepted"

    with pytest.raises(TenantAccessError):
        store.get(Shipment, other_id, store.list(Shipment, merchant_id)[0].id)
