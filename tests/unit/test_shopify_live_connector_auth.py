from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from sanocea.connectors.shopify_live import ShopifyAccessTokenManager, ShopifyAuthenticationError, ShopifyLiveConnector
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.store import Phase0Store

"""Deterministic tests for SHOPIFY CLIENT-CREDENTIALS AUTH HARDENING's connector-level behavior: the
bounded refresh-and-retry-once policy in ShopifyLiveConnector._graphql(), and - the requirement this
whole phase exists to prove - that a token refresh mid-mutation can never register as a logically new
mutation. No real network access; urllib.request.urlopen is mocked so every HTTP outcome is exact and
reproducible.
"""


def _http_error(code: int, body: dict) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url="https://cert-store.myshopify.com/x", code=code, msg="err", hdrs=None, fp=io.BytesIO(json.dumps(body).encode()))


def _ok_response(body: dict) -> MagicMock:
    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = json.dumps(body).encode()
    cm.__exit__.return_value = False
    return cm


def _token_response(token: str) -> tuple[int, dict]:
    return 200, {"access_token": token, "expires_in": 86399}


def _order_cancel_response(job_id: str) -> dict:
    return {"data": {"orderCancel": {"job": {"id": job_id}, "userErrors": []}}}


def _connector(token_calls: list[str]) -> ShopifyLiveConnector:
    def http_post(url, body):
        token = f"tok-{len(token_calls) + 1}"
        token_calls.append(token)
        return _token_response(token)

    token_manager = ShopifyAccessTokenManager(
        shop_domain="cert-store.myshopify.com", client_id="cid", client_secret="csecret", http_post=http_post,
    )
    return ShopifyLiveConnector(
        Phase0Store(), workflow=None, shop_domain="cert-store.myshopify.com",
        client_id="cid", client_secret="csecret", token_manager=token_manager,
    )


def _cancel_request(idempotency_key: str) -> MutationRequest:
    # cancel_order makes exactly ONE _graphql() call per _execute_mutation() invocation - unlike
    # update_product/create_product/publish_product, which (as of the real-store-driven upsert-by-SKU
    # fix) make a preliminary "find existing product" query before productSet. Used here so these
    # generic retry/idempotency tests exercise _graphql()'s own behavior, not product-specific call
    # counts that are free to change independently.
    return MutationRequest(
        merchant_id="mer_A", action="cancel_order", object_type="Order",
        payload={"external_order_id": "123"}, idempotency_key=idempotency_key,
    )


def test_graphql_refreshes_token_and_retries_once_on_auth_failure():
    token_calls: list[str] = []
    connector = _connector(token_calls)
    job_id = "gid://shopify/Job/1"

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [_http_error(401, {}), _ok_response(_order_cancel_response(job_id))]
        result = connector._execute_mutation(_cancel_request("key-1"))

    assert result.async_operation_id == job_id
    assert mock_urlopen.call_count == 2, "expected exactly one retry (2 total HTTP attempts)"
    assert token_calls == ["tok-1", "tok-2"], "a fresh token must be fetched for the retry, not the invalidated one reused"


def test_graphql_second_consecutive_auth_failure_stops_not_unbounded():
    token_calls: list[str] = []
    connector = _connector(token_calls)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [_http_error(401, {}), _http_error(403, {})]
        with pytest.raises(ShopifyAuthenticationError):
            connector._execute_mutation(_cancel_request("key-2"))

    assert mock_urlopen.call_count == 2, "must stop after exactly 2 attempts, never loop further on a second consecutive auth failure"


def test_graphql_non_auth_error_is_not_retried_as_auth_failure():
    """A 429/500/other 4xx must NOT trigger the token-refresh retry path at all - only 401/403 are
    treated as plausibly token-related."""
    token_calls: list[str] = []
    connector = _connector(token_calls)

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [_http_error(500, {})]
        with pytest.raises(RuntimeError):
            connector._execute_mutation(_cancel_request("key-3"))

    assert mock_urlopen.call_count == 1
    assert token_calls == ["tok-1"], "no second token fetch for a non-auth failure"


def test_mutation_idempotency_preserved_across_auth_refresh():
    """The requirement this whole phase exists to prove: a token refresh mid-mutation must never cause
    a logically new mutation. execute_mutation() is called TWICE with the SAME idempotency_key - the
    first call needs a token refresh internally (401 then success); the second call must be answered
    entirely from the idempotency cache, making ZERO further HTTP calls (proving the retried-but-
    ultimately-single first attempt is what got recorded, not two separate attempts)."""
    token_calls: list[str] = []
    connector = _connector(token_calls)
    job_id = "gid://shopify/Job/42"
    request = _cancel_request("stable-idempotency-key")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = [_http_error(401, {}), _ok_response(_order_cancel_response(job_id))]
        first_result = connector.execute_mutation(request)
        assert mock_urlopen.call_count == 2

        # Same idempotency_key, same scope - must be answered from the idempotency cache with NO further
        # HTTP calls at all, proving the refresh-and-retry above was invisible to idempotency and did not
        # register as two mutations.
        second_result = connector.execute_mutation(request)
        assert mock_urlopen.call_count == 2, "a repeated call with the same idempotency_key must not make any new HTTP calls"

    assert first_result.async_operation_id == job_id
    assert second_result.async_operation_id == job_id
    assert first_result.model_dump() == second_result.model_dump()
