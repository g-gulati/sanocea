"""Real HTTP tests (FastAPI TestClient - real routing, real auth dependencies, real middleware, same
pattern as tests/unit/test_phase45_api_integration.py) for the Command Center internal-operator UX
correction: one authenticated session must be able to switch between every authorized demo merchant
with zero additional credential prompts, while backend tenant authorization still passes on every single
request - never derived from the frontend.
"""

from __future__ import annotations

import base64
import os

import pytest

os.environ.setdefault("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
PG_DSN = os.environ["SANOCEA_PG_DSN"]
# apps.api.app builds a module-level `app = create_app()` at IMPORT time, which requires the master key
# env vars to already be set - must happen before `from fastapi.testclient import TestClient` triggers
# that import chain (same reason tests/unit/test_phase45_api_integration.py sets its own env var first).
if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="Requires a real Postgres DSN (SANOCEA_PG_DSN)",
)

DEMO_MERCHANTS = [
    "ref_anchal_heritage",
    "prospect_ajanta_soya",
    "prospect_healthvitals",
    "prospect_carzex",
    "prospect_premium_basket",
]


@pytest.fixture(scope="module")
def stack():
    """Boots the REAL FastAPI app against the REAL Postgres-backed store (not the in-memory harness) -
    this exercises the actual production auth/store code path, not a simplified stand-in. Resets every
    demo tenant once so each has a real Merchant row (api_key_merchants has a genuine FK to merchants),
    then mints one internal-operator key and one solo Ajanta key for the isolation assertions below."""
    from sanocea.apps.api.app import create_app
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore
    from sanocea.packages.prospect_demo import reset_prospect_tenant
    from sanocea.packages.reference_merchant import reset_reference_merchant

    reset_reference_merchant(dsn=PG_DSN)
    for merchant_id in DEMO_MERCHANTS[1:]:
        reset_prospect_tenant(merchant_id, dsn=PG_DSN)

    cred_provider = build_production_credential_provider(PG_DSN)
    store = PostgresStore(PG_DSN, credential_provider=cred_provider)
    app = create_app(store)
    client = TestClient(app)

    internal_key_id, internal_key = store.create_api_key(
        merchant_id=None, role="operator", label="test-internal-operator", allowed_merchants=DEMO_MERCHANTS,
    )
    solo_key_id, solo_key = store.create_api_key(
        merchant_id="prospect_ajanta_soya", role="operator", label="test-solo-ajanta",
    )
    return store, client, internal_key, solo_key


# --- 1-8: internal operator authenticates once, switches freely, no second prompt -------------------

def test_1_internal_operator_authenticates_once(stack):
    _, client, internal_key, _ = stack
    resp = client.get("/merchants/ref_anchal_heritage/profile", headers={"Authorization": f"Bearer {internal_key}"})
    assert resp.status_code == 200


