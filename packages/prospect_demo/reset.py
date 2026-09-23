"""Generic prospect demo tenant reset/seed orchestrator.

Deliberately NOT a per-prospect module: this single function drives every entry in
`PROSPECT_TENANTS` (tenants.py). Adding a new prospect tenant means adding a config entry, not writing
a new reset routine - the same "config + data, not new software" discipline the Reference Merchant's own
reset already exists as precedent for.

Reuses (never duplicates) the Reference Merchant's own table-clearing list, credential-provider
bootstrap, and CanonicalEntity/store conventions - see packages/reference_merchant/reset.py, which this
module never modifies and never runs against ref_anchal_heritage's own merchant_id.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import psycopg2

from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.models import (
    Channel,
    CommercialFact,
    Inventory,
    Merchant,
    ProductDraft,
    VariantDraft,
)
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.reference_merchant.reset import _REF_TABLES_TO_CLEAR
from sanocea.packages.reference_merchant.tenant import REF_MERCHANT_ID

from .tenants import DEMO_DISCLOSURE_TEXT, PROSPECT_TENANTS
from .scenarios import SCENARIO_SEEDERS

DEFAULT_LOCATION_REF = "loc_default_hub"


def reset_prospect_tenant(merchant_id: str, dsn: str | None = None) -> dict[str, Any]:
    """Deterministically resets ONE prospect demo tenant (see PROSPECT_TENANTS) to its canonical
    baseline: real, publicly-verified products + a synthetic operational scenario matching what that
    prospect actually told Sanocea matters to them. Never touches ref_anchal_heritage or any other
    prospect tenant - every DELETE below is scoped to this single merchant_id."""
    if merchant_id == REF_MERCHANT_ID:
        raise ValueError("reset_prospect_tenant must never target the Reference Merchant tenant")
    config = PROSPECT_TENANTS.get(merchant_id)
    if config is None:
        raise ValueError(f"unknown prospect demo tenant: {merchant_id!r}")

    if not dsn:
        dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
    if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
        os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
        os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

    cred_provider = build_production_credential_provider(dsn)
    store = PostgresStore(dsn, credential_provider=cred_provider)
    store.migrate()

    # A tenant wired to a REAL storefront (any channel whose type is not a demo_* placeholder) must survive a
    # reset with that connection intact. This reset used to wipe channels/credentials/config and re-seed
    # demo-only channels, silently severing the live Shopify link (found live: after pressing "Reset Demo",
    # WhatsApp uploads got no reply because the channel, credentials, owner contact and product rules were
    # all gone). For such a tenant, "reset" now means: clear the OPERATIONAL data (drafts, orders,
    # exceptions, approvals, audit, inventory...) and leave the integration records alone.
    live_channels = [c for c in store.list(Channel, merchant_id) if not str(c.type).startswith("demo_")]
    live_tenant = bool(live_channels)
    preserved_config = store.get_config(merchant_id) if live_tenant else {}
    keep_tables = {"credential_references", "merchant_configurations", "demo_session_contacts"} if live_tenant else set()

    wiped_counts: dict[str, int] = {}
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        # See migration 0001_phase05.sql: this GUC is the one narrow, explicit exception to
        # audit_events being append-only - scoped to this transaction, this reset call only.
        cur.execute("SET LOCAL sanocea.allow_demo_audit_reset = 'on'")
        for table in _REF_TABLES_TO_CLEAR:
            if table in keep_tables:
                continue
            if table == "channels" and live_tenant:
                cur.execute("DELETE FROM channels WHERE merchant_id = %s AND data->>'type' LIKE 'demo%%'", (merchant_id,))
            else:
                cur.execute(f"DELETE FROM {table} WHERE merchant_id = %s", (merchant_id,))
            wiped_counts[table] = cur.rowcount
        cur.execute("DELETE FROM idempotency_records WHERE scope LIKE %s", (f"{merchant_id}:%",))
        wiped_counts["idempotency_records"] = cur.rowcount

    baseline_audit_count = len(store.list_audit(merchant_id))

    # 1. Merchant identity
    store.put(Merchant(
        id=merchant_id, merchant_id=merchant_id,
        legal_name=config["legal_name"], display_name=config["display_name"],
    ))

    # 2. Merchant configuration - demo disclosure + prospect classification live here, queryable via the
    # existing GET /merchants/{id}/profile route the Command Center already calls for every tenant.
    seeded_config = {
        "currency": config["currency"],
        "gstin": config.get("gstin"),
        **config["policy_profile"],
        "demo": {
            "demo_type": config["demo_type"],
            "disclosure": DEMO_DISCLOSURE_TEXT,
            "known_channels": config["known_channels"],
            "enabled_scenarios": config["enabled_scenarios"],
            "public_catalogue_sources": config["public_catalogue_sources"],
            "prospect_provided_context": config["prospect_provided_context"],
        },
    }
    for preserved_key in ("shopify_live", "product_rules"):
        if preserved_key in preserved_config:
            seeded_config[preserved_key] = preserved_config[preserved_key]
    store.set_config(merchant_id, seeded_config)

    # 3. Demo channels - informational only. Deliberately NOT registered against any real/simulated
    # storefront connector type (never "shopify_live"/"shopify"/"woocommerce") - these tenants have no
    # live credentials and must never become publishable/mutable targets (Phase J). A channel `type` that
    # matches no entry in StorefrontConnectorRegistry simply means no connector is ever instantiated for
    # it, which is exactly the desired fail-closed default here.
    channels_created = []
    for channel_name in config["known_channels"]:
        channel_id = f"chn_{channel_name}"
        store.put(Channel(id=channel_id, merchant_id=merchant_id, type=f"demo_{channel_name}", name=channel_name))
        channels_created.append(channel_id)

    # 4. Real, publicly-verified products - one ProductDraft per public_products entry, commercial facts
    # classified EXTERNALLY_VERIFIED (the existing ProvenanceClassification value closest in meaning to
    # this task's PUBLIC_VERIFIED category - reused, not a new enum member added to the certified
    # provenance system). Already READY/approved: prospect demos are not re-running Anchal's own
    # conflict-detection certification story, they are showing a healthy catalogue with a scenario-
    # specific operational story layered on top (see scenarios.py).
    product_drafts: list[ProductDraft] = []
    for p in ([] if live_tenant else config["public_products"]):
        fact_source = p.get("source") or p.get("product_url") or "public_research"
        facts = {
            "title": CommercialFact(name="title", value=p["title"], source=fact_source, classification="EXTERNALLY_VERIFIED", verified=True, approved=True),
        }
        if p.get("price_paise") is not None:
            facts["price"] = CommercialFact(name="price", value=p["price_paise"], source=fact_source, classification="EXTERNALLY_VERIFIED", verified=True, approved=True)
        draft = ProductDraft(
            merchant_id=merchant_id,
            sku=p.get("sku"),
            title=p["title"],
            price=p.get("price_paise"),
            currency=p.get("currency", config["currency"]),
            product_type=p.get("category"),
            category=p.get("category"),
            attributes={
                "brand": p.get("brand"),
                "variant": p.get("variant"),
                "pack_size": p.get("pack_size"),
                "image_url": p.get("image_url"),
                "product_url": p.get("product_url"),
                "channel": p.get("channel"),
                "provenance": "PUBLIC_VERIFIED",
                "retrieval_date": p.get("retrieval_date"),
            },
            commercial_facts=facts,
            evidence_refs=[fact_source],
            identity_status="RESOLVED",
            variants=[VariantDraft(sku=p.get("sku"), price=p.get("price_paise"))],
            state="READY",
            approved_for_publication=True,
            approved_by="prospect_demo_seed",
        )
        store.put(draft)
        product_drafts.append(draft)

    # 5. Baseline inventory - one location, deterministic quantities derived from the tenant's own seed
    # (Phase K determinism requirement), never random per run.
    inventory_created = 0
    for i, draft in enumerate(product_drafts):
        if not draft.sku:
            continue
        qty = 40 + ((config["deterministic_seed"] + i * 7) % 60)
        store.put(Inventory(
            id=f"{merchant_id}:{DEFAULT_LOCATION_REF}:{draft.sku}",
            merchant_id=merchant_id, sku=draft.sku, location_ref=DEFAULT_LOCATION_REF,
            quantity=qty, available=qty,
        ))
        inventory_created += 1

    # 6. Scenario-specific synthetic operational data - real service calls, real domain models, no
    # bespoke per-prospect business logic (see scenarios.py).
    scenario_results: dict[str, Any] = {}
    for scenario_name in ([] if live_tenant else config["enabled_scenarios"]):
        seeder = SCENARIO_SEEDERS.get(scenario_name)
        if seeder is None:
            raise ValueError(f"no seeder registered for scenario {scenario_name!r}")
        scenario_results[scenario_name] = seeder(store, merchant_id, product_drafts, config)

    # 7. Operator API key, scoped to this merchant only (same mechanism as every existing operator key -
    # see packages/authn/deps.py::require_operator; a key minted here can never authenticate for any
    # other merchant_id).
    key_id, raw_api_key = store.create_api_key(merchant_id=merchant_id, role="operator", label=f"prospect-demo-operator-{merchant_id}")

    return {
        "status": "RESET_SUCCESSFUL",
        "merchant_id": merchant_id,
        "display_name": config["display_name"],
        "operator_key_id": key_id,
        "operator_api_key": raw_api_key,
        "channels_configured": channels_created,
        "products_seeded": len(product_drafts),
        "inventory_records_seeded": inventory_created,
        "scenario_results": scenario_results,
        "baseline_audit_events": baseline_audit_count,
        "wiped_counts": wiped_counts,
    }
