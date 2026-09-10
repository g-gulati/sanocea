from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import ExceptionRecord, ListingVerification, Merchant, Order, ProductDraft, SupportConversation
from sanocea.packages.object_storage import S3ObjectStorage
from sanocea.packages.onboarding import MerchantOnboardingService
from sanocea.packages.product_onboarding import ProductCompletenessValidator, ProductPublicationService, StructuredProductIngestor
from sanocea.packages.support import SupportWorkflowService
from sanocea.tests.unit.test_phase0_acceptance import shopify_headers, shopify_order_payload
from sanocea.workers.workflow import FakeTemporalEngine


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN") or not os.environ.get("SANOCEA_S3_BUCKET"),
    reason="requires real Postgres and S3/MinIO settings",
)


def storage() -> S3ObjectStorage:
    s3 = S3ObjectStorage(
        endpoint_url=os.environ.get("SANOCEA_S3_ENDPOINT"),
        access_key_id=os.environ["SANOCEA_S3_ACCESS_KEY"],
        secret_access_key=os.environ["SANOCEA_S3_SECRET_KEY"],
        bucket=os.environ["SANOCEA_S3_BUCKET"],
    )
    s3.ensure_bucket()
    return s3


def test_phase1_product_publication_monitoring_support_on_real_persistence():
    suffix = uuid4().hex[:8]
    merchant_id = f"p1_mer_{suffix}"
    other_id = f"p1_other_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    MerchantOnboardingService(store).onboard_phase1(merchant_id, "Phase 1 Merchant")
    MerchantOnboardingService(store).onboard_phase1(other_id, "Other Merchant", {"currency": "USD"})
    store.set_credential_ref(merchant_id, "shopify_webhook_secret", f"shopify_{suffix}")
    store.set_credential_ref(merchant_id, "chatwoot_webhook_secret", f"chatwoot_{suffix}")
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    chatwoot = ChatwootConnector(store)

    workdir = Path("sanocea/tests/fixtures/phase11_merchant/generated/integration_phase1")
    workdir.mkdir(parents=True, exist_ok=True)
    csv_file = workdir / f"products_{suffix}.csv"
    csv_file.write_text(
        "sku,title,price,currency,product_type,category,material,brand\n"
        f"P1-{suffix},Real Infra Product,999,INR,jewelry,jewelry,gold,Sanocea\n",
        encoding="utf-8",
    )
    ingestor = StructuredProductIngestor(store, storage())
    drafts = ingestor.ingest_file(merchant_id, csv_file, "text/csv")
    duplicate = ingestor.ingest_file(merchant_id, csv_file, "text/csv")
    assert duplicate[0].id == drafts[0].id
    validator = ProductCompletenessValidator(store)
    draft = validator.validate(drafts[0])
    draft = validator.approve_extracted_facts(draft, "merchant")
    draft = validator.approve_publication(draft, "merchant")
    publisher = ProductPublicationService(store, shopify)
    publication = publisher.create_publication(merchant_id, draft.id, f"{merchant_id}_shopify")
    verification = publisher.publish(merchant_id, publication.id)
    assert verification.outcome == "VERIFIED"
    assert store.list(ListingVerification, merchant_id)

    payload = shopify_order_payload(id=700000 + int(suffix[:4], 16), order_number=f"R-{suffix}", email="realinfra@example.com", updated_sequence=3)
    body = json.dumps(payload).encode()
    order_result = shopify.ingest_webhook(merchant_id, shopify_headers(body, f"shopify_{suffix}", f"ri-{suffix}"), body)
    # Reads the canonical Order directly off real Postgres persistence - OrderMonitoringService (a
    # Phase 1-era service that re-fetched the order from the connector and compared payment_status) was
    # removed as superseded: nothing in the current runtime wired it, and its functionality duplicated
    # PostOrderOperationsService.observe_inventory/monitor_fulfilment, which ARE wired into apps/api and
    # are exercised against this same real Postgres by the Phase 4.5/4.6 workload scripts. This
    # assertion keeps proving the fact this test cares about (webhook ingestion correctly persists
    # payment status to real Postgres) via the current architecture instead.
    observed = store.get(Order, merchant_id, order_result["order_id"])
    assert observed.payment_status == "paid"

    conversation = SupportConversation(
        merchant_id=merchant_id,
        channel_id=f"{merchant_id}_chatwoot",
        order_id=order_result["order_id"],
        last_message=f"Where is order R-{suffix}?",
    )
    store.put(conversation)
    support_action = SupportWorkflowService(store, chatwoot).handle_conversation(merchant_id, conversation.id)
    assert support_action.handling_mode == "AUTOMATIC"
    assert support_action.status == "executed"
    with pytest.raises(TenantAccessError):
        store.get(ProductDraft, other_id, draft.id)
    assert store.get_config(other_id)["currency"] == "USD"


def test_phase1_publication_readback_mismatch_persists_exception():
    suffix = uuid4().hex[:8]
    merchant_id = f"p1_mismatch_{suffix}"
    store = PostgresStore(os.environ["SANOCEA_PG_DSN"])
    store.migrate()
    MerchantOnboardingService(store).onboard_phase1(merchant_id, "Mismatch Merchant")
    shopify = ShopifyConnector(store, FakeTemporalEngine(store))
    workdir = Path("sanocea/tests/fixtures/phase11_merchant/generated/integration_phase1")
    workdir.mkdir(parents=True, exist_ok=True)
    csv_file = workdir / f"mismatch_{suffix}.csv"
    csv_file.write_text(f"sku,title,price,currency,product_type,category,material,brand\nMM-{suffix},Mismatch Product,50,INR,jewelry,jewelry,gold,Sanocea\n", encoding="utf-8")
    draft = StructuredProductIngestor(store, storage()).ingest_file(merchant_id, csv_file, "text/csv")[0]
    validator = ProductCompletenessValidator(store)
    draft = validator.approve_publication(validator.approve_extracted_facts(validator.validate(draft), "merchant"), "merchant")
    publisher = ProductPublicationService(store, shopify)
    publication = publisher.create_publication(merchant_id, draft.id, f"{merchant_id}_shopify")
    verified = publisher.publish(merchant_id, publication.id)
    shopify.external_products[verified.external_product_id]["title"] = "Changed"
    mismatch = publisher.verify(merchant_id, publication.id)
    assert mismatch.outcome == "MISMATCH"
    assert any(e.category == "publication_verification_mismatch" for e in store.list(ExceptionRecord, merchant_id))
