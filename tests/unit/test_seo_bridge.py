"""SEO bridge: auth, tenant isolation, allowlist and truth pass-through, against a REAL local HTTP server acting as the
SEO worker (no mocking of urllib). Same in-memory-store pattern as tests/unit/test_phase45_api_integration.py."""

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


class _FakeWorker(BaseHTTPRequestHandler):
    hits: list[str] = []
    fail_paths: set[str] = set()
    tenant = WORKER_TENANT

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):  # noqa: N802
        type(self).hits.append(self.path)
        if self.path in type(self).fail_paths:
            self.send_response(500); self.end_headers(); return
        if self.path == "/health":
            body = {"status": "healthy", "tenantId": type(self).tenant}
        elif self.path in VIEWS.values():
            body = {"marker": SECRET_MARKER, "path": self.path, "provenance": "[OBSERVED: TEST]"}
        else:
            # any mutating / unknown worker endpoint the bridge must never call
            body = {"MUTATED": True, "path": self.path}
        raw = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(raw)


@pytest.fixture
def worker():
    _FakeWorker.hits = []
    _FakeWorker.fail_paths = set()
    _FakeWorker.tenant = WORKER_TENANT
    srv = HTTPServer(("127.0.0.1", 0), _FakeWorker)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
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
    _, service_key = store.create_api_key(merchant_id=None, role="service", label="svc")
    _, sanocea_key = store.create_api_key(merchant_id="sanocea", role="operator", label="sanocea-op")
    _, other_key = store.create_api_key(merchant_id="mer_other", role="operator", label="other-op")
    return client, {"service": service_key, "sanocea": sanocea_key, "other": other_key}


def _h(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def test_requires_authentication(stack, worker):
    client, _ = stack
    assert client.get("/merchants/sanocea/seo/overview").status_code == 401
    assert client.get("/merchants/sanocea/seo/overview", headers=_h("not-a-key")).status_code == 401
    assert worker.hits == [], "unauthenticated requests must never reach the worker"


def test_matching_tenant_operator_gets_every_allowlisted_view_unmodified(stack, worker):
    client, keys = stack
    r = client.get("/merchants/sanocea/seo/overview", headers=_h(keys["sanocea"]))
    assert r.status_code == 200
    body = r.json()
    assert body["monitored"] is True
    assert set(body["views"]) == set(VIEWS)
    for name, path in VIEWS.items():
        assert body["views"][name] == {"ok": True, "data": {"marker": SECRET_MARKER, "path": path, "provenance": "[OBSERVED: TEST]"}}
    assert body["fetched_at"]


def test_tenant_isolation_operator_of_another_merchant_cannot_read_sanocea_seo(stack, worker):
    client, keys = stack
    r = client.get("/merchants/sanocea/seo/overview", headers=_h(keys["other"]))
    assert r.status_code == 403
    assert SECRET_MARKER not in r.text
    assert worker.hits == [], "a forbidden caller must not even trigger a worker request"


def test_tenant_isolation_other_merchant_own_path_gets_not_monitored_and_no_data(stack, worker):
    client, keys = stack
    r = client.get("/merchants/mer_other/seo/overview", headers=_h(keys["other"]))
    assert r.status_code == 200
    body = r.json()
    assert body == {"monitored": False, "merchant_id": "mer_other", "reason": "No SEO monitor is configured for this tenant."}
    assert SECRET_MARKER not in r.text
    assert WORKER_TENANT not in r.text, "the worker's tenant id must not leak to a non-matching tenant"
    assert worker.hits == ["/health"], "only the tenant check may reach the worker for a non-matching tenant"


def test_service_key_cannot_be_used_to_smuggle_the_wrong_tenant(stack, worker):
    client, keys = stack
    r = client.get("/merchants/mer_other/seo/overview", headers=_h(keys["service"]))
    assert r.status_code == 200 and r.json()["monitored"] is False
    assert SECRET_MARKER not in r.text


def test_only_allowlisted_persisted_read_paths_are_ever_requested_never_mutating_endpoints(stack, worker):
    client, keys = stack
    client.get("/merchants/sanocea/seo/overview", headers=_h(keys["sanocea"]))
    allowed = set(VIEWS.values()) | {"/health"}
    assert set(worker.hits) <= allowed
    for forbidden in ("/sync-gsc", "/run-tier2", "/sync-rankcommand"):
        assert forbidden not in worker.hits
        assert forbidden not in VIEWS.values()
    assert all(not p.startswith(("/sync", "/run")) for p in VIEWS.values())


def test_no_client_supplied_path_can_reach_the_worker(stack, worker):
    client, keys = stack
    for probe in ("/merchants/sanocea/seo/sync-gsc", "/merchants/sanocea/seo/..%2Fsync-gsc", "/merchants/sanocea/seo/overview/../../sync-gsc"):
        client.get(probe, headers=_h(keys["sanocea"]))
    assert not any(p.startswith(("/sync", "/run")) for p in worker.hits)


def test_one_failing_view_is_reported_unavailable_others_unaffected(stack, worker):
    client, keys = stack
    worker.fail_paths = {"/authority"}
    body = client.get("/merchants/sanocea/seo/overview", headers=_h(keys["sanocea"])).json()
    assert body["views"]["authority"]["ok"] is False
    assert "500" in body["views"]["authority"]["error"]
    assert "data" not in body["views"]["authority"], "a failed view must not carry defaulted data"
    assert body["views"]["scheduler"]["ok"] is True


def test_unreachable_worker_is_503_not_fabricated_data(stack):
    client, keys = stack
    os.environ["SEO_WORKER_URL"] = "http://127.0.0.1:9"  # nothing listens here
    try:
        r = client.get("/merchants/sanocea/seo/overview", headers=_h(keys["sanocea"]))
    finally:
        os.environ.pop("SEO_WORKER_URL", None)
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"].lower()


def test_bridge_unit_defaults_to_localhost_worker():
    assert SeoBridge().worker_url == "http://127.0.0.1:8089"
