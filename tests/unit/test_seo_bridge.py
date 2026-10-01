"""SEO bridge: GET /demo/seo/overview, authorized by the existing demo-session credential only. Sanocea's SEO tenant is an
internal tenant, not a merchant, so nothing here may create or require a merchant, config, channel or credential.

Runs against a REAL local HTTP server acting as the SEO worker (no mocking of urllib), and the real FastAPI app with the
in-memory store (the one demo_ephemeral_sessions lookup is stood in for by a fixture; the Postgres-backed version is
tests/integration/test_demo_seo_overview.py)."""

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
    rich = False

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):  # noqa: N802
        type(self).hits.append(self.path)
        if self.path in type(self).fail_paths:
            self.send_response(500); self.end_headers(); return
        if self.path == "/health":
            body = {"status": "healthy", "tenantId": WORKER_TENANT}
        elif self.path == "/scheduler" and type(self).rich:
            body = {"loopRunning": True, "lastHeartbeat": {"owner": "vmi123456:803425", "tickAt": "2026-10-01T03:28:30.636Z"},
                    "note": "db at /opt/sanocea/repo/packages/seo-stack/data/x.sqlite", "dbPath": "/opt/sanocea/x", "provenance": "[INFERRED]"}
        elif self.path == "/rank-movement" and type(self).rich:
            body = {"site": {"trajectories": [{"lowSample": True, "lastFetchedAt": "2026-09-30T15:31:57.179Z", "provenance": "[ESTIMATED]"},
                                              {"lowSample": False, "lastFetchedAt": "2026-09-29T00:00:00Z"}]}, "pages": {"trajectories": []}}
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
    _FakeWorker.rich = False
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


# ---- the retired surfaces are really gone -----------------------------------------------------------------------------

def test_retired_ui_and_internal_seo_route_no_longer_exist(stack, worker):
    _, client, keys = stack
    for key in keys.values():
        for path in ("/internal/seo/overview", "/ui", "/ui/anything", "/static/app.js", "/static/seo.js", "/merchants/sanocea/seo/overview"):
            assert client.get(path, headers=_h(key)).status_code in (404, 405), path
    assert worker.hits == []


def test_api_root_redirects_to_the_public_demo_not_a_ui(stack):
    _, client, _ = stack
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307) and r.headers["location"].endswith("/demo.html")


# ---- no production-data writes ---------------------------------------------------------------------------------------

def test_the_route_creates_no_merchant_credential_or_any_stored_record(stack, worker, demo_sessions):
    store, client, keys = stack
    before = (len(store.list_all_merchants()), len(store._api_keys), json.dumps(sorted(store._api_keys.values(), key=lambda r: r["id"]), default=str))
    for cls in ("service", "internal", "single", "demo_session"):
        client.get(DEMO_ROUTE, headers=_h(keys[cls]))
    client.get(DEMO_ROUTE)
    after = (len(store.list_all_merchants()), len(store._api_keys), json.dumps(sorted(store._api_keys.values(), key=lambda r: r["id"]), default=str))
    assert before == after
    assert "sanocea" not in [m.id for m in store.list_all_merchants()]


# ---- allowlist / truth / failure handling ------------------------------------------------------------------------------

def test_only_allowlisted_persisted_read_paths_are_ever_requested_never_mutating_endpoints(stack, worker, demo_sessions):
    _, client, keys = stack
    client.get(DEMO_ROUTE, headers=_h(keys["demo_session"]))
    assert set(worker.hits) <= set(VIEWS.values()) | {"/health"}
    for forbidden in ("/sync-gsc", "/run-tier2", "/sync-rankcommand"):
        assert forbidden not in worker.hits and forbidden not in VIEWS.values()
    assert all(not p.startswith(("/sync", "/run")) for p in VIEWS.values())


def test_no_client_supplied_path_can_reach_the_worker(stack, worker, demo_sessions):
    _, client, keys = stack
    for probe in ("/demo/seo/sync-gsc", "/demo/seo/..%2Fsync-gsc", "/demo/seo/overview/../../sync-gsc", "/demo/seo/overview?path=/sync-gsc"):
        client.get(probe, headers=_h(keys["demo_session"]))
    assert not any(p.startswith(("/sync", "/run")) for p in worker.hits)


