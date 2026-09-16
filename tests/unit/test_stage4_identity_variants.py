from __future__ import annotations

from pathlib import Path
import pytest

from sanocea.packages.domain_contract.models import (
    IdentityDecision,
    ProductDraft,
    VariantDraft,
)
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.product_onboarding.identity import (
    IdentityDecisionService,
    ProductIdentityResolver,
    compute_normalized_similarity,
)
from sanocea.packages.product_onboarding.ingestion import UnifiedProductIngestor
from sanocea.packages.product_onboarding.provenance import normalize_commercial_fact_value
from sanocea.packages.product_onboarding.validation import ProductCompletenessValidator
from sanocea.packages.product_onboarding.variants import VariantMatrixEngine


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "phase11_merchant" / "adversarial_pack"


def test_normalized_similarity():
    # Identical strings
    assert compute_normalized_similarity("Silk Saree", "Silk Saree") == 1.0
    # Formatting differences
    assert compute_normalized_similarity("Silk Saree", "silk-saree!") == 1.0
    # Similar titles
    sim = compute_normalized_similarity("Handmade Silk Stole", "Handcrafted Silk Stole")
    assert 0.70 <= sim < 1.0
    # Disjoint titles
    assert compute_normalized_similarity("Silk Saree", "Cotton Socks") < 0.40


def test_strict_non_fuzzy_identity_resolution_boundary():
    """Stage 4 Amendment 1:
    Fuzzy evidence (title similarity) MUST NOT automatically mark RESOLVED.
    It generates identity_candidates only and sets identity_status = AMBIGUOUS.
    """
    store = Phase0Store()
    resolver = ProductIdentityResolver(store)

    existing = ProductDraft(
        merchant_id="mer_test",
        sku="SKU-EXISTING-01",
        title="Artisanal Handwoven Silk Stole",
        price=249900,
        currency="INR",
        identity_status="RESOLVED",
        identity_key="sku:SKU-EXISTING-01",
    )

    # Incoming draft has similar title but NO authoritative identifier (no SKU, barcode, or style ID)
    incoming = ProductDraft(
        merchant_id="mer_test",
        title="Artisanal Handwoven Silk Stole",  # High similarity
        price=249900,
        currency="INR",
    )

    resolved = resolver.resolve_draft(incoming, [existing])
    assert resolved.identity_status == "AMBIGUOUS"
    assert resolved.identity_status != "RESOLVED"
    assert len(resolved.identity_candidates) > 0
    candidate = resolved.identity_candidates[0]
    assert candidate["candidate_id"] == existing.id
    assert candidate["confidence"] >= 0.70
    assert "fuzzy_title_similarity" in candidate["reason"]


def test_orthogonal_identity_status_blocks_publication():
    """Stage 4 Amendment 2:
    Identity status is orthogonal to validation state.
    A draft with state=READY cannot be approved or published if identity_status != RESOLVED.
    """
    store = Phase0Store()
    store.set_config("mer_test", {"publication": {"require_approval": False}})
    validator = ProductCompletenessValidator(store)

    draft = ProductDraft(
        merchant_id="mer_test",
        title="Ambiguous Product",
        price=150000,
        currency="INR",
        product_type="Accessories",
        state="READY",
        identity_status="AMBIGUOUS",
        identity_conflict_reason="Multiple potential matches found",
    )

    # 1. Publication policy must reject with EXCEPTION
    decision = validator.apply_publication_policy(draft)
    assert decision.outcome == "EXCEPTION"
    assert any("unresolved_product_identity:AMBIGUOUS" in r for r in decision.reasons)

    # 2. Human approval must fail closed on ambiguous identity
    with pytest.raises(ValueError, match="Cannot approve product draft"):
        validator.approve_publication(draft, actor="ops_lead")


