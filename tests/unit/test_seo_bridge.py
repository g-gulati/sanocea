"""SEO bridge (Option A): authorization by KEY CLASS on GET /internal/seo/overview. Sanocea's SEO tenant is an internal
tenant, not a merchant, so nothing here may create or require a merchant, config, channel or credential.

Runs against a REAL local HTTP server acting as the SEO worker (no mocking of urllib), and the real FastAPI app with the
in-memory store, same pattern as tests/unit/test_phase45_api_integration.py."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ.setdefault("SANOCEA_USE_IN_MEMORY_STORE", "1")

import pytest
from fastapi.testclient import TestClient

from sanocea.apps.api.app import create_app
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.seo_bridge import VIEWS, SeoBridge

WORKER_TENANT = "sanocea"
SECRET_MARKER = "SANOCEA-ONLY-SEO-DATA-7f3a"
ROUTE = "/internal/seo/overview"


class _FakeWorker(BaseHTTPRequestHandler):
    hits: list[str] = []
    fail_paths: set[str] = set()

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):  # noqa: N802
        type(self).hits.append(self.path)
        if self.path in type(self).fail_paths:
            self.send_response(500); self.end_headers(); return
        if self.path == "/health":
            body = {"status": "healthy", "tenantId": WORKER_TENANT}
        elif self.path in VIEWS.values():
            body = {"marker": SECRET_MARKER, "path": self.path, "provenance": "[OBSERVED: TEST]"}
        else:
            body = {"MUTATED": True, "path": self.path}  # any mutating/unknown endpoint the bridge must never call
        raw = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(raw)


@pytest.fixture
def worker():
    _FakeWorker.hits = []
    _FakeWorker.fail_paths = set()
    srv = HTTPServer(("127.0.0.1", 0), _FakeWorker)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    old = os.environ.get("SEO_WORKER_URL")
    os.environ["SEO_WORKER_URL"] = f"http://127.0.0.1:{srv.server_port}"
    yield _FakeWorker
    srv.shutdown()
    if old is None:
        os.environ.pop("SEO_WORKER_URL", None)
    else:
        os.environ["SEO_WORKER_URL"] = old


@pytest.fixture
def stack():
    store = Phase0Store()
    client = TestClient(create_app(store))
    keys = {
        "service": store.create_api_key(merchant_id=None, role="service", label="svc")[1],
        "internal": store.create_api_key(merchant_id=None, role="operator", label="internal", allowed_merchants=["mer_a", "mer_b"])[1],
        # single-merchant keys: an ordinary operator, one literally scoped to a merchant named "sanocea", and a demo-session-style key
        "single": store.create_api_key(merchant_id="mer_a", role="operator", label="single")[1],
        "single_named_sanocea": store.create_api_key(merchant_id="sanocea", role="operator", label="single-sanocea")[1],
        "demo_session": store.create_api_key(merchant_id="prospect_premium_basket_sess_deadbeef", role="operator", label="demo-session")[1],
    }
    return store, client, keys


def _h(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# ---- authorization by key class ------------------------------------------------------------------------------------

def test_no_key_and_bad_key_are_401_and_never_reach_the_worker(stack, worker):
    _, client, _ = stack
    assert client.get(ROUTE).status_code == 401
    assert client.get(ROUTE, headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.get(ROUTE, headers=_h("not-a-key")).status_code == 401
    assert worker.hits == []


@pytest.mark.parametrize("cls", ["service", "internal"])
def test_service_and_internal_operator_keys_get_every_allowlisted_view_unmodified(stack, worker, cls):
    _, client, keys = stack
    r = client.get(ROUTE, headers=_h(keys[cls]))
    assert r.status_code == 200
    body = r.json()
    assert body["monitored"] is True
    assert body["tenant_id"] == WORKER_TENANT
    assert set(body["views"]) == set(VIEWS)
    for name, path in VIEWS.items():
        assert body["views"][name] == {"ok": True, "data": {"marker": SECRET_MARKER, "path": path, "provenance": "[OBSERVED: TEST]"}}
    assert "merchant_id" not in body


@pytest.mark.parametrize("cls", ["single", "single_named_sanocea", "demo_session"])
def test_every_single_merchant_key_is_403_even_one_scoped_to_a_merchant_called_sanocea(stack, worker, cls):
    _, client, keys = stack
    r = client.get(ROUTE, headers=_h(keys[cls]))
    assert r.status_code == 403
    assert r.json() == {"detail": "internal operator or service credential required"}
    assert SECRET_MARKER not in r.text
    assert worker.hits == [], "a refused caller must never trigger a worker request"


def test_refusals_disclose_nothing_about_tenant_worker_or_routes(stack, worker):
    _, client, keys = stack
    for headers in (None, _h("bad"), _h(keys["single"])):
        r = client.get(ROUTE, headers=headers or {})
        assert r.status_code in (401, 403)
        text = r.text.lower()
        for leaked in ("sanocea", "127.0.0.1", "8089", "worker", "tenant", "merchant", "seo"):
            assert leaked not in text, f"{leaked!r} leaked in {r.status_code} body: {r.text}"


def test_old_merchant_scoped_route_no_longer_exists(stack, worker):
    _, client, keys = stack
    for key in keys.values():
        assert client.get("/merchants/sanocea/seo/overview", headers=_h(key)).status_code in (404, 405)
    assert worker.hits == []


# ---- no production-data writes ---------------------------------------------------------------------------------------

def test_the_route_creates_no_merchant_credential_or_any_stored_record(stack, worker):
    store, client, keys = stack
    before = (len(store.list_all_merchants()), len(store._api_keys), json.dumps(sorted(store._api_keys.values(), key=lambda r: r["id"]), default=str))
    for cls in ("service", "internal", "single", "demo_session"):
        client.get(ROUTE, headers=_h(keys[cls]))
    client.get(ROUTE)
    after = (len(store.list_all_merchants()), len(store._api_keys), json.dumps(sorted(store._api_keys.values(), key=lambda r: r["id"]), default=str))
    assert before == after
    assert "sanocea" not in [m.id for m in store.list_all_merchants()]


# ---- allowlist / truth / failure handling ------------------------------------------------------------------------------

def test_only_allowlisted_persisted_read_paths_are_ever_requested_never_mutating_endpoints(stack, worker):
    _, client, keys = stack
    client.get(ROUTE, headers=_h(keys["internal"]))
    assert set(worker.hits) <= set(VIEWS.values()) | {"/health"}
    for forbidden in ("/sync-gsc", "/run-tier2", "/sync-rankcommand"):
        assert forbidden not in worker.hits and forbidden not in VIEWS.values()
    assert all(not p.startswith(("/sync", "/run")) for p in VIEWS.values())


def test_no_client_supplied_path_can_reach_the_worker(stack, worker):
    _, client, keys = stack
    for probe in ("/internal/seo/sync-gsc", "/internal/seo/..%2Fsync-gsc", "/internal/seo/overview/../../sync-gsc", "/internal/seo/overview?path=/sync-gsc"):
        client.get(probe, headers=_h(keys["internal"]))
    assert not any(p.startswith(("/sync", "/run")) for p in worker.hits)


def test_one_failing_view_is_unavailable_without_defaults_and_others_unaffected(stack, worker):
    _, client, keys = stack
    worker.fail_paths = {"/authority"}
    body = client.get(ROUTE, headers=_h(keys["internal"])).json()
    assert body["views"]["authority"]["ok"] is False and "500" in body["views"]["authority"]["error"]
    assert "data" not in body["views"]["authority"]
    assert body["views"]["scheduler"]["ok"] is True


def test_unreachable_worker_is_a_generic_503_that_leaks_no_url(stack):
    _, client, keys = stack
    os.environ["SEO_WORKER_URL"] = "http://127.0.0.1:9"  # nothing listens here
    try:
        r = client.get(ROUTE, headers=_h(keys["internal"]))
    finally:
        os.environ.pop("SEO_WORKER_URL", None)
    assert r.status_code == 503
    assert r.json() == {"detail": "SEO worker unavailable"}
    assert "127.0.0.1" not in r.text


def test_worker_that_does_not_report_a_tenant_is_treated_as_unavailable(stack, worker, monkeypatch):
    _, client, keys = stack
    monkeypatch.setattr(SeoBridge, "_get", lambda self, path: {"status": "healthy"} if path == "/health" else {})
    assert client.get(ROUTE, headers=_h(keys["internal"])).status_code == 503


def test_view_error_text_never_contains_the_worker_url(stack, worker):
    bridge = SeoBridge(worker_url="http://127.0.0.1:9")
    with pytest.raises(Exception) as ei:
        bridge._get("/health")
    assert "127.0.0.1" not in str(ei.value)


def test_bridge_defaults_to_the_localhost_worker():
    assert SeoBridge().worker_url == "http://127.0.0.1:8089"