def test_one_failing_view_is_unavailable_without_defaults_and_others_unaffected(stack, worker, demo_sessions):
    _, client, keys = stack
    worker.fail_paths = {"/authority"}
    body = client.get(DEMO_ROUTE, headers=_h(keys["demo_session"])).json()
    assert body["views"]["authority"]["ok"] is False and "500" in body["views"]["authority"]["error"]
    assert "data" not in body["views"]["authority"] and body["views"]["authority"]["updated_at"] is None
    assert body["views"]["scheduler"]["ok"] is True


def test_worker_that_does_not_report_a_tenant_is_treated_as_unavailable(stack, worker, demo_sessions, monkeypatch):
    _, client, keys = stack
    monkeypatch.setattr(SeoBridge, "_get", lambda self, path: {"status": "healthy"} if path == "/health" else {})
    assert client.get(DEMO_ROUTE, headers=_h(keys["demo_session"])).status_code == 503


def test_view_error_text_never_contains_the_worker_url(stack, worker):
    bridge = SeoBridge(worker_url="http://127.0.0.1:9")
    with pytest.raises(Exception) as ei:
        bridge._get("/health")
    assert "127.0.0.1" not in str(ei.value)


def test_bridge_defaults_to_the_localhost_worker():
    assert SeoBridge().worker_url == "http://127.0.0.1:8089"


def test_the_internal_operator_dependency_is_gone():
    import sanocea.packages.seo_bridge as bridge_pkg
    assert not hasattr(bridge_pkg, "require_internal_operator")


# ==== GET /demo/seo/overview: the ONE bridge /demo.html reads, authorized by the existing demo-session key ===========

DEMO_ROUTE = "/demo/seo/overview"
ACTIVE_SESSION = "prospect_premium_basket_sess_deadbeef"


@pytest.fixture
def demo_sessions(monkeypatch):
    """The in-memory store has no demo_ephemeral_sessions table; stand in for that single read-only lookup."""
    import sanocea.packages.seo_bridge.client as client_mod
    active = {ACTIVE_SESSION}
    monkeypatch.setattr(client_mod, "_is_active_demo_session", lambda store, merchant_id: merchant_id in active)
    return active


def test_demo_route_no_or_bad_key_is_401_and_never_reaches_the_worker(stack, worker, demo_sessions):
    _, client, _ = stack
    for headers in ({}, {"Authorization": "Basic abc"}, _h("not-a-key")):
        assert client.get(DEMO_ROUTE, headers=headers).status_code == 401
    assert worker.hits == []


def test_active_demo_session_key_gets_every_view_including_signals(stack, worker, demo_sessions):
    _, client, keys = stack
    r = client.get(DEMO_ROUTE, headers=_h(keys["demo_session"]))
    assert r.status_code == 200
    body = r.json()
    assert set(body["views"]) == set(VIEWS) and "signals" in body["views"] and VIEWS["signals"] == "/search-signals"
    assert all(v["ok"] for v in body["views"].values())
    assert body["views"]["signals"]["data"]["path"] == "/search-signals"


@pytest.mark.parametrize("cls", ["service", "internal", "single", "single_named_sanocea"])
def test_every_non_demo_key_is_403_generic_and_never_reaches_the_worker(stack, worker, demo_sessions, cls):
    _, client, keys = stack
    r = client.get(DEMO_ROUTE, headers=_h(keys[cls]))
    assert r.status_code == 403
    assert r.json() == {"detail": "demo session required"}
    assert worker.hits == []


def test_expired_or_unknown_demo_session_is_403(stack, worker, demo_sessions):
    _, client, keys = stack
    demo_sessions.clear()  # session expired / reaped
    r = client.get(DEMO_ROUTE, headers=_h(keys["demo_session"]))
    assert r.status_code == 403 and r.json() == {"detail": "demo session required"}
    assert worker.hits == []


