from __future__ import annotations

import pytest
from sanocea.packages.domain_contract.models import ProductDraft
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.product_onboarding.recommendations import (
    format_missing_fields_notification,
    format_publish_confirmation,
    get_draft_recommendations,
)
from sanocea.packages.product_onboarding.taxonomy import (
    STANDARD_FOOD_TAXONOMY_FALLBACK,
    ShopifyTaxonomyService,
    TaxonomyCategoryRecommendation,
)


def test_taxonomy_service_recommend_category_almonds_and_cashews():
    service = ShopifyTaxonomyService()
    rec = service.recommend_category(
        connector=None,
        title="Smoky BBQ Almonds & Cashews",
        description="A bold blend of roasted almonds and cashews tossed in smoky barbecue seasoning.",
        tags="almonds, cashews, bbq, party snacks",
        sku="GC-NT-BBQ-0250G",
        product_type="",
    )

    assert rec is not None
    assert rec.category_id.startswith("gid://shopify/TaxonomyCategory/")
    assert "Food, Beverages & Tobacco" in rec.full_path
    assert "Nut" in rec.full_path or "Snack" in rec.full_path
    assert rec.confidence >= 0.80
    assert len(rec.evidence) > 0
    assert rec.product_type == "Dry Fruits & Nuts"


def test_taxonomy_service_caching():
    service = ShopifyTaxonomyService()
    res1 = service.search_taxonomy(None, "Nut & Seed Snacks")
    res2 = service.search_taxonomy(None, "Nut & Seed Snacks")
    assert res1 is res2  # Exactly same cached object


def test_taxonomy_service_respects_merchant_mappings():
    service = ShopifyTaxonomyService()
    config = {
        "product_rules": {
            "taxonomy_confidence_threshold": 0.85,
            "taxonomy_mappings": {
                "gourmet_nuts": "Nuts & Seeds",
            }
        }
    }
    rec = service.recommend_category(
        connector=None,
        title="California Almonds",
        description="Premium California almonds.",
        tags="gourmet_nuts",
        sku="GC-NT-ALM",
        merchant_config=config,
    )
    assert rec is not None
    assert any("merchant mapping" in e for e in rec.evidence)


def test_format_missing_fields_notification_includes_taxonomy_path():
    draft = ProductDraft(
        merchant_id="test_merchant",
        sku="GC-NT-BBQ-0250G",
        title="Smoky BBQ Almonds & Cashews",
        price=42900,
        validation_errors=["missing_required_attribute:product_type"],
        attributes={
            "description": "A bold blend of roasted almonds and cashews tossed in smoky barbecue seasoning.",
            "tags": "almonds, cashews, bbq, party snacks",
        }
    )

    # Attach recommendation
    service = ShopifyTaxonomyService()
    rec = service.attach_recommendation("test_merchant", draft)
    assert rec is not None

    missing = ["product_type"]
    msg = format_missing_fields_notification(draft, missing)

    assert "Recommended Shopify category:" in msg
    assert "Food, Beverages & Tobacco" in msg
    assert "Reply *APPROVE* to use this category" in msg
    assert "Dry Fruits & Nuts" in msg


def test_format_publish_confirmation_includes_category():
    text = format_publish_confirmation(
        title="Smoky BBQ Almonds & Cashews",
        sku="GC-NT-BBQ-0250G",
        completed_fields={
            "product_type": "Dry Fruits & Nuts",
            "category": "gid://shopify/TaxonomyCategory/fb-2-17-22",
        },
        outcome={"outcome": "published", "storefront_visible": True},
        audit_ref="AUDIT-TEST-1234",
        category_path="Food, Beverages & Tobacco > Food Items > Snack Foods > Nut & Seed Snacks",
    )

    assert "Smoky BBQ Almonds & Cashews" in text
    assert "Merchant Type: Dry Fruits & Nuts" in text
    assert "Shopify Category: Food, Beverages & Tobacco > Food Items > Snack Foods > Nut & Seed Snacks" in text
    assert "AUDIT-TEST-1234" in text
    assert "Live on Store" in text
