#!/usr/bin/env python3
"""Recovery tool: re-attach prospect_premium_basket to the REAL Shopify dev store.

Needed after anything that wipes the tenant's live-integration records (the generic prospect-demo reset does:
it deletes channels/credentials/config and re-seeds demo-only channels). Idempotent - safe to run any time.
Credentials are copied from the reference tenant, which points at the same dev store (same app, same secrets),
so nothing has to be typed or looked up again.

Usage: python scripts/restore_premium_basket_live_shopify.py <ngrok_public_url>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR.parent))
sys.path.insert(0, str(ROOT_DIR))

from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.models import Channel
from sanocea.packages.domain_contract.postgres_store import PostgresStore

MERCHANT_ID = "prospect_premium_basket"
SOURCE_MERCHANT_ID = "ref_anchal_heritage"
CHANNEL_ID = "prospect_premium_basket_shopify_live"
REQUIRED_FIELDS = ["sku", "title", "price", "currency", "product_type", "description", "tags"]
CREDENTIAL_REFS = ("shopify_live_shop_domain", "shopify_live_client_id", "shopify_live_client_secret", "shopify_webhook_secret")


def main() -> None:
    tunnel_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else None
    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55199/sanocea_phase05")
    store = PostgresStore(dsn, credential_provider=build_production_credential_provider(dsn))

    for ref in CREDENTIAL_REFS:
        store.set_credential_ref(MERCHANT_ID, ref, store.get_credential_ref(SOURCE_MERCHANT_ID, ref))
    print("credentials restored:", ", ".join(CREDENTIAL_REFS))

    if not any(c.type == "shopify_live" for c in store.list(Channel, MERCHANT_ID)):
        store.put(Channel(id=CHANNEL_ID, merchant_id=MERCHANT_ID, type="shopify_live", name="Shopify"))
        print("channel restored:", CHANNEL_ID)

    cfg = store.get_config(MERCHANT_ID)
    live = cfg.setdefault("shopify_live", {})
    live.setdefault("api_version", "2026-07")
    live["shop_domain"] = store.get_credential_ref(MERCHANT_ID, "shopify_live_shop_domain")
    if tunnel_url:
        live["webhook_delivery_base_url"] = tunnel_url
    rules = cfg.setdefault("product_rules", {})
    rules["required"] = REQUIRED_FIELDS
    rules["auto_publish_on_ingest"] = True
    store.set_config(MERCHANT_ID, cfg)
    print("config restored: shopify_live + product_rules (required fields incl. description/tags, auto-publish on ingest)")


if __name__ == "__main__":
    main()
