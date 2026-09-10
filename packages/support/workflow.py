from __future__ import annotations

from sanocea.packages.ai import AIProvider, DeterministicAIProvider
from sanocea.packages.audit import AuditLedger
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.models import (
    Cancellation,
    CustomerSupportAction,
    Exchange,
    Order,
    Refund,
    Return,
    Shipment,
    SupportConversation,
    SupportIntent,
)
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService


INTENTS = [
    "order_status",
    "shipment_status",
    "cancellation_request",
    "cancellation_status",
    "return_request",
    "refund_request",
    "address_change",
    "exchange_request",
    "damaged_item",
    "wrong_colour",
    "wrong_size",
    "wrong_item",
    "product_information",
    "availability_question",
    "delivery_problem",
    "partial_order_issue",
    "refund_status",
    "return_status",
    "exchange_status",
    "rto_status",
    "partial_refund_request",
    "unknown",
]

# Intents where a real, policy-gated canonical action can be REQUESTED (never executed) through the
# post_order engine, given a resolved order. Anything not in this set that still needs a mutation
# (exchange - the desired variant SKU cannot be parsed from free text) stays EXCEPTION-ONLY.
_ACTIONABLE_INTENTS = {"refund_request", "return_request", "cancellation_request"}


class SupportWorkflowService:
    """Journey: Chatwoot-shaped conversation event -> authenticated/verified ingress (at the connector
    layer - ChatwootConnector._verify_signature) -> SupportConversation -> deterministic intent/routing
    (here) -> canonical commerce truth lookup -> deterministic response/action where permitted ->
    approval/escalation where required -> response through the connector boundary.

    Support never maintains parallel business truth: every status answer is read live from the same
    canonical Order/Shipment/Refund/Return/Exchange/Cancellation rows the rest of the system uses, and
    every actionable request (refund/return/cancellation) is dispatched into the SAME policy-gated
    post_order engine methods a direct API call would use - never a support-only shortcut. Support
    NEVER calls execute_refund/execute_cancellation/complete_exchange/progress_return itself; it only
    ever creates the real, policy-gated request object and lets it flow through the ordinary operator
    approval/execution path (visible via the ordinary Approval/queries surfaces)."""

    def __init__(self, store, chatwoot_connector, ai: AIProvider | None = None, *, post_order=None) -> None:
        self.store = store
        self.chatwoot = chatwoot_connector
        self.ai = ai or DeterministicAIProvider()
        self.post_order = post_order
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)
        self.ai_calls: list[dict] = []

    def handle_conversation(self, merchant_id: str, conversation_id: str) -> CustomerSupportAction:
        conversation = self.store.get(SupportConversation, merchant_id, conversation_id)
        deterministic = self._deterministic_intent(conversation.last_message or "")
        if deterministic:
            intent = deterministic
            confidence = 1.0
            evidence_refs = conversation.external_refs and [conversation.external_refs[0].external_id] or []
            classifier = "deterministic"
        else:
            ai_result = self.ai.classify(conversation.last_message or "", INTENTS, conversation.external_refs and [conversation.external_refs[0].external_id] or [])
            self.ai_calls.append(
                {
                    "purpose": "support_intent_classification",
                    "merchant_id": merchant_id,
                    "workflow": "support",
                    "provider": ai_result.provider,
                    "model": ai_result.model,
                    "input_class": "support_message",
                    "deterministic_attempted_first": True,
                    "accepted": ai_result.confidence >= 0.7 and ai_result.output.get("label") != "unknown",
                    "latency_ms": None,
                    "estimated_tokens": len((conversation.last_message or "").split()),
                    "estimated_cost": 0.0,
                }
            )
            self.audit.record(
                merchant_id=merchant_id,
                actor="support",
                source="ai_provider",
                action="ai_invoked",
                object_type="SupportConversation",
                object_id=conversation.id,
                result=ai_result.output.get("label"),
            )
            intent = ai_result.output["label"]
            confidence = ai_result.confidence
            evidence_refs = ai_result.evidence_refs
            classifier = ai_result.provider
        support_intent = SupportIntent(
            merchant_id=merchant_id,
            conversation_id=conversation.id,
            intent=intent,
            confidence=confidence,
            evidence_refs=evidence_refs,
        )
        self.store.put(support_intent)
        order = self.store.get(Order, merchant_id, conversation.order_id) if conversation.order_id else None
        mode, action, response = self._decide(merchant_id, intent, order)
        record = CustomerSupportAction(
            merchant_id=merchant_id,
            conversation_id=conversation.id,
            order_id=order.id if order else None,
            intent=intent,
            handling_mode=mode,
            action=action,
            response_text=response,
            policy_decision=f"{mode}:{classifier}",
            status="proposed",
        )
        if mode == "AUTOMATIC":
            self.chatwoot.execute_mutation(
                MutationRequest(
                    merchant_id=merchant_id,
                    action="send_message",
                    object_type="SupportConversation",
                    payload={"conversation_id": conversation.id, "content": response},
                    idempotency_key=f"support-response:{conversation.id}:{intent}",
                )
            )
            record.status = "executed"
        elif mode == "APPROVAL-GATED":
            # The real, linked Approval was already created inside the post_order engine call in
            # _decide_actionable() below - support does not create a second, parallel approval surface.
            # "requested" (not "executed") makes explicit that support created the canonical request
            # object but never performed the underlying mutation itself.
            record.status = "requested"
        elif mode == "EXCEPTION-ONLY":
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.UNSUPPORTED_CUSTOMER_REQUEST,
                message=f"Support request requires intervention: {intent}",
                object_id=conversation.id,
            )
            record.status = "escalated"
        self.store.put(record)
        self.audit.record(
            merchant_id=merchant_id,
            actor="support",
            source="support_workflow",
            action="support_action_classified",
            object_type="CustomerSupportAction",
            object_id=record.id,
            result=record.handling_mode,
        )
        return record

    def _decide(self, merchant_id: str, intent: str, order: Order | None) -> tuple[str, str, str]:
        config = self.store.get_config(merchant_id)
        auto_response = config.get("support", {}).get("auto_response", {})
        if order and intent == "order_status" and auto_response.get(intent, True):
            return "AUTOMATIC", "send_status_response", f"Order #{order.order_number} is {order.status}. Payment status is {order.payment_status}."
        if order and intent in {"shipment_status", "delivery_problem"} and auto_response.get(intent, True):
            return "AUTOMATIC", "send_shipment_status", self._shipment_status_text(merchant_id, order)
        if order and intent == "refund_status" and auto_response.get("refund_status", True):
            refunds = [item for item in self.store.list(Refund, merchant_id) if item.order_id == order.id]
            status = refunds[-1].status if refunds else "not_started"
            return "AUTOMATIC", "send_refund_status", f"Refund status for order #{order.order_number}: {status}."
        if order and intent == "return_status" and auto_response.get("return_status", True):
            returns = [item for item in self.store.list(Return, merchant_id) if item.order_id == order.id]
            status = returns[-1].status if returns else "not_started"
            return "AUTOMATIC", "send_return_status", f"Return status for order #{order.order_number}: {status}."
        if order and intent == "exchange_status" and auto_response.get("exchange_status", True):
            exchanges = [item for item in self.store.list(Exchange, merchant_id) if item.order_id == order.id]
            status = exchanges[-1].status if exchanges else "not_started"
            return "AUTOMATIC", "send_exchange_status", f"Exchange status for order #{order.order_number}: {status}."
        if order and intent == "cancellation_status" and auto_response.get("cancellation_status", True):
            cancellations = [item for item in self.store.list(Cancellation, merchant_id) if item.order_id == order.id]
            status = cancellations[-1].status if cancellations else "not_requested"
            return "AUTOMATIC", "send_cancellation_status", f"Cancellation status for order #{order.order_number}: {status}."
        if order and intent == "rto_status" and auto_response.get("rto_status", True):
            shipments = [item for item in self.store.list(Shipment, merchant_id) if item.order_id == order.id]
            status = shipments[-1].status if shipments else "not_started"
            return "AUTOMATIC", "send_rto_status", f"Return-to-origin status for order #{order.order_number}: {status}."
        if intent in {"product_information", "availability_question"} and auto_response.get(intent, True):
            return "AUTOMATIC", "send_factual_catalog_response", "I can help with current product information from the verified catalogue."
        if order and self.post_order is not None and intent in _ACTIONABLE_INTENTS:
            return self._decide_actionable(merchant_id, intent, order)
        if intent in {"exchange_request", "wrong_colour", "wrong_size", "wrong_item", "damaged_item", "partial_order_issue"}:
            return "EXCEPTION-ONLY", "create_support_exception", "A team member will review this item-specific issue."
        if intent in _ACTIONABLE_INTENTS or intent == "partial_refund_request":
            # No order context could be resolved (or post_order was never wired in) - support cannot
            # safely act without a confirmed order, so this is real human-review work, not a fake
            # approval placeholder. This branch is what a prior bug looked like before this phase: it
            # used to silently return "APPROVAL-GATED" with no Approval/Exception ever created, making
            # the request invisible to every operator query surface.
            return "EXCEPTION-ONLY", "create_support_exception", "A team member will review and action this request."
        if intent == "address_change" and order and order.fulfillment_status:
            return "EXCEPTION-ONLY", "address_change_blocked", "Address changes after fulfilment require review."
        return "EXCEPTION-ONLY", "unsupported_request", "A team member will review this request."

    def _decide_actionable(self, merchant_id: str, intent: str, order: Order) -> tuple[str, str, str]:
        """Dispatches into the real, already-tested, policy-gated post_order engine. Each evaluate_*()
        call is itself idempotent per order (post_order._existing_for_order de-dupes), so a duplicate
        support event (webhook redelivery already de-duped one layer up, or two conversations about the
        same order) can never create two competing Refund/Return/Cancellation rows for one order."""
        if intent == "refund_request":
            refund = self.post_order.evaluate_refund(merchant_id, order, order.total_amount)
            pending = refund.status == "approval_required"
            text = f"Your refund request for order #{order.order_number} has been recorded and is {'awaiting approval' if pending else 'permitted for processing'}."
            return "APPROVAL-GATED", "refund_requested", text
        if intent == "return_request":
            self.post_order.evaluate_return(merchant_id, order, "customer_support_request")
            text = f"Your return request for order #{order.order_number} has been recorded and will be reviewed."
            return "APPROVAL-GATED", "return_requested", text
        if intent == "cancellation_request":
            cancellation = self.post_order.evaluate_cancellation(merchant_id, order)
            if cancellation.status == "denied":
                return "EXCEPTION-ONLY", "cancellation_not_eligible", f"Order #{order.order_number} can no longer be cancelled (already fulfilled) - a team member will review options."
            text = f"Your cancellation request for order #{order.order_number} has been recorded."
            return "APPROVAL-GATED", "cancellation_requested", text
        raise AssertionError(f"unreachable: {intent} not in _ACTIONABLE_INTENTS")

    def _shipment_status_text(self, merchant_id: str, order: Order) -> str:
        shipments = [s for s in self.store.list(Shipment, merchant_id) if s.order_id == order.id]
        if not shipments:
            return f"Order #{order.order_number} is {order.status}; no shipment has been created yet."
        shipment = shipments[-1]
        if shipment.status == "NDR":
            return f"Your shipment for order #{order.order_number} (tracking {shipment.tracking_number} via {shipment.carrier}) had a failed delivery attempt and is being followed up with the courier."
        return f"Shipment for order #{order.order_number} via {shipment.carrier} (tracking {shipment.tracking_number}) is currently: {shipment.status}."

    def _deterministic_intent(self, text: str) -> str | None:
        lowered = text.lower()
        if any(token in lowered for token in ["where is my parcel", "where is my package", "parcel status"]):
            return "shipment_status"
        if any(token in lowered for token in ["where is", "order status", "status of", "when will"]) and "order" in lowered:
            return "order_status"
        if "delivered" in lowered and any(token in lowered for token in ["don't have", "do not have", "not received"]):
            return "delivery_problem"
        if "only one item" in lowered or "partial order" in lowered or "missing item" in lowered:
            return "partial_order_issue"
        if any(token in lowered for token in ["tracking", "not moved", "ship", "arrive", "delivery", "courier"]):
            return "shipment_status" if "not moved" not in lowered else "delivery_problem"
        if "cancel" in lowered:
            if any(token in lowered for token in ["where", "when", "status"]):
                return "cancellation_status"
            return "cancellation_request"
        if "partial refund" in lowered:
            return "partial_refund_request"
        if "refund" in lowered and any(token in lowered for token in ["where", "when", "status"]):
            return "refund_status"
        if "refund" in lowered:
            return "refund_request"
        if "return" in lowered and any(token in lowered for token in ["where", "when", "status"]):
            return "return_status"
        if "return" in lowered:
            return "return_request"
        if "address" in lowered:
            return "address_change"
        if "exchange" in lowered or "change size" in lowered:
            if any(token in lowered for token in ["where", "when", "status"]):
                return "exchange_status"
            return "exchange_request"
        if "rto" in lowered or "return to origin" in lowered:
            return "rto_status"
        if "damaged" in lowered or "broken" in lowered:
            return "damaged_item"
        if "wrong item" in lowered or "incorrect item" in lowered:
            return "wrong_item"
        if "wrong colour" in lowered or "wrong color" in lowered:
            return "wrong_colour"
        if "wrong size" in lowered:
            return "wrong_size"
        if any(token in lowered for token in ["available", "in stock", "inventory", "replacement"]):
            return "availability_question"
        if any(token in lowered for token in ["what material", "composition", "product info"]):
            return "product_information"
        return None
