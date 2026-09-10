from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os

os.environ.setdefault("SANOCEA_USE_IN_MEMORY_STORE", "1")  # apps.api.app builds a module-level `app`
# at import time (the real uvicorn ASGI entry point) - this test never uses that instance (each test
# builds its own via create_app(store)), but the import itself must not require SANOCEA_PG_DSN.

import pytest
from fastapi.testclient import TestClient

from sanocea.apps.api.app import create_app
from sanocea.packages.domain_contract.models import Inventory
from sanocea.packages.domain_contract.store import Phase0Store


@pytest.fixture
def stack():
    """Boots the REAL FastAPI app (real routing, real auth dependencies, real middleware) against an
    in-memory store. Every test in this file goes through client.get/post - never a direct service call
    - this is what proves the runtime wiring, not just the underlying domain service."""
    store = Phase0Store()
    app = create_app(store)
    client = TestClient(app)
    service_key_id, service_key = store.create_api_key(merchant_id=None, role="service", label="bootstrap")
    return store, client, service_key


def _onboard(client, service_key, merchant_id="mer_c", webhook_secret="whsec_test"):
    resp = client.post(
        "/admin/merchants",
        headers={"Authorization": f"Bearer {service_key}"},
        json={
            "merchant_id": merchant_id,
            "display_name": "Integrated Test Merchant",
            "config": {
                "currency": "INR",
                "policy": {"refund": {"automatic_limit": 100000, "above_limit": "REQUIRE_APPROVAL"}},
                "finance": {"tolerances": {"default": 0}, "expected_charges": {}},
                "procurement": {"spending": {"auto_approve_limit": 1000000, "above_limit": "REQUIRE_APPROVAL"}},
            },
            "credentials": {"shopify_webhook_secret": webhook_secret},
            "suppliers": [{"name": "Acme", "default_lead_time_days": 5, "offers": [
                {"sku": "SKU-1", "supplier_sku": "ACME-1", "cost": 500, "currency": "INR", "moq": 1, "pack_quantity": 1, "lead_time_days": 5},
            ]}],
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _sign(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


# --- Auth: cannot choose another merchant_id and gain access ------------------------------------------


def test_health_requires_no_auth(stack):
    _, client, _ = stack
    assert client.get("/health").status_code == 200


def test_operator_route_requires_bearer_token(stack):
    _, client, _ = stack
    resp = client.get("/merchants/mer_c/orders")
    assert resp.status_code == 401


def test_operator_key_cannot_access_a_different_merchant(stack):
    store, client, service_key = stack
    result = _onboard(client, service_key, merchant_id="mer_c")
    other = _onboard(client, service_key, merchant_id="mer_other")
    # mer_c's own key works for mer_c...
    ok = client.get("/merchants/mer_c/orders", headers={"Authorization": f"Bearer {result['operator_api_key']}"})
    assert ok.status_code == 200
    # ...but must be REJECTED for mer_other, purely by changing the URL.
    forbidden = client.get("/merchants/mer_other/orders", headers={"Authorization": f"Bearer {result['operator_api_key']}"})
    assert forbidden.status_code == 403
    assert other["operator_api_key"] != result["operator_api_key"]


def test_service_key_cannot_call_admin_with_operator_role_key(stack):
    store, client, service_key = stack
    result = _onboard(client, service_key, merchant_id="mer_c")
    resp = client.post("/admin/api-keys", headers={"Authorization": f"Bearer {result['operator_api_key']}"}, json={"merchant_id": "mer_c", "role": "operator"})
    assert resp.status_code == 403


# --- Onboarding v2: config + credentials + supplier mappings, validated ------------------------------


def test_onboarding_v2_covers_finance_and_procurement_config(stack):
    store, client, service_key = stack
    result = _onboard(client, service_key)
    assert "finance" in result["config_sections_set"]
    assert "procurement" in result["config_sections_set"]
    assert result["suppliers_created"] == 1
    assert result["supplier_offers_created"] == 1
    assert result["credentials_set"] == ["shopify_webhook_secret"]


def test_onboarding_v2_rejects_invalid_config_before_activation(stack):
    store, client, service_key = stack
    resp = client.post(
        "/admin/merchants",
        headers={"Authorization": f"Bearer {service_key}"},
        json={"merchant_id": "mer_bad", "display_name": "Bad", "config": {"currency": "NOTACURRENCY", "procurement": {"spending": {"auto_approve_limit": "not-an-int"}}}},
    )
    assert resp.status_code == 422
    from sanocea.packages.domain_contract.models import Merchant
    assert store.list(Merchant, "mer_bad") == []


# --- Webhook: signature verification + idempotency + order path to inventory reservation -------------


def test_invalid_webhook_signature_is_rejected_before_mutation(stack):
    store, client, service_key = stack
    _onboard(client, service_key, webhook_secret="whsec_correct")
    body = json.dumps({"id": 999, "order_number": "X-1", "email": "a@b.com", "financial_status": "paid", "total_price": "10.00", "currency": "INR", "line_items": []}).encode()
    resp = client.post("/webhooks/shopify/mer_c", content=body, headers={"x-shopify-hmac-sha256": "wrong", "x-shopify-topic": "orders/create"})
    assert resp.status_code == 401
    from sanocea.packages.domain_contract.models import Order
    assert store.list(Order, "mer_c") == []


def test_valid_webhook_reserves_inventory_through_orchestrator(stack):
    store, client, service_key = stack
    onboarding = _onboard(client, service_key, webhook_secret="whsec_correct")
    store.put(Inventory(merchant_id="mer_c", sku="SKU-1", location_ref="default", quantity=10, available=10))

    payload = {
        "id": 12345, "order_number": "1001", "email": "buyer@example.com", "financial_status": "paid",
        "total_price": "500.00", "currency": "INR", "updated_sequence": 1,
        "line_items": [{"sku": "SKU-1", "title": "Test Item", "quantity": 3, "price": "166.66"}],
    }
    body = json.dumps(payload).encode()
    headers = {"x-shopify-hmac-sha256": _sign("whsec_correct", body), "x-shopify-topic": "orders/create", "x-shopify-webhook-id": "wh-1"}
    resp = client.post("/webhooks/shopify/mer_c", content=body, headers=headers)
    assert resp.status_code == 200

    op_key = onboarding["operator_api_key"]
    orders = client.get("/merchants/mer_c/orders", headers={"Authorization": f"Bearer {op_key}"}).json()
    assert len(orders) == 1
    inv = client.get("/merchants/mer_c/inventory", headers={"Authorization": f"Bearer {op_key}"}).json()
    reserved_row = next(i for i in inv if i["sku"] == "SKU-1")
    assert reserved_row["reserved"] == 3, "order webhook must have driven real inventory reservation, not just workflow bookkeeping"
    assert reserved_row["available"] == 7


def test_duplicate_webhook_produces_one_business_effect(stack):
    store, client, service_key = stack
    onboarding = _onboard(client, service_key, webhook_secret="whsec_correct")
    store.put(Inventory(merchant_id="mer_c", sku="SKU-1", location_ref="default", quantity=10, available=10))
    payload = {"id": 555, "order_number": "1002", "email": "b@example.com", "financial_status": "paid", "total_price": "500.00", "currency": "INR", "updated_sequence": 1, "line_items": [{"sku": "SKU-1", "title": "Item", "quantity": 2, "price": "250.00"}]}
    body = json.dumps(payload).encode()
    headers = {"x-shopify-hmac-sha256": _sign("whsec_correct", body), "x-shopify-topic": "orders/create", "x-shopify-webhook-id": "wh-dup"}
    client.post("/webhooks/shopify/mer_c", content=body, headers=headers)
    client.post("/webhooks/shopify/mer_c", content=body, headers=headers)  # exact retransmission

    op_key = onboarding["operator_api_key"]
    orders = client.get("/merchants/mer_c/orders", headers={"Authorization": f"Bearer {op_key}"}).json()
    assert len(orders) == 1
    inv = client.get("/merchants/mer_c/inventory", headers={"Authorization": f"Bearer {op_key}"}).json()
    reserved_row = next(i for i in inv if i["sku"] == "SKU-1")
    assert reserved_row["reserved"] == 2, "duplicate webhook must not double-reserve"


# --- Refund canonical-truth contradiction cannot silently occur ---------------------------------------


def test_refund_full_state_surfaces_both_operational_and_financial_dimensions(stack):
    store, client, service_key = stack
    onboarding = _onboard(client, service_key, webhook_secret="whsec_correct")
    op_key = onboarding["operator_api_key"]
    store.put(Inventory(merchant_id="mer_c", sku="SKU-1", location_ref="default", quantity=10, available=10))
    payload = {"id": 777, "order_number": "1003", "email": "c@example.com", "financial_status": "paid", "total_price": "1000.00", "currency": "INR", "updated_sequence": 1, "line_items": [{"sku": "SKU-1", "title": "Item", "quantity": 1, "price": "1000.00"}]}
    body = json.dumps(payload).encode()
    headers = {"x-shopify-hmac-sha256": _sign("whsec_correct", body), "x-shopify-topic": "orders/create", "x-shopify-webhook-id": "wh-refund-order"}
    client.post("/webhooks/shopify/mer_c", content=body, headers=headers)
    order = client.get("/merchants/mer_c/orders", headers={"Authorization": f"Bearer {op_key}"}).json()[0]

    refund = client.post("/merchants/mer_c/refunds", headers={"Authorization": f"Bearer {op_key}"}, json={"order_id": order["id"], "amount": 100000}).json()
    full = client.get(f"/merchants/mer_c/refunds/{refund['id']}", headers={"Authorization": f"Bearer {op_key}"}).json()
    assert full["operational_status"] in {"permitted", "approval_required"}
    assert full["financial_reconciliation_status"] == "pending"
    assert full["requires_attention"] is False


# --- Procurement through the running app ---------------------------------------------------------------


def test_procurement_lifecycle_through_api(stack):
    store, client, service_key = stack
    onboarding = _onboard(client, service_key, webhook_secret="whsec_correct")
    op_key = onboarding["operator_api_key"]

    from sanocea.packages.domain_contract.models import Supplier
    supplier = store.list(Supplier, "mer_c")[0]

    po = client.post(
        "/merchants/mer_c/procurement/purchase-orders", headers={"Authorization": f"Bearer {op_key}"},
        json={"supplier_id": supplier.id, "lines": [{"sku": "SKU-1", "quantity_ordered": 20}]},
    ).json()
    assert po["status"] == "AUTO_APPROVED"

    submitted = client.post(f"/merchants/mer_c/procurement/purchase-orders/{po['id']}/submit", headers={"Authorization": f"Bearer {op_key}"}, json={}).json()
    assert submitted["status"] == "SUBMITTED"

    ack = client.post(
        f"/merchants/mer_c/procurement/purchase-orders/{po['id']}/acknowledgements", headers={"Authorization": f"Bearer {op_key}"},
        json={"external_ref": "ack-1", "sequence": 1, "status": "confirmed", "lines": [{"sku": "SKU-1", "quantity_confirmed": 20, "unit_cost": 500}]},
    )
    assert ack.status_code == 200

    pos_after = client.get("/merchants/mer_c/purchase-orders", headers={"Authorization": f"Bearer {op_key}"}).json()
    assert pos_after[0]["status"] == "CONFIRMED"


def test_operator_summary_answers_what_needs_attention(stack):
    store, client, service_key = stack
    onboarding = _onboard(client, service_key)
    op_key = onboarding["operator_api_key"]
    summary = client.get("/merchants/mer_c/operator/summary", headers={"Authorization": f"Bearer {op_key}"}).json()
    assert set(summary.keys()) >= {"open_exceptions", "open_approvals", "uncertain_connector_commands", "failed_connector_commands", "refunds_with_financial_discrepancy", "needs_attention"}
