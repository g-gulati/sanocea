"""Self-service demo session leasing (browser self-service demo, Slice 1): POST /demo/sessions and
packages/prospect_demo/sessions.py, exercised against the real Postgres-backed store, same pattern as
tests/integration/test_internal_operator_multi_merchant_auth.py."""

from __future__ import annotations

import base64
import os
from datetime import timedelta

import pytest

os.environ.setdefault("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
PG_DSN = os.environ["SANOCEA_PG_DSN"]
if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="Requires a real Postgres DSN (SANOCEA_PG_DSN)",
)


@pytest.fixture()
def client():
    from sanocea.apps.api.app import create_app
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore

    cred_provider = build_production_credential_provider(PG_DSN)
    store = PostgresStore(PG_DSN, credential_provider=cred_provider)
    app = create_app(store)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_lease_state():
    """Every test gets an empty in-process lease table (see packages/prospect_demo/sessions.py) so
    tests don't leak leases into each other - this mirrors what a fresh API process would see."""
    from sanocea.packages.prospect_demo import sessions as sessions_module

    sessions_module._leases.clear()
    yield
    sessions_module._leases.clear()


def test_create_session_returns_a_scoped_key_for_a_prospect_tenant(client):
    from sanocea.packages.prospect_demo import PROSPECT_TENANTS

    resp = client.post("/demo/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["merchant_id"] in PROSPECT_TENANTS
    assert body["api_key"]
    assert body["session_id"].startswith("demosess_")
    assert body["expires_at"]


def test_session_key_is_scoped_to_its_own_merchant_only(client):
    resp = client.post("/demo/sessions")
    body = resp.json()
    mid, key = body["merchant_id"], body["api_key"]

    own = client.get(f"/merchants/{mid}/orders", headers={"Authorization": f"Bearer {key}"})
    assert own.status_code == 200

    other_mid = next(m for m in ["prospect_ajanta_soya", "prospect_healthvitals", "prospect_carzex", "prospect_premium_basket"] if m != mid)
    other = client.get(f"/merchants/{other_mid}/orders", headers={"Authorization": f"Bearer {key}"})
    assert other.status_code == 403


def test_sessions_lease_distinct_tenants_until_pool_exhausted(client):
    from sanocea.packages.prospect_demo import PROSPECT_TENANTS

    seen = set()
    for _ in range(len(PROSPECT_TENANTS)):
        resp = client.post("/demo/sessions")
        assert resp.status_code == 200
        seen.add(resp.json()["merchant_id"])
    assert seen == set(PROSPECT_TENANTS)

    exhausted = client.post("/demo/sessions")
    assert exhausted.status_code == 503


def test_expired_lease_is_reclaimed_and_stale_key_revoked():
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore
    from sanocea.packages.prospect_demo import lease_demo_session

    store = PostgresStore(PG_DSN, credential_provider=build_production_credential_provider(PG_DSN))

    first = lease_demo_session(store, dsn=PG_DSN, ttl=timedelta(seconds=-1))
    second = lease_demo_session(store, dsn=PG_DSN, ttl=timedelta(minutes=30))
    assert first["merchant_id"] == second["merchant_id"], "the already-expired tenant must be reclaimed first"
    assert store.resolve_api_key(first["api_key"]) is None, "the reclaimed session's stale key must be revoked"
    assert store.resolve_api_key(second["api_key"]) is not None
