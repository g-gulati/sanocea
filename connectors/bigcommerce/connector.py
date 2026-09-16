from __future__ import annotations

import base64
import hashlib
import hmac
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

"""BIGCOMMERCE SANDBOX CERTIFICATION - PREPARATION PHASE (platform certification #3).

Real BigCommerce REST connector - additive, alongside the existing simulated ShopifyConnector, the
real WooCommerceConnector, and the real ShopifyLiveConnector. Registered under its own channel type
"bigcommerce" (packages/runtime/service_graph.py); no other connector's behavior changes.

STATUS: written from current (September 2026) official BigCommerce developer documentation
(developer.bigcommerce.com, docs.bigcommerce.com) - the REST shapes below are believed correct as of
this writing, but this connector has NEVER been executed against a real BigCommerce sandbox (no
sandbox/credentials exist in this environment yet - Partner Portal account creation requires Manpreet's
own interactive signup and an approval wait; see
docs/architecture/bigcommerce-sandbox-certification-preparation.md). Every endpoint/payload shape here
should be re-verified against the real sandbox's own API reference on the FIRST real certification run,
before trusting any result - the same discipline WooCommerce's and Shopify's real connectors were built
and then corrected under.

DELIBERATE DESIGN DISCIPLINE (explicit instruction for this phase - do not violate without REAL sandbox
evidence first):
  - NO generic retry/backoff-on-staleness is implemented here, even though BigCommerce's own docs
    describe eventual consistency for inventory/location writes and webhook-to-resource visibility.
    Every method here is a single, plain HTTP call - exactly like ShopifyConnector/WooCommerceConnector.
    A retry/backoff mechanism is added ONLY if a real sandbox certification run actually observes a
    stale/not-yet-visible read-back - and even then, as the smallest possible GENERIC core change
    (never a BigCommerce-specific special case), never pre-emptively because documentation predicts it.
  - NO multi-location fulfilment-ROUTING policy is implemented here. "Which location should fulfil this
    order" is a business decision Sanocea's orchestration layer does not make for any platform today;
    this connector does not invent one for BigCommerce. It CAN target a *specific, caller-supplied*
    location for an inventory read/write (via the existing canonical `location_ref` concept already
    present on the `Inventory` model and `PostOrderOperationsService`'s `location` parameter - not a new
    concept) - addressing a location is a mechanical connector capability; deciding *which* location for
    a real order is explicitly out of scope here.
  - V2/V3 request routing, refund quote-then-execute sequencing, pagination, rate-limit header handling,
    and Standard-Webhooks signature verification are ALL connector-internal. Nothing about them is
    exposed to or assumed by Commerce-domain/orchestration code.

Auth model (deliberately the simplest available, per the gap-analysis recommendation): a store-level API
account issues a STATIC access token directly (Settings > Store-level API accounts) - unlike Shopify's
client-credentials grant, there is no token expiry/refresh cycle to manage, so - correctly, not from
oversight - this connector has no token-manager component analogous to ShopifyAccessTokenManager. The
full OAuth app-install flow remains available later if ever needed; not used for this certification.
"""

API_ROOT = "https://api.bigcommerce.com/stores/{store_hash}"


