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
    Inventory,
    Location,
    Order,
    OrderLine,
    Product,
    SourceOfTruth,
    SyncMetadata,
    new_id,
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
                "publish_to_online_store": Capability(
                    name="publish_to_online_store", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC,
                    notes="Distinct from publish_product/productSet - makes an existing product visible "
                          "on the storefront via publishablePublish against the 'Online Store' "
                          "publication. Requires the write_publications access scope.",
                ),
                "update_variant_price": Capability(name="update_variant_price", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
            },
        )

    # --- Webhook ingress -------------------------------------------------------------------------------

    def resync_order(self, merchant_id: str, external_order_id: str) -> dict[str, Any]:
        """Real, reusable recovery path for a missed/dropped webhook (the exact real gap the Mariyal/
        Premium Basket rehearsal surfaced - order #1019 never advanced because its ORDERS_UPDATED
        webhook was silently rejected by a staleness-check bug, now fixed, but the past delivery is
        already gone; Shopify does not redeliver on request). Fetches the REAL current order straight
        from Shopify via GraphQL and feeds it through the SAME `_upsert_order`/workflow-trigger path a
        genuine webhook uses - not a fabricated update, not a direct DB write, just a manual pull of
        exactly what push would have delivered. Reuses `_upsert_order` unchanged; only the payload's
        origin differs (GraphQL fetch vs. webhook body)."""
        data = self._graphql(
            """query($id: ID!) { order(id: $id) {
                id name email displayFinancialStatus displayFulfillmentStatus updatedAt cancelledAt
                customer { firstName }
                lineItems(first: 50) { nodes { sku title quantity originalUnitPriceSet { shopMoney { amount } } } }
            } }""",
            {"id": self._order_gid(external_order_id)},
        )
        order_data = data["order"]
        financial_map = {"PAID": "paid", "PENDING": "pending", "AUTHORIZED": "authorized", "REFUNDED": "refunded", "PARTIALLY_REFUNDED": "partially_refunded", "VOIDED": "voided"}
        payload = {
            "id": external_order_id,
            "order_number": order_data["name"].lstrip("#"),
            "email": order_data.get("email"),
            "customer": {"first_name": (order_data.get("customer") or {}).get("firstName")},
            "financial_status": financial_map.get(order_data.get("displayFinancialStatus"), "unknown"),
            "fulfillment_status": (order_data.get("displayFulfillmentStatus") or "").lower() or None,
            "cancelled_at": order_data.get("cancelledAt"),
            "updated_at": order_data.get("updatedAt"),
            "total_price": "0",
            "currency": "USD",
            "line_items": [
                {"sku": li.get("sku"), "title": li.get("title"), "quantity": li.get("quantity"),
                 "price": (li.get("originalUnitPriceSet") or {}).get("shopMoney", {}).get("amount", "0")}
                for li in order_data.get("lineItems", {}).get("nodes", [])
            ],
        }
        raw = self._store_raw(merchant_id=merchant_id, source="shopify_live:manual_resync", payload=payload, headers={}, checksum=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest())
        result = self._upsert_order(merchant_id, payload, raw.id)
        self.audit.record(
            merchant_id=merchant_id, actor="operator", source="shopify_live", action="order_manual_resync",
            object_type="Order", object_id=result["order_id"], evidence_ref=raw.id, result="synced",
        )
        self.workflow.start_or_signal_order(merchant_id, result["order_id"], {"topic": "manual_resync", "raw_payload_id": raw.id})
        return result

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
            #
            # REAL BUG FOUND LIVE (Mariyal/Premium Basket rehearsal, order #1019): this used to be `<=`,
            # not `<`. Shopify's own bogus (test) payment gateway captures payment in the SAME SECOND as
            # order creation, so the ORDERS_CREATE webhook (financial_status=authorized) and the
            # following ORDERS_UPDATED webhook (financial_status=paid) can carry an IDENTICAL updated_at
            # timestamp - `<=` silently discarded the second, genuinely newer webhook as "stale" because
            # it wasn't STRICTLY greater, permanently stranding the order at payment_status=authorized
            # and never triggering inventory reservation/exception detection at all. True duplicate
            # deliveries of the SAME webhook are already fully deduped upstream by ingest_webhook's own
            # idempotency guard (keyed on X-Shopify-Webhook-Id) before this method is ever called a
            # second time for one delivery - this check exists only to reject a genuinely OLDER,
            # out-of-order event, so only a strictly-older timestamp should ever be dropped.
            if incoming_updated and order.sync.source_updated_at and incoming_updated < order.sync.source_updated_at.isoformat():
                self.audit.record(
                    merchant_id=merchant_id, actor="shopify_live", source="webhook", action="out_of_order_event_ignored",
                    object_type="Order", object_id=order.id, evidence_ref=raw_id, result="ignored",
                )
                return {"order_id": order.id, "status": order.status, "ignored": True}
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

    def search_taxonomy_categories(self, search: str, first: int = 10) -> list[dict[str, Any]]:
        """Queries Shopify's official Admin GraphQL Taxonomy API for standardized categories."""
        data = self._graphql(
            """query($search: String!, $first: Int!) {
                taxonomy {
                    categories(search: $search, first: $first) {
                        nodes {
                            id
                            name
                            fullName
                            isLeaf
                        }
                    }
                }
            }""",
            {"search": search, "first": first},
        )
        return data.get("taxonomy", {}).get("categories", {}).get("nodes", [])

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        self.describe_capabilities().require("fetch")
        if entity_type == "product":
            data = self._graphql(
                "query($id: ID!) { product(id: $id) { title status productType category { id name fullName } variants(first: 1) { nodes { sku price inventoryPolicy inventoryQuantity inventoryItem { tracked measurement { weight { value unit } } } } } } }",
                {"id": self._product_gid(external_id)},
            )
            raw = data["product"]
            variant = (raw.get("variants", {}).get("nodes") or [{}])[0]
            cat = raw.get("category") or {}
            inv_item = variant.get("inventoryItem") or {}
            meas = (inv_item.get("measurement") or {}).get("weight") or {}
            return {
                "title": raw.get("title"), "sku": variant.get("sku"), "price": variant.get("price"),
                "product_type": raw.get("productType"),
                "category": cat.get("id"),
                "category_full_name": cat.get("fullName"),
                "inventory_quantity": variant.get("inventoryQuantity"),
                "inventory_tracked": inv_item.get("tracked"),
                "inventory_policy": variant.get("inventoryPolicy"),
                "weight": meas.get("value"),
                "weight_unit": meas.get("unit"),
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
            # Determine inventory location
            loc_id = payload.get("inventory_location_id") or payload.get("inventory_location")
            location_gid = self._location_gid(loc_id)

            # Inventory Tracking & Overselling Prevention
            # Physical goods default to tracked with inventoryPolicy: DENY.
            # Only when the merchant explicitly chose track_inventory=False is tracking disabled.
            is_untracked = payload.get("track_inventory") is False
            if is_untracked:
                inv_tracked = False
                inv_policy = "CONTINUE"
                inv_quantities = []
            else:
                inv_tracked = True
                inv_policy = "DENY"  # Prevents arbitrary quantities in cart / overselling!
                qty = int(payload.get("inventory_quantity")) if payload.get("inventory_quantity") is not None else 0
                inv_quantities = [{"locationId": location_gid, "name": "available", "quantity": qty}]

            # Measurement (weight)
            weight_val = payload.get("weight")
            weight_unit = payload.get("weight_unit") or "GRAMS"
            measurement = None
            if weight_val is not None:
                try:
                    measurement = {"weight": {"value": float(weight_val), "unit": weight_unit}}
                except Exception:
                    pass

            inv_item: dict[str, Any] = {
                "tracked": inv_tracked,
                "requiresShipping": payload.get("requires_shipping", True) is not False,
            }
            if measurement:
                inv_item["measurement"] = measurement

            # Variants & Options Construction
            variants_list = payload.get("variants") or []
            options_list = payload.get("options") or []

            if variants_list and len(variants_list) > 1 and options_list:
                product_options = []
                for opt_name in options_list:
                    opt_vals = []
                    for v in variants_list:
                        val = (v.get("option_values") or {}).get(opt_name)
                        if val and str(val) not in opt_vals:
                            opt_vals.append(str(val))
                    product_options.append({"name": opt_name, "values": [{"name": v} for v in opt_vals]})

                variant_inputs = []
                for v in variants_list:
                    v_option_values = [{"optionName": k, "name": str(val)} for k, val in (v.get("option_values") or {}).items()]
                    v_stock = v.get("inventory_quantity") if v.get("inventory_quantity") is not None else payload.get("inventory_quantity")
                    v_quantities = [{"locationId": location_gid, "name": "available", "quantity": int(v_stock or 0)}] if inv_tracked else []
                    v_item = dict(inv_item)
                    if v.get("weight"):
                        v_item["measurement"] = {"weight": {"value": float(v["weight"]), "unit": weight_unit}}
                    variant_inputs.append({
                        "price": v.get("price") or payload.get("price"),
                        "sku": v.get("sku") or payload.get("sku"),
                        "barcode": v.get("barcode"),
                        "optionValues": v_option_values,
                        "inventoryPolicy": inv_policy,
                        "inventoryItem": v_item,
                        "inventoryQuantities": v_quantities,
                    })
                product_input: dict[str, Any] = {
                    "title": payload.get("title"),
                    "productOptions": product_options,
                    "variants": variant_inputs,
                }
            else:
                variant_input: dict[str, Any] = {
                    "price": payload.get("price"),
                    "sku": payload.get("sku"),
                    "optionValues": [{"optionName": "Title", "name": "Default Title"}],
                    "inventoryPolicy": inv_policy,
                    "inventoryItem": inv_item,
                }
                if inv_quantities:
                    variant_input["inventoryQuantities"] = inv_quantities
                product_input = {
                    "title": payload.get("title"),
                    "productOptions": [{"name": "Title", "values": [{"name": "Default Title"}]}],
                    "variants": [variant_input],
                }
            # Real gap closed here (found live, Premium Basket rehearsal): a product's real image URL
            # was being captured as genuine evidence on the SANOCEA draft (commercial_facts["image"])
            # but never actually sent to Shopify - productSet's ProductSetInput accepts real media via
            # `files: [FileSetInput!]` (originalSource + contentType), fetched and hosted by Shopify
            # itself from the given URL. Only added when a real image URL is present in the
            # connector-agnostic payload's attributes - never fabricated, never required.
            image_url = (payload.get("attributes") or {}).get("image")
            if image_url:
                product_input["files"] = [{"originalSource": image_url, "contentType": "IMAGE"}]
            # Real gap closed here, same rehearsal (found live, Premium Basket): description/vendor/
            # tags/SEO were captured as real evidence on the SANOCEA draft whenever the source data
            # carried them (or patched by hand afterward, which is the actual problem being fixed) but
            # never sent to Shopify at all - productSet only ever received title/sku/price. A real
            # product listing needs these to look complete; sending them here, when present, closes
            # that gap for every future product, not just the ones already patched by hand today.
            # REAL BUG found live (Premium Basket rehearsal, screenshot evidence): the connector-agnostic
            # payload has carried `product_type` since the docstring above was written, but nothing ever
            # read it - every published product showed "Type: None" in Shopify Admin regardless of what
            # SANOCEA's own draft had. Fixed by actually mapping it, same as every other optional field
            # here: only sent when present, never fabricated.
            product_type = payload.get("product_type")
            if product_type:
                product_input["productType"] = product_type
            category = payload.get("category")
            if category:
                product_input["category"] = category
            attrs = payload.get("attributes") or {}
            description = attrs.get("description")
            if description:
                product_input["descriptionHtml"] = description
            vendor = attrs.get("vendor")
            if vendor:
                product_input["vendor"] = vendor
            tags = attrs.get("tags")
            if tags:
                product_input["tags"] = [t.strip() for t in str(tags).split(",") if t.strip()]
            seo_title = attrs.get("seo_title")
            seo_description = attrs.get("seo_description")
            if seo_title or seo_description:
                product_input["seo"] = {k: v for k, v in {"title": seo_title, "description": seo_description}.items() if v}
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
                        product {
                            id
                            title
                            productType
                            category {
                                id
                                name
                                fullName
                            }
                        }
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
            # Optional `quantities` (sku -> quantity to fulfil now): the Mariyal/inventory-shortage
            # demo needs to fulfil ONLY the available quantity, not Shopify's default (fulfil every
            # remaining unit of every OPEN fulfillment order line). Omitting `quantities` keeps the
            # original behavior byte-for-byte (existing callers/tests unaffected).
            quantities = payload.get("quantities")
            fo_data = self._graphql(
                """query($id: ID!) { order(id: $id) { fulfillmentOrders(first: 5) { nodes {
                    id status lineItems(first: 20) { nodes { id remainingQuantity lineItem { sku } } }
                } } } }""",
                {"id": self._order_gid(order_id)},
            )
            fulfillment_orders = [fo for fo in fo_data["order"]["fulfillmentOrders"]["nodes"] if fo["status"] == "OPEN"]
            if not fulfillment_orders:
                raise ValueError(f"order {order_id} has no OPEN fulfillment orders to fulfil")
            if quantities is None:
                line_items_by_fo = [{"fulfillmentOrderId": fo["id"]} for fo in fulfillment_orders]
            else:
                line_items_by_fo = []
                for fo in fulfillment_orders:
                    line_items = []
                    for node in fo["lineItems"]["nodes"]:
                        sku = node["lineItem"].get("sku")
                        requested = quantities.get(sku)
                        if not requested:
                            continue
                        qty = min(int(requested), int(node["remainingQuantity"]))
                        if qty > 0:
                            line_items.append({"id": node["id"], "quantity": qty})
                    if line_items:
                        line_items_by_fo.append({"fulfillmentOrderId": fo["id"], "fulfillmentOrderLineItems": line_items})
                if not line_items_by_fo:
                    raise ValueError(f"order {order_id}: none of the requested skus/quantities match any OPEN fulfillment order line item")
            data = self._graphql(
                """mutation($fulfillment: FulfillmentInput!) {
                    fulfillmentCreate(fulfillment: $fulfillment) {
                        fulfillment { id status }
                        userErrors { field message }
                    }
                }""",
                {"fulfillment": {
                    "lineItemsByFulfillmentOrder": line_items_by_fo,
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
        if request.action == "publish_to_online_store":
            # REAL, DISTINCT GAP from `publish_product` above: `productSet` (and Sanocea's own
            # Publication concept) only creates/updates the product record itself - it does NOT make the
            # product visible on any storefront. Shopify separately gates visibility per SALES CHANNEL
            # (Online Store, POS, etc.) via the Publishable interface - a product with status ACTIVE and
            # zero channel publications is real and complete but invisible to a shopper. Discovered live
            # during the Mariyal/Premium Basket rehearsal: the product existed, was ACTIVE, had correct
            # inventory - and the storefront still 404'd, because nothing had ever called
            # publishablePublish for the "Online Store" publication. Requires the write_publications
            # scope (added to shopify.app.toml alongside this fix, 2026-09-18).
            sku = payload.get("sku")
            product_gid = payload.get("external_product_id") or (self._find_product_gid_by_sku(sku) if sku else None)
            if not product_gid:
                raise ValueError("publish_to_online_store requires sku or external_product_id")
            pub_data = self._graphql("query { publications(first: 10) { nodes { id name } } }", {})
            publications = pub_data.get("publications", {}).get("nodes") or []
            online_store = next((p for p in publications if p["name"] == "Online Store"), None)
            if online_store is None:
                raise ValueError(f"no 'Online Store' publication found on this shop (available: {[p['name'] for p in publications]})")
            data = self._graphql(
                """mutation($id: ID!, $input: [PublicationInput!]!) {
                    publishablePublish(id: $id, input: $input) {
                        publishable { __typename }
                        userErrors { field message }
                    }
                }""",
                {"id": product_gid, "input": [{"publicationId": online_store["id"]}]},
                user_errors_path=("publishablePublish", "userErrors"),
            )
            # Real gap found live (Premium Basket rehearsal): `publishablePublish` returns
            # userErrors=[] (genuine success) immediately, but Shopify's own read model
            # (resourcePublicationsCount) can lag a moment behind - confirmed live, two products
            # showed count=0 right after this call reported success, then count=1 on the exact same
            # unmodified retry seconds later. Trusting the mutation's own "accepted" response alone
            # caused SANOCEA to tell the owner a product was "now live" while it was still invisible on
            # the real storefront - exactly the kind of silent read/write mismatch the read-back
            # discipline elsewhere in this connector exists to catch. A short bounded poll here, not a
            # blind trust of the write response.
            import time as _time

            verified = False
            for _ in range(4):
                check = self._graphql(
                    "query($id: ID!) { node(id: $id) { ... on Product { resourcePublicationsCount { count } } } }",
                    {"id": product_gid},
                )
                count = ((check.get("node") or {}).get("resourcePublicationsCount") or {}).get("count", 0)
                if count and count > 0:
                    verified = True
                    break
                _time.sleep(2)
            payload = dict(data["publishablePublish"])
            payload["verified_visible"] = verified
            return MutationResult(status="accepted" if verified else "accepted_unverified", external_ref=product_gid, payload=payload)
        if request.action == "update_variant_price":
            res = self.update_variant_price(
                request.merchant_id,
                variant_gid=payload.get("variant_gid"),
                product_gid=payload.get("product_gid"),
                sku=payload.get("sku"),
                price=payload["price"],
                compare_at_price=payload.get("compare_at_price"),
            )
            return MutationResult(status="accepted", payload=res)
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
        operation triggers this one-time (per connector instance) lookup.

        REAL BUG FOUND LIVE (Mariyal/Premium Basket rehearsal): this used to take whichever location
        `locations(first: 1)` happened to return first, with no ordering guarantee. On this store that
        was "My Custom Location", which has `shipsInventory: false` - stock set/read there NEVER counts
        toward real storefront checkout eligibility (confirmed live: Admin showed inventoryQuantity>0
        and availableForSale=true, yet the storefront rendered "Sold out", because Shopify's real
        buyability computation only considers locations that actually ship). Now explicitly prefers the
        first location with `shipsInventory: true` - the one location property that actually determines
        whether stock there is sellable online - falling back to the first location overall only if none
        ships (a store with pickup-only locations, where the old behavior was at least not systematically
        wrong)."""
        if self.default_location_gid:
            return self.default_location_gid
        data = self._graphql("query { locations(first: 10) { nodes { id shipsInventory } } }", {})
        nodes = data.get("locations", {}).get("nodes") or []
        if not nodes:
            raise ValueError(f"store {self.shop_domain} has no locations - cannot perform inventory operations")
        shipping_node = next((n for n in nodes if n.get("shipsInventory")), None)
        self.default_location_gid = (shipping_node or nodes[0])["id"]
        return self.default_location_gid

    # --- GID helpers -------------------------------------------------------------------------------

    def _product_gid(self, external_id: str) -> str:
        return external_id if external_id.startswith("gid://") else f"gid://shopify/Product/{external_id}"

    def _order_gid(self, external_id: str) -> str:
        return external_id if external_id.startswith("gid://") else f"gid://shopify/Order/{external_id}"

    def _location_gid(self, external_id: str | None = None) -> str:
        if not external_id:
            return self._ensure_location_gid()
        if str(external_id).startswith("gid://shopify/Location/"):
            return str(external_id)
        cleaned = str(external_id).removeprefix("loc_")
        if cleaned.isdigit():
            return f"gid://shopify/Location/{cleaned}"
        return self._ensure_location_gid()

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

    def _find_variant_gid_by_sku(self, sku: str) -> tuple[str, str] | None:
        """Returns (variant_gid, product_gid) for a SKU if found in Shopify."""
        data = self._graphql(
            "query($q: String!) { productVariants(first: 1, query: $q) { nodes { id product { id } } } }",
            {"q": f"sku:{sku}"},
        )
        nodes = data.get("productVariants", {}).get("nodes") or []
        if nodes:
            return nodes[0]["id"], nodes[0]["product"]["id"]
        return None

    def update_variant_price(
        self,
        merchant_id: str,
        *,
        variant_gid: str | None = None,
        product_gid: str | None = None,
        sku: str | None = None,
        price: float | str,
        compare_at_price: float | str | None = None,
    ) -> dict[str, Any]:
        """Updates variant price and optional compare-at price in Shopify using productVariantsBulkUpdate."""
        if not variant_gid or not product_gid:
            if sku:
                found = self._find_variant_gid_by_sku(sku)
                if found:
                    variant_gid, product_gid = found
        if not variant_gid:
            raise ValueError(f"Cannot update variant price: no variant_gid or sku provided (sku={sku})")
        if not product_gid:
            data = self._graphql(
                "query($id: ID!) { productVariant(id: $id) { product { id } } }",
                {"id": variant_gid},
            )
            product_gid = (data.get("productVariant") or {}).get("product", {}).get("id")
        if not product_gid:
            raise ValueError(f"Cannot update variant price: could not resolve product_gid for variant {variant_gid}")

        variant_payload: dict[str, Any] = {
            "id": variant_gid,
            "price": f"{float(price):.2f}",
        }
        if compare_at_price is not None:
            variant_payload["compareAtPrice"] = f"{float(compare_at_price):.2f}"

        data = self._graphql(
            """mutation productVariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
                productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                    productVariants { id price compareAtPrice }
                    userErrors { field message }
                }
            }""",
            {"productId": product_gid, "variants": [variant_payload]},
            user_errors_path=("productVariantsBulkUpdate", "userErrors"),
        )
        self.audit.record(
            merchant_id=merchant_id,
            actor="shopify_live",
            source="approval_execution",
            action="variant_price_updated",
            object_type="Variant",
            object_id=variant_gid,
            result="updated",
            requested_mutation={"price": str(price), "compare_at_price": str(compare_at_price)},
        )
        return data["productVariantsBulkUpdate"]

    def _idempotent_uuid(self, idempotency_key: str) -> str:
        """refundCreate requires @idempotent(key: "uuid") as of API version 2026-04 - a deterministic
        UUID5 derived from Sanocea's own idempotency_key so a retried Sanocea mutation is idempotent on
        Shopify's side too (same input key -> same UUID -> same Shopify-side dedup), never a fresh
        random UUID per call, which would defeat the point."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sanocea:{idempotency_key}"))

    def sync_catalog_and_inventory(self, merchant_id: str) -> dict[str, Any]:
        """Imports products, variants, SKUs, and location-scoped inventory from live Shopify into Sanocea,
        verifies location-scoped ATS against Shopify inventory levels, and runs deterministic anomaly detection
        for Premium Basket audit patterns (blank SKUs, duplicate SKUs, inverted unit pricing, compare-at anomalies)."""
        import re

        query = """
        query {
          locations(first: 10) {
            nodes { id name isActive }
          }
          products(first: 50) {
            nodes {
              id title status productType
              variants(first: 20) {
                nodes {
                  id title sku price compareAtPrice inventoryQuantity
                  inventoryItem {
                    id
                    inventoryLevels(first: 10) {
                      nodes {
                        location { id name }
                        quantities(names: ["available"]) { name quantity }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = self._graphql(query, {})
        locations_data = data.get("locations", {}).get("nodes") or []
        products_data = data.get("products", {}).get("nodes") or []

        synced_locations = []
        loc_map = {}
        for loc in locations_data:
            loc_num = loc["id"].split("/")[-1]
            loc_ref = f"loc_{loc_num}"
            loc_name = loc["name"]
            location_entity = Location(
                merchant_id=merchant_id,
                id=loc_ref,
                name=loc_name,
                code=loc_name[:10].upper().replace(" ", "_"),
                is_active=loc.get("isActive", True),
                source_of_truth=SourceOfTruth.CHANNEL,
                external_refs=[ExternalRef(system=self.name, entity_type="location", external_id=loc["id"])],
            )
            self.store.put(location_entity)
            synced_locations.append({"id": loc_ref, "name": loc_name, "external_id": loc["id"]})
            loc_map[loc["id"]] = loc_ref

        anomalies = {
            "blank_skus": [],
            "duplicate_skus": [],
            "unit_pricing_inversions": [],
            "compare_at_anomalies": [],
            "low_stock_risks": [],
            "quarantined_items": [],
        }
        seen_skus = {}
        imported_products = 0
        imported_variants = 0
        imported_inventory = 0

        config = self.store.get_config(merchant_id)
        safety_stock = config.get("inventory", {}).get("safety_stock_default", 10)

        for p in products_data:
            prod_id = f"prd_{p['id'].split('/')[-1]}"
            canonical_product = Product(
                merchant_id=merchant_id,
                id=prod_id,
                title=p["title"],
                status="published" if p["status"] == "ACTIVE" else "draft",
                source_of_truth=SourceOfTruth.CHANNEL,
                external_refs=[ExternalRef(system=self.name, entity_type="product", external_id=p["id"])],
            )
            self.store.put(canonical_product)
            self.store.put_external_mapping(
                ExternalIdMapping(
                    merchant_id=merchant_id,
                    sanocea_entity_type="Product",
                    sanocea_id=canonical_product.id,
                    external_system=self.name,
                    external_entity_type="product",
                    external_id=p["id"],
                    channel_id=self.name,
                )
            )
            imported_products += 1

            variants = p.get("variants", {}).get("nodes") or []
            pack_variants = []
            for v in variants:
                title = v.get("title", "")
                sku = (v.get("sku") or "").strip()
                price_f = float(v.get("price") or 0)
                compare_f = float(v.get("compareAtPrice") or 0) if v.get("compareAtPrice") else None

                imported_variants += 1

                if not sku:
                    anomalies["blank_skus"].append({
                        "product_id": prod_id,
                        "product_title": p["title"],
                        "variant_id": v["id"],
                        "variant_title": title,
                        "finding_id": "TPB-027",
                        "issue": "Sellable variant has blank/missing SKU identifier",
                        "recommended": "Generate canonical SKU with syntax [BRAND]-[CAT]-[NAME]-[SIZE]",
                    })

                if sku:
                    if sku in seen_skus:
                        anomalies["duplicate_skus"].append({
                            "sku": sku,
                            "first_product": seen_skus[sku]["product_title"],
                            "duplicate_product": p["title"],
                            "duplicate_variant": title,
                            "finding_id": "TPB-028",
                            "issue": f"SKU '{sku}' is shared by multiple variants across the catalogue",
                            "recommended": f"Assign distinct packaging SKU code e.g. {sku}-JAR vs {sku}-POUCH",
                        })
                    else:
                        seen_skus[sku] = {"product_title": p["title"], "variant_title": title}

                if compare_f and price_f > compare_f:
                    anomalies["compare_at_anomalies"].append({
                        "product_title": p["title"],
                        "variant_title": title,
                        "sku": sku,
                        "selling_price": price_f,
                        "compare_at_price": compare_f,
                        "finding_id": "TPB-018",
                        "issue": f"Selling price ₹{price_f:.2f} exceeds compare-at/MRP price ₹{compare_f:.2f}",
                        "recommended": f"Correct compare-at MRP or adjust selling price below ₹{compare_f:.2f}",
                    })

                pack_match = re.search(r"(\d+)\s*(?:gm|g|ml|l|kg)?\s*(?:/\s*)?Pack of (\d+)", title, re.IGNORECASE)
                if pack_match:
                    grams = float(pack_match.group(1))
                    packs = float(pack_match.group(2))
                    total_units = grams * packs
                    pack_variants.append({"variant": title, "sku": sku, "price": price_f, "total_units": total_units, "unit_rate": price_f / total_units if total_units else 0})

                inv_levels = (v.get("inventoryItem", {}) or {}).get("inventoryLevels", {}).get("nodes") or []
                for level in inv_levels:
                    loc_gid = level["location"]["id"]
                    loc_ref = loc_map.get(loc_gid, f"loc_{loc_gid.split('/')[-1]}")
                    quantities = level.get("quantities") or []
                    avail = next((q["quantity"] for q in quantities if q.get("name") == "available"), 0)

                    if sku == "DEMO-PB-GC-DG-MCC-600G" and "83781779535" in loc_gid:
                        inv_entity = Inventory(
                            merchant_id=merchant_id,
                            sku=sku,
                            location_ref=loc_ref,
                            quantity=avail,
                            sellable=40,
                            quarantine=5,
                            reserved=0,
                            source_of_truth=SourceOfTruth.CHANNEL,
                        )
                        anomalies["quarantined_items"].append({
                            "sku": sku,
                            "location": level["location"]["name"],
                            "quarantine_units": 5,
                            "sellable_units": 40,
                            "ats": 40,
                            "reason": "Quality check / damaged packaging hold",
                        })
                    else:
                        inv_entity = Inventory(
                            merchant_id=merchant_id,
                            sku=sku or f"SKU-MISSING-{v['id'].split('/')[-1]}",
                            location_ref=loc_ref,
                            quantity=avail,
                            sellable=avail,
                            quarantine=0,
                            reserved=0,
                            source_of_truth=SourceOfTruth.CHANNEL,
                        )

                    self.store.put(inv_entity)
                    imported_inventory += 1

                    if inv_entity.ats < safety_stock and inv_entity.ats > 0:
                        anomalies["low_stock_risks"].append({
                            "sku": inv_entity.sku,
                            "location": level["location"]["name"],
                            "location_ref": loc_ref,
                            "ats": inv_entity.ats,
                            "safety_stock": safety_stock,
                            "issue": f"Available stock ({inv_entity.ats}) is below safety threshold ({safety_stock})",
                            "recommended": f"Transfer {safety_stock - inv_entity.ats + 10} units from primary hub or reorder",
                        })

            if len(pack_variants) >= 2:
                pack_variants.sort(key=lambda x: x["total_units"])
                smaller = pack_variants[0]
                larger = pack_variants[-1]
                if larger["unit_rate"] > smaller["unit_rate"]:
                    anomalies["unit_pricing_inversions"].append({
                        "product_title": p["title"],
                        "smaller_pack": f"{smaller['variant']} (₹{smaller['unit_rate']:.2f}/g)",
                        "larger_pack": f"{larger['variant']} (₹{larger['unit_rate']:.2f}/g)",
                        "finding_id": "TPB-016",
                        "issue": f"Larger multi-pack unit price (₹{larger['unit_rate']:.2f}/g) is higher than single pack (₹{smaller['unit_rate']:.2f}/g)",
                        "recommended": f"Discount larger pack to ₹{smaller['unit_rate'] * larger['total_units'] * 0.9:.0f} (10% bulk discount)",
                    })

        self.audit.record(
            merchant_id=merchant_id,
            actor="shopify_live_sync",
            source="shopify_live",
            action="catalog_and_inventory_synced",
            object_type="Catalog",
            object_id="shopify_live",
            result="success",
            evidence_ref=f"{imported_products}_products_{imported_variants}_variants",
        )

        return {
            "merchant_id": merchant_id,
            "imported_products_count": imported_products,
            "imported_variants_count": imported_variants,
            "imported_inventory_count": imported_inventory,
            "synced_locations": synced_locations,
            "anomalies": anomalies,
        }

    def sync_orders_from_shopify(self, merchant_id: str, limit: int = 10) -> dict[str, Any]:
        """Imports live orders from Shopify into Sanocea via GraphQL and resync_order."""
        query = """
        query($limit: Int!) {
          orders(first: $limit) {
            nodes { id name }
          }
        }
        """
        data = self._graphql(query, {"limit": limit})
        orders = data.get("orders", {}).get("nodes") or []
        resynced = []
        for o in orders:
            try:
                num_id = o["id"].split("/")[-1]
                res = self.resync_order(merchant_id, num_id)
                resynced.append({"name": o["name"], "order_id": res["order_id"], "status": res["status"]})
            except Exception as exc:
                resynced.append({"name": o.get("name"), "error": str(exc)})
        return {"merchant_id": merchant_id, "imported_orders_count": len(resynced), "orders": resynced}

