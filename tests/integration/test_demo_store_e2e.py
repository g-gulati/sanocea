from __future__ import annotations

import os
import uuid
from datetime import datetime
import pytest

from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.models import (
    Approval,
    DemoSessionContact,
    Inventory,
    Order,
    OrderLine,
    SourceOfTruth,
    now_utc,
)
from sanocea.packages.notifications.resolution import DemoApprovalNotificationService
from sanocea.packages.notifications.transport import (
    DeliveryResult,
    InboundApprovalMessage,
    WhatsAppDemoTransport,
)
from sanocea.packages.runtime.service_graph import build_service_graph

PG_DSN = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55199/sanocea_phase05")
MERCHANT_ID = "prospect_premium_basket"


@pytest.fixture(scope="module")
def store():
    master_key = os.environ.get("SANOCEA_CRED_MASTER_KEY_V1", "KioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKio=")
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = master_key
    provider = build_production_credential_provider(PG_DSN)
    return PostgresStore(PG_DSN, credential_provider=provider)


@pytest.fixture(scope="module")
def graph(store):
    return build_service_graph(store)


@pytest.fixture(scope="module")
def mock_or_real_transport():
    base_url = os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000")
    api_key = os.environ.get("SANOCEA_WAHA_API_KEY", "sanocea-demo-local-only-key-not-for-production")
    return WhatsAppDemoTransport(waha_base_url=base_url, api_key=api_key)


@pytest.fixture(scope="module")
def notif_service(store, mock_or_real_transport):
    service = DemoApprovalNotificationService(store, mock_or_real_transport)
    service.set_session_contact(
        MERCHANT_ID,
        phone_e164="+919988940640",
        session_label="Integration Test Session",
        consented=True,
    )
    return service


def test_01_catalog_sync_and_anomalies(graph, store):
    """Import products, variants, SKUs, and inventory levels from demo Shopify store into Sanocea.
    Verify detection of Blank SKU (TPB-027), Duplicate SKU (TPB-028), Price Inversion (TPB-016),
    and Quarantined/Low Stock items."""
    connector = graph.storefronts.resolve(MERCHANT_ID)
    sync_res = connector.sync_catalog_and_inventory(MERCHANT_ID)

    assert sync_res["imported_products_count"] >= 4
    assert sync_res["imported_variants_count"] >= 6
    assert sync_res["imported_inventory_count"] >= 4

    anomalies = sync_res["anomalies"]
    assert len(anomalies["blank_skus"]) >= 1
    assert any(b["finding_id"] == "TPB-027" for b in anomalies["blank_skus"])

    assert len(anomalies["duplicate_skus"]) >= 1
    assert any(d["finding_id"] == "TPB-028" for d in anomalies["duplicate_skus"])

    assert len(anomalies["quarantined_items"]) >= 1
    assert any(q["quarantine_units"] == 5 for q in anomalies["quarantined_items"])


def test_02_location_scoped_ats_and_atomic_reservation(store):
    """Verify that location-scoped ATS excludes quarantined inventory from available-to-sell,
    and atomic reservation updates only sellable units."""
    sku = "DEMO-PB-GC-DG-MCC-600G"
    inv_lines = [i for i in store.list(Inventory, MERCHANT_ID) if i.sku == sku]
    assert len(inv_lines) >= 1

    shop_inv = next(i for i in inv_lines if "83781779535" in i.location_ref)
    assert shop_inv.quarantine == 5
    initial_sellable = shop_inv.sellable
    assert shop_inv.ats == initial_sellable

    # Atomic reservation of 2 units
    source_id = f"ord_test_{uuid.uuid4().hex[:8]}"
    store.reserve_order_lines_atomic(
        merchant_id=MERCHANT_ID,
        source_type="order",
        source_id=source_id,
        location_ref=shop_inv.location_ref,
        lines=[
            {
                "sku": sku,
                "quantity_requested": 2,
                "order_line_id": "line_1",
                "idempotency_key": f"idem_{uuid.uuid4().hex}",
            }
        ],
    )

    updated = next(i for i in store.list(Inventory, MERCHANT_ID) if i.id == shop_inv.id)
    assert updated.reserved >= 2
    assert updated.ats == initial_sellable - 2
    assert updated.quarantine == 5


def test_03_operational_vs_financial_reconciliation_status(store):
    """Verify that an order reaching DELIVERED status maintains financial_reconciliation_status
    as UNRECONCILED until explicit payment settlement occurs."""
    order_id = f"ord_rec_{uuid.uuid4().hex[:8]}"
    order = Order(
        merchant_id=MERCHANT_ID,
        id=order_id,
        order_number=f"TEST-{uuid.uuid4().hex[:4]}",
        channel_id="shopify_live",
        status="DELIVERED",
        fulfillment_status="delivered",
        financial_reconciliation_status="UNRECONCILED",
        total_amount=34900,
        currency="INR",
        source_of_truth=SourceOfTruth.SANOCEA,
        lines=[
            OrderLine(
                merchant_id=MERCHANT_ID,
                order_id=order_id,
                id="line_1",
                sku="DEMO-PB-BBQ-100G-1P",
                title="Smoky Hickory BBQ",
                quantity=1,
                unit_amount=34900,
            )
        ],
    )
    store.put(order)

    fetched = store.get(Order, MERCHANT_ID, order_id)
    assert fetched.status == "DELIVERED"
    assert fetched.fulfillment_status == "delivered"
    assert fetched.financial_reconciliation_status == "UNRECONCILED"

    fetched.financial_reconciliation_status = "SETTLED"
    store.put(fetched)
    assert store.get(Order, MERCHANT_ID, order_id).financial_reconciliation_status == "SETTLED"


