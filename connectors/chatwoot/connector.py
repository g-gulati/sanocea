from __future__ import annotations

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
    Order,
    SourceOfTruth,
    SupportConversation,
    SupportIntent,
)


class ChatwootConnector(GuardedConnector):
    name = "chatwoot"

    def __init__(self, store, workflow=None) -> None:
        """`workflow` is a SupportOrchestrator (duck-typed - only handle_conversation_event() is
        called), mirroring how ShopifyConnector accepts an OrderOrchestrator. Optional and defaulting
        to None keeps every existing direct-construction caller (tests, workload scripts that only
        exercise ingestion) working unchanged; without it, a webhook still creates a SupportConversation
        but nothing classifies intent or acts on it - the same "canonical data only" state Phase 4.6
        closes when a real orchestrator is wired in (see apps/api/app.py)."""
        super().__init__(store)
        self.workflow = workflow
        self.sent_messages: list[dict[str, Any]] = []

    def describe_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            connector=self.name,
            capabilities={
                "ingest_conversation_webhook": Capability(name="ingest_conversation_webhook", status=CapabilityStatus.SUPPORTED),
                "send_message": Capability(name="send_message", status=CapabilityStatus.SUPPORTED, mode=MutationMode.SYNC),
                "refund": Capability(name="refund", status=CapabilityStatus.UNSUPPORTED),
            },
        )

    def ingest_webhook(self, merchant_id: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        headers = {k.lower(): v for k, v in headers.items()}
        secret = self.store.get_credential_ref(merchant_id, "chatwoot_webhook_secret")
        self._verify_signature(headers, body, secret)
        payload = json.loads(body.decode("utf-8"))
        event_id = headers.get("x-chatwoot-delivery") or hashlib.sha256(body).hexdigest()
        raw = self._store_raw(
            merchant_id=merchant_id,
            source="chatwoot:webhook",
            payload=payload,
            headers=headers,
            checksum=hashlib.sha256(body).hexdigest(),
        )

        def op() -> dict[str, Any]:
            contact = payload.get("contact") or {}
            email = contact.get("email")
            customer = self.store.find_one(Customer, merchant_id, email=email) if email else None
            if customer is None:
                customer = Customer(
                    merchant_id=merchant_id,
                    email=email,
                    phone=contact.get("phone_number"),
                    name=contact.get("name"),
                    source_of_truth=SourceOfTruth.CHANNEL,
                )
                self.store.put(customer)
            message = ((payload.get("messages") or [{}])[-1]).get("content") or payload.get("content") or ""
            order = self._resolve_order(merchant_id, customer.id, message)
            conversation = SupportConversation(
                merchant_id=merchant_id,
                channel_id=str(payload.get("inbox", {}).get("id", "chatwoot")),
                customer_id=customer.id,
                order_id=order.id if order else None,
                last_message=message,
                source_of_truth=SourceOfTruth.CHANNEL,
            )
            self.store.put(conversation)
            self.store.put_external_mapping(
                ExternalIdMapping(
                    merchant_id=merchant_id,
                    sanocea_entity_type="SupportConversation",
                    sanocea_id=conversation.id,
                    external_system="chatwoot",
                    external_entity_type="conversation",
                    external_id=str(payload["id"]),
                    channel_id=conversation.channel_id,
                )
            )
            if self.workflow is not None:
                # Phase 4.6: the real runtime path - packages.support.workflow.SupportWorkflowService
                # does deterministic intent classification, canonical-truth lookup, and (where
                # permitted) dispatches into the real post_order engine. This is the ONE place intent
                # gets classified and persisted when a workflow is wired - no second, parallel
                # SupportIntent is created here, or "support must not maintain parallel business truth"
                # would be violated by this connector itself.
                action_result = self.workflow.handle_conversation_event(merchant_id, conversation.id)
                result = {"conversation_id": conversation.id, "order_id": order.id if order else None, "intent": action_result["intent"], "support_action": action_result}
            else:
                intent_name = "where_is_order" if "order" in message.lower() else "unknown"
                intent = SupportIntent(
                    merchant_id=merchant_id,
                    conversation_id=conversation.id,
                    intent=intent_name,
                    confidence=0.8 if intent_name != "unknown" else 0.2,
                    evidence_refs=[raw.id],
                    allowed_actions=["send_status_response"] if order else [],
                )
                self.store.put(intent)
                result = {"conversation_id": conversation.id, "order_id": order.id if order else None, "intent": intent.intent}
            self.audit.record(
                merchant_id=merchant_id,
                actor="chatwoot",
                source="webhook",
                action="conversation_webhook_ingested",
                object_type="SupportConversation",
                object_id=conversation.id,
                evidence_ref=raw.id,
                result="created",
                external_ref=ExternalRef(system="chatwoot", entity_type="conversation", external_id=str(payload["id"])),
            )
            return result

        result, created = self.idempotency.run_once(
            f"{merchant_id}:webhook:chatwoot:conversation", event_id, op
        )
        if not created:
            self.audit.record(
                merchant_id=merchant_id,
                actor="chatwoot",
                source="webhook",
                action="duplicate_webhook_ignored",
                object_type="SupportConversation",
                object_id=result["conversation_id"],
                evidence_ref=raw.id,
                result="duplicate",
            )
        return result | {"idempotent_replay": not created}

    def _resolve_order(self, merchant_id: str, customer_id: str, message: str) -> Order | None:
        candidates = [o for o in self.store.list(Order, merchant_id) if o.customer_id == customer_id]
        for order in candidates:
            if order.order_number in message or order.id in message:
                return order
        return candidates[0] if candidates else None

    def _verify_signature(self, headers: dict[str, str], body: bytes, secret: str) -> None:
        provided = headers.get("x-chatwoot-signature", "")
        timestamp = headers.get("x-chatwoot-timestamp", "")
        digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        expected = f"sha256={digest}"
        if not hmac.compare_digest(provided, expected):
            raise PermissionError("invalid Chatwoot webhook signature")

    def _execute_mutation(self, request: MutationRequest) -> MutationResult:
        if request.action != "send_message":
            return super()._execute_mutation(request)
        self.sent_messages.append(
            {
                "merchant_id": request.merchant_id,
                "conversation_id": request.payload["conversation_id"],
                "content": request.payload["content"],
            }
        )
        return MutationResult(status="sent", external_ref=str(request.payload["conversation_id"]))
