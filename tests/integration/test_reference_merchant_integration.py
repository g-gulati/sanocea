from __future__ import annotations

import os
import pytest

from scripts.run_reference_merchant_certification import run_certification

# Set dev store defaults if not provided in environment
os.environ.setdefault("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN", "sanocea-commerce-os-dev.myshopify.com")
os.environ.setdefault("SANOCEA_SHOPIFY_LIVE_CLIENT_ID", "1d3844f9bf7dd89697abfd62c29decf4")
os.environ.setdefault("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET", "REDACTED-SET-VIA-SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
os.environ.setdefault("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN")
        and os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID")
        and os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
        and os.environ.get("SANOCEA_PG_DSN")
    ),
    reason="Requires live Shopify dev store credentials and Postgres DSN",
)


def test_reference_merchant_end_to_end_certification():
    """Certifies the Reference Merchant (Anchal Heritage Organics) end-to-end.
    
    Verifies 11 core checkpoints across:
    1. Deterministic reset and tenant isolation
    2. Adversarial messy file ingestion and ballast quarantine
    3. Formula provenance and hidden sheet quarantine
    4. Multi-product PDF specification extraction
    5. Commercial fact conflict detection and fail-closed publication gate
    6. Audited human disambiguation and approval
    7. Multi-variant publication to live Shopify Dev Store
    8. Live Shopify Admin GraphQL read-back verification
    9. Multi-location inventory allocation and atomic reservation
    10. Customer return, restock, and policy-governed refund limits
    11. Append-only tamper-proof audit ledger lineage and database triggers
    """
    report = run_certification()
    assert report["verdict"] == "PASS"
    assert report["passed_checkpoints"] == 11
    assert report["total_checkpoints"] == 11
    assert report["tenant_id"] == "ref_anchal_heritage"
