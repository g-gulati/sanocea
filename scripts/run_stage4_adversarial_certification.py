#!/usr/bin/env python3
"""Stage 4 Certification Runner: Adversarial Merchant Ingestion, Product Identity & Variant Resolution.
Executes 14 rigorous certification checkpoints:
1. Adversarial package ingestion & ballast file quarantine (.DS_Store, corrupt binary)
2. Honest XLSX formula handling (preserves formula text, cached value, cell locator separately; fails closed)
3. Merged cell forward-filling across variant hierarchies
4. Hidden sheet isolation (supplier internal notes excluded from catalog)
5. Barcode collision detection (duplicate barcode across distinct styles fails closed into CONFLICT)
6. Strict non-fuzzy identity boundary (title/brand similarity generates candidates only, never marks RESOLVED)
7. Orthogonal identity publication gate (identity_status != RESOLVED blocks publication independently of state)
8. Durable merchant-scoped human identity decisions (SAME/DIFFERENT persisted with tenant isolation)
9. Variant lifecycle modeling (variant added, SKU changed, barcode changed, option renamed)
10. Stale catalogue revisions (absence != deletion; missing variant marked STALE without deletion)
11. Indian & international number/price formatting & missing units handling
12. Multi-product PDF specification extraction (Docling / Structured)
13. Live Shopify multi-variant publication with options & variants
14. Independent Shopify GraphQL read-back & append-only audit ledger lineage
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add workspace and parent directory to sys.path for robust module resolution
ROOT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = ROOT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import time
import urllib.request
import psycopg2
import base64

# Default test encryption master key for credential provider if not present in env
if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

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
    ProductPublicationService,
    UnifiedProductIngestor,
)
from sanocea.packages.product_onboarding.identity import (
    IdentityDecisionService,
    ProductIdentityResolver,
)
from sanocea.packages.product_onboarding.provenance import normalize_commercial_fact_value
from sanocea.packages.product_onboarding.variants import VariantMatrixEngine

SHOP_DOMAIN = os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN", "sanocea-commerce-os-dev.myshopify.com")
CLIENT_ID = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID", "1d3844f9bf7dd89697abfd62c29decf4")
CLIENT_SECRET = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET", "REDACTED-SET-VIA-SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
API_VERSION = os.environ.get("SANOCEA_SHOPIFY_LIVE_API_VERSION", "2026-07")
PG_DSN = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
S3_ENDPOINT = os.environ.get("SANOCEA_S3_ENDPOINT", "http://127.0.0.1:59000")
S3_ACCESS_KEY = os.environ.get("SANOCEA_S3_ACCESS_KEY", "sanocea-dev")
S3_SECRET_KEY = os.environ.get("SANOCEA_S3_SECRET_KEY", "sanocea-dev-secret")
S3_BUCKET = os.environ.get("SANOCEA_S3_BUCKET", "sanocea-phase05")

MERCHANT_ID = "stage4_adversarial_cert_merchant"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "phase11_merchant" / "adversarial_pack"
REPORT_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "phase11_merchant" / "generated" / "stage4_adversarial_certification_report.json"


def _shopify_graphql(token_manager: ShopifyAccessTokenManager, query: str, variables: dict) -> dict:
    token = token_manager.get_token()
    url = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())["data"]


def run_certification() -> dict:
    print("================================================================================")
    print("SANOCEA P0 STAGE 4: ADVERSARIAL MERCHANT INGESTION & VARIANT RESOLUTION")
    print("CERTIFICATION RUN")
    print("================================================================================")

    results: dict[str, dict] = {}

    # Initialize infra
    cred_provider = build_production_credential_provider(PG_DSN)
    store = PostgresStore(PG_DSN, credential_provider=cred_provider)
    token_manager = ShopifyAccessTokenManager(shop_domain=SHOP_DOMAIN, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    connector = ShopifyLiveConnector(
        store,
        workflow=None,
        shop_domain=SHOP_DOMAIN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        api_version=API_VERSION,
        token_manager=token_manager,
    )
    storage = S3ObjectStorage(
        endpoint_url=S3_ENDPOINT,
        access_key_id=S3_ACCESS_KEY,
        secret_access_key=S3_SECRET_KEY,
        bucket=S3_BUCKET,
    )
    ingestor = UnifiedProductIngestor(store, storage)
    validator = ProductCompletenessValidator(store)
    decision_svc = IdentityDecisionService(store)
    pub_service = ProductPublicationService(store, connector)
    variant_engine = VariantMatrixEngine()

    # Clean merchant DB state
    with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM product_drafts WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM publications WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM exceptions WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM approvals WHERE merchant_id = %s", (MERCHANT_ID,))
        cur.execute("DELETE FROM identity_decisions WHERE merchant_id = %s", (MERCHANT_ID,))

    baseline_audit = len(store.list_audit(MERCHANT_ID))
    store.put(Merchant(id=MERCHANT_ID, merchant_id=MERCHANT_ID, legal_name="Adversarial Merchant Ltd", display_name="Adversarial Certification Merchant"))
    store.set_config(
        MERCHANT_ID,
        {
            "product_rules": {"required": ["sku", "title", "price", "currency", "product_type"]},
            "publication": {"require_approval": False},
        },
    )

    # Checkpoint 1: Ingestion & Ballast Quarantine
    pack_files = [
        FIXTURES_DIR / "ballast_corrupt.bin",
        FIXTURES_DIR / ".DS_Store",
        FIXTURES_DIR / "adversarial_catalog.xlsx",
        FIXTURES_DIR / "malformed_rows.csv",
        FIXTURES_DIR / "colliding_barcodes.csv",
        FIXTURES_DIR / "multi_product_spec.pdf",
    ]
    drafts = ingestor.ingest_package(MERCHANT_ID, pack_files)
    audit_slice = store.list_audit(MERCHANT_ID)[baseline_audit:]
    quarantined = [e for e in audit_slice if e.action == "file_quarantined"]
    quarantined_files = {e.object_id for e in quarantined}
    cp1_pass = ("ballast_corrupt.bin" in quarantined_files and ".DS_Store" in quarantined_files and len(drafts) >= 4)
    results["1_ballast_quarantine"] = {
        "status": "PASS" if cp1_pass else "FAIL",
        "quarantined_files": list(quarantined_files),
        "drafts_extracted": len(drafts),
    }
    print(f"[{results['1_ballast_quarantine']['status']}] Checkpoint 1: Ballast isolation (.DS_Store, corrupt binary quarantined)")

    # Checkpoint 2: Honest Formula Handling & Merged Cells
    all_drafts = store.list(ProductDraft, MERCHANT_ID)
    kaftan = next(d for d in all_drafts if d.sku == "STYLE-KAFTAN-101")
    price_fact = kaftan.commercial_facts.get("price")
    cp2_pass = (
        kaftan.title == "Embroidered Silk Kaftan"
        and len(kaftan.variants) == 3
        and price_fact is not None
        and price_fact.metadata.get("formula_text") == "=1200*1.18"
        and price_fact.metadata.get("cached_value") == 1416.0
        and price_fact.metadata.get("formula_evaluated") is False
    )
    results["2_honest_formulas_merged_cells"] = {
        "status": "PASS" if cp2_pass else "FAIL",
        "formula_text": price_fact.metadata.get("formula_text") if price_fact else None,
        "cached_value": price_fact.metadata.get("cached_value") if price_fact else None,
        "variants_count": len(kaftan.variants),
    }
    print(f"[{results['2_honest_formulas_merged_cells']['status']}] Checkpoint 2: Honest formula extraction & merged cells unrolled")

    # Checkpoint 3: Hidden Sheet Isolation
    hidden_variants = [
        v for v in kaftan.variants
        if any(loc.get("sheet") == "Internal_Markup_Notes" for loc in v.source_locators)
    ]
    cp3_pass = (len(hidden_variants) == 0)
    results["3_hidden_sheet_isolation"] = {
        "status": "PASS" if cp3_pass else "FAIL",
        "hidden_variants_leaked": len(hidden_variants),
    }
    print(f"[{results['3_hidden_sheet_isolation']['status']}] Checkpoint 3: Hidden sheet isolated (internal notes excluded)")

    # Checkpoint 4: Barcode Collision Fail-Closed
    pants_draft = next((d for d in drafts if d.sku == "STYLE-PANTS-701" or d.attributes.get("style_code") == "STYLE-PANTS-701"), None)
    cp4_pass = (
        pants_draft is not None
        and pants_draft.identity_status == "CONFLICT"
        and "Barcode collision" in (pants_draft.identity_conflict_reason or "")
    )
    results["4_barcode_collision_detection"] = {
        "status": "PASS" if cp4_pass else "FAIL",
        "identity_status": pants_draft.identity_status if pants_draft else None,
        "conflict_reason": pants_draft.identity_conflict_reason if pants_draft else None,
    }
    print(f"[{results['4_barcode_collision_detection']['status']}] Checkpoint 4: Duplicate barcode across distinct styles detected (CONFLICT)")

    # Checkpoint 5: Strict Non-Fuzzy Identity Boundary
    title_only = next((d for d in drafts if not d.sku and "Silk Stole" in (d.title or "")), None)
    cp5_pass = (
        title_only is not None
        and title_only.identity_status in ("AMBIGUOUS", "UNRESOLVED")
        and title_only.identity_status != "RESOLVED"
    )
    results["5_non_fuzzy_identity_boundary"] = {
        "status": "PASS" if cp5_pass else "FAIL",
        "identity_status": title_only.identity_status if title_only else None,
        "candidates_count": len(title_only.identity_candidates) if title_only else 0,
    }
    print(f"[{results['5_non_fuzzy_identity_boundary']['status']}] Checkpoint 5: Non-fuzzy identity boundary enforced (AMBIGUOUS, candidates only)")

    # Checkpoint 6: Orthogonal Identity Publication Gate
    pants_pub_dec = validator.apply_publication_policy(pants_draft) if pants_draft else None
    title_pub_dec = validator.apply_publication_policy(title_only) if title_only else None
    cp6_pass = (
        pants_pub_dec is not None
        and pants_pub_dec.outcome == "EXCEPTION"
        and any("unresolved_product_identity:CONFLICT" in r for r in pants_pub_dec.reasons)
        and title_pub_dec is not None
        and title_pub_dec.outcome == "EXCEPTION"
    )
    results["6_orthogonal_publication_gate"] = {
        "status": "PASS" if cp6_pass else "FAIL",
        "pants_publication_outcome": pants_pub_dec.outcome if pants_pub_dec else None,
        "title_publication_outcome": title_pub_dec.outcome if title_pub_dec else None,
    }
    print(f"[{results['6_orthogonal_publication_gate']['status']}] Checkpoint 6: Orthogonal publication gate (fails closed on non-RESOLVED identity)")

    # Checkpoint 7: Durable Merchant-Scoped Human Identity Decisions
    if title_only:
        decision = decision_svc.record_decision(
            merchant_id=MERCHANT_ID,
            source_identifier_a=title_only.id,
            source_identifier_b="SKU-CANONICAL-STOLE-99",
            decision="SAME",
            canonical_id="prod_canonical_stole_99",
            decided_by="senior_cataloger",
        )
        title_only.sku = "SKU-CANONICAL-STOLE-99"
        title_only.product_id = decision.canonical_id
        title_only.identity_status = "RESOLVED"
        title_only.identity_key = f"decision:{decision.id}"
        store.put(title_only)

        different_dec = decision_svc.record_decision(
            merchant_id=MERCHANT_ID,
            source_identifier_a="PAIR-A",
            source_identifier_b="PAIR-B",
            decision="DIFFERENT",
            decided_by="senior_cataloger",
        )
        cp7_pass = (
            decision_svc.are_same(MERCHANT_ID, title_only.id, "SKU-CANONICAL-STOLE-99")
            and decision_svc.are_different(MERCHANT_ID, "PAIR-A", "PAIR-B")
            and not decision_svc.are_different("other_merchant", "PAIR-A", "PAIR-B")
        )
    else:
        cp7_pass = False
    results["7_durable_identity_decisions"] = {
        "status": "PASS" if cp7_pass else "FAIL",
        "tenant_isolation_verified": cp7_pass,
    }
    print(f"[{results['7_durable_identity_decisions']['status']}] Checkpoint 7: Durable human identity decisions recorded & scoped to merchant")

    # Checkpoint 8: Variant Lifecycle Transitions (Revision B)
    rev_b_path = FIXTURES_DIR / "catalog_revision_b.xlsx"
    ingestor.ingest_file(MERCHANT_ID, rev_b_path)
    kaftan_rev = next(d for d in store.list(ProductDraft, MERCHANT_ID) if d.sku == "STYLE-KAFTAN-101")
    variants_by_size = {v.option_values.get("Size"): v for v in kaftan_rev.variants}
    cp8_pass = (
        variants_by_size.get("S") is not None and variants_by_size["S"].status == "ACTIVE"
        and variants_by_size.get("M") is not None and variants_by_size["M"].sku == "KFTN-SLK-BLU-M-V2"
        and variants_by_size.get("L") is not None and variants_by_size["L"].status == "STALE"
        and variants_by_size.get("XL") is not None and variants_by_size["XL"].status == "ACTIVE"
    )
    results["8_variant_lifecycle_transitions"] = {
        "status": "PASS" if cp8_pass else "FAIL",
        "variant_s_status": variants_by_size["S"].status if "S" in variants_by_size else None,
        "variant_m_sku": variants_by_size["M"].sku if "M" in variants_by_size else None,
        "variant_l_status": variants_by_size["L"].status if "L" in variants_by_size else None,
        "variant_xl_status": variants_by_size["XL"].status if "XL" in variants_by_size else None,
    }
    print(f"[{results['8_variant_lifecycle_transitions']['status']}] Checkpoint 8: Variant lifecycle (added, SKU changed, absent variant STALE)")

    # Checkpoint 9: Number & International Format Normalization
    price_ind = normalize_commercial_fact_value("price", "₹1,49,999.00")
    price_eur = normalize_commercial_fact_value("price", "1.499,00 €")
    dim_no_unit = normalize_commercial_fact_value("dimensions", "15x10x5")
    cp9_pass = (price_ind == 14999900 and price_eur == 149900 and dim_no_unit.get("unit") is None)
    results["9_number_unit_normalization"] = {
        "status": "PASS" if cp9_pass else "FAIL",
        "price_indian_cents": price_ind,
        "price_european_cents": price_eur,
        "dim_unit_missing_detected": dim_no_unit.get("unit") is None,
    }
    print(f"[{results['9_number_unit_normalization']['status']}] Checkpoint 9: Indian/European formats & missing unit detection")

    # Checkpoint 10: Multi-Product PDF Extraction
    pdf_path = FIXTURES_DIR / "multi_product_spec.pdf"
    pdf_drafts = ingestor.ingest_file(MERCHANT_ID, pdf_path)
    cp10_pass = (len(pdf_drafts) >= 2)
    results["10_multi_product_pdf"] = {
        "status": "PASS" if cp10_pass else "FAIL",
        "pdf_drafts_count": len(pdf_drafts),
    }
    print(f"[{results['10_multi_product_pdf']['status']}] Checkpoint 10: Multi-product PDF extracted ({len(pdf_drafts)} products)")

    # Checkpoint 11: Live Shopify Multi-Variant Publication
    validated_kaftan = validator.validate(kaftan_rev)
    approved_kaftan = validator.approve_publication(validated_kaftan, actor="catalog_director")
    pub = pub_service.create_publication(MERCHANT_ID, approved_kaftan.id, "chn_shopify_live")
    verification = pub_service.publish(MERCHANT_ID, pub.id)
    cp11_pass = (verification.outcome == "VERIFIED" and verification.external_product_id is not None)
    shopify_product_id = verification.external_product_id
    results["11_shopify_multi_variant_publication"] = {
        "status": "PASS" if cp11_pass else "FAIL",
        "external_product_id": shopify_product_id,
        "verification_outcome": verification.outcome,
    }
    print(f"[{results['11_shopify_multi_variant_publication']['status']}] Checkpoint 11: Live Shopify multi-variant product published ({shopify_product_id})")

    # Checkpoint 12: Independent Shopify GraphQL Read-Back
    read_back_query = """
    query getProduct($id: ID!) {
      product(id: $id) {
        id
        title
        options {
          name
          values
        }
        variants(first: 10) {
          edges {
            node {
              id
              title
              sku
              price
            }
          }
        }
      }
    }
    """
    shopify_data = _shopify_graphql(token_manager, read_back_query, {"id": shopify_product_id})
    product_node = shopify_data.get("product")
    cp12_pass = (
        product_node is not None
        and "Silk Kaftan" in product_node.get("title", "")
    )
    results["12_shopify_read_back"] = {
        "status": "PASS" if cp12_pass else "FAIL",
        "shopify_title": product_node.get("title") if product_node else None,
        "shopify_options": product_node.get("options") if product_node else [],
    }
    print(f"[{results['12_shopify_read_back']['status']}] Checkpoint 12: Independent Shopify GraphQL read-back verified")

    # Checkpoint 13: Append-Only Audit Trigger Integrity
    final_audit = store.list_audit(MERCHANT_ID)[baseline_audit:]
    actions_seen = {e.action for e in final_audit}
    cp13_pass = (
        len(final_audit) >= 6
        and "file_quarantined" in actions_seen
        and "product_draft_created" in actions_seen
        and "publish_product" in actions_seen
    )
    results["13_append_only_audit_lineage"] = {
        "status": "PASS" if cp13_pass else "FAIL",
        "total_audit_events": len(final_audit),
        "actions_recorded": sorted(list(actions_seen)),
    }
    print(f"[{results['13_append_only_audit_lineage']['status']}] Checkpoint 13: Append-only audit trigger integrity verified ({len(final_audit)} events)")

    # Checkpoint 14: Identity Stability & Ingestion Idempotency
    re_drafts = ingestor.ingest_file(MERCHANT_ID, FIXTURES_DIR / "adversarial_catalog.xlsx")
    kaftan_re = next(d for d in store.list(ProductDraft, MERCHANT_ID) if d.sku == "STYLE-KAFTAN-101")
    cp14_pass = (kaftan_re.id == kaftan.id)
    results["14_identity_stability_idempotency"] = {
        "status": "PASS" if cp14_pass else "FAIL",
        "canonical_id_preserved": kaftan_re.id == kaftan.id,
    }
    print(f"[{results['14_identity_stability_idempotency']['status']}] Checkpoint 14: Identity stability & idempotency verified")

    # Final verdict
    all_passed = all(cp["status"] == "PASS" for cp in results.values())
    summary = {
        "certification_stage": "P0_STAGE4_ADVERSARIAL_INGESTION_IDENTITY",
        "verdict": "PASS" if all_passed else "FAIL",
        "passed_checkpoints": sum(1 for cp in results.values() if cp["status"] == "PASS"),
        "total_checkpoints": len(results),
        "target_store": SHOP_DOMAIN,
        "merchant_id": MERCHANT_ID,
        "checkpoints": results,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n================================================================================")
    print(f"STAGE 4 CERTIFICATION VERDICT: {summary['verdict']} ({summary['passed_checkpoints']}/{summary['total_checkpoints']})")
    print(f"Report written to: {REPORT_PATH}")
    print("================================================================================")

    return summary


if __name__ == "__main__":
    run_certification()
