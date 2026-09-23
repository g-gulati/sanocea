from __future__ import annotations

import json

import pytest

from sanocea.connectors.amazon import AmazonConnector
from sanocea.connectors.amazon.auth import LWA_TOKEN_URL, merchant_lwa_auth
from sanocea.connectors.amazon.connector import BASE_URL as AMAZON_BASE_URL
from sanocea.connectors.flipkart import FlipkartConnector
from sanocea.connectors.flipkart.auth import merchant_authorization_code_auth
from sanocea.connectors.flipkart.connector import BASE_URL
from sanocea.connectors.meesho import MeeshoConnector
from sanocea.connectors.meesho.auth import StaticSupplierCredentialsAuth
from sanocea.connectors.woocommerce import WooCommerceConnector
from sanocea.packages.connector_sdk import CapabilityUnconfirmed, MutationRequest
from sanocea.packages.domain_contract.models import Channel, ExceptionRecord, ListingVerification, Order, ProductDraft
from sanocea.packages.product_onboarding import ProductCompletenessValidator, ProductPublicationService
from sanocea.packages.runtime.storefront_registry import StorefrontConnectorRegistry

"""Step 9Q.2 Part H - one realistic synthetic merchant operating Shopify (D2C) AND Flipkart
(marketplace) simultaneously, proving Sanocea's canonical operational layer (ProductPublicationService,
Order/OrderLine, ExceptionRecord) handles both without any channel-specific branching in the domain
layer - the SAME ProductPublicationService.publish()/verify() code runs for both channels; only the
CONNECTOR each channel resolves to differs, exactly as tests/unit/test_architecture_connector_boundary.py
already enforces at the AST level. This is the first genuinely multi-storefront-per-merchant scenario
built in this codebase (see StorefrontConnectorRegistry.resolve_for_channel_id, added this step)."""


class FakeTransport:
    def __init__(self) -> None:
        self._queue: dict[tuple[str, str], list[tuple[int, dict, bytes]]] = {}
        self.calls: list[str] = []

    def queue(self, method: str, path: str, status: int, body: dict) -> None:
        self._queue.setdefault((method, path.split("?", 1)[0]), []).append((status, {}, json.dumps(body).encode()))

    def __call__(self, method, url, headers, body):
        self.calls.append(f"{method} {url}")
        key = (method, url.split("?", 1)[0])
        pending = self._queue.get(key)
        if not pending:
            raise AssertionError(f"no queued response for {method} {url}")
        return pending.pop(0)


@pytest.fixture
def multichannel_merchant(phase0):
    """mer_A already has a Shopify channel from the shared phase0 fixture - add a Flipkart one."""
    store, workflow, shopify, chatwoot = phase0
    store.put(Channel(id="chn_A_flipkart", merchant_id="mer_A", type="flipkart", name="Merchant A Flipkart"))
    transport = FakeTransport()
    transport.queue("POST", f"{BASE_URL}/oauth-service/oauth/token", 200, {"access_token": "tok-1", "expires_in": 3600})
    auth = merchant_authorization_code_auth(client_id="partner", client_secret="secret", refresh_token="rt", transport=transport)
    flipkart = FlipkartConnector(store, workflow, auth=auth, transport=transport)

    registry = StorefrontConnectorRegistry(store, workflow)
    registry.register("shopify", lambda store, workflow, merchant_id: shopify)
    registry.register("flipkart", lambda store, workflow, merchant_id: flipkart)
    return store, registry, shopify, flipkart, transport


