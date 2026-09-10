from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

from sanocea.connectors.woocommerce.oauth1 import sign_request

"""Multi-platform connector hardening, closure item 1: regression coverage for the OAuth1 signature
base-string bug found against the real local WooCommerce instance (poll_changes's modified_after cursor
returned 401 'Invalid signature'). Root cause was generic - a missing second percent-encoding pass over
the whole parameter string (RFC 5849 3.4.1.1), not specific to colons - so this test signs and sends a
real request for EVERY reserved character that needs percent-encoding, not just ':'. Runs against the
real local WooCommerce instance (infra/woocommerce-dev); skipped automatically when it isn't reachable,
exactly like every other real-infra test in this suite.
"""

WC_BASE_URL = os.environ.get("SANOCEA_WOOCOMMERCE_BASE_URL", "http://localhost:8890")
WC_CONSUMER_KEY = os.environ.get("SANOCEA_WOOCOMMERCE_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.environ.get("SANOCEA_WOOCOMMERCE_CONSUMER_SECRET")

pytestmark = pytest.mark.skipif(
    not (WC_CONSUMER_KEY and WC_CONSUMER_SECRET),
    reason="requires a real local WooCommerce instance - set SANOCEA_WOOCOMMERCE_CONSUMER_KEY/_SECRET (see infra/woocommerce-dev)",
)


def _signed_get(value: str) -> int:
    url = f"{WC_BASE_URL}/wp-json/wc/v3/products"
    signed = sign_request("GET", url, {"search": value}, WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
    full_url = f"{url}?{urllib.parse.urlencode(signed)}"
    try:
        with urllib.request.urlopen(full_url, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


@pytest.mark.parametrize(
    "value",
    [
        "plain",
        "x:y",  # the originally-found colon case (ISO8601 timestamps, e.g. poll_changes's modified_after)
        "2024-01-01T00:00:00",  # a real modified_after-shaped value
        "a b",  # space
        "a+b",  # plus
        "a/b",  # slash
        "a@b",  # at
        "a?b",  # question mark
        "a=b",  # equals
        "a&b",  # ampersand
        "a#b",  # hash
        "a'b",  # single quote
        'a"b',  # double quote
    ],
)
def test_signed_request_succeeds_for_every_reserved_character_in_a_query_value(value: str):
    status = _signed_get(value)
    assert status == 200, f"OAuth1 signature rejected a request with value={value!r} (status={status})"
