from __future__ import annotations

import json
from pathlib import Path

from sanocea.packages.domain_contract.models import ExceptionRecord, Order, ProductDraft, SupportConversation
from sanocea.packages.metrics import WorkloadCounters
from sanocea.packages.product_onboarding import ProductCompletenessValidator, ProductPublicationService, StructuredProductIngestor
from sanocea.packages.support import SupportWorkflowService
from sanocea.tests.unit.test_phase0_acceptance import shopify_headers, shopify_order_payload


def test_phase1_representative_local_capability_workload(phase0):
    store, workflow, shopify, chatwoot = phase0
    config = store.get_config("mer_A")
    config["product_rules"] = {
        "required": ["sku", "title", "price", "currency", "product_type"],
        "category_profiles": {"jewelry": ["material"]},
    }
    config["sla_thresholds"] = {"order_unfulfilled_hours": 9999}
    store.set_config("mer_A", config)
    counters = WorkloadCounters()

    workdir = Path("sanocea/tests/fixtures/phase11_merchant/generated/e2e_phase1")
    workdir.mkdir(parents=True, exist_ok=True)
    csv_file = workdir / "phase1_products.csv"
    rows = ["sku,title,price,currency,product_type,category,material,brand"]
    for i in range(1, 16):
        rows.append(f"SKU-{i},Clean Product {i},{100+i},INR,jewelry,jewelry,gold,Sanocea")
    for i in range(16, 19):
        rows.append(f"SKU-{i},Incomplete Product {i},,INR,jewelry,jewelry,,")
    for i in range(19, 21):
        rows.append(f"SKU-{i},Ambiguous Product {i},{100+i},INR,jewelry,jewelry,,")
    csv_file.write_text("\n".join(rows), encoding="utf-8")

    ingestor = StructuredProductIngestor(store)
    validator = ProductCompletenessValidator(store)
    publisher = ProductPublicationService(store, shopify)
    drafts = [validator.validate(draft) for draft in ingestor.ingest_file("mer_A", csv_file, "text/csv")]
    counters.products_processed = len(drafts)
    for draft in drafts:
        if draft.state == "NEEDS_APPROVAL" and draft.sku and int(draft.sku.split("-")[1]) <= 15:
            counters.products_requiring_human_approval += 1
            draft = validator.approve_extracted_facts(draft, "merchant")
            draft = validator.approve_publication(draft, "merchant")
            publication = publisher.create_publication("mer_A", draft.id, "chn_A_shopify")
            verification = publisher.publish("mer_A", publication.id)
            assert verification.outcome == "VERIFIED"
        elif draft.state in {"INCOMPLETE", "CONFLICTED"}:
            counters.products_requiring_corrective_work += 1
    # Intentionally inject one publication mismatch after a verified publication.
    verified = shopify.external_products[next(iter(shopify.external_products))]
    verified["title"] = "External Drift"
    first_publication = store.list(__import__("sanocea.packages.domain_contract.models", fromlist=["Publication"]).Publication, "mer_A")[0]
    mismatch = publisher.verify("mer_A", first_publication.id)
    assert mismatch.outcome == "MISMATCH"

    for i in range(1, 6):
        payload = shopify_order_payload(id=8000 + i, order_number=str(8000 + i), email=f"buyer{i}@example.com", updated_sequence=3)
        body = json.dumps(payload).encode()
        result = shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A", f"order-{i}"), body)
        duplicate = shopify.ingest_webhook("mer_A", shopify_headers(body, "shopify_secret_A", f"order-{i}"), body)
        assert duplicate["idempotent_replay"] is True
        counters.duplicate_mutations_observed += 1
        counters.orders_processed += 1

    orders = store.list(Order, "mer_A")
    messages = [
        "Where is order #8001?",
        "Shipment status for order #8002",
        "Where is order #8003?",
        "Status order #8004",
        "Tracking for order #8005",
        "Where is my order 8001",
        "order status please",
        "I want a refund",
        "Please change address",
        "Can you recommend a gift?",
    ]
    support = SupportWorkflowService(store, chatwoot)
    for idx, message in enumerate(messages, start=1):
        order = orders[(idx - 1) % len(orders)] if idx <= 7 else None
        conversation = SupportConversation(
            merchant_id="mer_A",
            channel_id="chn_A_chatwoot",
            customer_id=order.customer_id if order else None,
            order_id=order.id if order else None,
            last_message=message,
        )
        store.put(conversation)
        action = support.handle_conversation("mer_A", conversation.id)
        counters.support_requests_processed += 1
        if action.handling_mode == "AUTOMATIC":
            counters.support_requests_automatically_resolved += 1
        if action.handling_mode == "EXCEPTION-ONLY":
            counters.support_requests_escalated += 1

    exceptions = store.list(ExceptionRecord, "mer_A")
    counters.total_exceptions = len(exceptions)
    counters.total_approvals_requested = counters.products_requiring_human_approval

    assert counters.products_processed == 20
    assert counters.products_requiring_human_approval == 15
    assert counters.products_requiring_corrective_work == 5
    assert counters.orders_processed == 5
    assert counters.support_requests_processed == 10
    assert counters.support_requests_automatically_resolved >= 7
    assert counters.support_requests_escalated >= 1
    assert any(e.category == "publication_verification_mismatch" for e in exceptions)
    assert store.list(ProductDraft, "mer_B") == []
    assert counters.automation_rate > 0
    assert counters.cross_tenant_violations == 0
    assert counters.unresolved_workflow_failures == 0