@pytest.mark.parametrize("merchant_id", DEMO_MERCHANTS)
def test_2_to_6_same_session_reaches_every_demo_merchant(stack, merchant_id):
    """Items 2-6: same session/key -> Anchal, Ajanta, HealthVitals, Carzex, Premium Basket, all 200."""
    _, client, internal_key, _ = stack
    resp = client.get(f"/merchants/{merchant_id}/profile", headers={"Authorization": f"Bearer {internal_key}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == merchant_id


def test_7_no_second_credential_submission_required(stack):
    """The SAME raw key string, never re-derived, never re-submitted through any second auth step,
    reaches all 5 merchants across all 7 Command Center data endpoints each merchant screen needs."""
    _, client, internal_key, _ = stack
    headers = {"Authorization": f"Bearer {internal_key}"}
    endpoints = ["profile", "operator/summary", "catalogue/drafts", "exceptions", "approvals", "orders", "audit"]
    for merchant_id in DEMO_MERCHANTS:
        for endpoint in endpoints:
            resp = client.get(f"/merchants/{merchant_id}/{endpoint}", headers=headers)
            assert resp.status_code == 200, f"{merchant_id}/{endpoint} failed with the same never-resubmitted key"


def test_8_merchant_state_remains_isolated_across_switches(stack):
    _, client, internal_key, _ = stack
    headers = {"Authorization": f"Bearer {internal_key}"}
    ajanta_titles = {d["title"] for d in client.get("/merchants/prospect_ajanta_soya/catalogue/drafts", headers=headers).json()}
    hv_titles = {d["title"] for d in client.get("/merchants/prospect_healthvitals/catalogue/drafts", headers=headers).json()}
    assert ajanta_titles, "Ajanta must have real seeded products"
    assert hv_titles, "HealthVitals must have real seeded products"
    assert ajanta_titles.isdisjoint(hv_titles)


# --- 9-10: backend authorization, fail-closed ---------------------------------------------------------

def test_9_unauthorized_merchant_403(stack):
    _, client, internal_key, _ = stack
    resp = client.get("/merchants/some_unrelated_real_merchant/profile", headers={"Authorization": f"Bearer {internal_key}"})
    assert resp.status_code == 403


def test_10_nonexistent_merchant_fails_closed(stack):
    _, client, internal_key, _ = stack
    resp = client.get("/merchants/totally_made_up_merchant_xyz/profile", headers={"Authorization": f"Bearer {internal_key}"})
    assert resp.status_code == 403


# --- 11-13: prospect-scoped (single-merchant) session stays fully isolated ---------------------------

def test_11_prospect_scoped_session_reaches_its_own_merchant(stack):
    _, client, _, solo_key = stack
    resp = client.get("/merchants/prospect_ajanta_soya/profile", headers={"Authorization": f"Bearer {solo_key}"})
    assert resp.status_code == 200


def test_12_prospect_scoped_session_cannot_reach_another_merchant(stack):
    _, client, _, solo_key = stack
    resp = client.get("/merchants/prospect_healthvitals/profile", headers={"Authorization": f"Bearer {solo_key}"})
    assert resp.status_code == 403
    resp2 = client.get("/merchants/ref_anchal_heritage/profile", headers={"Authorization": f"Bearer {solo_key}"})
    assert resp2.status_code == 403


def test_13_prospect_scoped_session_cannot_enumerate_merchant_list(stack):
    _, client, _, solo_key = stack
    resp = client.get("/merchants", headers={"Authorization": f"Bearer {solo_key}"})
    assert resp.status_code == 403  # /merchants is require_service-only; no operator key, single- or
    # multi-merchant, may enumerate tenants through it.


# --- 14: no permanent credential exposed in frontend/browser storage/URL -----------------------------

def test_14_no_permanent_credential_in_served_frontend(stack):
    _, client, internal_key, solo_key = stack
    ui_html = client.get("/ui").text
    app_js = client.get("/static/app.js").text
    for secret in (internal_key, solo_key):
        assert secret not in ui_html
        assert secret not in app_js
    # No demo-token dispensing endpoint exists at all.
    assert client.get("/merchants/prospect_ajanta_soya/demo-token").status_code == 404
    # The frontend never writes a credential to localStorage - only sessionStorage, and only ever
    # REMOVES a legacy localStorage key (defensive cleanup), never sets one.
    assert "localStorage.setItem" not in app_js
    assert "sessionStorage.setItem('sanocea_operator_session'" in app_js or 'sessionStorage.setItem("sanocea_operator_session"' in app_js


# --- 15-17: regressions -------------------------------------------------------------------------------

def test_15_unauthenticated_request_rejected(stack):
    _, client, _, _ = stack
    resp = client.get("/merchants/prospect_ajanta_soya/profile")
    assert resp.status_code == 401


def test_16_existing_single_merchant_operator_keys_unaffected(stack):
    """An ordinary, pre-existing single-merchant key (no allowed_merchants rows) behaves byte-for-byte
    as before this change - this IS the Reference Merchant / prospect regression proof at the auth layer."""
    store, client, _, _ = stack
    key_id, raw_key = store.create_api_key(merchant_id="ref_anchal_heritage", role="operator", label="regression-check")
    ok = client.get("/merchants/ref_anchal_heritage/profile", headers={"Authorization": f"Bearer {raw_key}"})
    assert ok.status_code == 200
    blocked = client.get("/merchants/prospect_ajanta_soya/profile", headers={"Authorization": f"Bearer {raw_key}"})
    assert blocked.status_code == 403


def test_17_command_center_ui_still_serves_with_merchant_switcher(stack):
    _, client, _, _ = stack
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert 'id="merchant-select"' in resp.text
    assert 'id="demo-disclosure-banner"' in resp.text
