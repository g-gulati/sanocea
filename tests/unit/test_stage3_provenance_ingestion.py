from __future__ import annotations

from pathlib import Path
import pytest

from sanocea.packages.domain_contract.models import (
    Approval,
    CommercialFact,
    ProductDraft,
    ProvenanceClassification,
)
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.product_onboarding import (
    ProductCompletenessValidator,
    ProductPublicationService,
    StructuredProductIngestor,
    UnifiedProductIngestor,
)
from sanocea.packages.product_onboarding.provenance import (
    CommercialAIEnricher,
    ConflictResolutionError,
    PROTECTED_COMMERCIAL_FACTS,
    ZeroInventionPolicy,
    ZeroInventionViolationError,
    detect_and_merge_fact,
    normalize_commercial_fact_value,
    resolve_fact_conflict,
    sync_facts_to_extracted_attributes,
)


def test_commercial_fact_normalization_rules():
    # Price
    assert normalize_commercial_fact_value("price", "$149.99") == 14999
    assert normalize_commercial_fact_value("price", "149.99") == 14999
    assert normalize_commercial_fact_value("price", 149.99) == 14999
    assert normalize_commercial_fact_value("price", 15000) == 15000
    assert normalize_commercial_fact_value("price", "invalid") is None

    # Weight
    assert normalize_commercial_fact_value("weight", "650 g") == 650.0
    assert normalize_commercial_fact_value("weight", "0.65 kg") == 650.0
    assert normalize_commercial_fact_value("weight", 650) == 650.0

    # Dimensions
    assert normalize_commercial_fact_value("dimensions", "10x20x30 cm") == {
        "length": 10.0,
        "width": 20.0,
        "height": 30.0,
        "unit": "cm",
    }

    # Colours & sizes
    assert normalize_commercial_fact_value("colour", "navy blue") == "Navy"
    assert normalize_commercial_fact_value("colour", "charcoal grey") == "Charcoal"
    assert normalize_commercial_fact_value("size", "extra large") == "XL"

    # Tax & HSN
    assert normalize_commercial_fact_value("hsn", "6204.10") == "620410"
    assert normalize_commercial_fact_value("gst_rate", "18%") == 18.0
    assert normalize_commercial_fact_value("gst_rate", 0.18) == 18.0


def test_zero_invention_policy_blocks_protected_fact_ai_synthesis():
    policy = ZeroInventionPolicy()

    # Attempting to declare AI origin for protected commercial fact must raise violation
    for field in ["price", "sku", "weight", "hsn", "material", "inventory_quantity"]:
        with pytest.raises(ZeroInventionViolationError):
            policy.validate_fact_origin(
                name=field,
                value="100",
                classification=ProvenanceClassification.AI_ENRICHED,
                extractor="ai_model",
            )
        with pytest.raises(ZeroInventionViolationError):
            policy.validate_fact_origin(
                name=field,
                value="100",
                classification=ProvenanceClassification.SOURCE_FACT,
                extractor="llm",
            )


def test_ai_enricher_allows_marketing_copy_only():
    enricher = CommercialAIEnricher()
    draft = ProductDraft(
        merchant_id="mer_test",
        sku="TEST-SKU",
        title="Test Product",
        price=1000,
        currency="USD",
        product_type="Apparel",
    )

    # Permitted field: description
    fact = enricher.enrich_field(draft, "description", "Exquisite handcrafted silk apparel.")
    assert fact.classification == ProvenanceClassification.AI_ENRICHED.value
    assert draft.attributes["description"] == "Exquisite handcrafted silk apparel."
    assert draft.commercial_facts["description"].source.startswith("ai:")

    # Permitted field: tags
    enricher.enrich_field(draft, "tags", "silk,luxury,festive")
    assert draft.attributes["tags"] == "silk,luxury,festive"

    # Blocked field: price
    with pytest.raises(ZeroInventionViolationError):
        enricher.enrich_field(draft, "price", 9999)

    # Blocked field: weight
    with pytest.raises(ZeroInventionViolationError):
        enricher.enrich_field(draft, "weight", 500)

    # Blocked field: hsn
    with pytest.raises(ZeroInventionViolationError):
        enricher.enrich_field(draft, "hsn", "6204")


def test_cross_source_conflict_detection_preserves_locators():
    draft = ProductDraft(
        merchant_id="mer_test",
        sku="SKU-CONFLICT-003",
        title="Merino Wool Shawl",
        price=12000,
        currency="USD",
        product_type="Apparel",
    )

    fact_csv = CommercialFact(
        name="weight",
        value="450 g",
        source="file://catalog.csv",
        locator={"sheet": None, "row": 4, "column": "weight"},
        evidence_ref="file://catalog.csv#row=4&column=weight",
        classification=ProvenanceClassification.SOURCE_FACT.value,
        confidence=1.0,
    )
    detect_and_merge_fact(draft, fact_csv)
    assert not draft.commercial_facts["weight"].conflicted

    # Incoming conflicting fact from PDF
    fact_pdf = CommercialFact(
        name="weight",
        value="650 g",
        source="file://supplier_spec.pdf",
        locator={"page": 1, "line": 7, "extractor": "pdf_text_layer"},
        evidence_ref="file://supplier_spec.pdf#line=7",
        classification=ProvenanceClassification.SOURCE_FACT.value,
        confidence=0.95,
    )
    detect_and_merge_fact(draft, fact_pdf)

    # Conflict must be flagged and both locators preserved
    assert draft.commercial_facts["weight"].conflicted is True
    assert "conflicting_product_evidence:weight" in draft.conflicts
    assert draft.state == "CONFLICTED"
    conflict_history = draft.conflict_details["weight"]
    assert len(conflict_history) == 2
    assert conflict_history[0]["locator"] == {"sheet": None, "row": 4, "column": "weight"}
    assert conflict_history[1]["locator"] == {"page": 1, "line": 7, "extractor": "pdf_text_layer"}


