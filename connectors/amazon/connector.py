from __future__ import annotations

from typing import Any

from sanocea.packages.connector_sdk import (
    Capability,
    CapabilityStatus,
    ConnectorCapabilities,
    MarketplaceAuthStrategy,
    MarketplaceConnector,
    MutationMode,
    MutationRequest,
    MutationResult,
    Page,
    Transport,
)
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    ExternalIdMapping,
    ExternalRef,
    IdempotencyInfo,
    Order,
    OrderLine,
    ReconciliationResult,
    SourceOfTruth,
    SyncMetadata,
)
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService

from .auth import ENDPOINT_HOST_INDIA, MARKETPLACE_ID_INDIA, RestrictedDataTokenProvider
from .mappings import ORDER_STATUS_MAP
from .reports import interpret_async_status

"""Amazon India Selling Partner API connector - Step 9Q.3.

Built directly against Amazon's own official SP-API model repository (github.com/amzn/
selling-partner-api-models) and primary documentation (developer-docs.amazon.com/sp-api), fetched and
verified during this step - not from memory, not secondhand. Endpoint paths, the OrderStatus enum, the
LWA token contract, the RDT (Restricted Data Token) contract, marketplace id, and endpoint region for
India are all confirmed Level 1. See docs/connectors/amazon.md for the full source list and
docs/connectors/amazon-certification.md for the exact per-capability evidence grade - not every
capability below reaches the same confidence level, and this file's comments say which.

Distinguishes, per Step 9Q.3 Part 4/8, rather than forcing Amazon's genuinely different inventory and
fulfilment concepts into one shape:
  - FBA inventory (`fba_inventory_read`) - READ ONLY in production; the FBA Inventory API's write
    operations (createInventoryItem, deleteInventoryItem, addInventory) are explicitly documented as
    SANDBOX ONLY - there is no production seller-writable FBA inventory endpoint.
  - Merchant-fulfilled listing quantity (`merchant_fulfilled_inventory_write`) - NOT a separate
    endpoint; it is the `fulfillmentAvailability` attribute on a Listings Items PUT/PATCH, i.e. the
    SAME endpoint as catalogue_write, kept as its own named capability only so the matrix does not
    conflate "can read FBA stock levels" with "can tell Amazon my own warehouse's sellable quantity".
  - `cancellation` and `return_refund` are UNCONFIRMED, not assumed symmetric with Flipkart: no
    order-cancellation REST endpoint was found in the Orders API model, no cancellation feedType is
    documented in the Feeds API model's description, and the official SP-API models repository's own
    top-level directory listing contains no "returns"/"refunds" model family at all.
"""

BASE_URL = ENDPOINT_HOST_INDIA  # India is served by the EU SP-API endpoint region - confirmed directly.
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"


