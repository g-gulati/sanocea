from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
import urllib.request
import psycopg2
import pytest

from openpyxl import Workbook
from PIL import Image, ImageDraw
import pymupdf

from sanocea.connectors.shopify_live import ShopifyAccessTokenManager, ShopifyLiveConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.models import (
    Approval,
    CommercialFact,
    ExceptionRecord,
    Merchant,
    ProductDraft,
    ProvenanceClassification,
)
from sanocea.packages.exceptions import ExceptionCategory
from sanocea.packages.object_storage import S3ObjectStorage
from sanocea.packages.product_onboarding import (
    ProductCompletenessValidator,
    ProductOnboardingWorkflow,
    ProductPublicationService,
    UnifiedProductIngestor,
)
from sanocea.packages.product_onboarding.provenance import (
    CommercialAIEnricher,
    PROTECTED_COMMERCIAL_FACTS,
    ZeroInventionPolicy,
    ZeroInventionViolationError,
    detect_and_merge_fact,
    resolve_fact_conflict,
)

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN")
        and os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID")
        and os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
        and os.environ.get("SANOCEA_PG_DSN")
    ),
    reason="Requires live Shopify dev store credentials and Postgres DSN",
)

SHOP_DOMAIN = os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN", "")
CLIENT_ID = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET", "")
API_VERSION = os.environ.get("SANOCEA_SHOPIFY_LIVE_API_VERSION", "2026-07")
PG_DSN = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea@127.0.0.1:55432/sanocea_phase05")
MERCHANT_ID = "stage3_provenance_cert_merchant"


@pytest.fixture(scope="module")
def token_manager():
    return ShopifyAccessTokenManager(shop_domain=SHOP_DOMAIN, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)


@pytest.fixture(scope="module")
def store():
    cred_provider = build_production_credential_provider(PG_DSN)
    return PostgresStore(PG_DSN, credential_provider=cred_provider)


@pytest.fixture(scope="module")
def connector(store, token_manager):
    return ShopifyLiveConnector(
        store,
        workflow=None,
        shop_domain=SHOP_DOMAIN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        api_version=API_VERSION,
        token_manager=token_manager,
    )


@pytest.fixture(scope="module")
def storage():
    endpoint = os.environ.get("SANOCEA_S3_ENDPOINT", "http://127.0.0.1:59000")
    access_key = os.environ.get("SANOCEA_S3_ACCESS_KEY", "sanocea-dev")
    secret_key = os.environ.get("SANOCEA_S3_SECRET_KEY", "sanocea-dev-secret")
    bucket = os.environ.get("SANOCEA_S3_BUCKET", "sanocea-phase05")
    return S3ObjectStorage(endpoint_url=endpoint, access_key_id=access_key, secret_access_key=secret_key, bucket=bucket)


def _shopify_graphql(token_manager, query: str, variables: dict):
    token = token_manager.get_token()
    url = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["data"]


