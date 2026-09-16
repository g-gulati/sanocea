from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any
import psycopg2

from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.models import Channel, Inventory, Merchant
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from .generator import generate_reference_merchant_fixtures
from .tenant import (
    REF_CHANNELS,
    REF_CONFIG,
    REF_LOCATIONS,
    REF_MERCHANT_DISPLAY_NAME,
    REF_MERCHANT_ID,
    REF_MERCHANT_LEGAL_NAME,
)

_REF_TABLES_TO_CLEAR = (
    "purchase_order_lines", "purchase_orders", "supplier_acknowledgements", "inbound_shipment_lines",
    "inbound_shipments", "goods_receipt_lines", "goods_receipts", "replenishment_recommendations",
    "supplier_skus", "suppliers", "finance_reconciliations", "settlement_entries", "settlement_batches",
    "payment_observations", "returns", "exchanges", "refunds", "cancellations", "order_lines", "orders",
    "shipments", "tracking_events", "workflow_executions", "connector_commands", "approvals", "exceptions",
    "external_id_mappings", "raw_external_events", "credential_references",
    "merchant_configurations", "customers", "inventory", "channels", "api_keys",
    "product_drafts", "publications", "publication_attempts", "listing_verifications",
    "support_conversations", "support_intents", "customer_support_actions",
    "identity_decisions",
)


