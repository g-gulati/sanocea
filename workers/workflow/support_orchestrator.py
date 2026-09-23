from __future__ import annotations

from typing import Any


class SupportOrchestrator:
    """Phase 4.6: the runtime seam between ChatwootConnector's webhook ingress and
    packages.support.workflow.SupportWorkflowService, mirroring OrderOrchestrator's role for the
    Shopify order path. Without this, a Chatwoot webhook only ever produced canonical data a
    hypothetical agent could later read - nothing in the running application actually classified
    intent or acted on it. ChatwootConnector calls handle_conversation_event() from inside its own
    idempotency-guarded op(), so a duplicate webhook delivery can never trigger this (and therefore
    never the underlying post_order engine calls) more than once per unique event."""

    def __init__(self, support_service) -> None:
        self.support = support_service

    def handle_conversation_event(self, merchant_id: str, conversation_id: str) -> dict[str, Any]:
        action = self.support.handle_conversation(merchant_id, conversation_id)
        return {"action_id": action.id, "intent": action.intent, "handling_mode": action.handling_mode, "status": action.status}
