from __future__ import annotations

import json

import pytest

from sanocea.connectors.flipkart import FlipkartConnector
from sanocea.connectors.flipkart.auth import merchant_authorization_code_auth
from sanocea.connectors.flipkart.connector import BASE_URL
from sanocea.packages.connector_sdk import (
    CapabilityAccessRequired,
    CapabilityUnconfirmed,
    MutationRequest,
    UnsupportedCapability,
)
from sanocea.packages.domain_contract.models import ExceptionRecord, Order
from sanocea.packages.domain_contract.store import TenantAccessError

# Step 9Q.2 - deterministic contract-level tests built from Flipkart's OWN documented request/response
# shapes (fetched directly during this step: https://seller.flipkart.com/api-docs/FMSAPI.html,
# order-api-docs/OMAPIRef.html, order-api-docs/NotifIntro.html). No live credentials exist, so every test
# here injects a FakeTransport returning FIXED, SYNTHETIC responses shaped like the real documented
# fields (shipmentId, orderItems, sellingPrice, processingStatus, etc.) - this proves the connector's OWN
# request-building/response-parsing/mapping code, never Flipkart's live behavior. See
# docs/connectors/flipkart-certification.md - none of this constitutes LIVE VERIFIED or CERTIFIED.

TOKEN_URL = f"{BASE_URL}/oauth-service/oauth/token"