def test_conflict_resolution_with_human_audit_trail():
    draft = ProductDraft(
        merchant_id="mer_test",
        sku="SKU-CONFLICT-003",
        title="Merino Wool Shawl",
        price=12000,
        currency="USD",
        product_type="Apparel",
    )

    fact_csv = CommercialFact(
        name="weight",
        value="450 g",
        source="file://catalog.csv",
        locator={"sheet": None, "row": 4, "column": "weight"},
        evidence_ref="file://catalog.csv#row=4",
    )
    fact_pdf = CommercialFact(
        name="weight",
        value="650 g",
        source="file://supplier_spec.pdf",
        locator={"page": 1, "line": 7},
        evidence_ref="file://supplier_spec.pdf#line=7",
    )
    detect_and_merge_fact(draft, fact_csv)
    detect_and_merge_fact(draft, fact_pdf)

    # Operator resolves conflict by picking PDF
    resolve_fact_conflict(
        draft=draft,
        fact_name="weight",
        chosen_value="650 g",
        chosen_source="file://supplier_spec.pdf",
        actor="operator_gagan",
        resolution_note="Verified with supplier manufacturing sheet",
    )

    resolved_fact = draft.commercial_facts["weight"]
    assert resolved_fact.conflicted is False
    assert resolved_fact.value == "650 g"
    assert resolved_fact.approved is True
    assert resolved_fact.approved_by == "operator_gagan"
    assert resolved_fact.classification == ProvenanceClassification.HUMAN_APPROVED.value
    assert "conflicting_product_evidence:weight" not in draft.conflicts
    assert "weight" not in draft.conflict_details


def test_unified_ingestor_handles_csv_pdf_images():
    store = Phase0Store()
    ingestor = UnifiedProductIngestor(store)

    fixture_dir = Path("tests/fixtures/phase11_merchant/messy_merchant_pack")
    csv_path = fixture_dir / "messy_catalog.csv"
    pdf_path = fixture_dir / "supplier_spec.pdf"
    img_path = fixture_dir / "SKU-CLEAN-001-main.png"

    # CSV Ingestion
    csv_drafts = ingestor.ingest_file("mer_test", csv_path)
    assert len(csv_drafts) == 4
    sku_clean = next(d for d in csv_drafts if d.sku == "SKU-CLEAN-001")
    assert sku_clean.price == 14999
    assert sku_clean.commercial_facts["hsn"].value == "6204"
    assert sku_clean.commercial_facts["weight"].value == "350 g"

    # PDF Ingestion merges into existing SKU-CONFLICT-003 and detects conflict
    pdf_drafts = ingestor.ingest_file("mer_test", pdf_path)
    assert len(pdf_drafts) == 1
    assert pdf_drafts[0].sku == "SKU-CONFLICT-003"
    assert pdf_drafts[0].commercial_facts["weight"].conflicted is True
    assert "conflicting_product_evidence:weight" in pdf_drafts[0].conflicts
    assert len(pdf_drafts[0].conflict_details["weight"]) == 2

    # Image Ingestion
    img_drafts = ingestor.ingest_file("mer_test", img_path)
    assert len(img_drafts) == 1
    assert img_drafts[0].sku == "SKU-CLEAN-001"
    assert "image" in img_drafts[0].commercial_facts


def test_publication_gate_fail_closed_on_conflicted_or_missing_facts():
    store = Phase0Store()
    store.set_config(
        "mer_test",
        {
            "product_rules": {
                "required": ["sku", "title", "price", "currency", "product_type", "hsn", "material"]
            },
            "publication": {"require_approval": False},
        },
    )
    validator = ProductCompletenessValidator(store)

    # 1. Conflicted draft cannot be published
    conflicted_draft = ProductDraft(
        merchant_id="mer_test",
        sku="SKU-CONFLICT-003",
        title="Merino Wool Shawl",
        price=12000,
        currency="USD",
        product_type="Apparel",
        conflicts=["conflicting_product_evidence:weight"],
        state="CONFLICTED",
    )
    decision = validator.apply_publication_policy(conflicted_draft)
    assert decision.outcome == "EXCEPTION"
    assert "draft_state:CONFLICTED" in decision.reasons or any("conflict" in r for r in decision.reasons)

    # 2. Incomplete draft with missing protected fact cannot be published
    incomplete_draft = ProductDraft(
        merchant_id="mer_test",
        sku="SKU-MISSING-002",
        title="Linen Summer Tunic",
        price=8900,
        currency="USD",
        product_type="Apparel",
        state="INCOMPLETE",
    )
    incomplete_draft.commercial_facts["hsn"] = ZeroInventionPolicy.create_missing_fact("hsn")
    decision_inc = validator.apply_publication_policy(incomplete_draft)
    assert decision_inc.outcome == "EXCEPTION"

    # 3. Draft violating zero-invention (AI-invented HSN) cannot be published
    violation_draft = ProductDraft(
        merchant_id="mer_test",
        sku="SKU-VIOLATION-005",
        title="Synthesized Product",
        price=5000,
        currency="USD",
        product_type="Apparel",
        state="READY",
    )
    violation_draft.commercial_facts["hsn"] = CommercialFact(
        name="hsn",
        value="6204",
        source="ai:gpt-4",
        locator={},
        evidence_ref="ai://gpt-4",
        classification=ProvenanceClassification.AI_ENRICHED.value,
    )
    decision_v = validator.apply_publication_policy(violation_draft)
    assert decision_v.outcome == "EXCEPTION"
    assert "zero_invention_violation:hsn" in decision_v.reasons