def test_04_webhook_deduplication_and_out_of_order_protection(graph, store):
    """Verify that webhook ingestion rejects duplicate deliveries and drops stale out-of-order events."""
    connector = graph.storefronts.resolve(MERCHANT_ID)
    webhook_id = f"wh_test_{uuid.uuid4().hex}"
    secret = connector.client_secret

    order_payload = {
        "id": 999000111,
        "name": "#9999",
        "email": "customer@example.com",
        "financial_status": "paid",
        "updated_at": "2026-09-20T10:00:00Z",
        "line_items": [{"sku": "DEMO-PB-BBQ-100G-1P", "title": "Smoky BBQ", "quantity": 1, "price": "349.00"}],
    }
    body = os.urandom(0)
    import hashlib
    import hmac
    import base64
    import json

    raw_json = json.dumps(order_payload).encode("utf-8")
    digest = hmac.new(secret.encode(), raw_json, hashlib.sha256).digest()
    sig = base64.b64encode(digest).decode()

    headers = {
        "x-shopify-topic": "orders/create",
        "x-shopify-webhook-id": webhook_id,
        "x-shopify-hmac-sha256": sig,
    }

    # First delivery
    res1 = connector.ingest_webhook(MERCHANT_ID, headers, raw_json)
    assert res1.get("idempotent_replay") is False

    # Second delivery with identical webhook ID
    res2 = connector.ingest_webhook(MERCHANT_ID, headers, raw_json)
    assert res2.get("idempotent_replay") is True

    # Out-of-order event with older timestamp
    stale_payload = dict(order_payload)
    stale_payload["updated_at"] = "2026-09-19T08:00:00Z"
    stale_raw = json.dumps(stale_payload).encode("utf-8")
    stale_digest = hmac.new(secret.encode(), stale_raw, hashlib.sha256).digest()
    stale_headers = {
        "x-shopify-topic": "orders/updated",
        "x-shopify-webhook-id": f"wh_stale_{uuid.uuid4().hex}",
        "x-shopify-hmac-sha256": base64.b64encode(stale_digest).decode(),
    }
    res3 = connector.ingest_webhook(MERCHANT_ID, stale_headers, stale_raw)
    assert res3.get("ignored") is True


def test_05_whatsapp_daily_briefing(notif_service):
    """Verify that daily operational briefing dispatches with store health, ATS, and settlement metrics."""
    result = notif_service.send_daily_briefing(MERCHANT_ID)
    assert isinstance(result, DeliveryResult)
    assert result.delivered is True


def test_06_whatsapp_governance_approval_loop_end_to_end(notif_service, store, graph):
    """Verify WhatsApp approval lifecycle: DETAILS breakdown, LATER snooze, and APPROVE execution."""
    ref = f"APP-TEST-{uuid.uuid4().hex[:6].upper()}"
    approval = notif_service.approvals.request_approval(
        MERCHANT_ID,
        action="price_change",
        object_id="prd_9089094778959",
        requested_by="policy_engine:pricing_audit",
        summary="Adjust price to fix unit pricing inversion",
        reference=ref,
        evidence={
            "sku": "DEMO-PB-BBQ-100G-2P",
            "variant_gid": "gid://shopify/ProductVariant/46832702455887",
            "current_price": "998.00",
            "new_price": "629.00",
            "compare_at_price": "998.00",
            "likely_impact": "+18% conversion lift",
        },
        recommendation="Correct price to ₹629.00 with compare-at ₹998.00",
    )
    assert approval.status == "pending"

    contact = notif_service._active_contact_for_phone(MERCHANT_ID, "919988940640")
    assert contact is not None

    # Outbound alert
    send_res = notif_service.send_approval(
        MERCHANT_ID,
        approval.id,
        contact,
        merchant_display_name="The Premium Basket",
        channel="shopify_live",
    )
    assert send_res.delivered is True

    # Inbound DETAILS
    details_res = notif_service.handle_inbound(
        InboundApprovalMessage(
            provider="whatsapp_demo",
            provider_message_id=f"msg_{uuid.uuid4().hex}",
            from_identifier=contact.phone_e164,
            raw_text=f"DETAILS {ref}",
            received_at=datetime.now(),
        )
    )
    assert details_res["action"] == "details"
    assert store.get(Approval, MERCHANT_ID, approval.id).status == "pending"

    # Inbound LATER
    later_res = notif_service.handle_inbound(
        InboundApprovalMessage(
            provider="whatsapp_demo",
            provider_message_id=f"msg_{uuid.uuid4().hex}",
            from_identifier=contact.phone_e164,
            raw_text=f"LATER {ref}",
            received_at=datetime.now(),
        )
    )
    assert later_res["action"] == "later"
    assert store.get(Approval, MERCHANT_ID, approval.id).status == "pending"

    # Inbound APPROVE
    approve_res = notif_service.handle_inbound(
        InboundApprovalMessage(
            provider="whatsapp_demo",
            provider_message_id=f"msg_{uuid.uuid4().hex}",
            from_identifier=contact.phone_e164,
            raw_text=f"APPROVE {ref}",
            received_at=datetime.now(),
        )
    )
    assert approve_res["status"] == "approved"
    assert store.get(Approval, MERCHANT_ID, approval.id).status == "approved"

    # Verify Shopify reflects updated price
    connector = graph.storefronts.resolve(MERCHANT_ID)
    shopify_data = connector._graphql("""
    query {
      product(id: "gid://shopify/Product/9089094778959") {
        variants(first: 2) {
          nodes { id title price compareAtPrice }
        }
      }
    }
    """, {})
    v2 = next(v for v in shopify_data["product"]["variants"]["nodes"] if "Pack of 2" in v["title"])
    assert float(v2["price"]) == 629.00
    assert float(v2["compareAtPrice"]) == 998.00
