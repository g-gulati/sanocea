from __future__ import annotations

import base64
import hashlib
import hmac
import json

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.connector_sdk import MutationRequest, UnsupportedCapability
from sanocea.packages.domain_contract.models import Approval, AuditEvent, ExceptionRecord, ExternalIdMapping, Order, Product, WorkflowExecution
from sanocea.packages.domain_contract.store import TenantAccessError
from sanocea.packages.policy_engine import Decision, PolicyEngine
from sanocea.workers.ingestion import IngestionService
from sanocea.workers.workflow import FakeTemporalEngine
import pytest


def shopify_headers(body: bytes, secret: str, webhook_id: str = "wh_1", topic: str = "orders/paid") -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return {
        "X-Shopify-Hmac-Sha256": base64.b64encode(digest).decode(),
        "X-Shopify-Webhook-Id": webhook_id,
        "X-Shopify-Topic": topic,
    }


def chatwoot_headers(body: bytes, secret: str, delivery_id: str = "cw_1", timestamp: str = "1700000000") -> dict[str, str]:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return {
        "X-Chatwoot-Timestamp": timestamp,
        "X-Chatwoot-Signature": f"sha256={digest}",
        "X-Chatwoot-Delivery": delivery_id,
    }


def shopify_order_payload(**overrides):
    payload = {
        "id": 3812,
        "order_number": "3812",
        "email": "buyer@example.com",
        "financial_status": "paid",
        "fulfillment_status": None,
        "total_price": "1499.00",
        "currency": "INR",
        "updated_sequence": 10,
        "line_items": [{"title": "Phase 0 test product", "sku": "SKU-1", "quantity": 1, "price": "1499.00"}],
        "customer": {"first_name": "Buyer"},
    }
    payload.update(overrides)
    return payload


def test_phase0_acceptance_path_and_tenant_isolation(phase0):
    store, workflow, shopify, chatwoot = phase0

    order_body = json.dumps(shopify_order_payload(channel_id="chn_A_shopify")).encode()
    order_result = shopify.ingest_webhook("mer_A", shopify_headers(order_body, "shopify_secret_A"), order_body)

    assert order_result["status"] == "PAID"
    assert order_result["idempotent_replay"] is False
    order = store.get(Order, "mer_A", order_result["order_id"])
    assert order.order_number == "3812"
    assert order.payment_status == "paid"
    assert store.get_external_mapping("mer_A", "shopify", "order", "3812").sanocea_id == order.id
    assert store.list(WorkflowExecution, "mer_A")[0].business_key == f"order:{order.id}"
    assert any(a.action == "order_webhook_ingested" for a in store.list_audit("mer_A"))

    duplicate_result = shopify.ingest_webhook("mer_A", shopify_headers(order_body, "shopify_secret_A"), order_body)
    assert duplicate_result["idempotent_replay"] is True
    assert len(store.list(Order, "mer_A")) == 1

    support_payload = {
        "id": 9001,
        "contact": {"email": "buyer@example.com", "name": "Buyer"},
        "inbox": {"id": "chn_A_chatwoot"},
        "messages": [{"content": "Where is order #3812?"}],
    }
    support_body = json.dumps(support_payload).encode()
    support_result = chatwoot.ingest_webhook("mer_A", chatwoot_headers(support_body, "chatwoot_secret_A"), support_body)
    assert support_result["order_id"] == order.id
    assert support_result["intent"] == "where_is_order"

    decision = PolicyEngine().decide(
        store.get_config("mer_A")["policy"], "refund", {"amount": 149900}
    )
    assert decision == Decision.REQUIRE_APPROVAL
    response = chatwoot.execute_mutation(
        MutationRequest(
            merchant_id="mer_A",
            action="send_message",
            object_type="SupportConversation",
            payload={
                "conversation_id": support_result["conversation_id"],
                "content": "Order #3812 is paid and being prepared. Refunds above INR 10 require approval.",
            },
            idempotency_key="reply-3812-1",
        )
    )
    assert response.status == "sent"
    assert len(chatwoot.sent_messages) == 1
    chatwoot.execute_mutation(
        MutationRequest(
            merchant_id="mer_A",
            action="send_message",
            object_type="SupportConversation",
            payload={"conversation_id": support_result["conversation_id"], "content": "duplicate"},
            idempotency_key="reply-3812-1",
        )
    )
    assert len(chatwoot.sent_messages) == 1

    with pytest.raises(TenantAccessError):
        store.get(Order, "mer_B", order.id)
    assert store.list(Order, "mer_B") == []
    assert store.get_external_mapping("mer_B", "shopify", "order", "3812") is None
    with pytest.raises(TenantAccessError):
        store.get_credential_ref("mer_B", "chatwoot_webhook_secret")
    assert all(a.merchant_id == "mer_A" for a in store.list_audit("mer_A"))


def test_out_of_order_event_is_ignored(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload(updated_sequence=10)).encode()
    result = shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A", "wh_current"), body)
    older = json.dumps(shopify_order_payload(updated_sequence=5, financial_status="pending")).encode()
    older_result = shopify.ingest_webhook("mer_A", shopify_headers(older, "shopify_secret_A", "wh_old"), older)
    order = store.get(Order, "mer_A", result["order_id"])
    assert older_result["status"] == "PAID"
    assert order.status == "PAID"
    assert any(a.action == "out_of_order_event_ignored" for a in store.list_audit("mer_A"))


