from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

"""Shopify client-credentials grant (verified current mechanism for a headless backend acting on a
store in the developer's own organization - see
docs/architecture/shopify-dev-store-certification-preparation.md's authentication-verification
addendum; legacy admin-created custom apps, which used to show a static shpat_... token in the Shopify
admin, were deprecated 2026-01-01). Shopify never hands out a long-lived static token for this app type
- ShopifyAccessTokenManager exchanges a Client ID/Secret for a short-lived (~24h) access token itself,
on demand, and is the ONLY place that ever holds one.

The token is treated as ephemeral runtime state, never merchant configuration: it is never written to
the store, never included in any audit/exception/log message (every error message here names the shop
domain and an HTTP status, never the token or the client secret), and is held only in this object's own
process memory for as long as it remains valid.
"""


class ShopifyAuthenticationError(Exception):
    """Raised when the client-credentials grant itself fails, or when a subsequent Admin API call fails
    with an auth-shaped (401/403) response plausibly caused by an expired/revoked token. Never includes
    the client secret or an access token in its message - safe to log/surface as-is."""


HttpPost = Callable[[str, bytes], tuple[int, Any]]


def _default_http_post(url: str, body: bytes) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            parsed = json.loads(exc.read())
        except (ValueError, json.JSONDecodeError):
            parsed = {}
        return exc.code, parsed


class ShopifyAccessTokenManager:
    """One instance per (shop_domain, client_id) - in practice, one per merchant's ShopifyLiveConnector
    instance, which the StorefrontConnectorRegistry already caches per merchant, so concurrent requests
    for the SAME merchant share the SAME manager (and therefore the same cached token / the same lock)."""

    def __init__(
        self,
        *,
        shop_domain: str,
        client_id: str,
        client_secret: str,
        http_post: HttpPost = _default_http_post,
        clock: Callable[[], float] = time.monotonic,
        refresh_margin_seconds: float = 60.0,
    ) -> None:
        self.shop_domain = shop_domain.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._http_post = http_post
        self._clock = clock
        self._refresh_margin_seconds = refresh_margin_seconds
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expires_at: float | None = None

    def get_token(self) -> str:
        """Returns a cached, still-valid token, or fetches a fresh one. Holds the lock for the entire
        check-then-fetch so concurrent callers serialize on a genuine refresh rather than each firing
        their own client-credentials request - a caller that arrives after another thread already
        refreshed sees the freshly cached token on its own turn and never hits the network."""
        with self._lock:
            if self._is_fresh_locked():
                return self._token  # type: ignore[return-value]
            return self._fetch_locked()

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = None

    def _is_fresh_locked(self) -> bool:
        if self._token is None or self._expires_at is None:
            return False
        # Proactive refresh margin, not exact-expiry waiting - mirrors Shopify's own documented example
        # (refresh once within 60s of the token's real expiry), so a request is never signed with a
        # token that expires mid-flight.
        return self._clock() < (self._expires_at - self._refresh_margin_seconds)

    def _fetch_locked(self) -> str:
        url = f"https://{self.shop_domain}/admin/oauth/access_token"
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }).encode()
        status, parsed = self._http_post(url, body)
        if status != 200:
            raise ShopifyAuthenticationError(f"client credentials grant rejected by {self.shop_domain}: HTTP {status}")
        token = parsed.get("access_token") if isinstance(parsed, dict) else None
        expires_in = parsed.get("expires_in") if isinstance(parsed, dict) else None
        if not isinstance(token, str) or not token or not isinstance(expires_in, (int, float)) or isinstance(expires_in, bool):
            raise ShopifyAuthenticationError(f"malformed client credentials grant response from {self.shop_domain} (missing/invalid access_token or expires_in)")
        self._token = token
        self._expires_at = self._clock() + float(expires_in)
        return self._token

    def __repr__(self) -> str:
        return f"ShopifyAccessTokenManager(shop_domain={self.shop_domain!r}, token=<redacted>, cached={self._token is not None})"

    __str__ = __repr__