def reset_reference_merchant(
    dsn: str | None = None,
    fixtures_dir: Path | None = None,
) -> dict[str, Any]:
    """Deterministically resets the Reference Merchant (Anchal Heritage Organics) tenant to its
    canonical demonstration baseline.
    Cleans all existing transactional, catalog, and configuration records for ref_anchal_heritage,
    re-seeds merchant profile, multi-location inventory, live Shopify credentials, simulated channels,
    and returns a clean operational summary.
    """
    if not dsn:
        dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")

    # Ensure master keys are in env
    if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
        os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
        os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

    # 1. Direct SQL cleanup for ref_anchal_heritage
    wiped_counts: dict[str, int] = {}
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        for table in _REF_TABLES_TO_CLEAR:
            cur.execute(f"DELETE FROM {table} WHERE merchant_id = %s", (REF_MERCHANT_ID,))
            wiped_counts[table] = cur.rowcount
        cur.execute("DELETE FROM idempotency_records WHERE scope LIKE %s", (f"{REF_MERCHANT_ID}:%",))
        wiped_counts["idempotency_records"] = cur.rowcount

    # 2. Re-instantiate store with encrypted credential provider
    cred_provider = build_production_credential_provider(dsn)
    store = PostgresStore(dsn, credential_provider=cred_provider)
    store.migrate()

    baseline_audit_count = len(store.list_audit(REF_MERCHANT_ID))

    # 3. Seed Merchant entity
    merchant = Merchant(
        id=REF_MERCHANT_ID,
        merchant_id=REF_MERCHANT_ID,
        legal_name=REF_MERCHANT_LEGAL_NAME,
        display_name=REF_MERCHANT_DISPLAY_NAME,
    )
    store.put(merchant)

    # 4. Set merchant configuration
    store.set_config(REF_MERCHANT_ID, REF_CONFIG)

    # 5. Set channels
    for chn_id, chn_meta in REF_CHANNELS.items():
        channel = Channel(
            id=chn_id,
            merchant_id=REF_MERCHANT_ID,
            type=chn_meta["platform"],
            name=chn_meta["name"],
        )
        store.put(channel)

    # 6. Set encrypted credentials for live Shopify dev store
    shop_domain = os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN", "sanocea-commerce-os-dev.myshopify.com")
    client_id = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID", "1d3844f9bf7dd89697abfd62c29decf4")
    client_secret = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET", "REDACTED-SET-VIA-SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
    webhook_secret = os.environ.get("SANOCEA_SHOPIFY_WEBHOOK_SECRET", "REDACTED-SET-VIA-SANOCEA_SHOPIFY_WEBHOOK_SECRET")

    store.set_credential_ref(REF_MERCHANT_ID, "shopify_live_shop_domain", shop_domain)
    store.set_credential_ref(REF_MERCHANT_ID, "shopify_live_client_id", client_id)
    store.set_credential_ref(REF_MERCHANT_ID, "shopify_live_client_secret", client_secret)
    store.set_credential_ref(REF_MERCHANT_ID, "shopify_webhook_secret", webhook_secret)

    # 7. Seed baseline multi-location inventory
    inventory_items = [
        # Delhi Central Hub (loc_delhi_hub)
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_delhi_hub:ANCHAL-KACHI-1L-BTL",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-KACHI-1L-BTL",
            location_ref="loc_delhi_hub",
            quantity=150,
            available=150,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_delhi_hub:ANCHAL-KACHI-5L-CAN",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-KACHI-5L-CAN",
            location_ref="loc_delhi_hub",
            quantity=80,
            available=80,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_delhi_hub:ANCHAL-DESI-GHEE",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-DESI-GHEE",
            location_ref="loc_delhi_hub",
            quantity=60,
            available=60,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_delhi_hub:ANCHAL-WILD-HONEY",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-WILD-HONEY",
            location_ref="loc_delhi_hub",
            quantity=50,
            available=50,
        ),
        # Mumbai Bhiwandi Logistics Park (loc_mumbai_hub)
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_mumbai_hub:ANCHAL-KACHI-1L-BTL",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-KACHI-1L-BTL",
            location_ref="loc_mumbai_hub",
            quantity=100,
            available=100,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_mumbai_hub:ANCHAL-KACHI-5L-CAN",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-KACHI-5L-CAN",
            location_ref="loc_mumbai_hub",
            quantity=50,
            available=50,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_mumbai_hub:ANCHAL-DESI-GHEE",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-DESI-GHEE",
            location_ref="loc_mumbai_hub",
            quantity=40,
            available=40,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_mumbai_hub:ANCHAL-WILD-HONEY",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-WILD-HONEY",
            location_ref="loc_mumbai_hub",
            quantity=30,
            available=30,
        ),
        # Bengaluru South Distribution Node (loc_bengaluru_hub)
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_bengaluru_hub:ANCHAL-KACHI-1L-BTL",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-KACHI-1L-BTL",
            location_ref="loc_bengaluru_hub",
            quantity=50,
            available=50,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_bengaluru_hub:ANCHAL-KACHI-5L-CAN",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-KACHI-5L-CAN",
            location_ref="loc_bengaluru_hub",
            quantity=30,
            available=30,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_bengaluru_hub:ANCHAL-DESI-GHEE",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-DESI-GHEE",
            location_ref="loc_bengaluru_hub",
            quantity=25,
            available=25,
        ),
        Inventory(
            id=f"{REF_MERCHANT_ID}:loc_bengaluru_hub:ANCHAL-WILD-HONEY",
            merchant_id=REF_MERCHANT_ID,
            sku="ANCHAL-WILD-HONEY",
            location_ref="loc_bengaluru_hub",
            quantity=20,
            available=20,
        ),
    ]
    for inv in inventory_items:
        store.put(inv)

    # 8. Create operator API key for live demonstration cURL / HTTP calls
    key_id, raw_api_key = store.create_api_key(
        merchant_id=REF_MERCHANT_ID,
        role="operator",
        label="reference-merchant-operator",
    )

    # 9. Generate messy fixtures in target directory
    if fixtures_dir is None:
        fixtures_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "reference_merchant"
    fixtures = generate_reference_merchant_fixtures(fixtures_dir)

    return {
        "status": "RESET_SUCCESSFUL",
        "merchant_id": REF_MERCHANT_ID,
        "display_name": REF_MERCHANT_DISPLAY_NAME,
        "operator_key_id": key_id,
        "operator_api_key": raw_api_key,
        "locations_configured": list(REF_LOCATIONS.keys()),
        "channels_configured": list(REF_CHANNELS.keys()),
        "inventory_records_seeded": len(inventory_items),
        "baseline_audit_events": baseline_audit_count,
        "fixtures_generated": {k: str(v) for k, v in fixtures.items()},
        "wiped_counts": wiped_counts,
    }
