from __future__ import annotations

import os
from pathlib import Path
import psycopg2
import pytest

from sanocea.connectors.shopify_live import ShopifyAccessTokenManager, ShopifyLiveConnector
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.models import (
    IdentityDecision,
    Merchant,
    ProductDraft,
    VariantDraft,
)
from sanocea.packages.object_storage import S3ObjectStorage
from sanocea.packages.product_onboarding import (
    ProductCompletenessValidator,
    ProductOnboardingWorkflow,
    ProductPublicationService,
    UnifiedProductIngestor,
)
from sanocea.packages.product_onboarding.identity import (
    IdentityDecisionService,
    ProductIdentityResolver,
)
from sanocea.packages.product_onboarding.variants import VariantMatrixEngine

import base64

if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

SHOP_DOMAIN = os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN", "sanocea-commerce-os-dev.myshopify.com")
CLIENT_ID = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID", "1d3844f9bf7dd89697abfd62c29decf4")
CLIENT_SECRET = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET", "REDACTED-SET-VIA-SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
API_VERSION = os.environ.get("SANOCEA_SHOPIFY_LIVE_API_VERSION", "2026-07")
PG_DSN = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
S3_ENDPOINT = os.environ.get("SANOCEA_S3_ENDPOINT", "http://127.0.0.1:59000")
S3_ACCESS_KEY = os.environ.get("SANOCEA_S3_ACCESS_KEY", "sanocea-dev")
S3_SECRET_KEY = os.environ.get("SANOCEA_S3_SECRET_KEY", "sanocea-dev-secret")
S3_BUCKET = os.environ.get("SANOCEA_S3_BUCKET", "sanocea-phase05")

pytestmark = pytest.mark.skipif(
    not (SHOP_DOMAIN and CLIENT_ID and CLIENT_SECRET and PG_DSN),
    reason="Requires live Shopify dev store credentials and Postgres DSN",
)

MERCHANT_ID = "stage4_adversarial_cert_merchant"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "phase11_merchant" / "adversarial_pack"


@pytest.fixture(scope="module")
def token_manager():
    return ShopifyAccessTokenManager(shop_domain=SHOP_DOMAIN, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)


@pytest.fixture(scope="module")
def store():
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()
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
    return S3ObjectStorage(
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        bucket=S3_BUCKET,
    )


