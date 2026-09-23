#!/usr/bin/env python3
"""Demo-day endpoint sync for the Premium Basket rehearsal.

Run automatically by START_DEMO.bat / scripts/start_demo.ps1 once the API server is healthy and the
ngrok tunnel's real, current public URL is known. Ngrok's free-tier URL is DIFFERENT every time the
tunnel restarts, so a stale one from a previous session breaks real inbound Shopify webhook delivery
silently (Shopify just gets connection-refused / DNS errors against a dead tunnel). This closes that
gap: updates config.shopify_live.webhook_delivery_base_url to the CURRENT tunnel URL, re-registers the
real Shopify webhooks against it (idempotent - see ShopifyLiveConnector.register_webhooks), and
refreshes the WhatsApp session contact (also time-boxed, 4-hour expiry) so a fresh demo run doesn't
silently start with a dead webhook target or an expired approval-reply channel.

Usage: python scripts/sync_demo_endpoints.py <ngrok_public_url>
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = ROOT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import os

from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.runtime.service_graph import build_service_graph

MERCHANT_ID = "prospect_premium_basket"
OWNER_WHATSAPP = "919825133222"


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: sync_demo_endpoints.py <ngrok_public_url>", file=sys.stderr)
        sys.exit(1)
    tunnel_url = sys.argv[1].rstrip("/")

    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
    store = PostgresStore(dsn, credential_provider=build_production_credential_provider(dsn))

    config = store.get_config(MERCHANT_ID)
    shopify_cfg = config.setdefault("shopify_live", {})
    old_url = shopify_cfg.get("webhook_delivery_base_url")
    shopify_cfg["webhook_delivery_base_url"] = tunnel_url
    store.set_config(MERCHANT_ID, config)
    print(f"[1/3] webhook_delivery_base_url: {old_url} -> {tunnel_url}")

    graph = build_service_graph(store)
    # Explicit channel TYPE, not resolve()'s "whichever channel happens to be first" - this merchant
    # has 3 registered channels (shopify_live + 2 demo-only marketplace channels), so resolve() alone
    # is not safe to assume picks the real Shopify one.
    connector = graph.storefronts.resolve_for_channel_type(MERCHANT_ID, "shopify_live")
    result = connector.register_webhooks(MERCHANT_ID, "shopify_live")
    print(f"[2/3] Shopify webhooks registered against the new tunnel: {result.payload}")

    from sanocea.packages.notifications import DemoApprovalNotificationService
    from sanocea.packages.notifications.transport import WhatsAppDemoTransport

    transport = WhatsAppDemoTransport(
        waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"),
        api_key=os.environ.get("SANOCEA_WAHA_API_KEY"),
    )
    contact = DemoApprovalNotificationService(store, transport).set_session_contact(
        MERCHANT_ID, phone_e164=OWNER_WHATSAPP, session_label="demo-day auto-refresh", consented=True,
    )
    print(f"[3/3] WhatsApp session contact refreshed, valid until {contact.expires_at.isoformat()}")


if __name__ == "__main__":
    main()
