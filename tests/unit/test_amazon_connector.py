from __future__ import annotations

import json

import pytest

from sanocea.connectors.amazon import AmazonConnector
from sanocea.connectors.amazon.auth import LWA_TOKEN_URL, MARKETPLACE_ID_INDIA, merchant_lwa_auth
from sanocea.connectors.amazon.connector import BASE_URL
from sanocea.packages.connector_sdk import (
    CapabilityUnconfirmed,
    MutationRequest,
    UnsupportedCapability,
)
from sanocea.packages.domain_contract.models import ExceptionRecord, Order
from sanocea.packages.domain_contract.store import TenantAccessError

# Step 9Q.3 - deterministic contract-level tests built from Amazon's OWN official SP-API model
# repository (github.com/amzn/selling-partner-api-models) and primary documentation, fetched and
# verified directly this step. No live Amazon credentials exist, so every test injects a FakeTransport
# returning FIXED, SYNTHETIC responses shaped like the real documented fields (AmazonOrderId,
# OrderStatus, processingStatus, restrictedDataToken, etc.) - this proves the connector's OWN request-
# building/response-parsing/mapping code, never Amazon's live behavior. See
# docs/connectors/amazon-certification.md - none of this constitutes REAL_ACCOUNT_CERTIFIED.


@pytest.fixture
def sanocea_store(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    return store


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self._queue: dict[tuple[str, str], list[tuple[int, dict, bytes]]] = {}

    def queue(self, method: str, path: str, status: int, body: dict | None = None, headers: dict | None = None) -> None:
        encoded = json.dumps(body).encode() if isinstance(body, dict) else b""
        path = path.split("?", 1)[0]
        self._queue.setdefault((method, path), []).append((status, headers or {}, encoded))

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
        self.calls.append((method, url, dict(headers), body))
        path = url.split("?", 1)[0]
        pending = self._queue.get((method, path))
        if not pending:
            raise AssertionError(f"FakeTransport: no queued response for {method} {path} (queued: {list(self._queue)})")
        return pending.pop(0)


def _auth_ok(transport: FakeTransport) -> None:
    transport.queue("POST", LWA_TOKEN_URL, 200, {"access_token": "tok-1", "token_type": "bearer", "expires_in": 3600, "refresh_token": "rt-1"})


def _connector(transport: FakeTransport, store) -> AmazonConnector:
    auth = merchant_lwa_auth(client_id="app-id", client_secret="app-secret", refresh_token="merchant-rt", transport=transport)
    return AmazonConnector(store, None, auth=auth, seller_id="SELLER1", transport=transport)


# --- 1: LWA refresh lifecycle -------------------------------------------------------------------------

def test_lwa_token_reused_across_calls(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {"sku": "SKU-1", "summaries": [{"itemName": "Widget", "status": ["BUYABLE"]}], "offers": [{"price": {"amount": 199.0}}]})
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {"sku": "SKU-1", "summaries": [{"itemName": "Widget", "status": ["BUYABLE"]}], "offers": [{"price": {"amount": 199.0}}]})
    connector = _connector(transport, sanocea_store)
    connector.fetch("mer_A", "product", "SKU-1")
    connector.fetch("mer_A", "product", "SKU-1")
    assert len([c for c in transport.calls if c[1] == LWA_TOKEN_URL]) == 1


def test_lwa_uses_bare_header_no_bearer_prefix(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {"sku": "SKU-1"})
    connector = _connector(transport, sanocea_store)
    connector.fetch("mer_A", "product", "SKU-1")
    listing_call = next(c for c in transport.calls if c[1].startswith(f"{BASE_URL}/listings"))
    assert listing_call[2]["x-amz-access-token"] == "tok-1"
    assert "Authorization" not in listing_call[2]


# --- 2: auth failure ---------------------------------------------------------------------------------