class AmazonConnector(MarketplaceConnector):
    name = "amazon"

    def __init__(
        self, store, workflow, *, auth: MarketplaceAuthStrategy, seller_id: str,
        marketplace_ids: list[str] | None = None, transport: Transport | None = None,
    ) -> None:
        super().__init__(store, workflow, auth=auth, transport=transport)
        self.exceptions = ExceptionService(store)
        self.seller_id = seller_id
        # Kept as constructor DATA, never hardcoded business logic - defaults to India's confirmed
        # marketplaceId, but a merchant operating additional Amazon marketplaces supplies their own.
        self.marketplace_ids = marketplace_ids or [MARKETPLACE_ID_INDIA]
        self._rdt = RestrictedDataTokenProvider(host=BASE_URL, main_auth=auth, transport=self.transport)

    # --- Capability discovery ----------------------------------------------------------------------

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "auth": Capability(name="auth", status=CapabilityStatus.SUPPORTED, notes="LWA refresh_token grant, /auth/o2/token - Level 1 confirmed. x-amz-access-token header, no AWS SigV4 for standard calls."),
                "catalogue_read": Capability(name="catalogue_read", status=CapabilityStatus.SUPPORTED, notes="GET /listings/2021-08-01/items/{sellerId}/{sku} and .../items/{sellerId} (search) - Level 1 confirmed from the official OpenAPI model."),
                "catalogue_write": Capability(name="catalogue_write", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC, notes="PUT/PATCH /listings/2021-08-01/items/{sellerId}/{sku} - Level 1 confirmed. mode=ASYNC: Amazon documents this as an async-validated operation surfacing issues[], not a synchronous guaranteed-applied write."),
                "catalogue_delete": Capability(name="catalogue_delete", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC, notes="DELETE /listings/2021-08-01/items/{sellerId}/{sku} - Level 1 confirmed."),
                "fba_inventory_read": Capability(name="fba_inventory_read", status=CapabilityStatus.SUPPORTED, notes="GET /fba/inventory/v1/summaries - Level 1 confirmed."),
                "fba_inventory_write": Capability(name="fba_inventory_write", status=CapabilityStatus.UNSUPPORTED, notes="createInventoryItem/deleteInventoryItem/addInventory are explicitly documented SANDBOX ONLY - no production seller-writable FBA inventory endpoint exists."),
                "merchant_fulfilled_inventory_write": Capability(name="merchant_fulfilled_inventory_write", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC, notes="Same endpoint as catalogue_write (fulfillmentAvailability attribute) - kept distinct in the matrix only to avoid conflating it with FBA inventory."),
                "order_ingest": Capability(name="order_ingest", status=CapabilityStatus.SUPPORTED, notes="GET /orders/v0/orders, /orders/{orderId}, /orders/{orderId}/orderItems - Level 1 confirmed."),
                "order_buyer_info_read": Capability(name="order_buyer_info_read", status=CapabilityStatus.SUPPORTED, notes="GET /orders/{orderId}/buyerInfo, RDT-gated (dataElements=buyerInfo) - Level 1 confirmed."),
                "order_address_read": Capability(name="order_address_read", status=CapabilityStatus.SUPPORTED, notes="GET /orders/{orderId}/address, RDT-gated (dataElements=shippingAddress) - Level 1 confirmed."),
                "fulfilment_update": Capability(name="fulfilment_update", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC, notes="POST /orders/{orderId}/shipment (confirmShipment) - Level 1 confirmed."),
                "cancellation": Capability(name="cancellation", status=CapabilityStatus.UNCONFIRMED, notes="No order-cancellation REST endpoint exists in the Orders API model; no cancellation feedType is documented in the Feeds API model. Do not assume symmetry with Flipkart's real cancel_shipment endpoint."),
                "return_refund": Capability(name="return_refund", status=CapabilityStatus.UNCONFIRMED, notes="The official SP-API models repository's top-level model directory listing contains no returns/refunds API family at all (confirmed directly, github.com/amzn/selling-partner-api-models/models)."),
                "merchant_fulfillment_shipping": Capability(name="merchant_fulfillment_shipping", status=CapabilityStatus.UNCONFIRMED, notes="merchant-fulfillment-api-model directory confirmed to exist; exact endpoint contract not independently verified this step - REQUIRES FIRSTHAND SPEC CONFIRMATION before implementing."),
                "easy_ship_scheduling": Capability(name="easy_ship_scheduling", status=CapabilityStatus.UNCONFIRMED, notes="easy-ship-model directory confirmed to exist; exact endpoint contract not independently verified this step."),
                "order_notifications": Capability(name="order_notifications", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC, notes="POST /notifications/v1/subscriptions/{notificationType}, /destinations - real, self-serve, OAuth-gated only (Level 1 confirmed). Actually RECEIVING events additionally requires a real AWS SQS queue or EventBridge bus provisioned by the merchant/Sanocea - an infrastructure prerequisite, not a platform approval gate; consuming that queue is out of scope for this connector (see docs/connectors/amazon.md)."),
                "feed_submit": Capability(name="feed_submit", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC, notes="POST /feeds/2021-06-30/documents then /feeds - Level 1 confirmed. Async: submission != applied, see reports.py."),
                "report_submit": Capability(name="report_submit", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC, notes="POST /reports/2021-06-30/reports - Level 1 confirmed."),
                "settlement_ingest": Capability(name="settlement_ingest", status=CapabilityStatus.SUPPORTED, notes="GET /finances/v0/orders/{orderId}/financialEvents and /finances/v0/financialEventGroups - Level 1 confirmed; this is the authoritative reconciliation source, order-scoped exactly like Sanocea's existing reconcile() pattern."),
                "fetch": Capability(name="fetch", status=CapabilityStatus.SUPPORTED),
                "search": Capability(name="search", status=CapabilityStatus.SUPPORTED),
                "reconcile": Capability(name="reconcile", status=CapabilityStatus.SUPPORTED),
                # --- literal-action entries matching execute_mutation()'s require(request.action) ------
                "put_listing": Capability(name="put_listing", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "patch_listing": Capability(name="patch_listing", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "delete_listing": Capability(name="delete_listing", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "confirm_shipment": Capability(name="confirm_shipment", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "create_subscription": Capability(name="create_subscription", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "create_destination": Capability(name="create_destination", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "create_feed_document": Capability(name="create_feed_document", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "create_feed": Capability(name="create_feed", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "create_report": Capability(name="create_report", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
            },
        )

    # --- Reads --------------------------------------------------------------------------------------

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        self.describe_capabilities().require("fetch")
        if entity_type == "product":
            raw = self._request("GET", f"{BASE_URL}/listings/2021-08-01/items/{self.seller_id}/{external_id}", params={"marketplaceIds": ",".join(self.marketplace_ids)})
            summary = (raw.get("summaries") or [{}])[0]
            offer = (raw.get("offers") or [{}])[0] if raw.get("offers") else {}
            return {
                "title": summary.get("itemName"),
                "sku": raw.get("sku") or external_id,
                "price": f"{float((offer.get('price') or {}).get('amount', 0) or 0):.2f}",
                "status": "active" if "BUYABLE" in (summary.get("status") or []) else "inactive",
                "raw": raw,
            }
        if entity_type == "order":
            return self._request("GET", f"{BASE_URL}/orders/v0/orders/{external_id}")
        if entity_type == "order_items":
            return self._request("GET", f"{BASE_URL}/orders/v0/orders/{external_id}/orderItems")
        if entity_type == "order_buyer_info":
            rdt = self._rdt.request(method="GET", path=f"/orders/v0/orders/{external_id}/buyerInfo", data_elements=["buyerInfo"])
            return self._request("GET", f"{BASE_URL}/orders/v0/orders/{external_id}/buyerInfo", extra_headers={"x-amz-access-token": rdt})
        if entity_type == "order_address":
            rdt = self._rdt.request(method="GET", path=f"/orders/v0/orders/{external_id}/address", data_elements=["shippingAddress"])
            return self._request("GET", f"{BASE_URL}/orders/v0/orders/{external_id}/address", extra_headers={"x-amz-access-token": rdt})
        if entity_type == "financial_events":
            return self._request("GET", f"{BASE_URL}/finances/v0/orders/{external_id}/financialEvents")
        if entity_type == "feed_status":
            return self._request("GET", f"{BASE_URL}/feeds/2021-06-30/feeds/{external_id}")
        if entity_type == "report_status":
            return self._request("GET", f"{BASE_URL}/reports/2021-06-30/reports/{external_id}")
        if entity_type == "report_document":
            return self._request("GET", f"{BASE_URL}/reports/2021-06-30/documents/{external_id}")
        raise KeyError(entity_type)

    def search(self, merchant_id: str, entity_type: str, filters: dict[str, Any], cursor: str | None = None) -> Page:
        self.describe_capabilities().require("search")
        if entity_type == "order":
            params = {k: v for k, v in filters.items() if v is not None}
            params["MarketplaceIds"] = ",".join(self.marketplace_ids)
            if cursor:
                params = {"NextToken": cursor}
            raw = self._request("GET", f"{BASE_URL}/orders/v0/orders", params=params)
            payload = raw.get("payload", raw)
            return Page(items=payload.get("Orders", []), next_cursor=payload.get("NextToken"))
        if entity_type == "listing":
            params = {k: v for k, v in filters.items() if v is not None}
            params["marketplaceIds"] = ",".join(self.marketplace_ids)
            if cursor:
                params["pageToken"] = cursor
            raw = self._request("GET", f"{BASE_URL}/listings/2021-08-01/items/{self.seller_id}", params=params)
            return Page(items=raw.get("items", []), next_cursor=raw.get("pagination", {}).get("nextToken"))
        if entity_type == "fba_inventory":
            params = {k: v for k, v in filters.items() if v is not None}
            params["marketplaceIds"] = ",".join(self.marketplace_ids)
            if cursor:
                params["nextToken"] = cursor
            raw = self._request("GET", f"{BASE_URL}/fba/inventory/v1/summaries", params=params)
            payload = raw.get("payload", raw)
            return Page(items=payload.get("inventorySummaries", []), next_cursor=payload.get("pagination", {}).get("nextToken"))
        raise KeyError(entity_type)

    def poll_changes(self, merchant_id: str, cursor: str | None = None) -> Page:
        return self.search(merchant_id, "order", {}, cursor=cursor)

    # --- Mutations ------------------------------------------------------------------------------------

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        simulate = request.payload.get("simulate")
        if simulate == "429":
            raise RuntimeError("Amazon SP-API 429 rate limited")
        if simulate == "500":
            raise RuntimeError("Amazon SP-API 500")
        if simulate == "timeout_before_mutation":
            raise TimeoutError("timeout before mutation")
        payload = request.payload
        if request.action in {"put_listing", "patch_listing"}:
            if request.action == "put_listing":
                method, body = "PUT", {"productType": payload["product_type"], "attributes": payload["attributes"]}
            else:
                method, body = "PATCH", {"productType": payload["product_type"], "patches": payload["patches"]}
            raw = self._request(method, f"{BASE_URL}/listings/2021-08-01/items/{self.seller_id}/{payload['sku']}", body=body, params={"marketplaceIds": ",".join(self.marketplace_ids)})
            return MutationResult(status="accepted", external_ref=payload["sku"], payload=raw)
        if request.action == "delete_listing":
            raw = self._request("DELETE", f"{BASE_URL}/listings/2021-08-01/items/{self.seller_id}/{payload['sku']}", params={"marketplaceIds": ",".join(self.marketplace_ids)})
            return MutationResult(status="accepted", external_ref=payload["sku"], payload=raw)
        if request.action == "confirm_shipment":
            raw = self._request("POST", f"{BASE_URL}/orders/v0/orders/{payload['order_id']}/shipment", body={"marketplaceId": self.marketplace_ids[0], "packageDetail": payload["package_detail"]})
            return MutationResult(status="accepted", external_ref=payload["order_id"], payload=raw)
        if request.action == "create_subscription":
            raw = self._request("POST", f"{BASE_URL}/notifications/v1/subscriptions/{payload['notification_type']}", body={"payloadVersion": payload.get("payload_version", "1.0"), "destinationId": payload["destination_id"]})
            return MutationResult(status="accepted", external_ref=raw.get("payload", {}).get("subscriptionId"), payload=raw)
        if request.action == "create_destination":
            raw = self._request("POST", f"{BASE_URL}/notifications/v1/destinations", body={"name": payload["name"], "resourceSpecification": payload["resource_specification"]})
            return MutationResult(status="accepted", external_ref=raw.get("payload", {}).get("destinationId"), payload=raw)
        if request.action == "create_feed_document":
            raw = self._request("POST", f"{BASE_URL}/feeds/2021-06-30/documents", body={"contentType": payload.get("content_type", "application/json; charset=UTF-8")})
            return MutationResult(status="accepted", external_ref=raw.get("feedDocumentId"), payload=raw)
        if request.action == "create_feed":
            raw = self._request("POST", f"{BASE_URL}/feeds/2021-06-30/feeds", body={"feedType": payload["feed_type"], "marketplaceIds": self.marketplace_ids, "inputFeedDocumentId": payload["input_feed_document_id"]})
            return MutationResult(status="accepted", external_ref=raw.get("feedId"), payload=raw)
        if request.action == "create_report":
            raw = self._request("POST", f"{BASE_URL}/reports/2021-06-30/reports", body={"reportType": payload["report_type"], "marketplaceIds": self.marketplace_ids} | ({"dataStartTime": payload["data_start_time"]} if payload.get("data_start_time") else {}))
            return MutationResult(status="accepted", external_ref=raw.get("reportId"), payload=raw)
        return super()._execute_mutation(request)

    def get_feed_status(self, feed_id: str):
        raw = self.fetch("", "feed_status", feed_id)
        return interpret_async_status(feed_id, raw.get("processingStatus", ""), raw.get("resultFeedDocumentId"))

    def get_report_status(self, report_id: str):
        raw = self.fetch("", "report_status", report_id)
        return interpret_async_status(report_id, raw.get("processingStatus", ""), raw.get("reportDocumentId"))

    # --- Canonical order ingestion --------------------------------------------------------------------

    def sync_orders(self, merchant_id: str, cursor: str | None = None) -> tuple[list[str], str | None]:
        page = self.search(merchant_id, "order", {}, cursor=cursor)
        order_ids = [self._upsert_order(merchant_id, raw) for raw in page.items]
        return order_ids, page.next_cursor

    def _upsert_order(self, merchant_id: str, raw: dict[str, Any]) -> str:
        external_order_id = str(raw["AmazonOrderId"])
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_order_id)
        amazon_status = str(raw.get("OrderStatus", ""))
        canonical_status, fulfillment_status = ORDER_STATUS_MAP.get(amazon_status, (amazon_status or "UNKNOWN", None))
        if amazon_status and amazon_status not in ORDER_STATUS_MAP:
            self.exceptions.create(
                merchant_id=merchant_id, category=ExceptionCategory.UNMAPPED_CHANNEL_STATUS,
                message=f"Amazon order {external_order_id} status {amazon_status!r} has no confirmed canonical mapping - preserved verbatim",
                object_id=external_order_id, severity="info",
            )
        total_amount = int(float((raw.get("OrderTotal") or {}).get("Amount", 0) or 0) * 100)
        if mapping:
            order = self.store.get(Order, merchant_id, mapping.sanocea_id)
        else:
            order = Order(
                merchant_id=merchant_id, channel_id=raw.get("channel_id", "amazon"), order_number=external_order_id,
                status=canonical_status, fulfillment_status=fulfillment_status, total_amount=total_amount,
                currency=(raw.get("OrderTotal") or {}).get("CurrencyCode", "INR"),
                source_of_truth=SourceOfTruth.CHANNEL,
                idempotency=IdempotencyInfo(scope="amazon_order_sync", key=f"amazon:{external_order_id}"),
            )
        order.status = canonical_status
        order.fulfillment_status = fulfillment_status
        order.external_refs = [ref for ref in order.external_refs if not (ref.system == self.name and ref.entity_type == "order")] + [
            ExternalRef(system=self.name, entity_type="order", external_id=external_order_id, channel_id=order.channel_id)
        ]
        self.store.put(order)
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id, sanocea_entity_type="Order", sanocea_id=order.id,
                external_system=self.name, external_entity_type="order", external_id=external_order_id, channel_id=order.channel_id,
            )
        )
        return order.id

    def reconcile(self, merchant_id: str, scope: dict[str, Any]) -> list[dict[str, Any]]:
        external_id = str(scope["external_order_id"])
        mapping = self.store.get_external_mapping(merchant_id, self.name, "order", external_id)
        if not mapping:
            return []
        order = self.store.get(Order, merchant_id, mapping.sanocea_id)
        raw = self.fetch(merchant_id, "order", external_id)
        payload = raw.get("payload", raw)
        amazon_status = str(payload.get("OrderStatus", ""))
        external_status, _ = ORDER_STATUS_MAP.get(amazon_status, (amazon_status or "UNKNOWN", None))
        if order.status != external_status:
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
            if hasattr(self.store, "append_reconciliation_result"):
                self.store.append_reconciliation_result(
                    ReconciliationResult(
                        merchant_id=merchant_id, scope={"connector": self.name, "external_order_id": external_id},
                        canonical_ref={"type": "Order", "id": order.id, "status": order.status},
                        external_ref={"system": self.name, "type": "order", "id": external_id, "status": external_status},
                        result="divergent", exception_id=exc.id,
                    )
                )
            return [{"order_id": order.id, "external_status": external_status, "exception_id": exc.id}]
        return []
