from __future__ import annotations

import json

import pytest

from sanocea.connectors.meesho import MeeshoConnector
from sanocea.connectors.meesho.auth import StaticSupplierCredentialsAuth
from sanocea.connectors.meesho.connector import PRODUCTION_BASE_URL, SANDBOX_BASE_URL
from sanocea.packages.connector_sdk import CapabilityUnconfirmed

# Step 9Q.4 - Meesho's business-operation contracts (catalogue, orders, fulfilment, returns,
# settlement) have NO Level 1-3 evidence anywhere reached during this step's research - only Level 5
# vendor-integration summaries describing capability EXISTENCE, never a request/response schema. Per
# the mandate's explicit instruction ("do not manufacture tests around unsupported capabilities merely
# to inflate coverage"), this suite does NOT fabricate contract tests for those - it instead proves
# (a) the one real thing this connector implements (static per-supplier-location auth), and (b) that
# every business capability is HONESTLY refused (UNCONFIRMED), never silently treated as usable.


@pytest.fixture
def sanocea_store(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    return store


def _connector(store, **auth_kwargs) -> MeeshoConnector:
    defaults = {"client_id": "client-A", "security": "sec-A", "supplier_identifier": "loc-A"}
    auth = StaticSupplierCredentialsAuth(**{**defaults, **auth_kwargs})
    return MeeshoConnector(store, None, auth=auth)


# --- auth: static credentials, no token exchange ------------------------------------------------------

def test_auth_headers_are_static_and_present_on_every_call(sanocea_store):
    connector = _connector(sanocea_store)
    first = connector.auth.auth_headers()
    second = connector.auth.auth_headers()
    assert first["merchant"] == "client-A"
    assert first["security"] == "sec-A"
    assert first["supplier_identifier"] == "loc-A"
    assert "timestamp" in first and "timestamp" in second
    # No caching/expiry concept exists - invalidate() is a documented no-op, never raises.
    connector.auth.invalidate()
    connector.auth.auth_headers()


def test_connector_health_reflects_static_auth_mode(sanocea_store):
    connector = _connector(sanocea_store)
    health = connector.connector_health()
    assert health == {"connector": "meesho", "authenticated": True, "auth_mode": "static_credentials"}
    assert "sec-A" not in json.dumps(health), "the security credential must never appear in a health report"


def test_production_and_sandbox_base_urls_are_distinct(sanocea_store):
    prod = MeeshoConnector(sanocea_store, None, auth=StaticSupplierCredentialsAuth(client_id="c", security="s", supplier_identifier="l"))
    sandbox = MeeshoConnector(sanocea_store, None, auth=StaticSupplierCredentialsAuth(client_id="c", security="s", supplier_identifier="l"), base_url=SANDBOX_BASE_URL)
    assert prod.base_url == PRODUCTION_BASE_URL
    assert sandbox.base_url == SANDBOX_BASE_URL
    assert prod.base_url != sandbox.base_url


# --- credential isolation between merchants (per-supplier-location, not per-Sanocea-app) --------------

def test_credential_isolation_between_merchants(sanocea_store):
    connector_a = _connector(sanocea_store, client_id="client-A", security="sec-A", supplier_identifier="loc-A")
    connector_b = _connector(sanocea_store, client_id="client-B", security="sec-B", supplier_identifier="loc-B")
    headers_a = connector_a.auth.auth_headers()
    headers_b = connector_b.auth.auth_headers()
    assert headers_a["merchant"] != headers_b["merchant"]
    assert headers_a["security"] != headers_b["security"]
    assert headers_a["supplier_identifier"] != headers_b["supplier_identifier"]


def test_credential_failure_has_no_recovery_path_documented_as_such(sanocea_store):
    """Disclosed limitation, not a bug: invalidate() cannot actually recover a rejected static
    credential - it stays a no-op by design (see auth.py's docstring)."""
    connector = _connector(sanocea_store)
    before = connector.auth.auth_headers()
    connector.auth.invalidate()
    after = connector.auth.auth_headers()
    assert before["merchant"] == after["merchant"] and before["security"] == after["security"]


# --- every business capability is honestly UNCONFIRMED, never silently usable --------------------------

@pytest.mark.parametrize("capability", [
    "catalogue_read", "catalogue_write", "inventory_read", "inventory_write",
    "order_ingest", "order_confirmation", "fulfilment_update", "cancellation",
    "return_refund", "settlement_ingest", "order_notifications", "fetch", "search",
])
def test_business_capability_is_unconfirmed(sanocea_store, capability):
    connector = _connector(sanocea_store)
    with pytest.raises(CapabilityUnconfirmed):
        connector.describe_capabilities().require(capability)


def test_fetch_and_search_refuse_before_touching_any_entity_type(sanocea_store):
    """fetch()/search() must refuse via the capability gate BEFORE reaching any entity-type branching -
    proves no business logic silently executes despite the UNCONFIRMED classification."""
    connector = _connector(sanocea_store)
    with pytest.raises(CapabilityUnconfirmed):
        connector.fetch("mer_A", "order", "anything")
    with pytest.raises(CapabilityUnconfirmed):
        connector.search("mer_A", "order", {})


def test_auth_is_the_only_supported_capability(sanocea_store):
    connector = _connector(sanocea_store)
    caps = connector.describe_capabilities().capabilities
    supported = {name for name, cap in caps.items() if cap.status.value == "supported"}
    assert supported == {"auth"}, "no business capability may be marked SUPPORTED without a confirmed schema"