def test_auth_failure_after_repeated_401(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 401, {"errors": [{"code": "Unauthorized"}]})
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 401, {"errors": [{"code": "Unauthorized"}]})
    connector = _connector(transport, sanocea_store)
    with pytest.raises(PermissionError):
        connector.fetch("mer_A", "product", "SKU-1")


# --- 3: merchant/marketplace binding -----------------------------------------------------------------

def test_marketplace_ids_default_to_india_and_are_configurable(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [], "NextToken": None}})
    connector = _connector(transport, sanocea_store)
    connector.search("mer_A", "order", {})
    order_call = next(c for c in transport.calls if "/orders/v0/orders" in c[1])
    assert MARKETPLACE_ID_INDIA in order_call[1]

    transport2 = FakeTransport()
    _auth_ok(transport2)
    transport2.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [], "NextToken": None}})
    auth2 = merchant_lwa_auth(client_id="a", client_secret="b", refresh_token="c", transport=transport2)
    connector2 = AmazonConnector(sanocea_store, None, auth=auth2, seller_id="SELLER1", marketplace_ids=["A1VC38T7YXB528"], transport=transport2)
    connector2.search("mer_A", "order", {})
    order_call2 = next(c for c in transport2.calls if "/orders/v0/orders" in c[1])
    assert "A1VC38T7YXB528" in order_call2[1]


def test_credential_isolation_between_merchants(sanocea_store):
    """Two AmazonConnector instances (one per merchant, as service_graph.py's factory pattern already
    guarantees) never share tokens or seller_id."""
    transport_a = FakeTransport()
    _auth_ok(transport_a)
    auth_a = merchant_lwa_auth(client_id="a1", client_secret="s1", refresh_token="rt-merchant-A", transport=transport_a)
    connector_a = AmazonConnector(sanocea_store, None, auth=auth_a, seller_id="SELLER-A", transport=transport_a)

    transport_b = FakeTransport()
    transport_b.queue("POST", LWA_TOKEN_URL, 200, {"access_token": "tok-B", "expires_in": 3600})
    auth_b = merchant_lwa_auth(client_id="a2", client_secret="s2", refresh_token="rt-merchant-B", transport=transport_b)
    connector_b = AmazonConnector(sanocea_store, None, auth=auth_b, seller_id="SELLER-B", transport=transport_b)

    assert connector_a.seller_id != connector_b.seller_id
    assert connector_a.auth.refresh_token != connector_b.auth.refresh_token
    assert connector_a.transport is not connector_b.transport


# --- 4: listings read ----------------------------------------------------------------------------------

def test_listing_read_normalizes_shape(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {
        "sku": "SKU-1", "summaries": [{"itemName": "Widget", "status": ["BUYABLE", "DISCOVERABLE"]}], "offers": [{"price": {"amount": 199.0}}],
    })
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "product", "SKU-1")
    assert result["title"] == "Widget"
    assert result["sku"] == "SKU-1"
    assert result["price"] == "199.00"
    assert result["status"] == "active"


# --- 5: listing mutation payload + validation issues -------------------------------------------------

def test_put_listing_mutation_with_store(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("PUT", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {"sku": "SKU-1", "status": "ACCEPTED", "issues": []})
    connector = _connector(transport, sanocea_store)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="put_listing", object_type="Listing",
        payload={"sku": "SKU-1", "product_type": "PRODUCT", "attributes": {"item_name": [{"value": "Widget"}]}},
        idempotency_key="put:SKU-1",
    ))
    assert result.status == "accepted"
    assert result.payload["status"] == "ACCEPTED"


def test_put_listing_surfaces_validation_issues(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("PUT", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {
        "sku": "SKU-1", "status": "INVALID",
        "issues": [{"code": "90220", "message": "missing required attribute", "severity": "ERROR", "attributeNames": ["bullet_point"]}],
    })
    connector = _connector(transport, sanocea_store)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="put_listing", object_type="Listing",
        payload={"sku": "SKU-1", "product_type": "PRODUCT", "attributes": {}}, idempotency_key="put:SKU-1-bad",
    ))
    assert result.payload["status"] == "INVALID"
    assert result.payload["issues"][0]["severity"] == "ERROR"