def test_honest_xlsx_formula_and_merged_cells():
    """Stage 4 Amendment 3:
    Preserves formula text, cached value, cell locator separately.
    Does not claim native formula evaluation.
    Unrolls merged cells across parent-variant hierarchies.
    """
    store = Phase0Store()
    ingestor = UnifiedProductIngestor(store)
    xlsx_path = FIXTURES_DIR / "adversarial_catalog.xlsx"
    assert xlsx_path.exists(), f"Fixture not found: {xlsx_path}"

    drafts = ingestor.ingest_file("mer_test", xlsx_path)
    assert len(drafts) >= 1

    # STYLE-KAFTAN-101 was merged across 3 rows
    kaftan = next(d for d in drafts if d.sku == "STYLE-KAFTAN-101")
    assert kaftan.title == "Embroidered Silk Kaftan"
    assert len(kaftan.variants) == 3

    # Check that variant rows received the merged parent values
    for v in kaftan.variants:
        assert v.option_values.get("Color") == "Navy Blue"
        assert v.option_values.get("Size") in {"S", "M", "L"}
        assert v.price == 141600  # 1416.0 cached value in cents

    # Check formula metadata in commercial facts
    price_fact = kaftan.commercial_facts.get("price")
    assert price_fact is not None
    assert price_fact.metadata.get("formula_text") == "=1200*1.18"
    assert price_fact.metadata.get("cached_value") == 1416.0
    assert price_fact.metadata.get("formula_evaluated") is False


def test_durable_merchant_scoped_identity_decisions():
    """Stage 4 Amendment 4:
    Human SAME/DIFFERENT decisions persist and prevent unwanted candidate merges.
    Decisions are strictly scoped to merchant_id.
    """
    store = Phase0Store()
    decision_svc = IdentityDecisionService(store)
    resolver = ProductIdentityResolver(store, decision_svc)

    # 1. Record DIFFERENT decision for mer_1
    decision_svc.record_decision(
        merchant_id="mer_1",
        source_identifier_a="STYLE-RED-1",
        source_identifier_b="STYLE-RED-2",
        decision="DIFFERENT",
        decided_by="senior_catalog_manager",
        notes="Confirmed distinct sleeve embroidery",
    )

    # Check symmetric lookup
    assert decision_svc.are_different("mer_1", "STYLE-RED-1", "STYLE-RED-2") is True
    assert decision_svc.are_different("mer_1", "STYLE-RED-2", "STYLE-RED-1") is True

    # 2. Tenant isolation check: mer_2 must NOT see mer_1's decision
    assert decision_svc.are_different("mer_2", "STYLE-RED-1", "STYLE-RED-2") is False

    # 3. Verify resolver enforces DIFFERENT decision
    existing = ProductDraft(
        merchant_id="mer_1",
        sku="STYLE-RED-1",
        title="Red Silk Anarkali",
        identity_status="RESOLVED",
        identity_key="sku:STYLE-RED-1",
    )
    incoming = ProductDraft(
        merchant_id="mer_1",
        sku="STYLE-RED-2",
        title="Red Silk Anarkali",  # Identical title
    )
    resolved = resolver.resolve_draft(incoming, [existing])
    # Must NOT suggest candidate STYLE-RED-1 because human marked DIFFERENT
    for cand in resolved.identity_candidates:
        assert cand.get("candidate_sku") != "STYLE-RED-1"


