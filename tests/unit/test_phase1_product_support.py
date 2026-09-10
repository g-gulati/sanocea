from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.ai import DeterministicAIProvider
from sanocea.packages.ai.provider import AIResult
from sanocea.packages.domain_contract.models import (
    Approval,
    ExtractedAttribute,
    ExceptionRecord,
    ListingVerification,
    Order,
    ProductDraft,
    SupportConversation,
)
from sanocea.packages.onboarding import MerchantOnboardingService
from sanocea.packages.product_onboarding import ProductCompletenessValidator, ProductPublicationService, StructuredProductIngestor
from sanocea.packages.support import SupportWorkflowService
from sanocea.workers.workflow import FakeTemporalEngine


def test_product_draft_states_evidence_and_completeness_rules(phase0):
    store, *_ = phase0
    store.set_config("mer_A", {"product_rules": {"required": ["sku", "title", "price", "currency", "product_type"], "category_profiles": {"jewelry": ["material"]}}})
    csv_file = Path("sanocea/tests/fixtures/phase11_merchant/generated/unit_products.csv")
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    csv_file.write_text(
        "sku,title,price,currency,product_type,category,material\n"
        "SKU-1,Clean Ring,1000,INR,jewelry,jewelry,gold\n"
        "SKU-2,Incomplete Ring,,INR,jewelry,jewelry,\n",
        encoding="utf-8",
    )
    drafts = StructuredProductIngestor(store).ingest_file("mer_A", csv_file, "text/csv")
    validated = [ProductCompletenessValidator(store).validate(d) for d in drafts]
    assert validated[0].state == "NEEDS_APPROVAL"
    assert validated[0].extracted_attributes[0].source_locator["row"] == 2
    assert validated[1].state == "INCOMPLETE"
    assert "missing_required_attribute:price" in validated[1].validation_errors


def test_xlsx_structured_ingestion_preserves_sheet_row_column(phase0):
    store, *_ = phase0
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(["sku", "title", "price", "currency", "product_type"])
    ws.append(["XLS-1", "Workbook Product", 12.5, "INR", "apparel"])
    path = Path("sanocea/tests/fixtures/phase11_merchant/generated/unit_products.xlsx")
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    draft = StructuredProductIngestor(store).ingest_file("mer_A", path)[0]
    attr = next(a for a in draft.extracted_attributes if a.name == "sku")
    assert attr.source_locator == {"sheet": "Products", "row": 2, "column": "sku"}


def test_conflicting_evidence_marks_conflicted(phase0):
    store, *_ = phase0
    draft = ProductDraft(
        merchant_id="mer_A",
        sku="C-1",
        title="Conflict",
        price=100,
        currency="INR",
        product_type="jewelry",
        extracted_attributes=[],
    )
    from sanocea.packages.domain_contract.models import ExtractedAttribute

    draft.extracted_attributes = [
        ExtractedAttribute(name="material", value="gold", source_file="a", source_locator={"row": 1}, evidence_ref="a#1"),
        ExtractedAttribute(name="material", value="silver", source_file="b", source_locator={"row": 1}, evidence_ref="b#1"),
    ]
    assert ProductCompletenessValidator(store).validate(draft).state == "CONFLICTED"


def test_trusted_supplier_clean_product_can_auto_publish_without_human_approval(phase0):
    store, *_ = phase0
    store.set_config(
        "mer_A",
        {
            "product_rules": {"required": ["sku", "title", "price", "currency", "product_type"]},
            "publication": {"require_approval": False, "auto_publish_verified_clean": True},
            "supplier_profiles": {
                "supplier_a": {
                    "source_markers": ["supplier_a"],
                    "trusted_fields": ["sku", "title", "price", "currency", "product_type"],
                }
            },
        },
    )
    draft = ProductDraft(
        merchant_id="mer_A",
        sku="AUTO-1",
        title="Auto Publishable",
        price=1000,
        currency="INR",
        product_type="tops",
        extracted_attributes=[
            ExtractedAttribute(name="sku", value="AUTO-1", source_file="supplier_a/catalog.xlsx", source_locator={"row": 2}, evidence_ref="supplier_a#sku"),
            ExtractedAttribute(name="title", value="Auto Publishable", source_file="supplier_a/catalog.xlsx", source_locator={"row": 2}, evidence_ref="supplier_a#title"),
            ExtractedAttribute(name="price", value=10, source_file="supplier_a/catalog.xlsx", source_locator={"row": 2}, evidence_ref="supplier_a#price"),
            ExtractedAttribute(name="currency", value="INR", source_file="supplier_a/catalog.xlsx", source_locator={"row": 2}, evidence_ref="supplier_a#currency"),
            ExtractedAttribute(name="product_type", value="tops", source_file="supplier_a/catalog.xlsx", source_locator={"row": 2}, evidence_ref="supplier_a#product_type"),
        ],
    )
    validator = ProductCompletenessValidator(store)
    validated = validator.validate(draft)
    decision = validator.apply_publication_policy(validated)
    assert validated.state == "READY"
    assert decision.outcome == "AUTO_PUBLISH"
    assert store.get(ProductDraft, "mer_A", draft.id).approved_for_publication is True


