from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
import uuid
from typing import Any

from sanocea.packages.connector_sdk import (
    Capability,
    CapabilityStatus,
    ConnectorCapabilities,
    GuardedConnector,
    MutationMode,
    MutationRequest,
    MutationResult,
)
from sanocea.packages.domain_contract.models import (
    Customer,
    ExternalIdMapping,
    ExternalRef,
    IdempotencyInfo,
    Order,
    OrderLine,
    SourceOfTruth,
    SyncMetadata,
)

from .auth import ShopifyAccessTokenManager, ShopifyAuthenticationError

"""SHOPIFY DEV-STORE CERTIFICATION - PREPARATION PHASE.

Real Shopify Admin GraphQL API connector - NOT the existing in-memory ShopifyConnector simulator
(connectors/shopify/connector.py), which stays completely unchanged and keeps its "shopify" name and
its own zero-tolerance fault-injection test suite. This is a NEW, additive connector, registered under
the distinct channel type "shopify_live" (packages/runtime/service_graph.py) so it can never be
accidentally selected instead of the simulator for an existing merchant, and the simulator's own tests
are unaffected by anything in this file.

STATUS: written from current (September 2026) official Shopify documentation
(shopify.dev/docs/api/admin-graphql, shopify.dev/docs/apps/build/webhooks) - the GraphQL query/mutation
shapes below are believed correct as of API version 2026-07, but this connector has NEVER been executed
against a real Shopify store (no development-store credentials exist in this environment yet). Every
mutation/query here should be re-verified via GraphQL schema introspection against the real store on
the FIRST real certification run, before trusting any result - see
docs/architecture/shopify-dev-store-certification-preparation.md section 2 for exactly what is
build-time-verified (structurally sound Python, correct per public docs) versus what remains
runtime-unverified (actual field/type acceptance by a live store) until credentials exist.

Key real-API findings this connector is built around (see the prep doc's audit for the full list):
  - Product create/update: the CURRENT recommended mutation is `productSet` (not the older
    `productCreate` + `productVariantsBulkCreate` two-step, and not REST's `POST /products.json`,
    which the simulator's field names - "variants"/"metafields"/"productType" - superficially resemble
    but which Sanocea never actually called over HTTP).
  - Inventory is genuinely LOCATION-scoped (InventoryItem + Location + InventoryLevel) - there is no
    flat "available quantity" the way the simulator's fetch("inventory", ...) returns. A location id is
    required configuration, not something this connector can default sensibly.
  - Fulfillment goes through the FulfillmentOrder API (`fulfillmentCreate`, the FulfillmentOrder for an
    Order must be queried first) - not a bare "mark this order fulfilled" call.
  - `refundCreate` requires an `@idempotent(key: "uuid")` directive as of API version 2026-04 - this
    maps cleanly onto Sanocea's own existing idempotency_key concept (see _idempotent_uuid below).
  - Real Shopify order webhook payloads carry NO monotonic sequence number (no "updated_sequence" field
    - that field is specific to Sanocea's own simulator's hand-built test payloads and does not exist on
    a real Shopify webhook delivery). Stale/out-of-order webhook detection here uses `updated_at`
    timestamp comparison instead, the same approach WooCommerceConnector already uses for the same
    reason (WooCommerce also has no sequence field) - not a new pattern, but a REAL finding: the
    "REST-shaped payload with a sequence number" the simulator and Phase 1-4.6 test payloads assume is
    itself a simulator convenience that a real Shopify delivery will never send.

CLIENT-CREDENTIALS AUTH HARDENING (verified against current shopify.dev docs - legacy admin-created
custom apps, which used to show a static shpat_... token in the Shopify admin, were deprecated
2026-01-01): this connector never accepts a static access token. It authenticates with a Client
ID/Secret and obtains its own short-lived (~24h) access token via Shopify's client-credentials grant
(POST https://{shop}.myshopify.com/admin/oauth/access_token, grant_type=client_credentials) through
ShopifyAccessTokenManager (auth.py) - one manager instance per connector instance, which
StorefrontConnectorRegistry already caches per merchant, so concurrent requests for one merchant share
one cache/lock. The token is ephemeral runtime state ONLY: never persisted to the store, never logged,
never included in any audit/exception message. On an auth-shaped (401/403) API failure, _graphql()
invalidates the cached token and retries the SAME logical call exactly once with a fresh token - bounded
by a plain `for attempt in range(2)` loop, never an unbounded retry. Because this retry happens entirely
INSIDE one _execute_mutation() call - the same call IdempotencyService.run_once() treats as a single
`operation()` invocation - a token refresh can never cause a logically new mutation; Sanocea's own
idempotency_key/scope is fixed before any HTTP attempt and is never re-derived across the retry.

Default Location gid is discovered programmatically (a `{ locations(first: 1) { nodes { id } } }`
query, cached on first use) rather than required as configuration - there is no manual value for a
merchant to supply here.
"""