class BigCommerceConnector(GuardedConnector):
    name = "bigcommerce"

    def __init__(
        self,
        store,
        workflow,
        *,
        store_hash: str,
        access_token: str,
        webhook_verification_secret: str,
        webhook_delivery_base_url: str | None = None,
    ) -> None:
        super().__init__(store)
        self.workflow = workflow
        self.store_hash = store_hash
        self.access_token = access_token
        # Standard Webhooks signature verification key - set at webhook-creation time (POST /v3/hooks'
        # own `is_active`/secret configuration). Kept distinct from access_token, mirroring the same
        # separation ShopifyLiveConnector keeps between its access token and its webhook HMAC key.
        self.webhook_verification_secret = webhook_verification_secret
        self.webhook_delivery_base_url = webhook_delivery_base_url.rstrip("/") if webhook_delivery_base_url else None
        self._base_v2 = API_ROOT.format(store_hash=store_hash) + "/v2"
        self._base_v3 = API_ROOT.format(store_hash=store_hash) + "/v3"

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "ingest_order_webhook": Capability(name="ingest_order_webhook", status=CapabilityStatus.SUPPORTED),
                "publish_product": Capability(
                    name="publish_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v3"],
                    notes="V3 Catalog Products API (/v3/catalog/products). No implicit upsert-by-SKU (same "
                          "finding as Shopify's productSet) - this connector searches by SKU first "
                          "(GET /v3/catalog/products?sku=) and PUTs the existing product if found, POSTs "
                          "otherwise. UNVERIFIED against a live sandbox - exact required/optional fields "
                          "(e.g. `weight`, historically required for physical products) should be "
                          "confirmed on first real run.",
                ),
                "create_product": Capability(name="create_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v3"]),
                "update_product": Capability(name="update_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v3"]),
                "fetch": Capability(name="fetch", status=CapabilityStatus.SUPPORTED),
                "search": Capability(
                    name="search", status=CapabilityStatus.SUPPORTED,
                    notes="Cursor-based (page.after/page.before), BigCommerce's now-recommended REST "
                          "pagination style - not the older offset (page/limit) style. Page.next_cursor "
                          "is the next page's cursor token, or None past the last page.",
                ),
                "set_inventory": Capability(
                    name="set_inventory", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v3"],
                    notes="Location-scoped (V3 Inventory Locations + Inventory Items API). Accepts an "
                          "OPTIONAL `location_ref` in the payload (the SAME canonical field name "
                          "packages/domain_contract/models.py::Inventory already uses - not a new, "
                          "BigCommerce-specific concept) to target a SPECIFIC location; defaults to the "
                          "first location returned by /v3/inventory/locations if omitted. This connector "
                          "does not decide WHICH location a real order should be fulfilled from - that "
                          "remains entirely out of scope. BigCommerce's own docs describe these writes as "
                          "eventually consistent (a `transaction_id` is returned) - this connector does "
                          "NOT retry/poll for consistency; see the module docstring's design-discipline "
                          "note.",
                ),
                "create_fulfilment": Capability(
                    name="create_fulfilment", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v2"],
                    notes="V2 Order Shipments API (/v2/orders/{id}/shipments) - legacy-numbered but "
                          "actively maintained; supports multiple shipments per order, each scoped to a "
                          "subset of line items - real partial-shipment support neither the Shopify nor "
                          "WooCommerce connector's create_fulfilment models.",
                ),
                "cancel_order": Capability(
                    name="cancel_order", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v2"],
                    notes="No dedicated cancel mutation exists (unlike Shopify's orderCancel) - "
                          "cancellation is a plain order.status transition (PUT /v2/orders/{id}, "
                          "status_id for 'Cancelled') only permitted before ship-confirmation, the same "
                          "status-transition shape WooCommerceConnector already uses for the identical "
                          "reason.",
                ),
                "create_refund": Capability(
                    name="create_refund", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v3"],
                    notes="Two real calls: a refund QUOTE (POST .../payment_actions/refund_quotes) then "
                          "the actual refund (POST .../payment_actions/refunds) using the quote's data - "
                          "a genuinely different mutation shape from Shopify's single refundCreate or "
                          "WooCommerce's single-call ledger refund. Both calls happen entirely inside "
                          "THIS method - the connector-agnostic create_refund action/payload contract is "
                          "unchanged; whether that two-call sequencing can stay fully connector-internal "
                          "is itself one of this certification's real questions, not assumed answered.",
                ),
                "register_webhooks": Capability(name="register_webhooks", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, api_versions=["v3"]),
                "reconcile": Capability(name="reconcile", status=CapabilityStatus.SUPPORTED),
            },
        )

    # --- Webhook ingress -------------------------------------------------------------------------------

    def ingest_webhook(self, merchant_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in headers.items()}
        self._verify_webhook_signature(headers, body)
        payload = json.loads(body.decode("utf-8"))
        topic = payload.get("scope", "")
        # Standard Webhooks' own dedup key is the `webhook-id` header (distinct from BigCommerce's
        # resource id inside the payload) - the same "delivery id, not resource id" idempotency pattern
        # Shopify's X-Shopify-Webhook-Id and WooCommerce's checksum-of-body approach both use for the
        # identical reason (a redelivery of the SAME event must be a no-op, a genuinely NEW event for
        # the same resource must not be).
        webhook_id = headers.get("webhook-id") or hashlib.sha256(body).hexdigest()
        checksum = hashlib.sha256(body).hexdigest()
        raw = self._store_raw(merchant_id=merchant_id, source=f"bigcommerce:{topic}", payload=payload, headers=headers, checksum=checksum)

        def op() -> dict[str, Any]:
            result = self._upsert_order(merchant_id, payload, raw.id)
            self.audit.record(
                merchant_id=merchant_id, actor="bigcommerce", source="webhook", action="order_webhook_ingested",
                object_type="Order", object_id=result["order_id"], evidence_ref=raw.id, result="created_or_updated",
                external_ref=ExternalRef(system=self.name, entity_type="order", external_id=str(payload.get("data", {}).get("id"))),
            )
            self.workflow.start_or_signal_order(merchant_id, result["order_id"], {"topic": topic, "raw_payload_id": raw.id})
            return result

        result, created = self.idempotency.run_once(f"{merchant_id}:webhook:{self.name}:{topic}", webhook_id, op)
        if not created:
            self.audit.record(
                merchant_id=merchant_id, actor="bigcommerce", source="webhook", action="duplicate_webhook_ignored",
                object_type="Order", object_id=result["order_id"], evidence_ref=raw.id, result="duplicate",
            )
        return result | {"idempotent_replay": not created}

    def _verify_webhook_signature(self, headers: dict[str, str], body: bytes) -> None:
        """Standard Webhooks spec: header `webhook-signature` = "v1,<base64 HMAC-SHA256 of
        '{webhook-id}.{webhook-timestamp}.{raw_body}'>", keyed by the webhook's own verification secret.
        UNVERIFIED against a live sandbox - the exact secret-provisioning step (per-webhook vs.
        per-account) should be confirmed on the first real register_webhooks() call."""
        webhook_id = headers.get("webhook-id")
        timestamp = headers.get("webhook-timestamp")
        provided = headers.get("webhook-signature", "")
        if not webhook_id or not timestamp or not provided:
            raise PermissionError("missing Standard Webhooks signature headers")
        signed_content = f"{webhook_id}.{timestamp}.{body.decode('utf-8')}".encode()
        digest = hmac.new(self.webhook_verification_secret.encode(), signed_content, hashlib.sha256).digest()
        expected = f"v1,{base64.b64encode(digest).decode()}"
        candidates = provided.split(" ")
        if not any(hmac.compare_digest(expected, candidate) for candidate in candidates):
            raise PermissionError("invalid BigCommerce webhook signature")

    def _upsert_order(self, merchant_id: str, payload: dict[str, Any], raw_id: str) -> dict[str, Any]:
        # Standard Webhooks event payloads carry only {scope, data: {id, type}, ...} - the FULL order
        # resource is fetched separately, unlike Shopify/WooCommerce which embed the full resource in
        # the webhook body itself. A real, structural difference: order state here always comes from a
        # follow-up fetch(), never the webhook body directly.
        external_id = str(payload.get("data", {}).get("id"))
        external = self.fetch(merchant_id, "order", external_id)
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_id)
        billing = external.get("billing_address") or {}
        email = billing.get("email") or external.get("email")
        customer = None
        if email:
            customer = self.store.find_one(Customer, merchant_id, email=email)
            if customer is None:
                customer = Customer(
                    merchant_id=merchant_id, email=email, name=billing.get("first_name"),
                    source_of_truth=SourceOfTruth.CHANNEL, sync=SyncMetadata(raw_payload_ref=raw_id),
                )
                self.store.put(customer)
        status, payment_status = external.get("status"), external.get("payment_status")
        incoming_updated = external.get("date_modified")
        if mapping:
            order = self.store.get(Order, merchant_id, mapping.sanocea_id)
            # BigCommerce order webhook payloads carry no monotonic sequence number, matching the same
            # finding already made for Shopify and WooCommerce - date_modified comparison, same pattern.
            if incoming_updated and order.sync.source_updated_at and incoming_updated <= order.sync.source_updated_at.isoformat():
                self.audit.record(
                    merchant_id=merchant_id, actor="bigcommerce", source="webhook", action="out_of_order_event_ignored",
                    object_type="Order", object_id=order.id, evidence_ref=raw_id, result="ignored",
                )
                return {"order_id": order.id, "status": order.status}
        else:
            order = Order(
                merchant_id=merchant_id,
                channel_id=payload.get("channel_id", self.name),
                customer_id=customer.id if customer else None,
                order_number=str(external.get("id") or external_id),
                status=status or "PENDING",
                payment_status=payment_status,
                fulfillment_status=external.get("fulfillment_status"),
                total_amount=int(round(float(external.get("total_inc_tax", "0")) * 100)),
                currency=(external.get("currency_code") or "INR"),
                source_of_truth=SourceOfTruth.CHANNEL,
                idempotency=IdempotencyInfo(scope="bigcommerce_order_webhook", key=f"bigcommerce:{external_id}"),
            )
        order.status = status or order.status
        order.payment_status = payment_status
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
        for item in external.get("products", []):
            line = OrderLine(
                merchant_id=merchant_id, order_id=order.id, sku=item.get("sku"),
                title=item.get("name") or "Untitled", quantity=int(item.get("quantity", 1)),
                unit_amount=int(round(float(item.get("price_inc_tax", "0")) * 100)),
                source_of_truth=SourceOfTruth.CHANNEL, sync=SyncMetadata(raw_payload_ref=raw_id),
            )
            self.store.put(line)
        return {"order_id": order.id, "status": order.status}

    # --- Outbound reads ----------------------------------------------------------------------------

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        self.describe_capabilities().require("fetch")
        if entity_type == "product":
            raw = self._request("GET", self._base_v3, f"catalog/products/{external_id}", params={"include": "variants"})
            data = raw.get("data", raw)
            variant = (data.get("variants") or [{}])[0]
            return {
                "title": data.get("name"), "sku": variant.get("sku") or data.get("sku"),
                "price": str(variant.get("price") if variant.get("price") is not None else data.get("price")),
                "status": "active" if data.get("is_visible") else "inactive", "raw": data,
            }
        if entity_type == "inventory":
            # caller-agnostic fetch(): reads at the FIRST location if not told otherwise
            locations = self._list_locations()
            location_ref = locations[0]["id"] if locations else None
            raw = self._request("GET", self._base_v3, "inventory/items", params={"location_ids:in": str(location_ref), "identity.sku": external_id} if location_ref else {"identity.sku": external_id})
            items = raw.get("data") or []
            available = items[0].get("available_to_sell") if items else None
            return {"sku": external_id, "available": available, "raw": {"items": items, "location_ref": location_ref}}
        if entity_type == "order":
            raw = self._request("GET", self._base_v2, f"orders/{external_id}")
            return raw
        if entity_type == "fulfilment":
            raw = self._request("GET", self._base_v2, f"orders/{external_id}")
            return {"order_id": external_id, "status": raw.get("status")}
        if entity_type == "customer":
            return {"email": external_id}
        raise KeyError(entity_type)

    def _list_locations(self) -> list[dict[str, Any]]:
        raw = self._request("GET", self._base_v3, "inventory/locations")
        return raw.get("data") or []

    # --- Outbound mutations --------------------------------------------------------------------------

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        payload = request.payload
        if request.action in {"publish_product", "create_product", "update_product"}:
            # Connector-agnostic payload (title/sku/price/currency/product_type/attributes) - same
            # contract every connector accepts, per
            # docs/architecture/multi-platform-connector-hardening.md closure item 2. No upsert-by-SKU
            # exists on BigCommerce's V3 Catalog Products API (same finding already made for Shopify's
            # productSet) - searched for explicitly, mirroring WooCommerceConnector._find_product_by_sku.
            sku = str(payload.get("sku"))
            existing = self._find_product_by_sku(sku)
            body: dict[str, Any] = {
                "name": payload.get("title"), "sku": sku,
                "price": float(payload.get("price") or 0), "type": "physical",
                # `weight` has historically been REQUIRED for a physical product on this API - defaulted
                # to 0 here rather than omitted; confirm on first real run whether this remains true.
                "weight": payload.get("weight", 0),
            }
            if existing:
                raw = self._request("PUT", self._base_v3, f"catalog/products/{existing['id']}", body=body)
            else:
                raw = self._request("POST", self._base_v3, "catalog/products", body=body)
            product = raw.get("data", raw)
            return MutationResult(status="accepted", external_ref=str(product["id"]), payload=product)
        if request.action == "set_inventory":
            locations = self._list_locations()
            if not locations:
                raise ValueError(f"BigCommerce store {self.store_hash} has no inventory locations")
            location_ref = payload.get("location_ref") or locations[0]["id"]
            raw = self._request(
                "PUT", self._base_v3, "inventory/items/adjustments/absolute",
                body={"items": [{"identity": {"sku": payload.get("sku") or self._sku_for_product(payload["external_product_id"])}, "locations": [{"location_id": location_ref, "quantity": int(payload["quantity"])}]}]},
            )
            return MutationResult(status="accepted", payload={"raw": raw, "location_ref": location_ref})
        if request.action == "create_fulfilment":
            order_id = payload["external_order_id"]
            raw = self._request("POST", self._base_v2, f"orders/{order_id}/shipments", body={"tracking_number": payload.get("tracking_number", ""), "order_address_id": payload.get("order_address_id")})
            return MutationResult(status="accepted", external_ref=str(raw.get("id")), payload=raw)
        if request.action == "cancel_order":
            order_id = payload["external_order_id"]
            # No dedicated cancel mutation - a plain status transition (status_id 5 = "Cancelled" in
            # BigCommerce's default status set). UNVERIFIED: the exact status_id should be confirmed
            # against the real sandbox's /v2/order_statuses on first real run rather than assumed fixed.
            raw = self._request("PUT", self._base_v2, f"orders/{order_id}", body={"status_id": payload.get("status_id", 5)})
            return MutationResult(status="accepted", external_ref=str(order_id), payload=raw)
        if request.action == "create_refund":
            # Two real calls, entirely inside this one connector method - a quote, then the refund
            # itself using the quote's own data. Whether this two-step sequencing can stay fully
            # connector-internal (never surfaced to the connector-agnostic create_refund contract) is
            # one of this certification's real, open questions - not assumed answered here.
            order_id = payload["external_order_id"]
            quote_body = {"line_items": payload.get("line_items", []), "amount": {"amount": str(payload["amount"] / 100), "currency_code": payload.get("currency", "USD")}} if payload.get("amount") is not None else {}
            quote = self._request("POST", self._base_v3, f"orders/{order_id}/payment_actions/refund_quotes", body=quote_body)
            refund = self._request("POST", self._base_v3, f"orders/{order_id}/payment_actions/refunds", body=quote.get("data", quote))
            result = refund.get("data", refund)
            return MutationResult(status="accepted", external_ref=str(result.get("id")), payload=result)
        raise ValueError(f"unsupported BigCommerce mutation action: {request.action}")

    def _find_product_by_sku(self, sku: str) -> dict[str, Any] | None:
        raw = self._request("GET", self._base_v3, "catalog/products", params={"sku": sku})
        items = raw.get("data") or []
        return items[0] if items else None

    def _sku_for_product(self, external_product_id: str) -> str:
        raw = self._request("GET", self._base_v3, f"catalog/products/{external_product_id}")
        return raw.get("data", raw).get("sku")

    def register_webhooks(self, merchant_id: str, channel_id: str) -> MutationResult:
        # REAL FINDING PATTERN ALREADY SEEN TWICE (Shopify, WooCommerce): webhook creation is unlikely
        # to be naturally idempotent against a repeat call for the same (scope, destination) pair - list
        # existing hooks first and reuse a match, rather than assuming either blind success or blind
        # failure. UNVERIFIED whether BigCommerce actually rejects a true duplicate the way Shopify does;
        # confirm on first real run rather than assuming this defensive check was even necessary.
        if not self.webhook_delivery_base_url:
            raise ValueError("webhook_delivery_base_url was not configured for this BigCommerceConnector instance")
        delivery_url = f"{self.webhook_delivery_base_url}/webhooks/bigcommerce/{merchant_id}"
        existing = self._request("GET", self._base_v3, "hooks")
        existing_by_scope = {h["scope"]: h["id"] for h in (existing.get("data") or []) if h.get("destination") == delivery_url}
        webhook_ids = []
        for scope in ("store/order/created", "store/order/updated", "store/order/statusUpdated"):
            if scope in existing_by_scope:
                webhook_ids.append(existing_by_scope[scope])
                continue
            raw = self._request("POST", self._base_v3, "hooks", body={"scope": scope, "destination": delivery_url, "is_active": True})
            webhook_ids.append(raw.get("data", raw).get("id"))
        return MutationResult(status="accepted", payload={"webhook_ids": webhook_ids, "delivery_url": delivery_url})

    def reconcile(self, merchant_id: str, scope: dict[str, Any]) -> list[dict[str, Any]]:
        external_id = str(scope["external_order_id"])
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_id)
        if not mapping:
            return []
        order = self.store.get(Order, merchant_id, mapping.sanocea_id)
        external = self.fetch(merchant_id, "order", external_id)
        external_status = external.get("status") or "UNKNOWN"
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

    # --- Pagination ---------------------------------------------------------------------------------

    def search(self, merchant_id: str, entity_type: str, filters: dict[str, Any], cursor: str | None = None) -> Page:
        """Cursor-based (page.after), BigCommerce's own now-recommended REST pagination style - not the
        older offset (page/limit) style still supported for backward compatibility. UNVERIFIED exact
        response envelope shape (meta.pagination.cursor vs a Link header) until confirmed live."""
        self.describe_capabilities().require("search")
        if entity_type != "product":
            raise KeyError(entity_type)
        params = dict(filters)
        if cursor:
            params["page[after]"] = cursor
        raw = self._request("GET", self._base_v3, "catalog/products", params=params)
        items = raw.get("data") or []
        next_cursor = (raw.get("meta", {}).get("pagination", {}) or {}).get("cursor", {}).get("after")
        return Page(items=items, next_cursor=next_cursor)

    # --- HTTP transport -----------------------------------------------------------------------------

    def _request(self, method: str, base_url: str, path: str, *, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
        url = f"{base_url}/{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json", "X-Auth-Token": self.access_token},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            if exc.code == 429:
                # BigCommerce's own sliding-window rate-limit headers (X-Rate-Limit-Time-Reset-Ms etc.)
                # are NOT parsed/backed-off-on here, by the same deliberate discipline as the module
                # docstring - not pre-emptively added without a real observed 429 forcing the question.
                raise RuntimeError(f"BigCommerce API 429 rate limited: {detail}") from exc
            if exc.code >= 500:
                raise RuntimeError(f"BigCommerce API {exc.code}: {detail}") from exc
            raise ValueError(f"BigCommerce API {exc.code}: {detail}") from exc
