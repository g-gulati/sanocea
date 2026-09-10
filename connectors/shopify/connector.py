from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
    ReconciliationResult,
    SourceOfTruth,
    SyncMetadata,
)
from sanocea.workers.workflow import FakeTemporalEngine


class ShopifyConnector(GuardedConnector):
    name = "shopify"

    def __init__(self, store, workflow: FakeTemporalEngine) -> None:
        super().__init__(store)
        self.workflow = workflow
        self.external_orders: dict[str, dict[str, Any]] = {}
        self.external_products: dict[str, dict[str, Any]] = {}
        self.external_products_by_sku: dict[str, str] = {}

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "ingest_order_webhook": Capability(name="ingest_order_webhook", status=CapabilityStatus.SUPPORTED),
                "refund": Capability(name="refund", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "create_fulfilment": Capability(name="create_fulfilment", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "publish_product": Capability(name="publish_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC, api_versions=["admin-graphql-2026-07"]),
                "create_product": Capability(name="create_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "update_product": Capability(name="update_product", status=CapabilityStatus.SUPPORTED, mode=MutationMode.ASYNC),
                "fetch_product": Capability(name="fetch_product", status=CapabilityStatus.SUPPORTED),
                "fetch_inventory_observation": Capability(name="fetch_inventory_observation", status=CapabilityStatus.SUPPORTED),
                "fetch_fulfilment": Capability(name="fetch_fulfilment", status=CapabilityStatus.SUPPORTED),
                "fetch_customer": Capability(name="fetch_customer", status=CapabilityStatus.SUPPORTED),
                "fetch": Capability(name="fetch", status=CapabilityStatus.SUPPORTED),
                "reconcile": Capability(name="reconcile", status=CapabilityStatus.SUPPORTED),
            },
        )

    def ingest_webhook(self, merchant_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in headers.items()}
        secret = self.store.get_credential_ref(merchant_id, "shopify_webhook_secret")
        self._verify_hmac(headers, body, secret)
        topic = headers.get("x-shopify-topic", "")
        webhook_id = headers.get("x-shopify-webhook-id") or hashlib.sha256(body).hexdigest()
        payload = json.loads(body.decode("utf-8"))
        checksum = hashlib.sha256(body).hexdigest()
        raw = self._store_raw(
            merchant_id=merchant_id,
            source=f"shopify:{topic}",
            payload=payload,
            headers=headers,
            checksum=checksum,
        )

        def op() -> dict[str, Any]:
            result = self._upsert_order(merchant_id, payload, raw.id, webhook_id)
            self.audit.record(
                merchant_id=merchant_id,
                actor="shopify",
                source="webhook",
                action="order_webhook_ingested",
                object_type="Order",
                object_id=result["order_id"],
                evidence_ref=raw.id,
                result="created_or_updated",
                external_ref=ExternalRef(system="shopify", entity_type="order", external_id=str(payload["id"])),
            )
            self.workflow.start_or_signal_order(merchant_id, result["order_id"], {"topic": topic, "raw_payload_id": raw.id})
            return result

        result, created = self.idempotency.run_once(
            f"{merchant_id}:webhook:shopify:{topic}", webhook_id, op
        )
        if not created:
            self.audit.record(
                merchant_id=merchant_id,
                actor="shopify",
                source="webhook",
                action="duplicate_webhook_ignored",
                object_type="Order",
                object_id=result["order_id"],
                evidence_ref=raw.id,
                result="duplicate",
            )
        return result | {"idempotent_replay": not created}

    def _upsert_order(self, merchant_id: str, payload: dict[str, Any], raw_id: str, webhook_id: str) -> dict[str, Any]:
        external_id = str(payload["id"])
        mapping = self.store.get_external_mapping(merchant_id, "shopify", "order", external_id)
        email = payload.get("email")
        customer = None
        if email:
            customer = self.store.find_one(Customer, merchant_id, email=email)
            if customer is None:
                customer = Customer(
                    merchant_id=merchant_id,
                    email=email,
                    name=(payload.get("customer") or {}).get("first_name"),
                    source_of_truth=SourceOfTruth.CHANNEL,
                    sync=SyncMetadata(raw_payload_ref=raw_id),
                )
                self.store.put(customer)
        financial = payload.get("financial_status") or "unknown"
        cancelled = bool(payload.get("cancelled_at"))
        status = "CANCELLED" if cancelled else ("PAID" if financial == "paid" else financial.upper())
        if mapping:
            order = self.store.get(Order, merchant_id, mapping.sanocea_id)
            incoming_sequence = int(payload.get("updated_sequence", 0) or 0)
            current_sequence = order.sync.event_sequence or 0
            if incoming_sequence and incoming_sequence < current_sequence:
                self.audit.record(
                    merchant_id=merchant_id,
                    actor="shopify",
                    source="webhook",
                    action="out_of_order_event_ignored",
                    object_type="Order",
                    object_id=order.id,
                    evidence_ref=raw_id,
                    result="ignored",
                )
                return {"order_id": order.id, "status": order.status}
        else:
            order = Order(
                merchant_id=merchant_id,
                channel_id=payload.get("channel_id", "shopify"),
                customer_id=customer.id if customer else None,
                order_number=str(payload.get("order_number") or payload.get("name") or external_id),
                status=status,
                payment_status=financial,
                fulfillment_status=payload.get("fulfillment_status"),
                total_amount=int(float(payload.get("total_price", "0")) * 100),
                currency=payload.get("currency", "INR"),
                source_of_truth=SourceOfTruth.CHANNEL,
                idempotency=IdempotencyInfo(scope="shopify_order_webhook", key=webhook_id),
            )
        order.status = status
        order.payment_status = financial
        order.external_refs = [
            ref for ref in order.external_refs if not (ref.system == "shopify" and ref.entity_type == "order")
        ] + [ExternalRef(system="shopify", entity_type="order", external_id=external_id, channel_id=order.channel_id)]
        order.sync.raw_payload_ref = raw_id
        order.sync.event_sequence = int(payload.get("updated_sequence", order.sync.event_sequence or 0) or 0)
        self.store.put(order)
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id,
                sanocea_entity_type="Order",
                sanocea_id=order.id,
                external_system="shopify",
                external_entity_type="order",
                external_id=external_id,
                channel_id=order.channel_id,
            )
        )
        for item in payload.get("line_items", []):
            line = OrderLine(
                merchant_id=merchant_id,
                order_id=order.id,
                sku=item.get("sku"),
                title=item.get("title") or "Untitled",
                quantity=int(item.get("quantity", 1)),
                unit_amount=int(float(item.get("price", "0")) * 100),
                source_of_truth=SourceOfTruth.CHANNEL,
                sync=SyncMetadata(raw_payload_ref=raw_id),
            )
            self.store.put(line)
        self.external_orders[external_id] = payload
        return {"order_id": order.id, "status": order.status}

    def _verify_hmac(self, headers: dict[str, str], body: bytes, secret: str) -> None:
        provided = headers.get("x-shopify-hmac-sha256")
        digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode()
        if not provided or not hmac.compare_digest(provided, expected):
            raise PermissionError("invalid Shopify webhook HMAC")

    def fetch(self, merchant_id: str, entity_type: str, external_id: str) -> dict[str, Any]:
        self.describe_capabilities().require("fetch")
        if entity_type != "order":
            if entity_type == "product":
                # Normalized shape (title/sku/price/status) - this is the connector-agnostic contract
                # ProductPublicationService.verify() compares against; the raw Shopify payload
                # (variants array, ACTIVE/DRAFT status vocabulary) stays internal to this connector. A
                # real abstraction leak found and closed while wiring the WooCommerce platform-
                # independence test: verify() used to read raw["variants"][0]["sku"] and the literal
                # string "ACTIVE" directly - Shopify-specific shape leaking into domain-adjacent code.
                raw = self.external_products[external_id]
                variant = (raw.get("variants") or [{}])[0]
                return {
                    "title": raw.get("title"),
                    "sku": variant.get("sku"),
                    "price": variant.get("price"),
                    "status": "active" if raw.get("status") == "ACTIVE" else "inactive",
                    "raw": raw,
                }
            if entity_type == "inventory":
                return {"sku": external_id, "available": 10}
            if entity_type == "fulfilment":
                return {"order_id": external_id, "status": self.external_orders.get(external_id, {}).get("fulfillment_status") or "unfulfilled"}
            if entity_type == "customer":
                return {"email": external_id}
            raise KeyError(entity_type)
        return self.external_orders[external_id]

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        simulate = request.payload.get("simulate")
        if simulate == "429":
            raise RuntimeError("Shopify API 429 rate limited")
        if simulate == "500":
            raise RuntimeError("Shopify API 500")
        if simulate == "timeout_before_mutation":
            raise TimeoutError("timeout before mutation")
        if request.action in {"publish_product", "create_product", "update_product"}:
            # Sanocea's payload here is CONNECTOR-AGNOSTIC (title/sku/price/currency/product_type/
            # attributes) - this connector's own wire shape (variants array, metafields
            # namespace/key/value, Shopify's productType casing) is built HERE, internal to the
            # Shopify boundary, never upstream in domain code. See
            # docs/architecture/multi-platform-connector-hardening.md closure item 2 - this used to be
            # built by ProductPublicationService.prepare_shopify_payload() and handed in pre-shaped,
            # forcing every other connector to reverse-engineer Shopify's own wire format back out.
            payload = request.payload
            sku = str(payload.get("sku"))
            existing_id = self.external_products_by_sku.get(sku)
            if existing_id:
                return MutationResult(status="accepted", external_ref=existing_id, payload=self.external_products[existing_id])
            external_id = f"gid://shopify/Product/{hashlib.sha256(sku.encode()).hexdigest()[:12]}"
            attributes = payload.get("attributes") or {}
            product = {
                "id": external_id,
                "title": payload.get("title"),
                "productType": payload.get("product_type"),
                "variants": [{"sku": sku, "price": payload.get("price"), "currency": payload.get("currency")}],
                "metafields": [{"namespace": "sanocea", "key": k, "value": str(v)} for k, v in attributes.items()],
                "media": payload.get("media", []),
                "status": "ACTIVE",
            }
            self.external_products[external_id] = product
            self.external_products_by_sku[sku] = external_id
            if simulate == "timeout_after_mutation":
                raise TimeoutError("timeout after successful mutation")
            return MutationResult(status="accepted", external_ref=external_id, payload=product)
        return MutationResult(
            status="accepted",
            async_operation_id=f"shopify-{request.action}-{request.idempotency_key}",
            payload={"idempotency_key": request.idempotency_key},
        )

    def reconcile(self, merchant_id: str, scope: dict[str, Any]) -> list[dict[str, Any]]:
        external_id = str(scope["external_order_id"])
        mapping = self.store.get_external_mapping(merchant_id, "shopify", "order", external_id)
        if not mapping:
            return []
        order = self.store.get(Order, merchant_id, mapping.sanocea_id)
        external = self.external_orders[external_id]
        external_status = "CANCELLED" if external.get("cancelled_at") else ("PAID" if external.get("financial_status") == "paid" else "UNKNOWN")
        if order.status != external_status:
            from sanocea.packages.domain_contract.models import ExceptionRecord

            exc = ExceptionRecord(
                merchant_id=merchant_id,
                severity="warning",
                category="reconciliation_divergence",
                message=f"Order {order.id} canonical={order.status} external={external_status}",
                object_id=order.id,
                remediation_options=["refresh_from_source", "manual_review"],
            )
            self.store.put(exc)
            self.audit.record(
                merchant_id=merchant_id,
                actor="reconciliation",
                source="shopify",
                action="divergence_detected",
                object_type="Order",
                object_id=order.id,
                result="exception_created",
                error=exc.message,
            )
            if hasattr(self.store, "append_reconciliation_result"):
                self.store.append_reconciliation_result(
                    ReconciliationResult(
                        merchant_id=merchant_id,
                        scope={"connector": "shopify", "external_order_id": external_id},
                        canonical_ref={"type": "Order", "id": order.id, "status": order.status},
                        external_ref={"system": "shopify", "type": "order", "id": external_id, "status": external_status},
                        result="divergent",
                        exception_id=exc.id,
                    )
                )
            return [{"order_id": order.id, "external_status": external_status, "exception_id": exc.id}]
        return []