@pytest.fixture
def sanocea_store(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    return store


class FakeTransport:
    """Routes (method, path) -> a queue of canned (status, headers, body) responses, ignoring query
    string for matching but recording every call (including its query string) for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self._queue: dict[tuple[str, str], list[tuple[int, dict, bytes]]] = {}

    def queue(self, method: str, path: str, status: int, body: dict | bytes | None = None, headers: dict | None = None) -> None:
        encoded = json.dumps(body).encode() if isinstance(body, dict) else (body or b"")
        path = path.split("?", 1)[0]
        self._queue.setdefault((method, path), []).append((status, headers or {}, encoded))

    def __call__(self, method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
        self.calls.append((method, url, dict(headers), body))
        path = url.split("?", 1)[0]
        key = (method, path)
        pending = self._queue.get(key)
        if not pending:
            raise AssertionError(f"FakeTransport: no queued response for {method} {path} (queued keys: {list(self._queue)})")
        return pending.pop(0)


def _auth_ok(transport: FakeTransport, *, expires_in: int = 3600) -> None:
    transport.queue("POST", TOKEN_URL, 200, {"access_token": "tok-1", "token_type": "bearer", "expires_in": expires_in, "refresh_token": "rt-1"})


def _connector(transport: FakeTransport, store) -> FlipkartConnector:
    auth = merchant_authorization_code_auth(client_id="partner-id", client_secret="partner-secret", refresh_token="rt-0", transport=transport)
    return FlipkartConnector(store, None, auth=auth, transport=transport)


# --- 1: authentication lifecycle -------------------------------------------------------------------

def test_authentication_lifecycle_fetches_and_reuses_token(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "title": "Widget", "sellingPrice": 199.0, "status": "ACTIVE"})
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "title": "Widget", "sellingPrice": 199.0, "status": "ACTIVE"})
    connector = _connector(transport, sanocea_store)
    connector.fetch("mer_A", "product", "SKU-1")
    connector.fetch("mer_A", "product", "SKU-1")
    token_calls = [c for c in transport.calls if c[1] == TOKEN_URL]
    assert len(token_calls) == 1, "a still-valid token must be reused, not re-fetched on every call"


def test_authentication_forces_reauth_once_on_401_then_succeeds(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 401, {"error": "expired"})
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "title": "Widget", "sellingPrice": 199.0, "status": "ACTIVE"})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "product", "SKU-1")
    assert result["sku"] == "SKU-1"
    assert len([c for c in transport.calls if c[1] == TOKEN_URL]) == 2


def test_authentication_permission_error_after_repeated_401(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 401, {"error": "revoked"})
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 401, {"error": "revoked"})
    connector = _connector(transport, sanocea_store)
    with pytest.raises(PermissionError):
        connector.fetch("mer_A", "product", "SKU-1")


# --- 2: pagination -----------------------------------------------------------------------------------

def test_search_pagination_follows_next_page_url(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    next_url = f"{BASE_URL}/sellers/v3/shipments/filter?cursor=page2"
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, {
        "shipments": [{"shipmentId": "S1", "status": "APPROVED", "orderId": "O1", "orderItems": []}],
        "nextPageUrl": next_url,
    })
    transport.queue("GET", next_url, 200, {"shipments": [{"shipmentId": "S2", "status": "APPROVED", "orderId": "O2", "orderItems": []}], "nextPageUrl": None})
    connector = _connector(transport, sanocea_store)
    page1 = connector.search("mer_A", "shipment", {})
    assert page1.next_cursor == next_url
    assert page1.items[0]["shipmentId"] == "S1"
    page2 = connector.search("mer_A", "shipment", {}, cursor=page1.next_cursor)
    assert page2.next_cursor is None
    assert page2.items[0]["shipmentId"] == "S2"


# --- 3: listing read -----------------------------------------------------------------------------------

def test_listing_read_normalizes_shape(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "title": "Widget", "sellingPrice": 199.0, "status": "ACTIVE"})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "product", "SKU-1")
    assert result == {"title": "Widget", "sku": "SKU-1", "price": "199.00", "status": "active", "raw": {"skuId": "SKU-1", "title": "Widget", "sellingPrice": 199.0, "status": "ACTIVE"}}
    listing_calls = [c for c in transport.calls if c[1].startswith(f"{BASE_URL}/sellers/v3/listings")]
    assert "skuId=SKU-1" in listing_calls[0][1], "must use a real query parameter, not a smuggled header"


# --- 4: inventory read/update ----------------------------------------------------------------------------

def test_inventory_read(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "availableUnits": 12})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "inventory", "SKU-1")
    assert result == {"sku": "SKU-1", "available": 12}


def test_inventory_update_mutation(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "availableUnits": 5})
    connector = _connector(transport, sanocea_store)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="update_inventory", object_type="Listing",
        payload={"sku": "SKU-1", "quantity": 5}, idempotency_key="inv:SKU-1:5",
    ))
    assert result.status == "accepted"
    assert result.external_ref == "SKU-1"


# --- 5: order ingestion ---------------------------------------------------------------------------------

def test_order_ingestion_creates_canonical_order(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, {
        "shipments": [{
            "shipmentId": "SHIP-1", "status": "APPROVED", "orderId": "ORD-1",
            "orderItems": [{"sku": "SKU-1", "title": "Widget", "quantity": 2, "sellingPrice": 199.0}],
        }],
        "nextPageUrl": None,
    })
    connector = _connector(transport, sanocea_store)
    order_ids, next_cursor = connector.sync_orders("mer_A")
    assert next_cursor is None
    assert len(order_ids) == 1
    order = sanocea_store.get(Order, "mer_A", order_ids[0])
    assert order.order_number == "ORD-1"
    assert order.total_amount == 2 * 199 * 100
    flipkart_refs = [r for r in order.external_refs if r.system == "flipkart"]
    assert {r.entity_type for r in flipkart_refs} == {"order", "shipment"}


def test_order_ingestion_is_idempotent_on_replay(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    shipment_response = {
        "shipments": [{"shipmentId": "SHIP-2", "status": "APPROVED", "orderId": "ORD-2", "orderItems": [{"sku": "SKU-1", "title": "Widget", "quantity": 1, "sellingPrice": 100.0}]}],
        "nextPageUrl": None,
    }
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, shipment_response)
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, shipment_response)
    connector = _connector(transport, sanocea_store)
    first_ids, _ = connector.sync_orders("mer_A")
    second_ids, _ = connector.sync_orders("mer_A")
    assert first_ids == second_ids
    assert len([o for o in sanocea_store.list(Order, "mer_A") if o.order_number == "ORD-2"]) == 1


def test_unmapped_status_preserved_verbatim_and_flagged(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, {
        "shipments": [{"shipmentId": "SHIP-3", "status": "PACKED_AT_HUB_XYZ", "orderId": "ORD-3", "orderItems": []}],
        "nextPageUrl": None,
    })
    connector = _connector(transport, sanocea_store)
    order_ids, _ = connector.sync_orders("mer_A")
    order = sanocea_store.get(Order, "mer_A", order_ids[0])
    assert order.status == "PACKED_AT_HUB_XYZ", "an unmapped status must be preserved verbatim, never guessed at"
    exceptions = [e for e in sanocea_store.list(ExceptionRecord, "mer_A") if e.category == "unmapped_channel_status"]
    assert len(exceptions) == 1


# --- 6: fulfilment/status transition -----------------------------------------------------------------

def test_dispatch_shipment_mutation(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/dispatch", 200, {"shipmentId": "SHIP-1", "processingStatus": "SUCCESS"})
    connector = _connector(transport, sanocea_store)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="dispatch_shipment", object_type="Shipment",
        payload={"shipment_id": "SHIP-1", "location_id": "LOC-1"}, idempotency_key="dispatch:SHIP-1",
    ))
    assert result.status == "accepted"
    assert result.payload["processingStatus"] == "SUCCESS"


# --- 7: cancellation -----------------------------------------------------------------------------------

def test_cancel_shipment_mutation(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/cancel", 200, {"shipmentId": "SHIP-1", "processingStatus": "SUCCESS"})
    connector = _connector(transport, sanocea_store)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="cancel_shipment", object_type="Shipment",
        payload={"shipment_id": "SHIP-1", "location_id": "LOC-1", "reason": "OOS"}, idempotency_key="cancel:SHIP-1",
    ))
    assert result.status == "accepted"


# --- 8: return/refund mapping ----------------------------------------------------------------------------

def test_approve_return_mutation(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/sellers/v2/returns/approve", 200, {"returnId": "RET-1", "processingStatus": "SUCCESS"})
    connector = _connector(transport, sanocea_store)
    result = connector.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="approve_return", object_type="Return",
        payload={"return_id": "RET-1", "location_id": "LOC-1"}, idempotency_key="approve:RET-1",
    ))
    assert result.status == "accepted"
    assert result.external_ref == "RET-1"


# --- 9: settlement ingestion (UNCONFIRMED) -----------------------------------------------------------

def test_settlement_ingest_is_unconfirmed_not_silently_supported(sanocea_store):
    transport = FakeTransport()
    connector = _connector(transport, sanocea_store)
    with pytest.raises(CapabilityUnconfirmed):
        connector.describe_capabilities().require("settlement_ingest")


def test_order_notifications_is_access_required_not_silently_supported(sanocea_store):
    transport = FakeTransport()
    connector = _connector(transport, sanocea_store)
    with pytest.raises(CapabilityAccessRequired):
        connector.describe_capabilities().require("order_notifications")


def test_hyperlocal_order_ingest_is_unconfirmed(sanocea_store):
    """Step 9Q.1 Part D: HyperLocal catalogue capability must never be assumed to cover HyperLocal orders."""
    transport = FakeTransport()
    connector = _connector(transport, sanocea_store)
    with pytest.raises(CapabilityUnconfirmed):
        connector.describe_capabilities().require("hyperlocal_order_ingest")
    # ... but the catalogue/inventory/pricing legs ARE confirmed and must remain callable.
    connector.describe_capabilities().require("hyperlocal_catalogue_write")
    connector.describe_capabilities().require("hyperlocal_update_inventory")
    connector.describe_capabilities().require("hyperlocal_update_price")


# --- 10: retries / rate limiting -------------------------------------------------------------------------

def test_retries_on_429_then_succeeds(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 429, {}, headers={"Retry-After": "0"})
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "title": "Widget", "sellingPrice": 199.0, "status": "ACTIVE"})
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "product", "SKU-1")
    assert result["sku"] == "SKU-1"


def test_rate_limit_exhausted_raises_runtime_error(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    for _ in range(3):
        transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 429, {}, headers={"Retry-After": "0"})
    connector = _connector(transport, sanocea_store)
    with pytest.raises(RuntimeError):
        connector.fetch("mer_A", "product", "SKU-1")


def test_5xx_retries_then_exhausts(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    for _ in range(3):
        transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 500, {"error": "internal"})
    connector = _connector(transport, sanocea_store)
    with pytest.raises(RuntimeError):
        connector.fetch("mer_A", "product", "SKU-1")


# --- 11: malformed / partial response -----------------------------------------------------------------

def test_malformed_payload_missing_required_field_raises(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    connector = _connector(transport, sanocea_store)
    with pytest.raises(KeyError):
        connector.execute_mutation(MutationRequest(
            merchant_id="mer_A", action="dispatch_shipment", object_type="Shipment",
            payload={}, idempotency_key="bad:1",
        ))


def test_partial_response_missing_optional_field_defaults_gracefully(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1"})  # no title/price/status
    connector = _connector(transport, sanocea_store)
    result = connector.fetch("mer_A", "product", "SKU-1")
    assert result["title"] is None
    assert result["status"] == "inactive"


# --- 12: unsupported operation -----------------------------------------------------------------------

def test_unsupported_operation_raises_unsupported_capability(sanocea_store):
    transport = FakeTransport()
    connector = _connector(transport, sanocea_store)
    with pytest.raises(UnsupportedCapability):
        connector.execute_mutation(MutationRequest(
            merchant_id="mer_A", action="not_a_real_action", object_type="Whatever",
            payload={}, idempotency_key="x",
        ))


# --- 13: tenant isolation -------------------------------------------------------------------------------

def test_tenant_isolation_on_order_lookup(sanocea_store):
    transport = FakeTransport()
    _auth_ok(transport)
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, {
        "shipments": [{"shipmentId": "SHIP-9", "status": "APPROVED", "orderId": "ORD-9", "orderItems": []}], "nextPageUrl": None,
    })
    connector = _connector(transport, sanocea_store)
    order_ids, _ = connector.sync_orders("mer_A")
    with pytest.raises(TenantAccessError):
        sanocea_store.get(Order, "mer_B", order_ids[0])
