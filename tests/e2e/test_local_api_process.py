from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from uuid import uuid4

import httpx
import pytest


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_API_URL"),
    reason="requires running Sanocea API process in SANOCEA_API_URL",
)


def test_local_api_process_shopify_and_chatwoot_flow():
    base_url = os.environ["SANOCEA_API_URL"].rstrip("/")
    order_number = str(94000 + int(uuid4().hex[:4], 16) % 1000)
    webhook_id = f"e2e-wh-{uuid4().hex}"
    payload = {
        "id": int(order_number),
        "order_number": order_number,
        "email": "e2e-local@example.com",
        "financial_status": "paid",
        "total_price": "799.00",
        "currency": "INR",
        "updated_sequence": 3,
        "line_items": [{"title": "E2E local order", "sku": "E2E", "quantity": 1, "price": "799.00"}],
    }
    body = json.dumps(payload).encode()
    sig = base64.b64encode(hmac.new(b"shopify_secret_A", body, hashlib.sha256).digest()).decode()
    headers = {
        "X-Shopify-Hmac-Sha256": sig,
        "X-Shopify-Webhook-Id": webhook_id,
        "X-Shopify-Topic": "orders/paid",
        "Content-Type": "application/json",
    }
    first = httpx.post(f"{base_url}/webhooks/shopify/mer_A", content=body, headers=headers, timeout=30)
    second = httpx.post(f"{base_url}/webhooks/shopify/mer_A", content=body, headers=headers, timeout=30)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    assert first.json()["order_id"] == second.json()["order_id"]

    support_payload = {
        "id": int(order_number) + 100000,
        "contact": {"email": "e2e-local@example.com", "name": "E2E Buyer"},
        "inbox": {"id": "chn_A_chatwoot"},
        "messages": [{"content": f"Where is order #{order_number}?"}],
    }
    support_body = json.dumps(support_payload).encode()
    ts = "1700000000"
    support_sig = "sha256=" + hmac.new(
        b"chatwoot_secret_A", ts.encode() + b"." + support_body, hashlib.sha256
    ).hexdigest()
    support = httpx.post(
        f"{base_url}/webhooks/chatwoot/mer_A",
        content=support_body,
        headers={
            "X-Chatwoot-Timestamp": ts,
            "X-Chatwoot-Signature": support_sig,
            "X-Chatwoot-Delivery": f"e2e-cw-{uuid4().hex}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    assert support.status_code == 200
    assert support.json()["order_id"] == first.json()["order_id"]
    assert support.json()["intent"] == "where_is_order"

