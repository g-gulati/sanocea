from __future__ import annotations

import threading
import time

import pytest

from sanocea.connectors.shopify_live.auth import ShopifyAccessTokenManager, ShopifyAuthenticationError

"""Deterministic tests for the client-credentials grant token manager - no real network access, no real
Shopify store. http_post and clock are both dependency-injected fakes (the same seam
ShopifyAccessTokenManager was built with specifically so this could be tested without credentials that
do not exist yet). Covers the SHOPIFY CLIENT-CREDENTIALS AUTH HARDENING acceptance list: successful
acquisition, reuse before expiry, proactive refresh, concurrent callers, malformed response,
authentication rejection, and Client Secret/token redaction. The remaining acceptance items (refresh +
one retry, second failure stops, idempotency preserved across refresh) are connector-level behavior and
live in test_shopify_live_connector_auth.py.
"""


def _manager(http_post, *, clock=None, refresh_margin_seconds=60.0):
    return ShopifyAccessTokenManager(
        shop_domain="cert-store.myshopify.com", client_id="client-id-123", client_secret="super-secret-value",
        http_post=http_post, clock=clock or (lambda: 0.0), refresh_margin_seconds=refresh_margin_seconds,
    )


def test_successful_token_acquisition():
    calls = []

    def http_post(url, body):
        calls.append((url, body))
        return 200, {"access_token": "tok-1", "expires_in": 86399}

    manager = _manager(http_post)
    token = manager.get_token()

    assert token == "tok-1"
    assert len(calls) == 1
    assert calls[0][0] == "https://cert-store.myshopify.com/admin/oauth/access_token"
    assert b"grant_type=client_credentials" in calls[0][1]
    assert b"client_id=client-id-123" in calls[0][1]


def test_token_reused_before_expiry():
    call_count = 0
    clock_value = [0.0]

    def http_post(url, body):
        nonlocal call_count
        call_count += 1
        return 200, {"access_token": f"tok-{call_count}", "expires_in": 86399}

    manager = _manager(http_post, clock=lambda: clock_value[0])
    first = manager.get_token()
    clock_value[0] = 100.0  # far from expiry (86399s) and far from the 60s margin
    second = manager.get_token()

    assert first == second == "tok-1"
    assert call_count == 1


def test_proactive_refresh_before_exact_expiry():
    call_count = 0
    clock_value = [0.0]

    def http_post(url, body):
        nonlocal call_count
        call_count += 1
        return 200, {"access_token": f"tok-{call_count}", "expires_in": 120}

    manager = _manager(http_post, clock=lambda: clock_value[0], refresh_margin_seconds=60.0)
    first = manager.get_token()
    assert first == "tok-1"
    # expires_at = 120; margin = 60 -> "fresh" only while clock < 60. At clock=65 the token has NOT
    # actually expired yet (65 < 120) but is within the proactive-refresh margin, so a NEW fetch must
    # happen rather than waiting for the literal expiry instant.
    clock_value[0] = 65.0
    second = manager.get_token()

    assert second == "tok-2"
    assert call_count == 2


def test_concurrent_callers_do_not_each_fetch_a_token():
    call_count = 0
    call_lock = threading.Lock()

    def http_post(url, body):
        nonlocal call_count
        with call_lock:
            call_count += 1
        time.sleep(0.05)  # widen the race window so concurrent callers would overlap if unsynchronized
        return 200, {"access_token": "shared-token", "expires_in": 86399}

    manager = _manager(http_post)
    results: list[str] = []
    results_lock = threading.Lock()

    def worker():
        token = manager.get_token()
        with results_lock:
            results.append(token)

    threads = [threading.Thread(target=worker) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert call_count == 1, f"expected exactly one client-credentials fetch under concurrency, got {call_count}"
    assert results == ["shared-token"] * 12


def test_malformed_token_response_raises_and_does_not_cache():
    def http_post(url, body):
        return 200, {"access_token": "tok-1"}  # missing expires_in

    manager = _manager(http_post)
    with pytest.raises(ShopifyAuthenticationError, match="malformed"):
        manager.get_token()
    # A malformed response must not leave a poisoned/partial cache - a later successful call must still work.
    assert manager._token is None
    assert manager._expires_at is None


def test_authentication_rejection_raises():
    def http_post(url, body):
        return 401, {"error": "invalid_client"}

    manager = _manager(http_post)
    with pytest.raises(ShopifyAuthenticationError, match="HTTP 401"):
        manager.get_token()


def test_client_secret_and_token_never_appear_in_repr_or_errors():
    secret = "super-secret-value"

    def http_post_success(url, body):
        return 200, {"access_token": "tok-should-not-leak", "expires_in": 86399}

    manager = _manager(http_post_success)
    manager.get_token()
    assert secret not in repr(manager)
    assert secret not in str(manager)
    assert "tok-should-not-leak" not in repr(manager)
    assert "tok-should-not-leak" not in str(manager)

    def http_post_reject(url, body):
        return 401, {}

    rejecting_manager = _manager(http_post_reject)
    try:
        rejecting_manager.get_token()
        pytest.fail("expected ShopifyAuthenticationError")
    except ShopifyAuthenticationError as exc:
        assert secret not in str(exc)
