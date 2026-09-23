from __future__ import annotations

import os

import psycopg2
import pytest

from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.prospect_demo import PROSPECT_TENANTS, list_demo_tenants, reset_prospect_tenant
from sanocea.packages.reference_merchant import REF_MERCHANT_ID

os.environ.setdefault("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
PG_DSN = os.environ["SANOCEA_PG_DSN"]

pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="Requires a real Postgres DSN (SANOCEA_PG_DSN)",
)


def _store() -> PostgresStore:
    cred_provider = build_production_credential_provider(PG_DSN)
    return PostgresStore(PG_DSN, credential_provider=cred_provider)


@pytest.mark.parametrize("merchant_id", list(PROSPECT_TENANTS.keys()))
def test_each_prospect_tenant_resets_cleanly(merchant_id: str):
    result = reset_prospect_tenant(merchant_id, dsn=PG_DSN)
    assert result["status"] == "RESET_SUCCESSFUL"
    assert result["merchant_id"] == merchant_id
    assert result["products_seeded"] > 0, "every prospect config must carry at least one real product"
    assert result["operator_api_key"], "reset must mint a merchant-scoped operator key"


def test_real_products_are_classified_externally_verified():
    reset_prospect_tenant("prospect_ajanta_soya", dsn=PG_DSN)
    store = _store()
    from sanocea.packages.domain_contract.models import ProductDraft

    drafts = store.list(ProductDraft, "prospect_ajanta_soya")
    assert drafts, "Ajanta must have seeded real product drafts"
    for draft in drafts:
        assert draft.attributes.get("provenance") == "PUBLIC_VERIFIED"
        title_fact = draft.commercial_facts.get("title")
        assert title_fact is not None
        assert title_fact.classification == "EXTERNALLY_VERIFIED"
        assert title_fact.source, "every public fact must carry a real source, never blank"


def test_reset_is_deterministic():
    first = reset_prospect_tenant("prospect_healthvitals", dsn=PG_DSN)
    second = reset_prospect_tenant("prospect_healthvitals", dsn=PG_DSN)
    assert first["products_seeded"] == second["products_seeded"]
    assert first["inventory_records_seeded"] == second["inventory_records_seeded"]
    assert first["scenario_results"] == second["scenario_results"]


def test_tenant_isolation_no_cross_contamination():
    reset_prospect_tenant("prospect_ajanta_soya", dsn=PG_DSN)
    reset_prospect_tenant("prospect_carzex", dsn=PG_DSN)
    store = _store()
    from sanocea.packages.domain_contract.models import ProductDraft

    ajanta_titles = {d.title for d in store.list(ProductDraft, "prospect_ajanta_soya")}
    carzex_titles = {d.title for d in store.list(ProductDraft, "prospect_carzex")}
    assert ajanta_titles.isdisjoint(carzex_titles)
    assert not any("Carzex" in t for t in ajanta_titles)
    assert not any("Anchal" in t for t in carzex_titles)


def test_reset_prospect_tenant_refuses_reference_merchant():
    with pytest.raises(ValueError):
        reset_prospect_tenant(REF_MERCHANT_ID, dsn=PG_DSN)


def test_unknown_tenant_rejected():
    with pytest.raises(ValueError):
        reset_prospect_tenant("prospect_does_not_exist", dsn=PG_DSN)


def test_no_customer_pii_seeded():
    reset_prospect_tenant("prospect_premium_basket", dsn=PG_DSN)
    with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("select count(*) from customers where merchant_id = %s", ("prospect_premium_basket",))
        assert cur.fetchone()[0] == 0, "prospect demo scenarios must never seed real or fake customer PII"


def test_list_demo_tenants_includes_reference_and_all_prospects():
    tenants = {t["merchant_id"] for t in list_demo_tenants()}
    assert REF_MERCHANT_ID in tenants
    for merchant_id in PROSPECT_TENANTS:
        assert merchant_id in tenants


def test_scenario_seeders_use_real_exception_and_approval_records():
    reset_prospect_tenant("prospect_healthvitals", dsn=PG_DSN)
    store = _store()
    from sanocea.packages.domain_contract.models import Approval, ExceptionRecord

    exceptions = store.list(ExceptionRecord, "prospect_healthvitals")
    approvals = store.list(Approval, "prospect_healthvitals")
    assert any(e.category == "fulfilment_delay" for e in exceptions), "HealthVitals scenario must surface a real fulfilment-delay exception"
    assert any(a.action == "escalate_fulfilment_delay" and a.status == "pending" for a in approvals)