# --- 6: inventory read/update, distinguishing FBA from merchant-fulfilled ----------------------------

def test_fba_inventory_read(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/fba/inventory/v1/summaries", 200, {"payload": {"inventorySummaries": [{"sellerSku": "SKU-1", "asin": "B000123", "totalQuantity": 10, "fulfillableQuantity": 8}], "pagination": {}}})
    connector = _connector(transport, sanocea_store)
    page = connector.search("mer_A", "fba_inventory", {})
    assert page.items[0]["sellerSku"] == "SKU-1"


def test_fba_inventory_write_is_unsupported_in_production(sanocea_store):
    """FBA Inventory API's write endpoints are explicitly documented sandbox-only - must never be
    marked SUPPORTED for a production connector."""
    transport = FakeTransport()
    connector = _connector(transport, sanocea_store)
    with pytest.raises(UnsupportedCapability):
        connector.describe_capabilities().require("fba_inventory_write")


def test_merchant_fulfilled_inventory_write_uses_listings_endpoint(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("PATCH", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {"sku": "SKU-1", "status": "ACCEPTED"})
    connector = _connector(transport, sanocea_store)
    connector.describe_capabilities().require("merchant_fulfilled_inventory_write")  # does not raise
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="patch_listing", object_type="Listing",
        payload={"sku": "SKU-1", "product_type": "PRODUCT", "patches": [{"op": "replace", "path": "/attributes/fulfillment_availability", "value": [{"quantity": 5}]}]},
        idempotency_key="patch-inv:SKU-1",
    ))
    assert result.status == "accepted"


# --- 7: order pagination + order item retrieval -------------------------------------------------------

def test_order_search_pagination_via_next_token(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [{"AmazonOrderId": "O1", "OrderStatus": "Unshipped"}], "NextToken": "page2token"}})
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [{"AmazonOrderId": "O2", "OrderStatus": "Shipped"}], "NextToken": None}})
    connector = _connector(transport, sanocea_store)
    page1 = connector.search("mer_A", "order", {})
    assert page1.next_cursor == "page2token"
    page2 = connector.search("mer_A", "order", {}, cursor=page1.next_cursor)
    assert page2.next_cursor is None
    assert page2.items[0]["AmazonOrderId"] == "O2"
    next_token_call = next(c for c in transport.calls if "NextToken=page2token" in c[1])
    assert next_token_call


def test_order_items_retrieval(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders/O1/orderItems", 200, {"payload": {"OrderItems": [{"ASIN": "B1", "SellerSKU": "SKU-1", "QuantityOrdered": 2}]}})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "order_items", "O1")
    assert result["payload"]["OrderItems"][0]["SellerSKU"] == "SKU-1"


# --- 8: unknown order status ---------------------------------------------------------------------------

def test_order_ingestion_creates_canonical_order(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [{
        "AmazonOrderId": "O-100", "OrderStatus": "Unshipped", "OrderTotal": {"Amount": "399.00", "CurrencyCode": "INR"},
    }], "NextToken": None}})
    connector = _connector(transport, sanocea_store)
    order_ids, next_cursor = connector.sync_orders("mer_A")
    assert next_cursor is None
    order = sanocea_store.get(Order, "mer_A", order_ids[0])
    assert order.order_number == "O-100"
    assert order.status == "PAID" and order.fulfillment_status == "pending"
    assert order.total_amount == 39900


def test_unknown_order_status_preserved_verbatim_and_flagged(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [{
        "AmazonOrderId": "O-101", "OrderStatus": "SomeFutureStatusNotYetDocumented", "OrderTotal": {"Amount": "0", "CurrencyCode": "INR"},
    }], "NextToken": None}})
    connector = _connector(transport, sanocea_store)
    order_ids, _ = connector.sync_orders("mer_A")
    order = sanocea_store.get(Order, "mer_A", order_ids[0])
    assert order.status == "SomeFutureStatusNotYetDocumented"
    exceptions = [e for e in sanocea_store.list(ExceptionRecord, "mer_A") if e.category == "unmapped_channel_status"]
    assert len(exceptions) == 1