class CountingAIProvider(DeterministicAIProvider):
    def __init__(self) -> None:
        self.calls = 0

    def classify(self, text: str, labels: list[str], evidence_refs: list[str]) -> AIResult:
        self.calls += 1
        return super().classify(text, labels, evidence_refs)


def test_shopify_transformation_publication_and_mismatch_exception(phase0):
    store, workflow, shopify, _chatwoot = phase0
    store.set_config("mer_A", {"product_rules": {"required": ["sku", "title", "price", "currency", "product_type"]}})
    draft = ProductDraft(merchant_id="mer_A", sku="PUB-1", title="Publishable", price=129900, currency="INR", product_type="jewelry")
    store.put(draft)
    validator = ProductCompletenessValidator(store)
    draft = validator.validate(draft)
    draft = validator.approve_publication(draft, "merchant")
    service = ProductPublicationService(store, shopify)
    publication = service.create_publication("mer_A", draft.id, "chn_A_shopify")
    verification = service.publish("mer_A", publication.id)
    assert verification.outcome == "VERIFIED"
    assert store.list(ListingVerification, "mer_A")[0].outcome == "VERIFIED"
    external_id = verification.external_product_id
    shopify.external_products[external_id]["title"] = "Changed Outside"
    mismatch = service.verify("mer_A", publication.id)
    assert mismatch.outcome == "MISMATCH"
    assert any(e.category == "publication_verification_mismatch" for e in store.list(ExceptionRecord, "mer_A"))


def test_external_mutation_success_response_lost_retry_uses_stable_lookup(phase0):
    _store, _workflow, shopify, _chatwoot = phase0
    from sanocea.packages.connector_sdk import MutationRequest

    request = MutationRequest(
        merchant_id="mer_A",
        action="publish_product",
        object_type="ProductDraft",
        payload={"sku": "LOST-1", "title": "Lost Response", "price": "10.00"},
        idempotency_key="publish-lost-1",
    )
    first = shopify.execute_mutation(request)
    replay = shopify._execute_mutation(request)
    assert first.external_ref == replay.external_ref
    assert len(shopify.external_products) == 1


def test_support_handling_modes_and_ai_safeguards(phase0):
    store, _workflow, _shopify, chatwoot = phase0
    order = store.list(__import__("sanocea.packages.domain_contract.models", fromlist=["Order"]).Order, "mer_A")
    conversation = SupportConversation(
        merchant_id="mer_A",
        channel_id="chn_A_chatwoot",
        order_id=None,
        last_message="I want something strange",
    )
    store.put(conversation)
    action = SupportWorkflowService(store, chatwoot, DeterministicAIProvider()).handle_conversation("mer_A", conversation.id)
    assert action.handling_mode == "EXCEPTION-ONLY"
    assert any(e.category == "unsupported_customer_request" for e in store.list(ExceptionRecord, "mer_A"))


def test_support_deterministic_intent_avoids_ai_call(phase0):
    store, _workflow, _shopify, chatwoot = phase0
    order = Order(
        merchant_id="mer_A",
        channel_id="chn_A_shopify",
        order_number="1001",
        status="open",
        payment_status="paid",
        total_amount=1000,
        currency="INR",
    )
    store.put(order)
    ai = CountingAIProvider()
    conversation = SupportConversation(
        merchant_id="mer_A",
        channel_id="chn_A_chatwoot",
        order_id=order.id,
        last_message=f"Where is my order {order.order_number}?",
    )
    store.put(conversation)
    action = SupportWorkflowService(store, chatwoot, ai).handle_conversation("mer_A", conversation.id)
    assert action.handling_mode == "AUTOMATIC"
    assert action.policy_decision == "AUTOMATIC:deterministic"
    assert ai.calls == 0


def test_merchant_onboarding_is_configuration_not_code(phase0):
    store, *_ = phase0
    count = MerchantOnboardingService(store).onboard_phase1("mer_C", "Merchant C", {"currency": "USD"})
    assert count >= 15
    assert store.get_config("mer_C")["currency"] == "USD"
    assert store.get_config("mer_A") != store.get_config("mer_C")