def test_variant_matrix_lifecycle_transitions():
    """Stage 4 Amendment 6:
    Variant lifecycle modeling:
    - variant added
    - SKU changed
    - barcode changed
    - variant removed from newer source (marked STALE; absence != deletion)
    """
    engine = VariantMatrixEngine()

    # Initial revision
    initial_draft = ProductDraft(
        merchant_id="mer_test",
        sku="STYLE-KAFTAN-101",
        title="Silk Kaftan",
        options=["Color", "Size"],
        variants=[
            engine.create_variant_draft(sku="KFTN-S", barcode="8901", option_values={"Color": "Navy", "Size": "S"}, price=140000),
            engine.create_variant_draft(sku="KFTN-M", barcode="8902", option_values={"Color": "Navy", "Size": "M"}, price=140000),
            engine.create_variant_draft(sku="KFTN-L", barcode="8903", option_values={"Color": "Navy", "Size": "L"}, price=140000),
        ],
    )

    # Newer revision:
    # S: present
    # M: SKU changed to KFTN-M-V2, option renamed to Navy Blue
    # L: ABSENT (must become STALE, not deleted!)
    # XL: newly added
    incoming_variants = [
        engine.create_variant_draft(sku="KFTN-S", barcode="8901", option_values={"Color": "Navy Blue", "Size": "S"}, price=145000),
        engine.create_variant_draft(sku="KFTN-M-V2", barcode="8902", option_values={"Color": "Navy Blue", "Size": "M"}, price=145000),
        engine.create_variant_draft(sku="KFTN-XL", barcode="8904", option_values={"Color": "Navy Blue", "Size": "XL"}, price=145000),
    ]

    reconciled = engine.reconcile_variant_lifecycle(initial_draft, incoming_variants, source_revision="rev_b")

    variants_by_size = {v.option_values.get("Size"): v for v in reconciled.variants}

    # S: ACTIVE with updated price
    assert variants_by_size["S"].status == "ACTIVE"
    assert variants_by_size["S"].price == 145000

    # M: ACTIVE with updated SKU
    assert variants_by_size["M"].status == "ACTIVE"
    assert variants_by_size["M"].sku == "KFTN-M-V2"

    # L: STALE (Absence != Deletion)
    assert variants_by_size["L"].status == "STALE"
    assert variants_by_size["L"].sku == "KFTN-L"

    # XL: ACTIVE (newly added)
    assert variants_by_size["XL"].status == "ACTIVE"
    assert variants_by_size["XL"].sku == "KFTN-XL"


def test_number_format_and_unit_normalization():
    """Exercises Indian number formatting (₹1,49,999.00), European formatting (1.499,00 €),
    weight units, and missing dimension units.
    """
    # Indian price
    assert normalize_commercial_fact_value("price", "₹1,49,999.00") == 14999900
    assert normalize_commercial_fact_value("price", "1,499.00") == 149900

    # European price (dot thousands, comma decimal)
    assert normalize_commercial_fact_value("price", "1.499,00 €") == 149900
    assert normalize_commercial_fact_value("price", "1499,50") == 149950

    # Weights
    assert normalize_commercial_fact_value("weight", "850 g") == 850.0
    assert normalize_commercial_fact_value("weight", "1.2 kg") == 1200.0

    # Dimensions with and without unit
    dim_with_unit = normalize_commercial_fact_value("dimensions", "20x15x3 cm")
    assert dim_with_unit == {"length": 20.0, "width": 15.0, "height": 3.0, "unit": "cm"}

    dim_no_unit = normalize_commercial_fact_value("dimensions", "15x10x5")
    assert dim_no_unit["unit"] is None


def test_fault_isolation_on_ballast_and_corrupt_files():
    """Verifies that packages containing .DS_Store, Thumbs.db, or corrupt binary ballast
    are quarantined gracefully into the audit log without crashing package ingestion.
    """
    store = Phase0Store()
    ingestor = UnifiedProductIngestor(store)

    ballast_path = FIXTURES_DIR / "ballast_corrupt.bin"
    ds_store_path = FIXTURES_DIR / ".DS_Store"
    csv_path = FIXTURES_DIR / "malformed_rows.csv"

    # Ingest package containing both corrupt ballast and valid CSV
    drafts = ingestor.ingest_package("mer_test", [ballast_path, ds_store_path, csv_path])

    # Must process valid products without raising an unhandled exception
    assert len(drafts) > 0

    # Verify that ballast files were quarantined in the audit ledger
    audit_events = store.list_audit("mer_test")
    quarantined = [e for e in audit_events if e.action == "file_quarantined"]
    assert len(quarantined) >= 2
    quarantined_files = {e.object_id for e in quarantined}
    assert "ballast_corrupt.bin" in quarantined_files
    assert ".DS_Store" in quarantined_files