def test_same_product_publishes_to_shopify_and_flipkart_via_one_service(multichannel_merchant):
    store, registry, shopify, flipkart, transport = multichannel_merchant
    draft = ProductDraft(merchant_id="mer_A", sku="MC-1", title="Multichannel Widget", price=19900, currency="INR", product_type="general")
    store.put(draft)
    draft = ProductCompletenessValidator(store).validate(draft)
    draft = ProductCompletenessValidator(store).approve_publication(draft, "merchant")

    service = ProductPublicationService(store, registry)

    # --- D2C leg: Shopify, via the SAME service, SAME method calls -----------------------------------
    shopify_pub = service.create_publication("mer_A", draft.id, "chn_A_shopify")
    shopify_verification = service.publish("mer_A", shopify_pub.id)
    assert shopify_verification.outcome == "VERIFIED"

    # --- Marketplace leg: Flipkart, via the IDENTICAL service/method calls - only channel_id differs --
    transport.queue("POST", f"{BASE_URL}/sellers/v3/listings", 200, {"listingId": "FK-LISTING-1", "skuId": "MC-1", "title": "Multichannel Widget", "sellingPrice": 199.0, "status": "ACTIVE"})
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "MC-1", "title": "Multichannel Widget", "sellingPrice": 199.0, "status": "ACTIVE"})
    flipkart_pub = service.create_publication("mer_A", draft.id, "chn_A_flipkart")
    flipkart_verification = service.publish("mer_A", flipkart_pub.id)
    assert flipkart_verification.outcome == "VERIFIED"

    # Two DISTINCT Publication rows, two DISTINCT ListingVerification rows, resolved to the CORRECT
    # connector each time - the domain layer (ProductPublicationService) never branched on platform name.
    verifications = store.list(ListingVerification, "mer_A")
    assert {v.publication_id for v in verifications} == {shopify_pub.id, flipkart_pub.id}
    assert shopify.external_products, "Shopify's own in-memory store must have received the publish"
    assert any("sellers/v3/listings" in c for c in transport.calls), "Flipkart's real endpoint must have been called, not skipped"


def test_flipkart_order_ingestion_fulfilment_reconciliation_and_exception_flow(multichannel_merchant):
    store, registry, shopify, flipkart, transport = multichannel_merchant

    # --- Flipkart order arrives (poll-based ingestion, per Step 9Q.1 - no confirmed webhook path) ------
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, {
        "shipments": [{"shipmentId": "SHIP-100", "status": "APPROVED", "orderId": "FK-ORD-100",
                        "orderItems": [{"sku": "MC-1", "title": "Multichannel Widget", "quantity": 1, "sellingPrice": 199.0}]}],
        "nextPageUrl": None,
    })
    order_ids, _ = flipkart.sync_orders("mer_A")
    order = store.get(Order, "mer_A", order_ids[0])
    assert order.status == "APPROVED"

    # --- Fulfilment: dispatch the shipment through the SAME connector's real, documented endpoint ------
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/dispatch", 200, {"shipmentId": "SHIP-100", "processingStatus": "SUCCESS"})
    dispatch_result = flipkart.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="dispatch_shipment", object_type="Shipment",
        payload={"shipment_id": "SHIP-100", "location_id": "LOC-1"}, idempotency_key="dispatch:SHIP-100",
    ))
    assert dispatch_result.status == "accepted"

    # --- Post-order event: a later sync reports DELIVERED - canonical Order must reflect it -------------
    transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, {
        "shipments": [{"shipmentId": "SHIP-100", "status": "DELIVERED", "orderId": "FK-ORD-100", "orderItems": []}],
        "nextPageUrl": None,
    })
    flipkart.sync_orders("mer_A")
    order = store.get(Order, "mer_A", order.id)
    assert order.status == "PAID" and order.fulfillment_status == "fulfilled"

    # --- Reconciliation: canonical Order is stale relative to what the channel now reports --------------
    order.status = "APPROVED"  # simulate a canonical row that drifted behind the channel
    store.put(order)
    transport.queue("GET", f"{BASE_URL}/sellers/v3/shipments", 200, {"shipments": [{"shipmentId": "SHIP-100", "status": "DELIVERED"}]})
    divergences = flipkart.reconcile("mer_A", {"external_order_id": "FK-ORD-100"})
    assert len(divergences) == 1
    assert divergences[0]["external_status"] == "PAID"

    # --- Settlement ingestion: UNCONFIRMED must refuse, not silently attempt --------------------------
    with pytest.raises(CapabilityUnconfirmed):
        flipkart.describe_capabilities().require("settlement_ingest")

    # --- Exception/reporting: both the reconciliation divergence above surfaced an ExceptionRecord ------
    exceptions = store.list(ExceptionRecord, "mer_A")
    assert any(e.category == "reconciliation_divergence" for e in exceptions)


