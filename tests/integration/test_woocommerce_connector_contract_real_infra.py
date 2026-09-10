from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest

from sanocea.connectors.woocommerce import WooCommerceConnector
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.store import Phase0Store

"""Real-infra tests for the WooCommerce connector's completed minimum contract: page-based pagination,
poll_changes/incremental sync, register_webhooks, and variable products/variations. All run against
the ACTUAL local WooCommerce instance (infra/woocommerce-dev, via `wp-env start`) - never faked.
Skipped automatically when that instance isn't reachable, exactly like every other real-infra test in
this suite is skipped when its backing infrastructure isn't up.
"""

WC_BASE_URL = os.environ.get("SANOCEA_WOOCOMMERCE_BASE_URL", "http://localhost:8890")
WC_CONSUMER_KEY = os.environ.get("SANOCEA_WOOCOMMERCE_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.environ.get("SANOCEA_WOOCOMMERCE_CONSUMER_SECRET")

pytestmark = pytest.mark.skipif(
    not (WC_CONSUMER_KEY and WC_CONSUMER_SECRET),
    reason="requires a real local WooCommerce instance - set SANOCEA_WOOCOMMERCE_CONSUMER_KEY/_SECRET (see infra/woocommerce-dev)",
)


@pytest.fixture()
def connector():
    return WooCommerceConnector(
        Phase0Store(), workflow=None, base_url=WC_BASE_URL,
        consumer_key=WC_CONSUMER_KEY, consumer_secret=WC_CONSUMER_SECRET,
        webhook_delivery_base_url="http://host.docker.internal:8099",
    )


def test_pagination_returns_items_and_a_real_next_cursor_from_wp_total_pages_header(connector):
    suffix = uuid4().hex[:6]
    created_ids = []
    for i in range(3):
        result = connector.execute_mutation(MutationRequest(
            merchant_id="m1", action="create_product", object_type="ProductDraft",
            payload={"title": f"Pagination Test {suffix}-{i}", "sku": f"PAGE-{suffix}-{i}", "price": "10.00"},
            idempotency_key=f"page-test-{suffix}-{i}",
        ))
        created_ids.append(result.external_ref)

    page1 = connector.search("m1", "product", {"per_page": 1}, cursor=None)
    assert len(page1.items) == 1
    assert page1.next_cursor is not None, "with per_page=1 and a real catalogue, there must be a next page"

    page2 = connector.search("m1", "product", {"per_page": 1}, cursor=page1.next_cursor)
    assert len(page2.items) == 1
    assert page1.items[0]["id"] != page2.items[0]["id"], "consecutive pages must return DIFFERENT items"


def test_poll_changes_without_a_cursor_lists_the_real_catalogue(connector):
    """The unconditional (cursor=None) path - no modified_after param at all - real items, a real
    next_cursor derived from real date_modified_gmt values."""
    result = connector.poll_changes("m1", cursor=None)
    assert isinstance(result.items, list)
    if result.items:
        assert result.next_cursor is not None


def test_poll_changes_with_a_modified_after_cursor(connector):
    """FIXED (multi-platform connector hardening, closure item 1): this used to fail with an OAuth1
    'Invalid signature' 401 whenever the modified_after cursor (an ISO8601 timestamp, which contains
    ':') was included as a query parameter. Root cause was a missing second percent-encoding pass in
    connectors/woocommerce/oauth1.py's signature base string construction (RFC 5849 3.4.1.1) - generic
    to ANY reserved character in a parameter value, not colon-specific; see
    tests/integration/test_woocommerce_oauth1_signing.py for the full reserved-character regression
    coverage. Fixed, and this is now a normal passing test against the real WooCommerce instance."""
    suffix = uuid4().hex[:6]
    baseline = connector.poll_changes("m1", cursor=None)
    baseline_cursor = baseline.next_cursor

    time.sleep(2)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="m1", action="create_product", object_type="ProductDraft",
        payload={"title": f"Poll Changes Test {suffix}", "sku": f"POLL-{suffix}", "price": "20.00"},
        idempotency_key=f"poll-test-{suffix}",
    ))
    new_product_id = int(result.external_ref)

    changed = connector.poll_changes("m1", cursor=baseline_cursor)
    changed_ids = {item["id"] for item in changed.items}
    assert new_product_id in changed_ids, "poll_changes must surface a product modified after the given cursor"
    assert changed.next_cursor is not None and changed.next_cursor >= baseline_cursor


def test_register_webhooks_creates_real_webhook_subscriptions(connector):
    merchant_id = f"wh_test_{uuid4().hex[:8]}"
    connector.store.set_credential_ref(merchant_id, "woocommerce_webhook_secret", "test-secret-for-register-webhooks")
    mutation_result = connector.register_webhooks(merchant_id, f"{merchant_id}_woocommerce")
    assert mutation_result.status == "accepted"
    webhook_ids = mutation_result.payload["webhook_ids"]
    assert len(webhook_ids) == 2  # order.created + order.updated
    # Verify against the REAL WooCommerce API, not just the connector's own return value.
    for webhook_id in webhook_ids:
        raw = connector._request("GET", f"webhooks/{webhook_id}")
        assert raw["status"] == "active"
        assert merchant_id in raw["delivery_url"]


def test_variable_product_creates_parent_and_variations_with_real_readback(connector):
    suffix = uuid4().hex[:6]
    result = connector.execute_mutation(MutationRequest(
        merchant_id="m1", action="create_variable_product", object_type="ProductDraft",
        payload={
            "title": f"Variable Test Shirt {suffix}",
            "attribute_name": "Size",
            "variants": [
                {"option": "Small", "sku": f"VAR-{suffix}-S", "price": "499.00", "quantity": 5},
                {"option": "Large", "sku": f"VAR-{suffix}-L", "price": "549.00", "quantity": 3},
            ],
        },
        idempotency_key=f"variable-test-{suffix}",
    ))
    assert result.status == "accepted"
    parent_id = result.external_ref
    variations = result.payload["variations"]
    assert len(variations) == 2
    assert {v["option"] for v in variations} == {"Small", "Large"}

    small = next(v for v in variations if v["option"] == "Small")
    fetched = connector.fetch("m1", "product_variation", f"{parent_id}:{small['id']}")
    assert fetched["sku"] == f"VAR-{suffix}-S"
    assert fetched["price"] == "499.00"
    assert fetched["available"] == 5
    assert fetched["option"] == "Small"

    # The parent itself must be real and of type "variable" - a genuinely different resource shape
    # from a simple product, not something normalized away.
    parent_raw = connector._request("GET", f"products/{parent_id}")
    assert parent_raw["type"] == "variable"
    assert len(parent_raw["variations"]) == 2