def test_all_confirmed_order_statuses_map_without_exception(sanocea_store):
    from sanocea.connectors.amazon.mappings import ORDER_STATUS_MAP
    transport = FakeTransport()
    _auth_ok(transport)
    for i, status in enumerate(ORDER_STATUS_MAP):
        transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [{
            "AmazonOrderId": f"O-{i}", "OrderStatus": status, "OrderTotal": {"Amount": "0", "CurrencyCode": "INR"},
        }], "NextToken": None}})
    connector = _connector(transport, sanocea_store)
    for _ in ORDER_STATUS_MAP:
        connector.sync_orders("mer_A")
    exceptions = [e for e in sanocea_store.list(ExceptionRecord, "mer_A") if e.category == "unmapped_channel_status"]
    assert len(exceptions) == 0, "every currently-documented status must map without raising the unmapped-status exception"


# --- 9: fulfilment-mode distinction ---------------------------------------------------------------------

def test_confirm_shipment_mutation(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/orders/v0/orders/O-100/shipment", 200, {"payload": {}})
    connector = _connector(transport, sanocea_store)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="confirm_shipment", object_type="Order",
        payload={"order_id": "O-100", "package_detail": {"packageReferenceId": "1", "carrierCode": "OTHER", "trackingNumber": "T1", "shipDate": "2026-09-12T00:00:00Z", "shipMethod": "Standard", "packageDetail": {"packageReferenceId": "1"}}},
        idempotency_key="ship:O-100",
    ))
    assert result.status == "accepted"


def test_easy_ship_and_merchant_fulfillment_remain_unconfirmed(sanocea_store):
    """Fulfilment-mode distinction (Part 6): confirm_shipment (MFN via Orders API) is real and
    implemented; Easy Ship and the standalone Merchant Fulfillment API are model-family-confirmed only,
    not schema-verified, and must stay UNCONFIRMED rather than being guessed at."""
    transport = FakeTransport()
    connector = _connector(transport, sanocea_store)
    connector.describe_capabilities().require("confirm_shipment")  # does not raise
    with pytest.raises(CapabilityUnconfirmed):
        connector.describe_capabilities().require("easy_ship_scheduling")
    with pytest.raises(CapabilityUnconfirmed):
        connector.describe_capabilities().require("merchant_fulfillment_shipping")


# --- cancellation / returns: UNCONFIRMED, never assumed symmetric with Flipkart -----------------------

def test_cancellation_and_returns_are_unconfirmed_not_assumed_from_flipkart(sanocea_store):
    transport = FakeTransport()
    connector = _connector(transport, sanocea_store)
    with pytest.raises(CapabilityUnconfirmed):
        connector.describe_capabilities().require("cancellation")
    with pytest.raises(CapabilityUnconfirmed):
        connector.describe_capabilities().require("return_refund")


# --- 10: notification subscription ---------------------------------------------------------------------

def test_notification_subscription_lifecycle(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/notifications/v1/destinations", 200, {"payload": {"destinationId": "dest-1"}})
    transport.queue("POST", f"{BASE_URL}/notifications/v1/subscriptions/ORDER_CHANGE", 200, {"payload": {"subscriptionId": "sub-1", "destinationId": "dest-1"}})
    connector = _connector(transport, sanocea_store)
    dest = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="create_destination", object_type="Destination",
        payload={"name": "sanocea-sqs", "resource_specification": {"sqs": {"arn": "arn:aws:sqs:ap-south-1:123:queue"}}}, idempotency_key="dest:1",
    ))
    assert dest.external_ref == "dest-1"
    sub = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="create_subscription", object_type="Subscription",
        payload={"notification_type": "ORDER_CHANGE", "destination_id": "dest-1"}, idempotency_key="sub:1",
    ))
    assert sub.external_ref == "sub-1"