def test_hyperlocal_capability_aware_routing_on_the_same_merchant_config(multichannel_merchant):
    """Step 9Q.1 Part D: adding the documented Flipkart Minutes (HyperLocal) catalogue/inventory/pricing
    leg to the SAME merchant/connector must route SUPPORTED actions through and refuse UNCONFIRMED ones
    - no separate Channel/connector needed, since HyperLocal is a distinct set of actions on the SAME
    Flipkart connector, not a different platform."""
    store, registry, shopify, flipkart, transport = multichannel_merchant

    transport.queue("POST", f"{BASE_URL}/listings/v3/hyperlocal", 200, {"listingId": "HL-1", "skuId": "MC-1"})
    result = flipkart.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="hyperlocal_publish_product", object_type="Listing",
        payload={"location_id": "DARKSTORE-1", "sku": "MC-1", "title": "Multichannel Widget"}, idempotency_key="hl-publish:MC-1",
    ))
    assert result.status == "accepted"

    transport.queue("POST", f"{BASE_URL}/listings/v3/hyperlocal/update/inventory", 200, {"skuId": "MC-1", "availableUnits": 3})
    inv_result = flipkart.execute_mutation(MutationRequest(
        merchant_id="mer_A", action="hyperlocal_update_inventory", object_type="Listing",
        payload={"location_id": "DARKSTORE-1", "sku": "MC-1", "quantity": 3}, idempotency_key="hl-inv:MC-1",
    ))
    assert inv_result.status == "accepted"

    # Orders/fulfilment/returns/settlement for HyperLocal remain UNCONFIRMED - capability-aware routing
    # must refuse these even though the catalogue/inventory legs on the SAME connector just succeeded.
    for capability in ("hyperlocal_order_ingest", "hyperlocal_fulfilment_update", "hyperlocal_return_refund", "hyperlocal_settlement_ingest"):
        with pytest.raises(CapabilityUnconfirmed):
            flipkart.describe_capabilities().require(capability)


# --- Step 9Q.3: three-way coexistence - Shopify + Flipkart + Amazon on ONE merchant --------------------

def test_shopify_flipkart_amazon_coexist_on_one_merchant_with_channel_aware_resolution(phase0):
    store, workflow, shopify, chatwoot = phase0
    store.put(Channel(id="chn_A_flipkart", merchant_id="mer_A", type="flipkart", name="Merchant A Flipkart"))
    store.put(Channel(id="chn_A_amazon", merchant_id="mer_A", type="amazon", name="Merchant A Amazon"))

    flipkart_transport = _make_flipkart_transport()
    flipkart_auth = merchant_authorization_code_auth(client_id="p", client_secret="s", refresh_token="rt", transport=flipkart_transport)
    flipkart = FlipkartConnector(store, workflow, auth=flipkart_auth, transport=flipkart_transport)

    amazon_transport = _make_amazon_transport()
    amazon_auth = merchant_lwa_auth(client_id="a", client_secret="b", refresh_token="rt2", transport=amazon_transport)
    amazon = AmazonConnector(store, workflow, auth=amazon_auth, seller_id="SELLER1", transport=amazon_transport)

    registry = StorefrontConnectorRegistry(store, workflow)
    registry.register("shopify", lambda store, workflow, merchant_id: shopify)
    registry.register("flipkart", lambda store, workflow, merchant_id: flipkart)
    registry.register("amazon", lambda store, workflow, merchant_id: amazon)

    # Channel-aware resolution: each channel_id must resolve to its OWN connector, never "whichever is first".
    assert registry.resolve_for_channel_id("mer_A", "chn_A_shopify") is shopify
    assert registry.resolve_for_channel_id("mer_A", "chn_A_flipkart") is flipkart
    assert registry.resolve_for_channel_id("mer_A", "chn_A_amazon") is amazon

    # Ingest one order from each marketplace channel into the SAME canonical Order model, no
    # channel-specific branching anywhere in the domain layer (AST-enforced separately).
    flipkart_transport.queue("POST", f"{BASE_URL}/sellers/v3/shipments/filter", 200, {
        "shipments": [{"shipmentId": "S-FK-1", "status": "APPROVED", "orderId": "FK-1", "orderItems": []}], "nextPageUrl": None,
    })
    fk_ids, _ = flipkart.sync_orders("mer_A")

    amazon_transport.queue("GET", f"{AMAZON_BASE_URL}/orders/v0/orders", 200, {"payload": {"Orders": [
        {"AmazonOrderId": "AMZ-1", "OrderStatus": "Shipped", "OrderTotal": {"Amount": "0", "CurrencyCode": "INR"}},
    ], "NextToken": None}})
    amz_ids, _ = amazon.sync_orders("mer_A")

    fk_order = store.get(Order, "mer_A", fk_ids[0])
    amz_order = store.get(Order, "mer_A", amz_ids[0])
    assert fk_order.order_number == "FK-1"
    assert amz_order.order_number == "AMZ-1" and amz_order.status == "PAID" and amz_order.fulfillment_status == "fulfilled"
    assert {o.id for o in store.list(Order, "mer_A")} >= {fk_order.id, amz_order.id}


