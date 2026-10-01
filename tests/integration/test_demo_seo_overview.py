"""GET /demo/seo/overview against the real Postgres-backed store: the credential is a real key leased by
POST /demo/sessions, and "active session" is the real demo_ephemeral_sessions row. Only the SEO worker is a local
stand-in HTTP server (the bridge makes real urllib requests to it), same as tests/unit/test_seo_bridge.py."""

from __future__ import annotations

import base64
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

os.environ.setdefault("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
PG_DSN = os.environ["SANOCEA_PG_DSN"]
if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()

from fastapi.testclient import TestClient  # noqa: E402

from sanocea.packages.seo_bridge import VIEWS  # noqa: E402

ROUTE = "/demo/seo/overview"


class _Worker(BaseHTTPRequestHandler):
    hits: list[str] = []

    def log_message(self, *a):
        pass

    def do_GET(self):  # noqa: N802
        type(self).hits.append(self.path)
        if self.path == "/health":
            body = {"status": "healthy", "tenantId": "sanocea", "dbPath": "/opt/x/seo.sqlite"}
        elif self.path == "/scheduler":
            body = {"loopRunning": True, "lastHeartbeat": {"owner": "host1:4242", "tickAt": "2026-10-01T03:28:30.636Z"}, "provenance": "[OBSERVED: TEST]"}
        elif self.path in VIEWS.values():
            body = {"path": self.path, "provenance": "[OBSERVED: TEST]"}
        else:
            body = {"MUTATED": True}
        raw = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(raw)


@pytest.fixture()
def stack():
    from sanocea.apps.api.app import create_app
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore

    _Worker.hits = []
    srv = HTTPServer(("127.0.0.1", 0), _Worker)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    old = os.environ.get("SEO_WORKER_URL")
    os.environ["SEO_WORKER_URL"] = f"http://127.0.0.1:{srv.server_port}"
    store = PostgresStore(PG_DSN, credential_provider=build_production_credential_provider(PG_DSN))
    client = TestClient(create_app(store))
    yield store, client
    srv.shutdown()
    if old is None:
        os.environ.pop("SEO_WORKER_URL", None)
    else:
        os.environ["SEO_WORKER_URL"] = old


def _lease(client) -> dict:
    r = client.post("/demo/sessions")
    assert r.status_code == 200, r.text
    return r.json()


def _bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def test_a_really_leased_demo_session_reads_every_view_with_worker_timestamps_and_redaction(stack):
    _, client = stack
    sess = _lease(client)
    r = client.get(ROUTE, headers=_bearer(sess["api_key"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["views"]) == set(VIEWS)
    assert body["views"]["scheduler"]["updated_at"] == "2026-10-01T03:28:30.636Z"  # the worker's own timestamp
    assert body["views"]["scheduler"]["data"]["provenance"] == "[OBSERVED: TEST]"  # label untouched
    raw = json.dumps(body)
    for leaked in ("host1", "4242", "/opt/x", ".sqlite", "dbPath", "owner"):
        assert leaked not in raw, leaked
    assert not any(p.startswith(("/sync", "/run")) for p in _Worker.hits)


def test_an_expired_demo_session_is_refused(stack):
    import psycopg2

    _, client = stack
    sess = _lease(client)
    assert client.get(ROUTE, headers=_bearer(sess["api_key"])).status_code == 200
    with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("UPDATE demo_ephemeral_sessions SET expires_at = now() - interval '1 minute' WHERE merchant_id = %s", (sess["merchant_id"],))
    r = client.get(ROUTE, headers=_bearer(sess["api_key"]))
    assert r.status_code == 403 and r.json() == {"detail": "demo session required"}


def test_a_non_demo_key_is_refused_even_if_valid(stack):
    store, client = stack
    sess = _lease(client)
    # a real merchant-scoped operator key for a merchant that is NOT a demo session
    from sanocea.packages.prospect_demo import PROSPECT_TENANTS

    template = next(iter(PROSPECT_TENANTS))
    _, key = store.create_api_key(merchant_id=template, role="operator", label="not-a-session")
    r = client.get(ROUTE, headers=_bearer(key))
    assert r.status_code == 403 and r.json() == {"detail": "demo session required"}
    assert sess["merchant_id"] != template


def test_no_key_and_garbage_key_are_401(stack):
    _, client = stack
    assert client.get(ROUTE).status_code == 401
    assert client.get(ROUTE, headers=_bearer("sk_not_a_real_key")).status_code == 401
    assert _Worker.hits == []


def test_the_route_writes_nothing(stack):
    import psycopg2

    _, client = stack
    sess = _lease(client)
    def counts():
        with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
            cur.execute("SELECT (SELECT count(*) FROM api_keys), (SELECT count(*) FROM demo_ephemeral_sessions), (SELECT count(*) FROM merchants)")
            return cur.fetchone()
    before = counts()
    for _ in range(3):
        assert client.get(ROUTE, headers=_bearer(sess["api_key"])).status_code == 200
    assert counts() == before
