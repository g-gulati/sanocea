from __future__ import annotations

import hashlib
import hmac
import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from sanocea.packages.connector_sdk import (
    Capability,
    CapabilityStatus,
    ConnectorCapabilities,
    GuardedConnector,
    MutationMode,
    MutationRequest,
    MutationResult,
    Page,
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

from .oauth1 import sign_request

# WooCommerce order status -> Sanocea canonical Order.status/payment_status. WooCommerce's status
# vocabulary is a flat, order-level state machine (no separate financial_status/fulfillment_status
# dimensions the way Shopify's webhook payload has) - this mapping is the connector-owned translation;
# canonical Order keeps its existing two-dimension shape regardless of which platform is the source.
_STATUS_MAP = {
    "pending": ("PENDING", "pending"),
    "on-hold": ("PENDING", "pending"),
    "processing": ("PAID", "paid"),
    "completed": ("PAID", "paid"),
    "cancelled": ("CANCELLED", "cancelled"),
    "refunded": ("REFUNDED", "refunded"),
    "failed": ("PENDING", "failed"),
    "checkout-draft": ("PENDING", "pending"),
}


class WooCommerceConnector(GuardedConnector):
    """Minimum connector required by Sanocea's existing connector contract to talk to a real WooCommerce
    REST API store. Genuinely different platform semantics from Shopify (OAuth1.0a one-legged signing,
    HMAC-SHA256 webhook verification with a DIFFERENT header set, checksum-based webhook idempotency
    since WooCommerce sends no delivery-id, integer resource ids, flat order status vocabulary, no
    first-class Fulfillment/tracking resource) are handled ENTIRELY inside this file - nothing upstream
    of GuardedConnector's protocol needs to know WooCommerce exists. See
    docs/architecture/woocommerce-platform-independence.md for the full platform-independence test this
    was built for, including which semantic differences could NOT be normalized away (reported as
    findings, not hacked around).
    """

    name = "woocommerce"

    def __init__(self, store, workflow, *, base_url: str, consumer_key: str, consumer_secret: str, webhook_delivery_base_url: str | None = None) -> None:
        super().__init__(store)
        self.workflow = workflow
        self.base_url = base_url.rstrip("/")
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        # Only needed by register_webhooks() - the base URL of THIS Sanocea instance, as WooCommerce
        # itself must be able to reach it (e.g. http://host.docker.internal:8080 for this local dev
        # setup, or a real public HTTPS URL in production).
        self.webhook_delivery_base_url = webhook_delivery_base_url.rstrip("/") if webhook_delivery_base_url else None

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "ingest_order_webhook": Capability(name="ingest_order_webhook", status=CapabilityStatus.SUPPORTED),
                "refund": Capability(name="refund", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["wc/v3"]),
                "create_fulfilment": Capability(
                    name="create_fulfilment", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC,
                    notes="WooCommerce core has no first-class Fulfillment/tracking-number resource unlike Shopify - "
                          "this transitions order.status to 'processing'/'completed', the closest native equivalent.",
                ),
                "cancel_order": Capability(name="cancel_order", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "publish_product": Capability(name="publish_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["wc/v3"]),
                "create_product": Capability(name="create_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "update_product": Capability(name="update_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "set_inventory": Capability(name="set_inventory", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "create_variable_product": Capability(
                    name="create_variable_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC,
                    notes="WooCommerce models a variable product as a parent product (type='variable') plus a "
                          "separate /products/{id}/variations sub-resource, each variation carrying its own "
                          "sku/price/stock and one option per defined attribute - structurally different from "
                          "Shopify's inline variants array. Not normalized to Shopify's shape.",
                ),
                "fetch": Capability(name="fetch", status=CapabilityStatus.SUPPORTED),
                "search": Capability(
                    name="search", status=CapabilityStatus.SUPPORTED,
                    notes="Page-based (page/per_page query params, X-WP-Total(Pages) response headers), not "
                          "cursor-based like Shopify's GraphQL Admin API. Page.next_cursor here is the next "
                          "page NUMBER as a string, not an opaque cursor token.",
                ),
                "poll_changes": Capability(
                    name="poll_changes", status=CapabilityStatus.SUPPORTED,
                    notes="Uses WooCommerce's modified_after filter (ISO8601) on /products, ordered by "
                          "date_modified ascending. cursor is the ISO8601 timestamp of the last-seen change. "
                          "The cursor path (a ':'-bearing query value) previously 401'd - a generic missing "
                          "second percent-encoding pass in connectors/woocommerce/oauth1.py's signature base "
                          "string (RFC 5849 3.4.1.1), fixed; see oauth1.py's docstring and "
                          "tests/integration/test_woocommerce_oauth1_signing.py.",
                ),
                "register_webhooks": Capability(name="register_webhooks", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
            },
        )

    # --- Webhook ingress -------------------------------------------------------------------------------

    def ingest_webhook(self, merchant_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in headers.items()}
        secret = self.store.get_credential_ref(merchant_id, "woocommerce_webhook_secret")
        self._verify_signature(headers, body, secret)
        topic = headers.get("x-wc-webhook-topic", "")
        payload = json.loads(body.decode("utf-8"))
        checksum = hashlib.sha256(body).hexdigest()
        raw = self._store_raw(merchant_id=merchant_id, source=f"woocommerce:{topic}", payload=payload, headers=headers, checksum=checksum)

        # No delivery-id header exists in WooCommerce's webhook contract (unlike Shopify's
        # X-Shopify-Webhook-Id) - idempotency here is keyed on the RAW PAYLOAD CHECKSUM instead. An
        # exact-duplicate redelivery (identical bytes) is a no-op replay; a genuinely later delivery for
        # the same order (different status/content) has a different checksum and is correctly processed
        # as a new event - this is the deliberate WooCommerce-appropriate idempotency strategy, not a
        # weaker imitation of Shopify's.
        def op() -> dict[str, Any]:
            result = self._upsert_order(merchant_id, payload, raw.id)
            self.audit.record(
                merchant_id=merchant_id, actor="woocommerce", source="webhook", action="order_webhook_ingested",
                object_type="Order", object_id=result["order_id"], evidence_ref=raw.id, result="created_or_updated",
                external_ref=ExternalRef(system="woocommerce", entity_type="order", external_id=str(payload["id"])),
            )
            self.workflow.start_or_signal_order(merchant_id, result["order_id"], {"topic": topic, "raw_payload_id": raw.id})
            return result

        result, created = self.idempotency.run_once(f"{merchant_id}:webhook:woocommerce:{topic}", checksum, op)
        if not created:
            self.audit.record(
                merchant_id=merchant_id, actor="woocommerce", source="webhook", action="duplicate_webhook_ignored",
                object_type="Order", object_id=result["order_id"], evidence_ref=raw.id, result="duplicate",
            )
        return result | {"idempotent_replay": not created}

    def _verify_signature(self, headers: dict[str, str], body: bytes, secret: str) -> None:
        provided = headers.get("x-wc-webhook-signature")
        digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode()
        if not provided or not hmac.compare_digest(provided, expected):
            raise PermissionError("invalid WooCommerce webhook signature")

    def _upsert_order(self, merchant_id: str, payload: dict[str, Any], raw_id: str) -> dict[str, Any]:
        external_id = str(payload["id"])
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_id)
        billing = payload.get("billing") or {}
        email = billing.get("email")
        customer = None
        if email:
            customer = self.store.find_one(Customer, merchant_id, email=email)
            if customer is None:
                customer = Customer(
                    merchant_id=merchant_id, email=email, name=billing.get("first_name"),
                    source_of_truth=SourceOfTruth.CHANNEL, sync=SyncMetadata(raw_payload_ref=raw_id),
                )
                self.store.put(customer)
        wc_status = payload.get("status", "pending")
        status, payment_status = _STATUS_MAP.get(wc_status, ("PENDING", "pending"))
        if mapping:
            order = self.store.get(Order, merchant_id, mapping.sanocea_id)
            # WooCommerce has no monotonic per-order sequence number in its webhook payload (unlike
            # Shopify's updated_sequence) - date_modified is the closest ordering signal WooCommerce
            # actually provides. A delivery whose date_modified is not newer than what canonical Order
            # already reflects is treated as stale and ignored, the WooCommerce-appropriate equivalent
            # of Shopify's sequence check, using the field WooCommerce actually sends.
            incoming_modified = payload.get("date_modified") or payload.get("date_modified_gmt")
            if incoming_modified and order.sync.source_updated_at and incoming_modified <= order.sync.source_updated_at.isoformat():
                self.audit.record(
                    merchant_id=merchant_id, actor="woocommerce", source="webhook", action="out_of_order_event_ignored",
                    object_type="Order", object_id=order.id, evidence_ref=raw_id, result="ignored",
                )
                return {"order_id": order.id, "status": order.status}
        else:
            order = Order(
                merchant_id=merchant_id,
                channel_id=payload.get("channel_id", "woocommerce"),
                customer_id=customer.id if customer else None,
                order_number=str(payload.get("number") or external_id),
                status=status,
                payment_status=payment_status,
                fulfillment_status=wc_status,
                total_amount=int(round(float(payload.get("total", "0")) * 100)),
                currency=payload.get("currency", "INR"),
                source_of_truth=SourceOfTruth.CHANNEL,
                idempotency=IdempotencyInfo(scope="woocommerce_order_webhook", key=f"wc:{external_id}"),
            )
        order.status = status
        order.payment_status = payment_status
        order.fulfillment_status = wc_status
        order.external_refs = [ref for ref in order.external_refs if not (ref.system == self.name and ref.entity_type == "order")] + [
            ExternalRef(system=self.name, entity_type="order", external_id=external_id, channel_id=order.channel_id)
        ]
        order.sync.raw_payload_ref = raw_id
        incoming_modified = payload.get("date_modified") or payload.get("date_modified_gmt")
        if incoming_modified:
            from datetime import datetime

            try:
                order.sync.source_updated_at = datetime.fromisoformat(incoming_modified)
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
                title=item.get("name") or "Untitled", quantity=int(item.get("quantity", 1)),
                unit_amount=int(round(float(item.get("total", "0")) / max(int(item.get("quantity", 1)), 1) * 100)),
                source_of_truth=SourceOfTruth.CHANNEL, sync=SyncMetadata(raw_payload_ref=raw_id),
            )
            self.store.put(line)
        return {"order_id": order.id, "status": order.status}

    # --- Outbound reads ----------------------------------------------------------------------------

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        self.describe_capabilities().require("fetch")
        if entity_type == "product":
            raw = self._request("GET", f"products/{external_id}")
            return {
                "title": raw.get("name"),
                "sku": raw.get("sku"),
                "price": raw.get("regular_price") or raw.get("price"),
                "status": "active" if raw.get("status") == "publish" else "inactive",
                "raw": raw,
            }
        if entity_type == "inventory":
            raw = self._request("GET", f"products/{external_id}")
            return {"sku": raw.get("sku"), "available": raw.get("stock_quantity")}
        if entity_type == "product_variation":
            # external_id is "{parent_id}:{variation_id}" - WooCommerce variations are only addressable
            # relative to their parent product, unlike a flat product id.
            parent_id, variation_id = external_id.split(":")
            raw = self._request("GET", f"products/{parent_id}/variations/{variation_id}")
            return {
                "sku": raw.get("sku"),
                "price": raw.get("regular_price") or raw.get("price"),
                "status": "active" if raw.get("status") == "publish" else "inactive",
                "available": raw.get("stock_quantity"),
                "option": (raw.get("attributes") or [{}])[0].get("option"),
                "raw": raw,
            }
        if entity_type == "order":
            return self._request("GET", f"orders/{external_id}")
        if entity_type == "fulfilment":
            raw = self._request("GET", f"orders/{external_id}")
            return {"order_id": external_id, "status": raw.get("status")}
        if entity_type == "customer":
            return {"email": external_id}
        raise KeyError(entity_type)

    # --- Outbound mutations --------------------------------------------------------------------------

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        payload = request.payload
        if request.action in {"publish_product", "create_product", "update_product"}:
            # Sanocea's payload here is CONNECTOR-AGNOSTIC (title/sku/price/currency/product_type/
            # attributes) - this connector reads it directly and builds its own WooCommerce REST body.
            # No Shopify-shape unpacking (variants[0]/lookup_key) needed or wanted here; see
            # docs/architecture/multi-platform-connector-hardening.md closure item 2.
            sku = str(payload.get("sku"))
            existing = self._find_product_by_sku(sku)
            body = {
                "name": payload.get("title"),
                "sku": sku,
                "regular_price": payload.get("price"),
                "manage_stock": True,
            }
            quantity = payload.get("quantity") or payload.get("stock_quantity")
            if quantity is not None:
                body["stock_quantity"] = int(quantity)
            if existing:
                raw = self._request("PUT", f"products/{existing['id']}", body=body)
            else:
                raw = self._request("POST", "products", body=body)
            return MutationResult(status="accepted", external_ref=str(raw["id"]), payload=raw)
        if request.action == "set_inventory":
            product_id = payload["external_product_id"]
            raw = self._request("PUT", f"products/{product_id}", body={"stock_quantity": int(payload["quantity"]), "manage_stock": True})
            return MutationResult(status="accepted", external_ref=str(raw["id"]), payload=raw)
        if request.action == "create_refund":
            order_id = payload["external_order_id"]
            # api_refund=false records a manual/ledger refund instead of WooCommerce attempting to call
            # the payment gateway's OWN refund API - a genuine WooCommerce-specific refund semantic:
            # most gateways (including WooCommerce's own bundled Cash-on-Delivery/Bank-Transfer/Cheque
            # methods) do not implement automatic gateway refunds at all, and orders/{id}/refunds
            # defaults to attempting one, failing with woocommerce_rest_cannot_create_order_refund for
            # any gateway that doesn't support it. Unlike Shopify (where Sanocea IS always talking to
            # the actual payment processor, live or Bogus Gateway, and a refund is inherently
            # "automatic"), WooCommerce refunds are ledger-first by default - the merchant's own
            # gateway integration (if any) decides whether automatic refund is even possible. This is
            # handled here, inside the connector, not surfaced as a WooCommerce-specific concept
            # anywhere in Sanocea's refund domain logic.
            body: dict[str, Any] = {"api_refund": False}
            if payload.get("amount") is not None:
                body["amount"] = f"{payload['amount'] / 100:.2f}"
            if payload.get("reason"):
                body["reason"] = payload["reason"]
            raw = self._request("POST", f"orders/{order_id}/refunds", body=body)
            return MutationResult(status="accepted", external_ref=str(raw["id"]), payload=raw)
        if request.action == "create_variable_product":
            # WooCommerce-specific shape, deliberately NOT normalized to Shopify's inline variants array
            # (see the create_variable_product Capability.notes) - a parent product (type="variable")
            # defines one or more attributes with variation=True; each variation is then a SEPARATE
            # resource under /products/{parent_id}/variations, carrying its own sku/price/stock and
            # exactly one option per defined attribute.
            attribute_name = payload.get("attribute_name", "Variant")
            variants = payload["variants"]
            parent_body = {
                "name": payload["title"],
                "type": "variable",
                "attributes": [{"name": attribute_name, "visible": True, "variation": True, "options": [v["option"] for v in variants]}],
            }
            if payload.get("parent_sku"):
                parent_body["sku"] = payload["parent_sku"]
            parent = self._request("POST", "products", body=parent_body)
            parent_id = parent["id"]
            variation_refs = []
            for variant in variants:
                var_body: dict[str, Any] = {
                    "sku": variant["sku"],
                    "regular_price": variant["price"],
                    "attributes": [{"name": attribute_name, "option": variant["option"]}],
                }
                quantity = variant.get("quantity")
                if quantity is not None:
                    var_body["manage_stock"] = True
                    var_body["stock_quantity"] = int(quantity)
                variation = self._request("POST", f"products/{parent_id}/variations", body=var_body)
                variation_refs.append({"id": variation["id"], "sku": variation.get("sku"), "option": variant["option"]})
            return MutationResult(status="accepted", external_ref=str(parent_id), payload={"parent": parent, "variations": variation_refs})
        if request.action in {"cancel_order", "create_fulfilment"}:
            order_id = payload["external_order_id"]
            new_status = "cancelled" if request.action == "cancel_order" else payload.get("status", "processing")
            raw = self._request("PUT", f"orders/{order_id}", body={"status": new_status})
            return MutationResult(status="accepted", external_ref=str(raw["id"]), payload=raw)
        raise ValueError(f"unsupported WooCommerce mutation action: {request.action}")

    def _find_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        results = self._request("GET", "products", params={"sku": sku})
        return results[0] if results else None

    def reconcile(self, merchant_id: str, scope: dict[str, Any]) -> list[dict[str, Any]]:
        external_id = str(scope["external_order_id"])
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_id)
        if not mapping:
            return []
        order = self.store.get(Order, merchant_id, mapping.sanocea_id)
        external = self._request("GET", f"orders/{external_id}")
        wc_status = external.get("status", "pending")
        external_status, _ = _STATUS_MAP.get(wc_status, ("PENDING", "pending"))
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

    # --- HTTP transport --------------------------------------------------------------------------------

    def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None, params: dict[str, str] | None = None) -> Any:
        return self._request_with_headers(method, path, body=body, params=params)[0]

    def _request_with_headers(self, method: str, path: str, *, body: dict[str, Any] | None = None, params: dict[str, str] | None = None) -> tuple[Any, dict[str, str]]:
        url = f"{self.base_url}/wp-json/wc/v3/{path}"
        signed = sign_request(method, url, {k: str(v) for k, v in (params or {}).items()}, self.consumer_key, self.consumer_secret)
        full_url = f"{url}?{urllib.parse.urlencode(signed)}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(full_url, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
        try:
            # A generous timeout is deliberate: this local wp-env/Docker-on-Windows WordPress instance
            # was empirically observed taking 10-15s+ per request even for simple reads (see
            # docs/architecture/woocommerce-platform-independence.md's "HTTP behaviour" finding) - a real
            # environment characteristic of Docker Desktop's Windows filesystem translation layer, not a
            # connector defect. A real Linux-hosted WooCommerce store would not exhibit this.
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read()), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if exc.code == 429:
                raise RuntimeError(f"WooCommerce API 429 rate limited: {detail}") from exc
            if exc.code >= 500:
                raise RuntimeError(f"WooCommerce API {exc.code}: {detail}") from exc
            raise ValueError(f"WooCommerce API {exc.code}: {detail}") from exc

    # --- Pagination / incremental sync -------------------------------------------------------------

    def search(self, merchant_id: str, entity_type: str, filters: dict[str, Any], cursor: str | None = None) -> Page:
        """Page-based (page/per_page), not cursor-based like Shopify's GraphQL Admin API - Page.next_cursor
        is the next page NUMBER as a string (or None past the last page), read from WooCommerce's own
        X-WP-TotalPages response header, never inferred from the returned item count."""
        self.describe_capabilities().require("search")
        if entity_type != "product":
            raise KeyError(entity_type)
        page = int(cursor) if cursor else 1
        params = {"page": str(page), "per_page": str(filters.get("per_page", 20))}
        if filters.get("sku"):
            params["sku"] = filters["sku"]
        items, headers = self._request_with_headers("GET", "products", params=params)
        total_pages = int(headers.get("X-WP-TotalPages") or headers.get("x-wp-totalpages") or 1)
        next_cursor = str(page + 1) if page < total_pages else None
        return Page(items=items, next_cursor=next_cursor)

    def poll_changes(self, merchant_id: str, cursor: str | None = None) -> Page:
        """Uses WooCommerce's modified_after filter (ISO8601, exclusive) ordered by date_modified
        ascending. The returned next_cursor is the latest date_modified_gmt seen this call (or the
        input cursor unchanged if nothing new) - callers persist and pass it back to resume from
        exactly where they left off, never re-scanning the whole catalogue."""
        self.describe_capabilities().require("poll_changes")
        params = {"orderby": "modified", "order": "asc", "per_page": "50"}
        if cursor:
            params["modified_after"] = cursor
        items = self._request("GET", "products", params=params)
        latest = cursor
        for item in items:
            modified = item.get("date_modified_gmt")
            if modified and (latest is None or modified > latest):
                latest = modified
        return Page(items=items, next_cursor=latest)

    def register_webhooks(self, merchant_id: str, channel_id: str) -> MutationResult:
        if not self.webhook_delivery_base_url:
            raise ValueError("webhook_delivery_base_url was not configured for this WooCommerceConnector instance")
        secret = self.store.get_credential_ref(merchant_id, "woocommerce_webhook_secret")
        delivery_url = f"{self.webhook_delivery_base_url}/webhooks/woocommerce/{merchant_id}"
        created = []
        for topic in ("order.created", "order.updated"):
            raw = self._request("POST", "webhooks", body={
                "name": f"Sanocea {topic}", "topic": topic, "delivery_url": delivery_url, "secret": secret, "status": "active",
            })
            created.append(raw["id"])
        return MutationResult(status="accepted", payload={"webhook_ids": created, "delivery_url": delivery_url})