def test_in_memory_store_without_a_dsn_fails_closed(stack, worker):
    _, client, keys = stack  # no demo_sessions patch: real _is_active_demo_session on a store with no dsn
    assert client.get(DEMO_ROUTE, headers=_h(keys["demo_session"])).status_code == 403


def test_demo_refusals_disclose_nothing(stack, worker, demo_sessions):
    _, client, keys = stack
    for headers in ({}, _h("bad"), _h(keys["single"])):
        text = client.get(DEMO_ROUTE, headers=headers).text.lower()
        for leaked in ("127.0.0.1", "8089", "worker", "tenant", "sanocea", "internal"):
            assert leaked not in text, text


def test_worker_internal_fields_are_redacted_and_provenance_and_timestamps_pass_through_exactly(stack, worker, demo_sessions):
    _, client, keys = stack
    worker.rich = True
    body = client.get(DEMO_ROUTE, headers=_h(keys["demo_session"])).json()
    raw = json.dumps(body)
    for leaked in ("vmi123456", "803425", "/opt/sanocea", "dbPath", "owner", ".sqlite"):
        assert leaked not in raw, leaked
    sched = body["views"]["scheduler"]
    assert sched["data"]["provenance"] == "[INFERRED]"          # worker labels are never remapped
    assert sched["data"]["lastHeartbeat"]["tickAt"] == "2026-10-01T03:28:30.636Z"
    assert sched["updated_at"] == "2026-10-01T03:28:30.636Z"     # the worker's own timestamp, not ours
    rm = body["views"]["rank_movement_gsc"]
    assert rm["data"]["site"]["trajectories"][0]["lowSample"] is True and rm["data"]["site"]["trajectories"][0]["provenance"] == "[ESTIMATED]"
    assert rm["updated_at"] == "2026-09-30T15:31:57.179Z"        # latest worker-reported fetch time


def test_view_with_no_worker_timestamp_reports_none_never_a_made_up_time(stack, worker, demo_sessions):
    _, client, keys = stack
    body = client.get(DEMO_ROUTE, headers=_h(keys["demo_session"])).json()
    assert body["views"]["serp_rank_movement"]["updated_at"] is None
    assert body["views"]["bing"]["updated_at"] is None


def test_demo_route_is_read_only_and_requests_only_allowlisted_paths(stack, worker, demo_sessions):
    store, client, keys = stack
    before = (len(store.list_all_merchants()), len(store._api_keys))
    client.get(DEMO_ROUTE, headers=_h(keys["demo_session"]))
    assert (len(store.list_all_merchants()), len(store._api_keys)) == before
    assert set(worker.hits) <= set(VIEWS.values()) | {"/health"}
    assert not any(p.startswith(("/sync", "/run")) for p in worker.hits)


def test_demo_unreachable_worker_is_generic_503(stack, demo_sessions):
    _, client, keys = stack
    os.environ["SEO_WORKER_URL"] = "http://127.0.0.1:9"
    try:
        r = client.get(DEMO_ROUTE, headers=_h(keys["demo_session"]))
    finally:
        os.environ.pop("SEO_WORKER_URL", None)
    assert r.status_code == 503 and r.json() == {"detail": "SEO worker unavailable"} and "127.0.0.1" not in r.text


def test_redact_unit():
    from sanocea.packages.seo_bridge import redact
    out = redact({"owner": "h:1", "a": [{"dbPath": "/x", "k": "ok [OBSERVED]"}], "s": "at /opt/sanocea/z/y.sqlite now", "n": 3, "u": "https://a.b/c", "h": "vmi33:803425", "e": "BING_WEBMASTER_API_KEY is not configured", "p": "[OBSERVED: COMMON CRAWL DOMAIN REFERENCE GRAPH]"})
    assert out == {"e": "a required setting is not configured", "p": "[OBSERVED: COMMON CRAWL DOMAIN REFERENCE GRAPH]", "a": [{"k": "ok [OBSERVED]"}], "s": "at <redacted> now", "n": 3, "u": "https://a.b/c", "h": "<redacted>"}