def _make_flipkart_transport():
    from tests.unit.test_flipkart_connector import FakeTransport as _FT, TOKEN_URL as _FK_TOKEN_URL
    t = _FT()
    t.queue("POST", _FK_TOKEN_URL, 200, {"access_token": "fk-tok", "expires_in": 3600})
    return t


def _make_amazon_transport():
    from tests.unit.test_amazon_connector import FakeTransport as _AT
    t = _AT()
    t.queue("POST", LWA_TOKEN_URL, 200, {"access_token": "amz-tok", "expires_in": 3600})
    return t


# --- Step 9Q.4: five-way coexistence - Shopify + WooCommerce + Flipkart + Amazon + Meesho -------------

def test_five_channel_coexistence_and_channel_aware_resolution(phase0):
    store, workflow, shopify, chatwoot = phase0
    for channel_id, channel_type in [
        ("chn_A_woocommerce", "woocommerce"), ("chn_A_flipkart", "flipkart"),
        ("chn_A_amazon", "amazon"), ("chn_A_meesho", "meesho"),
    ]:
        store.put(Channel(id=channel_id, merchant_id="mer_A", type=channel_type, name=f"Merchant A {channel_type}"))

    woocommerce = WooCommerceConnector(store, workflow, base_url="https://example-store.test", consumer_key="ck", consumer_secret="cs")
    flipkart_transport = _make_flipkart_transport()
    flipkart = FlipkartConnector(store, workflow, auth=merchant_authorization_code_auth(client_id="p", client_secret="s", refresh_token="rt", transport=flipkart_transport), transport=flipkart_transport)
    amazon_transport = _make_amazon_transport()
    amazon = AmazonConnector(store, workflow, auth=merchant_lwa_auth(client_id="a", client_secret="b", refresh_token="rt2", transport=amazon_transport), seller_id="SELLER1", transport=amazon_transport)
    meesho = MeeshoConnector(store, workflow, auth=StaticSupplierCredentialsAuth(client_id="m", security="sec", supplier_identifier="loc1"))

    registry = StorefrontConnectorRegistry(store, workflow)
    registry.register("shopify", lambda store, workflow, merchant_id: shopify)
    registry.register("woocommerce", lambda store, workflow, merchant_id: woocommerce)
    registry.register("flipkart", lambda store, workflow, merchant_id: flipkart)
    registry.register("amazon", lambda store, workflow, merchant_id: amazon)
    registry.register("meesho", lambda store, workflow, merchant_id: meesho)

    # Every channel resolves to its OWN, distinct connector instance - no cross-merchant/cross-channel
    # state sharing, no "whichever channel happens to be first" ambiguity.
    resolved = {
        "shopify": registry.resolve_for_channel_id("mer_A", "chn_A_shopify"),
        "woocommerce": registry.resolve_for_channel_id("mer_A", "chn_A_woocommerce"),
        "flipkart": registry.resolve_for_channel_id("mer_A", "chn_A_flipkart"),
        "amazon": registry.resolve_for_channel_id("mer_A", "chn_A_amazon"),
        "meesho": registry.resolve_for_channel_id("mer_A", "chn_A_meesho"),
    }
    assert resolved["shopify"] is shopify
    assert resolved["woocommerce"] is woocommerce
    assert resolved["flipkart"] is flipkart
    assert resolved["amazon"] is amazon
    assert resolved["meesho"] is meesho
    assert len({id(c) for c in resolved.values()}) == 5, "five distinct connector instances, never shared"

    # Meesho's honest capability posture must survive coexistence unaffected by the other four channels.
    with pytest.raises(CapabilityUnconfirmed):
        meesho.describe_capabilities().require("order_ingest")
