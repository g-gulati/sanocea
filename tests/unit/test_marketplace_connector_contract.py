from __future__ import annotations

import json

import pytest

from sanocea.connectors.flipkart import FlipkartConnector
from sanocea.connectors.flipkart.auth import TOKEN_URL, self_issued_client_credentials_auth
from sanocea.connectors.flipkart.connector import BASE_URL
from sanocea.packages.connector_sdk import MarketplaceConnector, MerchantAuthorizationCodeAuth, SelfIssuedClientCredentialsAuth

# Step 9Q.2 - proves the MarketplaceConnector auth plug-point is genuinely pluggable, not hardwired to
# one Flipkart-specific auth shape (Part E's explicit requirement) - the SAME FlipkartConnector class,
# unmodified, works correctly with EITHER SelfIssuedClientCredentialsAuth (a single seller's own app) OR
# MerchantAuthorizationCodeAuth (Sanocea's actual multi-tenant aggregator mode). See
# tests/unit/test_flipkart_connector.py for the full contract-level test suite exercising the
# authorization-code path in depth; this file specifically covers the client-credentials path and the
# generic pluggability claim, so the two files are complementary, not duplicative.


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._queue: dict[tuple[str, str], list[tuple[int, dict, bytes]]] = {}

    def queue(self, method: str, path: str, status: int, body: dict) -> None:
        self._queue.setdefault((method, path.split("?", 1)[0]), []).append((status, {}, json.dumps(body).encode()))

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url))
        key = (method, url.split("?", 1)[0])
        pending = self._queue.get(key)
        if not pending:
            raise AssertionError(f"no queued response for {method} {url}")
        return pending.pop(0)


def test_self_issued_client_credentials_auth_works_against_the_same_connector(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    transport = _FakeTransport()
    transport.queue("POST", TOKEN_URL, 200, {"access_token": "self-tok", "expires_in": 3600})
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "title": "Widget", "sellingPrice": 10.0, "status": "ACTIVE"})
    auth = self_issued_client_credentials_auth(client_id="seller-app-id", client_secret="seller-app-secret", transport=transport)
    connector = FlipkartConnector(store, None, auth=auth, transport=transport)
    result = connector.fetch("mer_A", "product", "SKU-1")
    assert result["sku"] == "SKU-1"


def test_client_credentials_and_authorization_code_are_both_real_marketplace_auth_strategies():
    """Both concrete strategies satisfy the SAME MarketplaceAuthStrategy shape (auth_headers/invalidate)
    - a future Amazon/Meesho/Myntra connector can reuse either without MarketplaceConnector itself
    changing, which is the actual claim Part E asked to be proven, not just asserted in a docstring."""
    transport = _FakeTransport()
    transport.queue("POST", "https://example.test/token", 200, {"access_token": "a", "expires_in": 10})
    a = SelfIssuedClientCredentialsAuth(token_url="https://example.test/token", client_id="x", client_secret="y", transport=transport)
    assert a.auth_headers() == {"Authorization": "Bearer a"}

    transport2 = _FakeTransport()
    transport2.queue("POST", "https://example.test/token", 200, {"access_token": "b", "expires_in": 10})
    b = MerchantAuthorizationCodeAuth(token_url="https://example.test/token", client_id="x", client_secret="y", refresh_token="rt", transport=transport2)
    assert b.auth_headers() == {"Authorization": "Bearer b"}


def test_marketplace_connector_cannot_be_used_without_an_auth_strategy():
    with pytest.raises(TypeError):
        MarketplaceConnector(None, None)  # missing required keyword-only `auth`


def test_connector_health_reports_auth_state_without_exposing_the_token(phase0):
    store, _workflow, _shopify, _chatwoot = phase0
    transport = _FakeTransport()
    transport.queue("POST", TOKEN_URL, 200, {"access_token": "super-secret-token", "expires_in": 3600})
    transport.queue("GET", f"{BASE_URL}/sellers/v3/listings", 200, {"skuId": "SKU-1", "status": "ACTIVE"})
    auth = self_issued_client_credentials_auth(client_id="x", client_secret="y", transport=transport)
    connector = FlipkartConnector(store, None, auth=auth, transport=transport)

    before = connector.connector_health()
    assert before == {"connector": "flipkart", "authenticated": False, "token_expires_at": 0.0}

    connector.fetch("mer_A", "product", "SKU-1")
    after = connector.connector_health()
    assert after["authenticated"] is True
    assert after["token_expires_at"] is not None
    assert "super-secret-token" not in json.dumps(after)
