from __future__ import annotations

import json

import pytest

from sanocea.tests.unit.test_phase0_acceptance import chatwoot_headers, shopify_headers, shopify_order_payload
from sanocea.packages.domain_contract.models import Order


def test_invalid_shopify_signature_rejected_and_no_business_mutation(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload()).encode()
    with pytest.raises(PermissionError):
        shopify.ingest_webhook("mer_A", shopify_headers(body, "wrong"), body)
    assert store.list_audit("mer_A") == []


def test_malformed_webhook_rejected(phase0):
    _store, _workflow, shopify, _chatwoot = phase0
    body = b"{not-json"
    with pytest.raises(Exception):
        shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A"), body)


def test_connector_error_mapping_for_429_and_500(phase0):
    _store, _workflow, shopify, _chatwoot = phase0
    mapped_429 = shopify.map_error(TimeoutError("external API 429"))
    mapped_500 = shopify.map_error(RuntimeError("external API 500"))
    assert mapped_429["connector"] == "shopify"
    assert "429" in mapped_429["message"]
    assert "500" in mapped_500["message"]


def test_raw_payload_headers_redact_authentication_material(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload()).encode()
    shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A", "redact-wh"), body)
    order = store.list(Order, "mer_A")[0]
    raw = store.get_raw_payload("mer_A", order.sync.raw_payload_ref)
    assert raw.headers["x-shopify-hmac-sha256"] == "[redacted]"
    assert raw.headers["x-shopify-webhook-id"] == "redact-wh"
