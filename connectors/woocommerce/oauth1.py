from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse

"""WooCommerce REST API "OAuth 1.0a one-legged" request signing (RFC 5849, minus the token - only
consumer key/secret). WooCommerce REQUIRES this over plain HTTP; Basic Auth (header or query-string)
is only accepted when the store is served over HTTPS (verified empirically against a real local
WooCommerce instance while building this connector - see
docs/architecture/woocommerce-platform-independence.md). A production WooCommerce store is virtually
always HTTPS, where Basic Auth would work too, but signing this way is correct in both cases and is
WooCommerce's own documented, sanctioned method - not a workaround for a local-only limitation.

FIXED (multi-platform connector hardening, closure item 1): the signature base string was built with
only ONE percent-encoding pass. RFC 5849 3.4.1.3.2 requires the normalized parameter string to be built
first (each key/value percent-encoded, joined with LITERAL '=' and '&'), and RFC 5849 3.4.1.1 then
requires that ENTIRE parameter string to be percent-encoded AGAIN as a single unit before being
concatenated into the base string. The old code skipped this second pass - it built the parameter
string with %3D/%26 standing in for '=' and '&' (mimicking what the outer encoding of those two
characters alone would produce) and spliced it into the base string unescaped, but never re-escaped the
'%' character that a %-encoded reserved character (e.g. ':' -> '%3A') introduces. That stray '%' should
itself become '%25' under the required second pass. For any parameter value containing ONLY unreserved
characters (RFC 3986: ALPHA / DIGIT / '-' / '.' / '_' / '~' - true of every SKU/page-number/id this
connector had signed until poll_changes's ISO8601 modified_after cursor), quote() never produces a '%',
so the missing second pass was silently a no-op and the bug went undetected. Confirmed empirically
against the real local WooCommerce instance: every reserved character tried (':', ' ', '+', '/', '@',
'?', '=', '&', '#', "'", '"') reproduced the same 401 "Invalid signature" under the old single-encoding
construction and was fixed by this double-encoding fix - not a colon-specific special case.
"""


def sign_request(method: str, url: str, params: dict[str, str], consumer_key: str, consumer_secret: str) -> dict[str, str]:
    """Returns `params` merged with the oauth_* parameters (including oauth_signature) required to
    authenticate a WooCommerce REST API request. Caller appends these to the query string (WooCommerce's
    one-legged OAuth1 reads them from $_GET/$_POST or a parsed Authorization header - query string is
    the simplest, most portable choice for a JSON API client)."""
    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA256",
    }
    all_params = dict(params)
    all_params.update(oauth_params)

    def enc(value: object) -> str:
        return urllib.parse.quote(str(value), safe="")

    # RFC 5849 3.4.1.3.2: normalized parameter string, each key/value percent-encoded individually,
    # joined with LITERAL '=' and '&' (not yet percent-encoded themselves).
    parameter_string = "&".join(f"{enc(k)}={enc(v)}" for k, v in sorted(all_params.items()))
    # RFC 5849 3.4.1.1: the whole parameter string is then percent-encoded AGAIN as a single opaque
    # unit before being spliced into the signature base string - this is the pass the old code skipped.
    base_string = f"{method.upper()}&{enc(url)}&{enc(parameter_string)}"
    signing_key = f"{consumer_secret}&"
    signature = base64.b64encode(hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()).decode()
    oauth_params["oauth_signature"] = signature
    return {**params, **oauth_params}