# --- 11: async feed/report lifecycle ----------------------------------------------------------------

def test_feed_submission_is_not_equivalent_to_applied_mutation(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/feeds/2021-06-30/documents", 200, {"feedDocumentId": "doc-1", "url": "https://example.test/upload"})
    transport.queue("POST", f"{BASE_URL}/feeds/2021-06-30/feeds", 200, {"feedId": "feed-1"})
    connector = _connector(transport, sanocea_store)
    doc = connector.execute_mutation(MutationRequest(merchant_id="mer_A", action="create_feed_document", object_type="Feed", payload={}, idempotency_key="doc:1"))
    feed = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="create_feed", object_type="Feed",
        payload={"feed_type": "JSON_LISTINGS_FEED", "input_feed_document_id": doc.external_ref}, idempotency_key="feed:1",
    ))
    assert feed.external_ref == "feed-1"
    # Submission alone must never be reported as a completed mutation - only get_feed_status() can say that.
    transport.queue("GET", f"{BASE_URL}/feeds/2021-06-30/feeds/feed-1", 200, {"processingStatus": "IN_PROGRESS"})
    status = connector.get_feed_status("feed-1")
    assert status.verdict == "STILL_UNKNOWN"
    assert status.connector_command_status == "executing"


def test_feed_status_transitions_to_confirmed_succeeded(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/feeds/2021-06-30/feeds/feed-2", 200, {"processingStatus": "DONE", "resultFeedDocumentId": "resdoc-1"})
    connector = _connector(transport, sanocea_store)
    status = connector.get_feed_status("feed-2")
    assert status.verdict == "CONFIRMED_SUCCEEDED"
    assert status.connector_command_status == "succeeded"
    assert status.document_id == "resdoc-1"


def test_feed_status_transitions_to_confirmed_not_applied(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/feeds/2021-06-30/feeds/feed-3", 200, {"processingStatus": "FATAL"})
    connector = _connector(transport, sanocea_store)
    status = connector.get_feed_status("feed-3")
    assert status.verdict == "CONFIRMED_NOT_APPLIED"
    assert status.connector_command_status == "failed"


def test_report_lifecycle(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/reports/2021-06-30/reports", 200, {"reportId": "report-1"})
    connector = _connector(transport, sanocea_store)
    report = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="create_report", object_type="Report",
        payload={"report_type": "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL"}, idempotency_key="report:1",
    ))
    assert report.external_ref == "report-1"
    transport.queue("GET", f"{BASE_URL}/reports/2021-06-30/reports/report-1", 200, {"processingStatus": "DONE", "reportDocumentId": "rdoc-1"})
    status = connector.get_report_status("report-1")
    assert status.verdict == "CONFIRMED_SUCCEEDED"
    assert status.document_id == "rdoc-1"


# --- 12: finance/settlement parsing --------------------------------------------------------------------

def test_settlement_ingestion_order_scoped(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/finances/v0/orders/O-100/financialEvents", 200, {"payload": {"FinancialEvents": {"ShipmentEventList": [{"AmazonOrderId": "O-100", "PostedDate": "2026-09-12T00:00:00Z"}]}}})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "financial_events", "O-100")
    assert result["payload"]["FinancialEvents"]["ShipmentEventList"][0]["AmazonOrderId"] == "O-100"


# --- 13: throttling / 429 retry / timeout / 5xx / malformed --------------------------------------------

def test_429_retry_then_succeeds(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 429, {}, headers={"Retry-After": "0"})
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {"sku": "SKU-1"})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "product", "SKU-1")
    assert result["sku"] == "SKU-1"


def test_429_retries_exhausted(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    for _ in range(3):
        transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 429, {}, headers={"Retry-After": "0"})
    connector = _connector(transport, sanocea_store)
    with pytest.raises(RuntimeError):
        connector.fetch("mer_A", "product", "SKU-1")