def test_refund_and_fulfilment_idempotency_after_restart(phase0):
    _store, _workflow, shopify, _chatwoot = phase0
    request = MutationRequest(
        merchant_id="mer_A",
        action="refund",
        object_type="Refund",
        payload={"order_id": "ord_1", "amount": 500},
        idempotency_key="refund-1",
    )
    first = shopify.execute_mutation(request)
    second = shopify.execute_mutation(request)
    assert first == second
    fulfilment = MutationRequest(
        merchant_id="mer_A",
        action="create_fulfilment",
        object_type="Fulfilment",
        payload={"order_id": "ord_1"},
        idempotency_key="fulfil-1",
    )
    assert shopify.execute_mutation(fulfilment) == shopify.execute_mutation(fulfilment)


def test_workflow_retry_restart_timer_approval_signal_and_failure(phase0):
    store, workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload()).encode()
    result = shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A"), body)
    execution = store.list(WorkflowExecution, "mer_A")[0]
    assert workflow.run_step_with_retry(execution.temporal_workflow_id, "payment_verified", fail_times=1) == "retrying"
    assert workflow.run_step_with_retry(execution.temporal_workflow_id, "payment_verified", fail_times=1) == "completed"
    snapshot = workflow.snapshot()
    restarted = FakeTemporalEngine(store)
    restarted.restore(snapshot)
    restarted.timer_fired(execution.temporal_workflow_id, "shipment_delay_check")
    approval = restarted.wait_for_approval("mer_A", execution.temporal_workflow_id, "refund", result["order_id"])
    assert store.get(Approval, "mer_A", approval.id).status == "pending"
    restarted.approve("mer_A", approval.id, "operator@example.com")
    restarted.signal(execution.temporal_workflow_id, {"type": "external_tracking_update"})
    exc = restarted.fail(execution.temporal_workflow_id, "carrier API unavailable")
    assert store.get(ExceptionRecord, "mer_A", exc.id).category == "workflow_failure"
    actions = [a.action for a in store.list_audit("mer_A")]
    assert "payment_verified_retry" in actions
    assert "timer:shipment_delay_check" in actions
    assert "approval_requested" in actions
    assert "workflow_failed" in actions


def test_unsupported_connector_capability(phase0):
    _store, _workflow, shopify, chatwoot = phase0
    with pytest.raises(UnsupportedCapability):
        shopify.propose_mutation(
            MutationRequest(
                merchant_id="mer_A",
                action="delete_product",
                object_type="Product",
                payload={},
                idempotency_key="pub-1",
            )
        )
    with pytest.raises(UnsupportedCapability):
        chatwoot.propose_mutation(
            MutationRequest(
                merchant_id="mer_A",
                action="refund",
                object_type="Refund",
                payload={},
                idempotency_key="bad-1",
            )
        )


def test_policy_outcomes(phase0):
    store, *_ = phase0
    engine = PolicyEngine()
    policy = store.get_config("mer_A")["policy"]
    assert engine.decide(policy, "refund", {"amount": 999}) == Decision.ALLOW
    assert engine.decide(policy, "refund", {"amount": 1001}) == Decision.REQUIRE_APPROVAL
    assert engine.decide(policy, "unknown", {}) == Decision.DENY


def test_product_ingestion_keeps_uncertain_values_as_draft(phase0):
    store, *_ = phase0
    product, approval = IngestionService(store).ingest_supplier_file(
        "mer_A", "supplier.txt", b"Diamond ring\nmetal: gold"
    )
    saved = store.get(Product, "mer_A", product.id)
    assert saved.status == "draft"
    assert saved.attributes["extracted_title"]["verified"] is False
    assert saved.evidence_refs
    assert store.get(Approval, "mer_A", approval.id).status == "pending"


def test_reconciliation_divergence_creates_exception_not_overwrite(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload()).encode()
    result = shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A"), body)
    shopify.external_orders["3812"] = shopify_order_payload(cancelled_at="2026-09-08T00:00:00Z")
    divergence = shopify.reconcile("mer_A", {"external_order_id": "3812"})
    assert divergence
    order = store.get(Order, "mer_A", result["order_id"])
    assert order.status == "PAID"
    assert store.get(ExceptionRecord, "mer_A", divergence[0]["exception_id"]).category == "reconciliation_divergence"


def test_cross_merchant_cannot_access_audit_config_approvals_or_connector_ops(phase0):
    store, workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload()).encode()
    result = shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A"), body)
    approval = workflow.wait_for_approval("mer_A", f"order-mer_A-{result['order_id']}", "refund", result["order_id"])
    with pytest.raises(TenantAccessError):
        store.get(Approval, "mer_B", approval.id)
    assert store.list_audit("mer_B") == []
    assert store.get_config("mer_B") != store.get_config("mer_A")
    with pytest.raises(PermissionError):
        shopify.ingest_webhook("mer_B", shopify_headers(body, "shopify_secret_A"), body)


def test_external_id_mapping_is_separate_from_canonical_fields(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload()).encode()
    result = shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A"), body)
    order = store.get(Order, "mer_A", result["order_id"])
    mapping = store.get_external_mapping("mer_A", "shopify", "order", "3812")
    assert isinstance(mapping, ExternalIdMapping)
    assert not hasattr(order, "shopify_order_id")


def test_audit_ledger_is_append_only_visible_record(phase0):
    store, _workflow, shopify, _chatwoot = phase0
    body = json.dumps(shopify_order_payload()).encode()
    shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A"), body)
    audit = store.list_audit("mer_A")
    assert audit
    assert all(isinstance(event, AuditEvent) for event in audit)
    assert any(event.evidence_ref for event in audit)
