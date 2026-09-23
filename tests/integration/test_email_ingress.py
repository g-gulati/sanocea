from __future__ import annotations

import base64
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SANOCEA_PG_DSN", "postgresql://sanocea:sanocea@127.0.0.1:55432/sanocea_phase05")
PG_DSN = os.environ["SANOCEA_PG_DSN"]
if not os.environ.get("SANOCEA_CRED_MASTER_KEY_CURRENT"):
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(b"\x2a" * 32).decode()
os.environ.setdefault("SANOCEA_DEMO_TRUSTED_SENDERS", "bigbrandloot@gmail.com")

from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.skipif(not os.environ.get("SANOCEA_PG_DSN"), reason="Requires a real Postgres DSN")

FIXTURE = "tests/fixtures/prospect_demo_email/Ajanta_New_Product_Master.xlsx"


@pytest.fixture(scope="module")
def stack():
    from sanocea.apps.api.app import create_app
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore
    from sanocea.packages.prospect_demo import reset_prospect_tenant

    reset_prospect_tenant("prospect_ajanta_soya", dsn=PG_DSN)
    cred_provider = build_production_credential_provider(PG_DSN)
    store = PostgresStore(PG_DSN, credential_provider=cred_provider)
    app = create_app(store)
    client = TestClient(app)
    _, service_key = store.create_api_key(merchant_id=None, role="service", label="test-email-ingress-service")
    with open(FIXTURE, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    return client, service_key, content_b64


def _payload(message_id, content_b64, **overrides):
    p = {
        "message_id": message_id,
        "sender": "bigbrandloot@gmail.com",
        "to_addresses": ["bigbrandloot+demo-ajanta@gmail.com"],
        "subject": "New Product File - Ajanta",
        "filename": "Ajanta_New_Product_Master.xlsx",
        "content_base64": content_b64,
    }
    p.update(overrides)
    return p


def test_real_email_ingestion_end_to_end(stack):
    client, service_key, content_b64 = stack
    resp = client.post(
        "/demo/email-ingest", headers={"Authorization": f"Bearer {service_key}"},
        json=_payload("it-msg-001", content_b64),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["merchant_id"] == "prospect_ajanta_soya"
    assert body["idempotent_replay"] is False
    assert body["records_received"] > 0
    assert body["records_ready"] + body["records_requiring_attention"] == body["records_received"]
    assert body["elapsed_seconds"] > 0
    # Real timestamps, not fabricated - each stage strictly monotonic.
    stages = [body["email_received_at"], body["ingestion_started_at"], body["ingestion_completed_at"],
              body["validation_completed_at"], body["workflow_completed_at"]]
    assert stages == sorted(stages)


def test_duplicate_email_replay_does_not_duplicate_work(stack):
    client, service_key, content_b64 = stack
    first = client.post("/demo/email-ingest", headers={"Authorization": f"Bearer {service_key}"}, json=_payload("it-msg-002", content_b64)).json()
    second = client.post("/demo/email-ingest", headers={"Authorization": f"Bearer {service_key}"}, json=_payload("it-msg-002", content_b64)).json()
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert second["records_received"] == first["records_received"]
    assert second["run_id"] == first["run_id"]


def test_revised_attachment_same_message_id_is_reprocessed(stack):
    """A genuinely revised attachment under the SAME message_id must NOT be silently treated as a
    duplicate - the content hash differs from the original, so idempotency (keyed on message_id +
    content hash together) correctly treats it as a new, distinct run rather than a replay."""
    client, service_key, content_b64 = stack
    original = client.post("/demo/email-ingest", headers={"Authorization": f"Bearer {service_key}"}, json=_payload("it-msg-003", content_b64)).json()
    # A real edit: drop the last real product row's worth of bytes isn't safe to hand-craft, so instead
    # reuse a DIFFERENT real fixture file under the SAME message_id - still a "revised attachment",
    # still a different content hash, and still a valid, safely-parseable xlsx (unlike appending a
    # trailing byte, which Python's zipfile tolerates and would not actually change the parsed content).
    with open("tests/fixtures/prospect_demo_email/HealthVitals_New_Product_Master.xlsx", "rb") as f:
        revised_b64 = base64.b64encode(f.read()).decode()
    resp = client.post("/demo/email-ingest", headers={"Authorization": f"Bearer {service_key}"}, json=_payload("it-msg-003", revised_b64))
    revised = resp.json()
    assert resp.status_code == 200
    assert revised["idempotent_replay"] is False  # genuinely reprocessed, not deduped to the original's cached result
    assert revised["run_id"] != original["run_id"]


@pytest.mark.parametrize("to_addresses,sender,expected_status", [
    (["bigbrandloot+demo-unknown@gmail.com"], "bigbrandloot@gmail.com", 422),
    (["someone@example.com"], "bigbrandloot@gmail.com", 422),
    (["bigbrandloot+demo-ajanta@gmail.com"], "attacker@evil.com", 422),
    (["bigbrandloot+demo-ajanta@gmail.com", "bigbrandloot+demo-carzex@gmail.com"], "bigbrandloot@gmail.com", 422),
    (["bigbrandloot+demo-ajanta@gmail.com"], "bigbrandloot@gmail.com", 200),
])
def test_routing_fail_closed(stack, to_addresses, sender, expected_status):
    client, service_key, content_b64 = stack
    resp = client.post(
        "/demo/email-ingest", headers={"Authorization": f"Bearer {service_key}"},
        json=_payload(f"it-routing-{hash((tuple(to_addresses), sender))}", content_b64, to_addresses=to_addresses, sender=sender),
    )
    assert resp.status_code == expected_status


@pytest.mark.parametrize("filename,content,reason", [
    ("malware.exe", b"MZ\x90\x00fake", "unsupported attachment type"),
    ("corrupt.xlsx", b"not a real zip", "not a real Office Open XML"),
])
def test_attachment_safety_rejections(stack, filename, content, reason):
    client, service_key, _ = stack
    payload = _payload(f"it-sec-{filename}", base64.b64encode(content).decode(), filename=filename)
    resp = client.post("/demo/email-ingest", headers={"Authorization": f"Bearer {service_key}"}, json=payload)
    assert resp.status_code == 422
    assert reason in resp.json()["detail"]


def test_operator_key_cannot_call_service_only_endpoint(stack):
    client, _, content_b64 = stack
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider
    from sanocea.packages.domain_contract.postgres_store import PostgresStore

    store = PostgresStore(PG_DSN, credential_provider=build_production_credential_provider(PG_DSN))
    _, operator_key = store.create_api_key(merchant_id="prospect_ajanta_soya", role="operator", label="test-should-fail")
    resp = client.post("/demo/email-ingest", headers={"Authorization": f"Bearer {operator_key}"}, json=_payload("it-msg-004", content_b64))
    assert resp.status_code == 403