def test_5xx_retries_then_exhausts(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    for _ in range(3):
        transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 500, {"errors": []})
    connector = _connector(transport, sanocea_store)
    with pytest.raises(RuntimeError):
        connector.fetch("mer_A", "product", "SKU-1")


def test_malformed_payload_missing_required_field_raises(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    connector = _connector(transport, sanocea_store)
    with pytest.raises(KeyError):
        connector.execute_mutation(MutationRequest(
            merchant_id="mer_A", action="confirm_shipment", object_type="Order", payload={}, idempotency_key="bad:1",
        ))


def test_unsupported_operation_raises():
    transport = FakeTransport()
    from sanocea.packages.domain_contract.store import Phase0Store
    connector = _connector(transport, Phase0Store())
    with pytest.raises(UnsupportedCapability):
        connector.execute_mutation(MutationRequest(merchant_id="mer_A", action="not_a_real_action", object_type="X", payload={}, idempotency_key="x"))


# --- 14: tenant isolation ------------------------------------------------------------------------------

def test_tenant_isolation_on_order_lookup(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [{"AmazonOrderId": "O-9", "OrderStatus": "Pending", "OrderTotal": {"Amount": "0", "CurrencyCode": "INR"}}], "NextToken": None}})
    connector = _connector(transport, sanocea_store)
    order_ids, _ = connector.sync_orders("mer_A")
    with pytest.raises(TenantAccessError):
        sanocea_store.get(Order, "mer_B", order_ids[0])


# --- 15: no sensitive token/PII leakage -----------------------------------------------------------------

def test_no_secrets_or_tokens_leak_into_audit_or_exceptions(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [{"AmazonOrderId": "O-secret-check", "OrderStatus": "WeirdUnknownStatus", "OrderTotal": {"Amount": "0", "CurrencyCode": "INR"}}], "NextToken": None}})
    connector = _connector(transport, sanocea_store)
    connector.sync_orders("mer_A")
    audit_dump = json.dumps([e.model_dump(mode="json") for e in sanocea_store.list_audit("mer_A")])
    exception_dump = json.dumps([e.model_dump(mode="json") for e in sanocea_store.list(ExceptionRecord, "mer_A")])
    assert "tok-1" not in audit_dump and "tok-1" not in exception_dump
    assert "app-secret" not in audit_dump and "app-secret" not in exception_dump


def test_connector_health_never_exposes_the_token(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/listings/2021-08-01/items/SELLER1/SKU-1", 200, {"sku": "SKU-1"})
    connector = _connector(transport, sanocea_store)
    connector.fetch("mer_A", "product", "SKU-1")
    health = connector.connector_health()
    assert "tok-1" not in json.dumps(health)
    assert health["authenticated"] is True


# --- RDT (restricted data) ------------------------------------------------------------------------------

def test_restricted_data_token_used_for_buyer_info(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/tokens/2021-03-01/restrictedDataToken", 200, {"restrictedDataToken": "rdt-1", "expiresIn": 3600})
    transport.queue("GET", f"{BASE_URL}/orders/v0/orders/O-1/buyerInfo", 200, {"payload": {"BuyerEmail": "buyer@example.test"}})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "order_buyer_info", "O-1")
    assert result["payload"]["BuyerEmail"] == "buyer@example.test"
    buyer_info_call = next(c for c in transport.calls if "buyerInfo" in c[1] and c[0] == "GET")
    assert buyer_info_call[2]["x-amz-access-token"] == "rdt-1", "the RDT, not the main access token, must be used for the restricted call"


def test_rdt_rejects_unconfirmed_data_elements():
    from sanocea.connectors.amazon.auth import RestrictedDataTokenProvider
    transport = FakeTransport()
    provider = RestrictedDataTokenProvider(host=BASE_URL, main_auth=merchant_lwa_auth(client_id="a", client_secret="b", refresh_token="c", transport=transport), transport=transport)
    with pytest.raises(ValueError):
        provider.request(method="GET", path="/orders/v0/orders/O-1/somethingElse", data_elements=["not_a_real_data_element"])