def test_stage3_messy_pack_ingestion_and_provenance_lifecycle(store, connector, storage, token_manager):
    # 0. Setup merchant configuration with clean state
    with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM product_drafts WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM publications WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM exceptions WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM approvals WHERE merchant_id = %s", (MERCHANT_ID,))
    baseline_audit_count = len(store.list_audit(MERCHANT_ID))
    store.put(Merchant(id=MERCHANT_ID, merchant_id=MERCHANT_ID, legal_name="Stage 3 Provenance Ltd", display_name="Stage 3 Provenance Cert Merchant"))
    store.set_config(
        MERCHANT_ID,
        {
            "product_rules": {
                "required": ["sku", "title", "price", "currency", "product_type", "hsn", "material"],
            },
            "publication": {
                "require_approval": False,
                "auto_publish_verified_clean": True,
            },
        },
    )

    workflow = ProductOnboardingWorkflow(store, storage, connector)

    # 1. Prepare messy merchant source fixtures
    pack_dir = Path("tests/fixtures/phase11_merchant/messy_merchant_pack")
    ts = int(time.time())
    sku_clean = f"SKU-CLEAN-{ts}"
    sku_missing = f"SKU-MISSING-{ts}"
    sku_conflict = f"SKU-CONFLICT-{ts}"
    sku_invalid = f"SKU-INVALID-{ts}"

    csv_content = (
        f"SKU,Item_Name,Retail_Price,Currency,Type,Fabric,Gross_Weight,HSN_Code,Origin_Country,Inventory_Quantity\n"
        f"{sku_clean},Stage3 Silk Kurti,149.99,USD,Apparel,100% Mulberry Silk,350 g,6204,India,50\n"
        f"{sku_missing},Stage3 Linen Tunic,89.00,USD,Apparel,,,,India,25\n"
        f"{sku_conflict},Stage3 Merino Shawl,120.00,USD,Apparel,Merino Wool,450 g,6214,India,30\n"
        f"{sku_invalid},Stage3 Defective Sample,N/A,USD,Apparel,Cotton,200 g,6204,India,10\n"
    )
    csv_file = pack_dir / f"messy_catalog_{ts}.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    # Conflicting PDF spec sheet for sku_conflict (specifies 650 g weight instead of 450 g)
    doc = pymupdf.open()
    page = doc.new_page()
    pdf_text = f"""
Supplier Technical Specification Sheet
SKU: {sku_conflict}
Title: Stage3 Merino Shawl
Price: 120.00
Currency: USD
Product Type: Apparel
Material: Merino Wool
Weight: 650 g
Country of Origin: India
HSN: 6214
"""
    page.insert_text((50, 72), pdf_text)
    pdf_file = pack_dir / f"supplier_spec_{ts}.pdf"
    doc.save(pdf_file)
    doc.close()

    # Image for clean product
    img = Image.new("RGB", (300, 300), color=(220, 230, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 30, 270, 270], fill=(180, 200, 230), outline=(50, 50, 100), width=3)
    img_file = pack_dir / f"{sku_clean}-main.png"
    img.save(img_file)

    try:
        # 2. Ingest Mixed Package
        drafts = workflow.ingest_package(MERCHANT_ID, [csv_file, pdf_file, img_file])
        drafts_by_sku = {d.sku: d for d in drafts if d.sku}

        # --- A. Verify SKU-CLEAN-001 ---
        clean_draft = drafts_by_sku[sku_clean]
        assert clean_draft.price == 14999
        assert clean_draft.commercial_facts["hsn"].value == "6204"
        assert clean_draft.commercial_facts["weight"].value == "350 g"
        assert "image" in clean_draft.commercial_facts
        # Locators must be preserved
        assert clean_draft.commercial_facts["price"].locator["row"] == 2
        assert clean_draft.commercial_facts["image"].locator["dimensions"] == "300x300"

        # State must be NEEDS_APPROVAL
        assert clean_draft.state == "NEEDS_APPROVAL"

        # --- B. Verify SKU-MISSING-002 (Zero-Invention Policy) ---
        missing_draft = drafts_by_sku[sku_missing]
        assert missing_draft.state == "INCOMPLETE"
        # Zero-invention check: HSN must be MISSING, never guessed or synthesized
        assert missing_draft.commercial_facts["hsn"].classification == ProvenanceClassification.MISSING.value
        assert "missing_required_attribute:hsn" in missing_draft.validation_errors

        # Publication Gate Fail-Closed Test: Attempting to publish must be blocked
        pub_result_missing = workflow.request_publication(
            MERCHANT_ID, missing_draft.id, channel_id="shopify_live", requested_by="operator_test"
        )
        assert pub_result_missing["outcome"] == "blocked"
        assert any("missing_required_attribute:hsn" in r or "draft_state:INCOMPLETE" in r for r in pub_result_missing["reasons"])

        # --- C. Verify SKU-CONFLICT-003 (Conflict Detection) ---
        conflict_draft = drafts_by_sku[sku_conflict]
        assert conflict_draft.state == "CONFLICTED"
        assert "conflicting_product_evidence:weight" in conflict_draft.conflicts
        assert conflict_draft.commercial_facts["weight"].conflicted is True
        # Both conflicting locators must be preserved in conflict details
        conflict_entries = conflict_draft.conflict_details["weight"]
        assert len(conflict_entries) == 2
        sources = [e["source"] for e in conflict_entries]
        assert any("messy_catalog" in s for s in sources)
        assert any("supplier_spec" in s for s in sources)

        # Publication Gate Fail-Closed Test: Cannot publish conflicted draft
        pub_result_conflict = workflow.request_publication(
            MERCHANT_ID, conflict_draft.id, channel_id="shopify_live", requested_by="operator_test"
        )
        assert pub_result_conflict["outcome"] == "blocked"
        assert any("conflicting_product_evidence:weight" in r or "draft_state:CONFLICTED" in r for r in pub_result_conflict["reasons"])

        # --- D. Conflict Resolution by Human Operator ---
        resolved_draft = workflow.resolve_conflict(
            merchant_id=MERCHANT_ID,
            draft_id=conflict_draft.id,
            fact_name="weight",
            chosen_value="650 g",
            chosen_source=f"file://{pdf_file.resolve()}",
            actor="stage3_certifier",
            note="Verified heavy winter weave specification with mill lead",
        )
        assert resolved_draft.commercial_facts["weight"].conflicted is False
        assert resolved_draft.commercial_facts["weight"].value == "650 g"
        assert resolved_draft.commercial_facts["weight"].classification == ProvenanceClassification.HUMAN_APPROVED.value
        assert "conflicting_product_evidence:weight" not in resolved_draft.conflicts
        assert resolved_draft.state == "NEEDS_APPROVAL"

        # --- E. Verify SKU-INVALID-004 ---
        invalid_draft = drafts_by_sku[sku_invalid]
        assert invalid_draft.state == "INVALID"
        assert "invalid_price" in invalid_draft.validation_errors
        pub_result_invalid = workflow.request_publication(
            MERCHANT_ID, invalid_draft.id, channel_id="shopify_live", requested_by="operator_test"
        )
        assert pub_result_invalid["outcome"] == "blocked"

        # --- F. Live Shopify Continuation: Publish SKU-CLEAN-001 ---
        # 1. Approve product facts
        approved_clean = workflow.approve_product_facts(MERCHANT_ID, clean_draft.id, approver_id="stage3_certifier")
        assert approved_clean.state == "READY"

        # 2. Add creative AI enrichment (description) and verify provenance boundary
        enricher = CommercialAIEnricher()
        enricher.enrich_field(
            approved_clean, "description", "Exquisite 100% pure mulberry silk evening kurti with fine hand embroidery."
        )
        assert approved_clean.commercial_facts["description"].classification == ProvenanceClassification.AI_ENRICHED.value
        # Re-verifying zero-invention: trying to enrich price must raise violation
        with pytest.raises(ZeroInventionViolationError):
            enricher.enrich_field(approved_clean, "price", 9999)

        # 3. Publish to live Shopify dev store
        pub_result = workflow.request_publication(
            MERCHANT_ID, approved_clean.id, channel_id="shopify_live", requested_by="stage3_certifier"
        )
        assert pub_result["outcome"] == "published"
        verification = pub_result["verification"]
        assert verification["outcome"] == "VERIFIED"
        external_product_id = verification["external_product_id"]
        assert external_product_id.startswith("gid://shopify/Product/")

        # 4. Independent Read-Back Verification against Shopify GraphQL
        readback = _shopify_graphql(
            token_manager,
            "query($id: ID!) { product(id: $id) { title status variants(first: 1) { nodes { sku price } } } }",
            {"id": external_product_id},
        )
        sp_product = readback.get("product") or {}
        assert sp_product.get("title") == "Stage3 Silk Kurti"
        assert sp_product.get("status") == "ACTIVE"
        variant = sp_product.get("variants", {}).get("nodes", [{}])[0]
        assert variant.get("sku") == sku_clean
        assert variant.get("price") == "149.99"

        # 5. Full Audit Trail Reconstruction
        audit_records = store.list_audit(MERCHANT_ID)[baseline_audit_count:]
        actions = [r.action for r in audit_records]
        assert "product_draft_created" in actions
        assert "conflict_resolved" in actions
        assert "product_facts_approved" in actions
        assert "listing_verified" in actions

        # 6. Cleanup: Delete published product from Shopify dev store
        del_res = _shopify_graphql(
            token_manager,
            "mutation($input: ProductDeleteInput!) { productDelete(input: $input) { deletedProductId userErrors { message } } }",
            {"input": {"id": external_product_id}},
        )
        assert del_res.get("productDelete", {}).get("deletedProductId") == external_product_id

    finally:
        csv_file.unlink(missing_ok=True)
        pdf_file.unlink(missing_ok=True)
        img_file.unlink(missing_ok=True)