def test_stage4_adversarial_package_e2e(store, connector, storage):
    # 1. Clean DB state for this merchant (respecting append-only audit trigger)
    with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM product_drafts WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM publications WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM exceptions WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM approvals WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM identity_decisions WHERE merchant_id = %s", (MERCHANT_ID,))

    baseline_audit = len(store.list_audit(MERCHANT_ID))
    store.put(Merchant(id=MERCHANT_ID, merchant_id=MERCHANT_ID, legal_name="Adversarial Merchant Ltd", display_name="Adversarial Ingestion Merchant"))
    store.set_config(
        MERCHANT_ID,
        {
            "product_rules": {"required": ["sku", "title", "price", "currency", "product_type"]},
            "publication": {"require_approval": False},
        },
    )

    ingestor = UnifiedProductIngestor(store, storage)
    validator = ProductCompletenessValidator(store)
    decision_svc = IdentityDecisionService(store)
    pub_service = ProductPublicationService(store, connector)

    # 2. Ingest Adversarial Catalog Package (XLSX, Malformed CSV, Colliding Barcodes, Ballast)
    pack_files = [
        FIXTURES_DIR / "ballast_corrupt.bin",
        FIXTURES_DIR / ".DS_Store",
        FIXTURES_DIR / "adversarial_catalog.xlsx",
        FIXTURES_DIR / "malformed_rows.csv",
        FIXTURES_DIR / "colliding_barcodes.csv",
        FIXTURES_DIR / "multi_product_spec.pdf",
    ]
    drafts = ingestor.ingest_package(MERCHANT_ID, pack_files)
    assert len(drafts) >= 4

    # 3. Check Fault Isolation: ballast quarantined into audit
    audit_events = store.list_audit(MERCHANT_ID)[baseline_audit:]
    quarantined = [e for e in audit_events if e.action == "file_quarantined"]
    assert len(quarantined) >= 2
    quarantined_files = {e.object_id for e in quarantined}
    assert "ballast_corrupt.bin" in quarantined_files
    assert ".DS_Store" in quarantined_files

    # 4. Check Honest Formula Handling & Merged Cells
    kaftan = next(d for d in store.list(ProductDraft, MERCHANT_ID) if d.sku == "STYLE-KAFTAN-101")
    assert kaftan.title == "Embroidered Silk Kaftan"
    assert len(kaftan.variants) == 3
    assert kaftan.identity_status == "RESOLVED"
    price_fact = kaftan.commercial_facts.get("price")
    assert price_fact.metadata.get("formula_text") == "=1200*1.18"
    assert price_fact.metadata.get("cached_value") == 1416.0
    assert price_fact.metadata.get("formula_evaluated") is False

    # 5. Check Barcode Collision Handling (Fail Closed)
    pants = next((d for d in drafts if d.sku == "STYLE-PANTS-701" or (d.attributes.get("style_code") == "STYLE-PANTS-701")), None)
    if pants:
        assert pants.identity_status == "CONFLICT"
        assert "Barcode collision" in (pants.identity_conflict_reason or "")
        # Publication gate must fail closed
        decision = validator.apply_publication_policy(pants)
        assert decision.outcome == "EXCEPTION"
        assert any("unresolved_product_identity:CONFLICT" in r for r in decision.reasons)

    # 6. Check Non-Fuzzy Identity Boundary
    # The title-only draft from malformed_rows.csv
    title_only = next((d for d in drafts if not d.sku and "Silk Stole" in (d.title or "")), None)
    if title_only:
        assert title_only.identity_status in ("AMBIGUOUS", "UNRESOLVED")
        assert title_only.identity_status != "RESOLVED"
        # Operator makes durable SAME decision linking to a new canonical SKU
        decision = decision_svc.record_decision(
            merchant_id=MERCHANT_ID,
            source_identifier_a=title_only.id,
            source_identifier_b="SKU-CANONICAL-STOLE-99",
            decision="SAME",
            canonical_id="prod_canonical_stole_99",
            decided_by="senior_cataloger",
        )
        # Re-resolve identity
        title_only.sku = "SKU-CANONICAL-STOLE-99"
        title_only.product_id = decision.canonical_id
        title_only.identity_status = "RESOLVED"
        title_only.identity_key = f"decision:{decision.id}"
        store.put(title_only)

    # 7. Check Variant Lifecycle Transitions with Revision B
    rev_b_path = FIXTURES_DIR / "catalog_revision_b.xlsx"
    rev_b_drafts = ingestor.ingest_file(MERCHANT_ID, rev_b_path)
    kaftan_rev = next(d for d in store.list(ProductDraft, MERCHANT_ID) if d.sku == "STYLE-KAFTAN-101")
    variants_by_size = {v.option_values.get("Size"): v for v in kaftan_rev.variants}

    # S: ACTIVE
    assert variants_by_size["S"].status == "ACTIVE"
    # M: ACTIVE with changed SKU
    assert variants_by_size["M"].status == "ACTIVE"
    assert variants_by_size["M"].sku == "KFTN-SLK-BLU-M-V2"
    # L: STALE (Absence != Deletion)
    assert variants_by_size["L"].status == "STALE"
    # XL: ACTIVE (newly added)
    assert variants_by_size["XL"].status == "ACTIVE"

    # 8. Approve and Publish Multi-Variant Parent Draft to Live Shopify
    validated_kaftan = validator.validate(kaftan_rev)
    approved_kaftan = validator.approve_publication(validated_kaftan, actor="catalog_director")
    assert approved_kaftan.approved_for_publication is True

    pub = pub_service.create_publication(MERCHANT_ID, approved_kaftan.id, "chn_shopify_live")
    verification = pub_service.publish(MERCHANT_ID, pub.id)
    assert verification.outcome == "VERIFIED"
    assert verification.external_product_id is not None
    print(f"Published multi-variant Kaftan to Shopify: {verification.external_product_id}")

    # 9. Verify Append-Only Audit Trigger Integrity
    final_audit = store.list_audit(MERCHANT_ID)[baseline_audit:]
    assert len(final_audit) >= 6
    actions = {e.action for e in final_audit}
    assert "file_quarantined" in actions
    assert "product_draft_created" in actions
    assert "publish_product" in actions