GRAPHQL_API_VERSION = "2026-07"


class ShopifyLiveConnector(GuardedConnector):
    name = "shopify_live"

    def __init__(
        self,
        store,
        workflow,
        *,
        shop_domain: str,
        client_id: str,
        client_secret: str,
        api_version: str = GRAPHQL_API_VERSION,
        webhook_delivery_base_url: str | None = None,
        default_location_gid: str | None = None,
        token_manager: ShopifyAccessTokenManager | None = None,
    ) -> None:
        super().__init__(store)
        self.workflow = workflow
        self.shop_domain = shop_domain.rstrip("/")
        self.client_secret = client_secret  # webhook HMAC key AND the client-credentials grant secret - the app's client secret, not a per-shop value
        self.api_version = api_version
        self.webhook_delivery_base_url = webhook_delivery_base_url.rstrip("/") if webhook_delivery_base_url else None
        # Inventory mutations require a Location gid - Shopify has no notion of a single "default" stock
        # level the way the simulator's flat fetch("inventory", ...) pretends. Discovered programmatically
        # (see _ensure_location_gid) rather than required as configuration - never guessed or fabricated.
        self.default_location_gid = default_location_gid
        # `token_manager` is injectable purely for testing (a fake manager with a fake clock/http_post) -
        # every real caller lets this build its own ShopifyAccessTokenManager from client_id/client_secret.
        self._token_manager = token_manager or ShopifyAccessTokenManager(
            shop_domain=self.shop_domain, client_id=client_id, client_secret=client_secret,
        )

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "ingest_order_webhook": Capability(name="ingest_order_webhook", status=CapabilityStatus.SUPPORTED),
                "publish_product": Capability(
                    name="publish_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC,
                    api_versions=[self.api_version],
                    notes="Uses the productSet mutation (current recommended create/update path as of "
                          "2026-07), not the older productCreate+productVariantsBulkCreate two-step and "
                          "not REST. UNVERIFIED against a live store - ProductSetInput's exact accepted "
                          "field set should be confirmed via schema introspection on first real run.",
                ),
                "create_product": Capability(name="create_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=[self.api_version]),
                "update_product": Capability(name="update_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=[self.api_version]),
                "fetch": Capability(name="fetch", status=CapabilityStatus.SUPPORTED),
                "set_inventory": Capability(
                    name="set_inventory", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC,
                    notes="Location-scoped (InventoryItem + Location + InventoryLevel via "
                          "inventorySetQuantities) - there is no flat, location-less inventory concept "
                          "on real Shopify the way the existing simulator models it. The location gid "
                          "is discovered programmatically (_ensure_location_gid) on first use, never "
                          "configured manually.",
                ),
                "create_fulfilment": Capability(
                    name="create_fulfilment", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC,
                    notes="Goes through the FulfillmentOrder API (query the order's fulfillmentOrders, "
                          "then fulfillmentCreate) - not a direct order-level 'mark fulfilled' call. "
                          "Uses fulfillmentCreate, not the deprecated fulfillmentCreateV2.",
                ),
                "cancel_order": Capability(name="cancel_order", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "create_refund": Capability(
                    name="create_refund", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC,
                    notes="refundCreate requires an @idempotent(key: \"uuid\") directive as of API "
                          "version 2026-04 - this connector derives a stable UUID5 from Sanocea's own "
                          "idempotency_key so a retried request is idempotent on the Shopify side too, "
                          "not just Sanocea's.",
                ),
                "register_webhooks": Capability(name="register_webhooks", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "reconcile": Capability(name="reconcile", status=CapabilityStatus.SUPPORTED),
            },
        )

    # --- Webhook ingress -------------------------------------------------------------------------------

    def ingest_webhook(self, merchant_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in headers.items()}
        self._verify_hmac(headers, body)
        topic = headers.get("x-shopify-topic", "")
        # X-Shopify-Webhook-Id is the correct, real dedup key (real Shopify webhook retries - up to 8
        # over 4 hours - reuse the same id) - same header Sanocea's own simulator already expects, so no
        # change needed to the idempotency STRATEGY, only to what field decides staleness (see below).
        webhook_id = headers.get("x-shopify-webhook-id") or hashlib.sha256(body).hexdigest()
        payload = json.loads(body.decode("utf-8"))
        checksum = hashlib.sha256(body).hexdigest()
        raw = self._store_raw(merchant_id=merchant_id, source=f"shopify_live:{topic}", payload=payload, headers=headers, checksum=checksum)

        def op() -> dict[str, Any]:
            result = self._upsert_order(merchant_id, payload, raw.id)
            self.audit.record(
                merchant_id=merchant_id, actor="shopify_live", source="webhook", action="order_webhook_ingested",
                object_type="Order", object_id=result["order_id"], evidence_ref=raw.id, result="created_or_updated",
                external_ref=ExternalRef(system=self.name, entity_type="order", external_id=str(payload["id"])),
            )
            self.workflow.start_or_signal_order(merchant_id, result["order_id"], {"topic": topic, "raw_payload_id": raw.id})
            return result

        result, created = self.idempotency.run_once(f"{merchant_id}:webhook:{self.name}:{topic}", webhook_id, op)
        if not created:
            self.audit.record(
                merchant_id=merchant_id, actor="shopify_live", source="webhook", action="duplicate_webhook_ignored",
                object_type="Order", object_id=result["order_id"], evidence_ref=raw.id, result="duplicate",
            )
        return result | {"idempotent_replay": not created}

    def _verify_hmac(self, headers: dict[str, str], body: bytes) -> None:
        provided = headers.get("x-shopify-hmac-sha256")
        digest = hmac.new(self.client_secret.encode(), body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode()
        if not provided or not hmac.compare_digest(provided, expected):
            raise PermissionError("invalid Shopify webhook HMAC")

    def _upsert_order(self, merchant_id: str, payload: dict[str, Any], raw_id: str) -> dict[str, Any]:
        external_id = str(payload["id"])
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_id)
        email = payload.get("email")
        customer = None
        if email:
            customer = self.store.find_one(Customer, merchant_id, email=email)
            if customer is None:
                customer = Customer(
                    merchant_id=merchant_id, email=email, name=(payload.get("customer") or {}).get("first_name"),
                    source_of_truth=SourceOfTruth.CHANNEL, sync=SyncMetadata(raw_payload_ref=raw_id),
                )
                self.store.put(customer)
        financial = payload.get("financial_status") or "unknown"
        cancelled = bool(payload.get("cancelled_at"))
        status = "CANCELLED" if cancelled else ("PAID" if financial == "paid" else financial.upper())
        incoming_updated = payload.get("updated_at")
        if mapping:
            order = self.store.get(Order, merchant_id, mapping.sanocea_id)
            # REAL finding (see module docstring): real Shopify order webhooks carry no monotonic
            # sequence number - "updated_sequence" is a Sanocea test-payload-only field. Staleness is
            # judged by comparing updated_at timestamps instead, mirroring WooCommerceConnector's
            # date_modified approach (same underlying reason: neither real platform sends a sequence
            # int, only Sanocea's own simulator payloads invented one for deterministic test ordering).
            if incoming_updated and order.sync.source_updated_at and incoming_updated <= order.sync.source_updated_at.isoformat():
                self.audit.record(
                    merchant_id=merchant_id, actor="shopify_live", source="webhook", action="out_of_order_event_ignored",
                    object_type="Order", object_id=order.id, evidence_ref=raw_id, result="ignored",
                )
                return {"order_id": order.id, "status": order.status}
        else:
            order = Order(
                merchant_id=merchant_id,
                channel_id=payload.get("channel_id", self.name),
                customer_id=customer.id if customer else None,
                order_number=str(payload.get("order_number") or payload.get("name") or external_id),
                status=status,
                payment_status=financial,
                fulfillment_status=payload.get("fulfillment_status"),
                total_amount=int(round(float(payload.get("total_price", "0")) * 100)),
                currency=payload.get("currency", "INR"),
                source_of_truth=SourceOfTruth.CHANNEL,
                idempotency=IdempotencyInfo(scope="shopify_live_order_webhook", key=f"shopify_live:{external_id}"),
            )
        order.status = status
        order.payment_status = financial
        order.external_refs = [ref for ref in order.external_refs if not (ref.system == self.name and ref.entity_type == "order")] + [
            ExternalRef(system=self.name, entity_type="order", external_id=external_id, channel_id=order.channel_id)
        ]
        order.sync.raw_payload_ref = raw_id
        if incoming_updated:
            from datetime import datetime

            try:
                order.sync.source_updated_at = datetime.fromisoformat(incoming_updated.replace("Z", "+00:00"))
            except ValueError:
                pass
        self.store.put(order)
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id, sanocea_entity_type="Order", sanocea_id=order.id,
                external_system=self.name, external_entity_type="order", external_id=external_id, channel_id=order.channel_id,
            )
        )
        for item in payload.get("line_items", []):
            line = OrderLine(
                merchant_id=merchant_id, order_id=order.id, sku=item.get("sku"),
                title=item.get("title") or "Untitled", quantity=int(item.get("quantity", 1)),
                unit_amount=int(round(float(item.get("price", "0")) * 100)),
                source_of_truth=SourceOfTruth.CHANNEL, sync=SyncMetadata(raw_payload_ref=raw_id),
            )
            self.store.put(line)
        return {"order_id": order.id, "status": order.status}

    # --- Outbound reads ----------------------------------------------------------------------------

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        self.describe_capabilities().require("fetch")
        if entity_type == "product":
            data = self._graphql(
                "query($id: ID!) { product(id: $id) { title status variants(first: 1) { nodes { sku price } } } }",
                {"id": self._product_gid(external_id)},
            )
            raw = data["product"]
            variant = (raw.get("variants", {}).get("nodes") or [{}])[0]
            return {
                "title": raw.get("title"), "sku": variant.get("sku"), "price": variant.get("price"),
                "status": "active" if raw.get("status") == "ACTIVE" else "inactive", "raw": raw,
            }
        if entity_type == "inventory":
            # REAL FINDING: external_id here is a PRODUCT gid (this is the id Sanocea's own
            # ExternalIdMapping/Publication actually tracks - there is no separate "inventory id"
            # anywhere in Sanocea's domain model), but a real InventoryItem is a SEPARATE Shopify entity
            # scoped to one ProductVariant, not interchangeable with a Product gid. Resolved via the
            # product's own (first) variant, not assumed equal to the product id.
            location_gid = self._ensure_location_gid()
            inventory_item_gid, sku, available, _level_active = self._inventory_item_for_product(external_id, location_gid)
            return {"sku": sku, "available": available, "raw": {"inventory_item_id": inventory_item_gid}}
        if entity_type == "order":
            data = self._graphql(
                "query($id: ID!) { order(id: $id) { name displayFinancialStatus displayFulfillmentStatus updatedAt cancelledAt } }",
                {"id": self._order_gid(external_id)},
            )
            return data["order"]
        if entity_type == "fulfilment":
            data = self._graphql(
                "query($id: ID!) { order(id: $id) { displayFulfillmentStatus } }",
                {"id": self._order_gid(external_id)},
            )
            return {"order_id": external_id, "status": data["order"].get("displayFulfillmentStatus")}
        if entity_type == "customer":
            return {"email": external_id}
        raise KeyError(entity_type)

    # --- Outbound mutations --------------------------------------------------------------------------

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        payload = request.payload
        if request.action in {"publish_product", "create_product", "update_product"}:
            # Connector-agnostic payload in (title/sku/price/currency/product_type/attributes) - same
            # contract every connector accepts, per docs/architecture/multi-platform-connector-hardening.md
            # closure item 2. Translated HERE into productSet's ProductSetInput shape.
            #
            # REAL FINDING (confirmed against the real Shopify dev store, not assumed from docs alone):
            # productSet REQUIRES every variant to carry optionValues - "Expected value to not be null" -
            # even for a single-variant/no-real-options product. There is no null/omitted-options path.
            # Every real Shopify product has at least one option; a plain single-SKU product uses
            # Shopify's own convention of one option named "Title" with value "Default Title" (the same
            # shape Shopify's own admin UI/REST API produces for a non-variant product). Declared at the
            # product level (productOptions) and referenced by each variant's optionValues.
            variant_input: dict[str, Any] = {
                "price": payload.get("price"), "sku": payload.get("sku"),
                "optionValues": [{"optionName": "Title", "name": "Default Title"}],
            }
            product_input: dict[str, Any] = {
                "title": payload.get("title"),
                "productOptions": [{"name": "Title", "values": [{"name": "Default Title"}]}],
                "variants": [variant_input],
            }
            # REAL FINDING: productSet with no `identifier` ALWAYS creates a new product, even for a SKU
            # that already exists - it is not an implicit upsert-by-SKU the way the simulator (and
            # WooCommerce's real REST API) both behave. Confirmed against the real store: an "update"
            # call with no identifier produced a second, distinct product gid instead of updating the
            # first. Fixed by looking up any existing product for this SKU first (a real query, not
            # cached/assumed) and passing identifier: {id: ...} when found, exactly mirroring
            # WooCommerceConnector._find_product_by_sku's role for the real WooCommerce connector.
            variables: dict[str, Any] = {"input": product_input, "synchronous": True}
            sku = payload.get("sku")
            existing_gid = self._find_product_gid_by_sku(sku) if sku else None
            if existing_gid:
                variables["identifier"] = {"id": existing_gid}
            data = self._graphql(
                """mutation($input: ProductSetInput!, $identifier: ProductSetIdentifiers, $synchronous: Boolean) {
                    productSet(input: $input, identifier: $identifier, synchronous: $synchronous) {
                        product { id title }
                        userErrors { field message }
                    }
                }""",
                variables,
                user_errors_path=("productSet", "userErrors"),
            )
            product = data["productSet"]["product"]
            return MutationResult(status="accepted", external_ref=product["id"], payload=product)
        if request.action == "set_inventory":
            # REAL FINDINGS, all confirmed against the real store:
            # 1. `ignoreCompareQuantity` is not a field on InventorySetQuantitiesInput in this store's
            #    current schema ("Field is not defined") - the assumption came from secondary
            #    documentation describing an older/different compare-and-swap surface.
            # 2. InventoryQuantityInput instead REQUIRES `changeFromQuantity` (the currently-known
            #    quantity, for compare-and-swap safety) - there is no unconditional absolute-set path.
            # 3. `external_product_id` here is a PRODUCT gid, not an InventoryItem gid (see fetch()'s
            #    "inventory" branch finding) - resolved via _inventory_item_for_product.
            # 4. Both inventorySetQuantities AND inventoryActivate require the @idempotent directive
            #    ("required for this mutation but was not provided") - not only refundCreate, as
            #    originally documented; a broader real-API pattern than assumed.
            # 5. A freshly created product's variant has NO InventoryLevel at any location - not a level
            #    with quantity 0, no level record AT ALL - until explicitly activated there via
            #    inventoryActivate.
            # 6. THE DEEPEST FINDING: a productSet-created variant's InventoryItem.tracked defaults to
            #    false. While untracked, BOTH inventoryActivate(available:...) AND inventorySetQuantities
            #    return status="accepted", zero userErrors, a real inventoryAdjustmentGroup/inventoryLevel
            #    id - and have COMPLETELY NO EFFECT on the item's actual quantity, which stays 0
            #    regardless of what was requested. Confirmed live, repeatedly, isolating every other
            #    variable (literal vs. variable argument syntax made no difference - a red herring from
            #    an earlier, less isolated test). Only after inventoryItemUpdate(input: {tracked: true})
            #    does a subsequent quantity mutation actually take visible effect. Fixed by unconditionally
            #    ensuring tracked=true before every activate/set call - cheap, idempotent-safe, and the
            #    only way this action can be trusted to have actually done anything.
            location_gid = self._ensure_location_gid()
            inventory_item_gid, _sku, current_quantity, level_active = self._inventory_item_for_product(payload["external_product_id"], location_gid)
            idempotency_key = self._idempotent_uuid(request.idempotency_key)
            self._graphql(
                """mutation($id: ID!, $input: InventoryItemInput!, $idempotencyKey: String!) {
                    inventoryItemUpdate(id: $id, input: $input) @idempotent(key: $idempotencyKey) {
                        inventoryItem { id tracked }
                        userErrors { field message }
                    }
                }""",
                {"id": inventory_item_gid, "input": {"tracked": True}, "idempotencyKey": self._idempotent_uuid(f"{request.idempotency_key}:track")},
                user_errors_path=("inventoryItemUpdate", "userErrors"),
            )
            if not level_active:
                data = self._graphql(
                    """mutation($id: ID!, $locationId: ID!, $available: Int!, $idempotencyKey: String!) {
                        inventoryActivate(inventoryItemId: $id, locationId: $locationId, available: $available) @idempotent(key: $idempotencyKey) {
                            inventoryLevel { id }
                            userErrors { field message }
                        }
                    }""",
                    {"id": inventory_item_gid, "locationId": location_gid, "available": int(payload["quantity"]), "idempotencyKey": idempotency_key},
                    user_errors_path=("inventoryActivate", "userErrors"),
                )
                return MutationResult(status="accepted", payload=data["inventoryActivate"])
            data = self._graphql(
                """mutation($input: InventorySetQuantitiesInput!, $idempotencyKey: String!) {
                    inventorySetQuantities(input: $input) @idempotent(key: $idempotencyKey) {
                        inventoryAdjustmentGroup { id }
                        userErrors { field message }
                    }
                }""",
                {"input": {
                    "name": "available",
                    "reason": "correction",
                    "quantities": [{
                        "inventoryItemId": inventory_item_gid,
                        "locationId": location_gid,
                        "quantity": int(payload["quantity"]),
                        "changeFromQuantity": current_quantity or 0,
                    }],
                }, "idempotencyKey": idempotency_key},
                user_errors_path=("inventorySetQuantities", "userErrors"),
            )
            return MutationResult(status="accepted", payload=data["inventorySetQuantities"])
        if request.action == "create_fulfilment":
            order_id = payload["external_order_id"]
            fo_data = self._graphql(
                "query($id: ID!) { order(id: $id) { fulfillmentOrders(first: 5) { nodes { id status } } } }",
                {"id": self._order_gid(order_id)},
            )
            fulfillment_orders = [fo for fo in fo_data["order"]["fulfillmentOrders"]["nodes"] if fo["status"] == "OPEN"]
            if not fulfillment_orders:
                raise ValueError(f"order {order_id} has no OPEN fulfillment orders to fulfil")
            data = self._graphql(
                """mutation($fulfillment: FulfillmentInput!) {
                    fulfillmentCreate(fulfillment: $fulfillment) {
                        fulfillment { id status }
                        userErrors { field message }
                    }
                }""",
                {"fulfillment": {
                    "lineItemsByFulfillmentOrder": [{"fulfillmentOrderId": fo["id"]} for fo in fulfillment_orders],
                    "notifyCustomer": False,
                }},
                user_errors_path=("fulfillmentCreate", "userErrors"),
            )
            return MutationResult(status="accepted", payload=data["fulfillmentCreate"]["fulfillment"])
        if request.action == "cancel_order":
            order_id = payload["external_order_id"]
            data = self._graphql(
                """mutation($orderId: ID!, $reason: OrderCancelReason!, $refund: Boolean!, $restock: Boolean!) {
                    orderCancel(orderId: $orderId, reason: $reason, refund: $refund, restock: $restock, staffNote: "Cancelled via Sanocea") {
                        job { id }
                        userErrors { field message }
                    }
                }""",
                {
                    "orderId": self._order_gid(order_id),
                    "reason": payload.get("reason", "OTHER"),
                    "refund": bool(payload.get("refund", False)),
                    "restock": bool(payload.get("restock", True)),
                },
                user_errors_path=("orderCancel", "userErrors"),
            )
            return MutationResult(status="accepted", async_operation_id=data["orderCancel"]["job"]["id"], payload=data["orderCancel"])
        if request.action == "create_refund":
            # REAL FINDING: a refund transaction on any gateway OTHER than 'cash', 'store-credit', or
            # 'exchange-credit' requires a `parentId` referencing the ORIGINAL sale transaction -
            # confirmed live: "Transactions not on 'store-credit', 'exchange-credit', or 'cash' gateways
            # require a parent_id". An order with no prior captured payment transaction (e.g. one
            # created without an explicit transactions input) has no parent to reference. 'cash' is
            # Shopify's own sanctioned gateway for exactly this manual/ledger-refund case - the same
            # concept WooCommerceConnector's api_refund=false already models for COD orders - so it is
            # the correct default here, not merely a workaround for a missing parent transaction.
            order_id = payload["external_order_id"]
            refund_input: dict[str, Any] = {"orderId": self._order_gid(order_id)}
            if payload.get("amount") is not None:
                refund_input["transactions"] = [{
                    "orderId": self._order_gid(order_id),
                    "kind": "REFUND",
                    "gateway": payload.get("gateway", "cash"),
                    "amount": f"{payload['amount'] / 100:.2f}",
                }]
            if payload.get("reason"):
                refund_input["note"] = payload["reason"]
            data = self._graphql(
                """mutation RefundCreate($input: RefundInput!, $idempotencyKey: String!) {
                    refundCreate(input: $input) @idempotent(key: $idempotencyKey) {
                        refund { id totalRefundedSet { presentmentMoney { amount currencyCode } } }
                        userErrors { field message }
                    }
                }""",
                {"input": refund_input, "idempotencyKey": self._idempotent_uuid(request.idempotency_key)},
                user_errors_path=("refundCreate", "userErrors"),
            )
            refund = data["refundCreate"]["refund"]
            return MutationResult(status="accepted", external_ref=refund["id"], payload=refund)
        raise ValueError(f"unsupported Shopify (live) mutation action: {request.action}")

    def register_webhooks(self, merchant_id: str, channel_id: str) -> MutationResult:
        # REAL FINDING: webhookSubscriptionCreate is NOT idempotent by itself - a second call for the
        # exact same (topic, uri) pair fails outright ("Address for this topic has already been taken"),
        # confirmed live on a real repeat certification run against an unchanged tunnel URL. Made
        # idempotent HERE by listing existing subscriptions first and reusing any that already match,
        # rather than either fabricating success or letting a legitimate re-run fail.
        if not self.webhook_delivery_base_url:
            raise ValueError("webhook_delivery_base_url was not configured for this ShopifyLiveConnector instance")
        delivery_url = f"{self.webhook_delivery_base_url}/webhooks/shopify_live/{merchant_id}"
        existing = self._graphql(
            """query { webhookSubscriptions(first: 50) {
                nodes { id topic endpoint { __typename ... on WebhookHttpEndpoint { callbackUrl } } }
            } }""",
            {},
        )
        existing_by_topic = {
            n["topic"]: n["id"]
            for n in existing.get("webhookSubscriptions", {}).get("nodes", [])
            if n.get("endpoint", {}).get("__typename") == "WebhookHttpEndpoint" and n["endpoint"].get("callbackUrl") == delivery_url
        }
        webhook_ids = []
        for topic in ("ORDERS_CREATE", "ORDERS_UPDATED", "ORDERS_CANCELLED"):
            if topic in existing_by_topic:
                webhook_ids.append(existing_by_topic[topic])
                continue
            data = self._graphql(
                """mutation($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
                    webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
                        webhookSubscription { id topic }
                        userErrors { field message }
                    }
                }""",
                {"topic": topic, "webhookSubscription": {"uri": delivery_url}},
                user_errors_path=("webhookSubscriptionCreate", "userErrors"),
            )
            webhook_ids.append(data["webhookSubscriptionCreate"]["webhookSubscription"]["id"])
        return MutationResult(status="accepted", payload={"webhook_ids": webhook_ids, "delivery_url": delivery_url})

    def reconcile(self, merchant_id: str, scope: dict[str, Any]) -> list[dict[str, Any]]:
        external_id = str(scope["external_order_id"])
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_id)
        if not mapping:
            return []
        order = self.store.get(Order, merchant_id, mapping.sanocea_id)
        external = self.fetch(merchant_id, "order", external_id)
        external_status = "CANCELLED" if external.get("cancelledAt") else ("PAID" if external.get("displayFinancialStatus") == "PAID" else "UNKNOWN")
        if order.status != external_status:
            from sanocea.packages.domain_contract.models import ExceptionRecord

            exc = ExceptionRecord(
                merchant_id=merchant_id, severity="warning", category="reconciliation_divergence",
                message=f"Order {order.id} canonical={order.status} external={external_status}",
                object_id=order.id, remediation_options=["refresh_from_source", "manual_review"],
            )
            self.store.put(exc)
            self.audit.record(
                merchant_id=merchant_id, actor="reconciliation", source=self.name, action="divergence_detected",
                object_type="Order", object_id=order.id, result="exception_created", error=exc.message,
            )
            return [{"order_id": order.id, "external_status": external_status, "exception_id": exc.id}]
        return []

    # --- GraphQL transport -----------------------------------------------------------------------------

    def _graphql(self, query: str, variables: dict[str, Any], *, user_errors_path: tuple[str, ...] | None = None) -> dict[str, Any]:
        """Bounded to AT MOST two attempts total: the original call, and - only if it failed with an
        auth-shaped (401/403) response plausibly caused by an expired/revoked token - exactly one retry
        with a freshly-fetched token. A second consecutive auth failure is raised immediately, never
        retried again - this is a plain `range(2)` loop, structurally incapable of looping unboundedly.
        This entire retry happens inside ONE call from _execute_mutation()'s perspective, so
        IdempotencyService.run_once() (which wraps _execute_mutation as a single `operation()`) never
        sees more than one logical attempt - a token refresh can never register as a new mutation."""
        last_auth_error: ShopifyAuthenticationError | None = None
        for attempt in range(2):
            token = self._token_manager.get_token()
            try:
                return self._graphql_once(query, variables, token, user_errors_path=user_errors_path)
            except ShopifyAuthenticationError as exc:
                last_auth_error = exc
                self._token_manager.invalidate()
                if attempt == 0:
                    continue
                raise
        assert last_auth_error is not None  # unreachable: the loop above always returns or raises
        raise last_auth_error

    def _graphql_once(self, query: str, variables: dict[str, Any], token: str, *, user_errors_path: tuple[str, ...] | None) -> dict[str, Any]:
        url = f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"
        body = json.dumps({"query": query, "variables": variables}).encode()
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                parsed = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if exc.code in (401, 403):
                # Plausibly an expired/revoked access token - never the client secret, never the token
                # itself, in this message. Handled by _graphql()'s bounded retry-once above.
                raise ShopifyAuthenticationError(f"Shopify Admin API rejected the request (HTTP {exc.code}) against {self.shop_domain} - plausibly an expired/revoked access token") from exc
            if exc.code == 429:
                raise RuntimeError(f"Shopify Admin API 429 rate limited: {detail}") from exc
            if exc.code >= 500:
                raise RuntimeError(f"Shopify Admin API {exc.code}: {detail}") from exc
            raise ValueError(f"Shopify Admin API {exc.code}: {detail}") from exc
        if parsed.get("errors"):
            # GraphQL-level errors (distinct from userErrors, which are business-logic validation
            # failures inside a successful HTTP 200 response). A THROTTLED error code here means the
            # query-cost leaky bucket (extensions.cost) is exhausted - genuinely different rate-limit
            # semantics from WooCommerce's/REST's plain 429, so surfaced as its own RuntimeError rather
            # than reused generic handling.
            codes = {e.get("extensions", {}).get("code") for e in parsed["errors"]}
            if "THROTTLED" in codes:
                raise RuntimeError(f"Shopify Admin GraphQL API throttled (cost budget exhausted): {parsed['errors']}")
            raise ValueError(f"Shopify Admin GraphQL API errors: {parsed['errors']}")
        data = parsed.get("data") or {}
        if user_errors_path:
            node = data
            for key in user_errors_path[:-1]:
                node = node.get(key, {}) if node else {}
            user_errors = (node or {}).get(user_errors_path[-1]) if node else None
            if user_errors:
                raise ValueError(f"Shopify mutation userErrors: {user_errors}")
        return data

    def _ensure_location_gid(self) -> str:
        """Discovers and caches the store's primary inventory location - never configured manually. A
        merchant onboarding onto shopify_live supplies no location value at all; the first inventory
        operation triggers this one-time (per connector instance) lookup."""
        if self.default_location_gid:
            return self.default_location_gid
        data = self._graphql("query { locations(first: 1) { nodes { id } } }", {})
        nodes = data.get("locations", {}).get("nodes") or []
        if not nodes:
            raise ValueError(f"store {self.shop_domain} has no locations - cannot perform inventory operations")
        self.default_location_gid = nodes[0]["id"]
        return self.default_location_gid

    # --- GID helpers -------------------------------------------------------------------------------

    def _product_gid(self, external_id: str) -> str:
        return external_id if external_id.startswith("gid://") else f"gid://shopify/Product/{external_id}"

    def _order_gid(self, external_id: str) -> str:
        return external_id if external_id.startswith("gid://") else f"gid://shopify/Order/{external_id}"

    def _inventory_item_for_product(self, product_external_id: str, location_gid: str) -> tuple[str, str | None, int, bool]:
        """Resolves a real Shopify InventoryItem (a separate entity, scoped to one ProductVariant) and
        its current available quantity at `location_gid` from a PRODUCT gid - the only id Sanocea's own
        domain model tracks for a published listing. Returns (inventory_item_gid, sku, available)."""
        data = self._graphql(
            """query($id: ID!, $locationId: ID!) {
                product(id: $id) {
                    variants(first: 1) {
                        nodes {
                            sku
                            inventoryItem {
                                id
                                inventoryLevel(locationId: $locationId) { quantities(names: ["available"]) { quantity } }
                            }
                        }
                    }
                }
            }""",
            {"id": self._product_gid(product_external_id), "locationId": location_gid},
        )
        variant = (data.get("product", {}).get("variants", {}).get("nodes") or [{}])[0]
        inventory_item = variant.get("inventoryItem") or {}
        inventory_item_gid = inventory_item.get("id")
        if not inventory_item_gid:
            raise ValueError(f"product {product_external_id} has no variant/inventoryItem to resolve inventory against")
        # REAL FINDING: inventoryLevel(locationId:) returns null - not a level with quantity 0 - when
        # the item has never been activated at that location. A freshly created product's variant is
        # NOT active at any location by default; this is how set_inventory below decides whether to
        # activate (inventoryActivate) or update (inventorySetQuantities).
        level = inventory_item.get("inventoryLevel")
        level_active = level is not None
        quantities = (level or {}).get("quantities") or []
        available = next((q["quantity"] for q in quantities if q), 0)
        return inventory_item_gid, variant.get("sku"), available, level_active

    def _find_product_gid_by_sku(self, sku: str) -> str | None:
        """A real search query (Shopify's search syntax on the productVariants root field), not a
        cache/assumption - the real ground truth productSet's own `identifier` argument needs to update
        an existing product instead of creating a duplicate."""
        data = self._graphql(
            "query($q: String!) { productVariants(first: 1, query: $q) { nodes { product { id } } } }",
            {"q": f"sku:{sku}"},
        )
        nodes = data.get("productVariants", {}).get("nodes") or []
        return nodes[0]["product"]["id"] if nodes else None

    def _idempotent_uuid(self, idempotency_key: str) -> str:
        """refundCreate requires @idempotent(key: "uuid") as of API version 2026-04 - a deterministic
        UUID5 derived from Sanocea's own idempotency_key so a retried Sanocea mutation is idempotent on
        Shopify's side too (same input key -> same UUID -> same Shopify-side dedup), never a fresh
        random UUID per call, which would defeat the point."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sanocea:{idempotency_key}"))
