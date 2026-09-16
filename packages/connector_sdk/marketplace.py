from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol

from .base import GuardedConnector

"""Step 9Q.2 - the MarketplaceConnector contract.

Step 9Q.1's research concluded that Amazon, Flipkart, Meesho, Myntra, AJIO, Nykaa and JioMart share a
sufficiently stable OPERATIONAL shape (auth -> catalogue -> inventory -> orders -> fulfilment ->
returns -> settlement) to justify one connector family with pluggable authentication - while their
AUTH/ONBOARDING friction differs sharply (Flipkart: self-access OAuth with zero platform gate; Amazon:
private-app self-auth or public-app review; Meesho/Myntra/AJIO/Nykaa/JioMart: platform-issued
credentials per merchant). This module captures exactly that: a thin specialization of GuardedConnector
that (a) makes the auth strategy an injected, swappable object rather than something baked into the
connector class, (b) provides one shared HTTP transport/retry/rate-limit helper so every marketplace
connector handles 429/5xx/timeout identically, and (c) does nothing else - it is deliberately NOT a
generic "call any marketplace" abstraction; each connector still owns its own wire-format
translation, status-vocabulary mapping, and capability declarations, exactly as GuardedConnector's
existing docstring already establishes for Shopify/WooCommerce.

TimeoutError/RuntimeError here mean exactly what they mean everywhere else in this codebase (see
packages/post_order/operations.py's Step 9 mutation-recovery work): TimeoutError = the response was
lost, outcome genuinely unknown; RuntimeError = the platform's HTTP layer rejected/errored the request
itself. Any future marketplace-order read-back/recovery work can reuse Step 9's exact read-back
discipline against these connectors for free, because the exception vocabulary already matches.
"""


class MarketplaceAuthStrategy(Protocol):
    """A pluggable authentication strategy for a MarketplaceConnector. Different channels issue
    credentials completely differently (Flipkart: self-access OAuth2 client-credentials, zero platform
    gate; Amazon: LWA OAuth with a refresh token from a merchant's authorization grant; Meesho/Myntra/
    AJIO/Nykaa/JioMart: platform-issued static credentials per merchant) - MarketplaceConnector itself
    must never assume any one of these shapes."""

    def auth_headers(self) -> dict[str, str]:
        """Returns the HTTP headers (e.g. {"Authorization": "Bearer ..."}) needed on every request.
        May perform a token exchange/refresh internally the first time, or when the cached token has
        expired - callers never need to know which."""
        ...

    def invalidate(self) -> None:
        """Forces the next auth_headers() call to re-authenticate rather than reuse a cached token -
        used when a request comes back 401/403 despite a token that looked unexpired."""
        ...


class SelfIssuedClientCredentialsAuth:
    """OAuth2 client-credentials grant (RFC 6749 4.4) - Flipkart's documented "self-access" path: a
    seller/merchant issues their OWN client_id/client_secret directly from their seller dashboard
    (Manage Profile -> Developer Access), with no separate platform-level partner approval for this
    path. This class implements the STANDARD, protocol-level client-credentials exchange mechanics
    (which are not Flipkart-specific and cannot be "fabricated" - RFC 6749 is the primary source for the
    grant shape itself); the exact TOKEN ENDPOINT PATH is channel-specific and is therefore a REQUIRED
    constructor argument, never a hardcoded guess - see connectors/flipkart/auth.py for how Flipkart's
    connector supplies it, and docs/connectors/flipkart-certification.md for what remains to be
    confirmed against Flipkart's own documentation/a real account before this is trusted live.
    """

    def __init__(
        self, *, token_url: str, client_id: str, client_secret: str,
        transport: "Transport | None" = None, clock: Callable[[], float] = time.time,
        leeway_seconds: int = 30, header_name: str = "Authorization", header_format: str = "Bearer {token}",
    ) -> None:
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.transport = transport or default_http_transport
        self.clock = clock
        self.leeway_seconds = leeway_seconds
        # Step 9Q.3 - Amazon's confirmed LWA contract puts the access token in a bare `x-amz-access-token`
        # header (no "Bearer" prefix, no AWS SigV4 signing needed for standard calls per Amazon's own
        # docs), materially different from Flipkart's standard `Authorization: Bearer <token>` - proven
        # by BOTH real channels to be a genuine, non-hypothetical cross-marketplace auth variance, hence
        # this small additive parameterization rather than a new Amazon-only auth class.
        self.header_name = header_name
        self.header_format = header_format
        self._token: str | None = None
        self._expires_at: float = 0.0

    def auth_headers(self) -> dict[str, str]:
        if self._token is None or self.clock() >= self._expires_at:
            self._refresh()
        return {self.header_name: self.header_format.format(token=self._token)}

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0

    def _refresh(self) -> None:
        body = f"grant_type=client_credentials&client_id={self.client_id}&client_secret={self.client_secret}".encode()
        status, _headers, response_body = self.transport(
            "POST", self.token_url, {"Content-Type": "application/x-www-form-urlencoded"}, body,
        )
        if status == 429:
            raise RuntimeError("marketplace auth 429 rate limited")
        if status >= 500:
            raise RuntimeError(f"marketplace auth {status}")
        if status >= 400:
            raise ValueError(f"marketplace auth rejected client credentials: {status}")
        parsed = json.loads(response_body)
        self._token = parsed["access_token"]
        self._expires_at = self.clock() + int(parsed.get("expires_in", 3600)) - self.leeway_seconds


class MerchantAuthorizationCodeAuth:
    """OAuth2 authorization-code grant + refresh token (RFC 6749 4.1 + 6) - the path a MULTI-TENANT
    AGGREGATOR like Sanocea actually needs (as opposed to SelfIssuedClientCredentialsAuth above, which
    is a single seller's own app acting on their own single account). Flipkart's documented shape for
    this is exactly this pattern: Sanocea registers once as an API Partner (Partner Dashboard, ~72hr
    review - see docs/connectors/flipkart-certification.md), then EACH merchant separately authorizes
    Sanocea via a standard OAuth consent redirect, yielding a per-merchant refresh token this class
    exchanges for short-lived access tokens indefinitely afterward - no merchant interaction needed
    again unless the grant is revoked. This is also the same OAuth shape Amazon's LWA and most other
    Marketplace-family channels use for third-party aggregators, so this strategy is written to be
    reused there unchanged, not Flipkart-specific.

    Sanocea never performs the initial consent-redirect leg itself in this class (that is a one-time,
    UI-driven merchant onboarding action, out of scope for a connector) - this class starts from an
    already-obtained authorization_code (first exchange) or an already-stored refresh_token (every
    exchange after), both supplied by the caller/onboarding flow, never fabricated here.
    """

    def __init__(
        self, *, token_url: str, client_id: str, client_secret: str,
        refresh_token: str | None = None, authorization_code: str | None = None, redirect_uri: str | None = None,
        transport: "Transport | None" = None, clock: Callable[[], float] = time.time, leeway_seconds: int = 30,
        header_name: str = "Authorization", header_format: str = "Bearer {token}",
    ) -> None:
        if not refresh_token and not authorization_code:
            raise ValueError("MerchantAuthorizationCodeAuth requires a refresh_token or an authorization_code")
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._authorization_code = authorization_code
        self.redirect_uri = redirect_uri
        self.transport = transport or default_http_transport
        self.clock = clock
        self.leeway_seconds = leeway_seconds
        # See SelfIssuedClientCredentialsAuth's docstring above for why this parameterization exists -
        # Amazon LWA uses `x-amz-access-token: <token>` (no Bearer prefix), Flipkart uses standard
        # `Authorization: Bearer <token>` - both real, both now expressible without a channel-specific
        # auth class.
        self.header_name = header_name
        self.header_format = header_format
        self._token: str | None = None
        self._expires_at: float = 0.0

    def auth_headers(self) -> dict[str, str]:
        if self._token is None or self.clock() >= self._expires_at:
            self._refresh()
        return {self.header_name: self.header_format.format(token=self._token)}

    def invalidate(self) -> None:
        self._token = None
        self._expires_at = 0.0

    def _refresh(self) -> None:
        if self.refresh_token:
            form = f"grant_type=refresh_token&refresh_token={self.refresh_token}&client_id={self.client_id}&client_secret={self.client_secret}"
        else:
            form = (
                f"grant_type=authorization_code&code={self._authorization_code}"
                f"&client_id={self.client_id}&client_secret={self.client_secret}&redirect_uri={self.redirect_uri or ''}"
            )
        status, _headers, response_body = self.transport(
            "POST", self.token_url, {"Content-Type": "application/x-www-form-urlencoded"}, form.encode(),
        )
        if status == 429:
            raise RuntimeError("marketplace auth 429 rate limited")
        if status >= 500:
            raise RuntimeError(f"marketplace auth {status}")
        if status >= 400:
            raise ValueError(f"marketplace auth rejected authorization: {status}")
        parsed = json.loads(response_body)
        self._token = parsed["access_token"]
        self._expires_at = self.clock() + int(parsed.get("expires_in", 3600)) - self.leeway_seconds
        # A refresh grant may rotate the refresh token itself - persist the new one if issued, so the
        # NEXT refresh (possibly in a future process) uses the current one, not a stale/revoked one.
        if parsed.get("refresh_token"):
            self.refresh_token = parsed["refresh_token"]
        self._authorization_code = None  # single-use - never reused once any token exchange succeeds


# (method, url, headers, body) -> (status_code, response_headers, response_body_bytes)
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, dict[str, str], bytes]]


def default_http_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except TimeoutError:
        raise
    except urllib.error.URLError as exc:
        raise TimeoutError(str(exc)) from exc


class MarketplaceConnector(GuardedConnector):
    """Base for the MarketplaceConnector family (Flipkart first, Amazon/Meesho/Myntra/AJIO/Nykaa/JioMart
    later per Step 9Q.1's Wave 1/2 roadmap). Subclasses supply their own wire format, status-vocabulary
    mapping, and describe_capabilities() - this base only standardizes the auth plug-point and the
    HTTP transport/retry/rate-limit handling shared by all of them."""

    #: The standard capability-name vocabulary every MarketplaceConnector subclass should use so
    #: capability matrices are comparable across channels (Step 9Q.1 output 3's "connector family"
    #: conclusion). A subclass is free to add channel-specific extras beyond this list (e.g. Flipkart's
    #: "hyperlocal_catalogue_read"), but should not rename these core ones.
    STANDARD_CAPABILITIES = (
        "auth", "catalogue_read", "catalogue_write", "inventory_read", "inventory_write",
        "order_ingest", "fulfilment_update", "cancellation", "return_refund", "settlement_ingest",
    )

    def __init__(self, store, workflow, *, auth: MarketplaceAuthStrategy, transport: Transport | None = None) -> None:
        super().__init__(store)
        self.workflow = workflow
        self.auth = auth
        self.transport = transport or default_http_transport

    def _request(
        self, method: str, url: str, *, body: dict[str, Any] | None = None, params: dict[str, str] | None = None,
        extra_headers: dict[str, str] | None = None, max_retries: int = 2, simulate: str | None = None,
    ) -> dict[str, Any]:
        """One HTTP call with auth, JSON encode/decode, and bounded rate-limit-aware retry. Same
        TimeoutError/RuntimeError vocabulary as the rest of the codebase (see module docstring) - callers
        that need Step 9-style read-back-before-retry discipline for a specific mutation can reuse it
        unchanged against this connector family. `params` are real query-string parameters (the normal
        REST convention for a filtered GET), never smuggled through custom headers.
        """
        if simulate == "429":
            raise RuntimeError("marketplace API 429 rate limited")
        if simulate == "500":
            raise RuntimeError("marketplace API 500")
        if simulate == "timeout_before_mutation" or simulate == "timeout":
            raise TimeoutError("timeout before marketplace mutation")
        if params:
            import urllib.parse

            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urllib.parse.urlencode(params)}"
        headers = {"Content-Type": "application/json", **self.auth.auth_headers(), **(extra_headers or {})}
        data = json.dumps(body).encode() if body is not None else None
        attempt = 0
        while True:
            status, response_headers, response_body = self.transport(method, url, headers, data)
            if status == 401 or status == 403:
                # Token may have expired between issuance and this call - one forced re-auth retry,
                # never more (a genuinely revoked/invalid credential must surface as a real error, not
                # loop forever).
                if attempt == 0:
                    self.auth.invalidate()
                    headers = {"Content-Type": "application/json", **self.auth.auth_headers(), **(extra_headers or {})}
                    attempt += 1
                    continue
                raise PermissionError(f"marketplace API authorization rejected: {status}")
            if status == 429:
                if attempt >= max_retries:
                    raise RuntimeError("marketplace API 429 rate limited (retries exhausted)")
                retry_after = response_headers.get("Retry-After") or response_headers.get("retry-after")
                time.sleep(min(float(retry_after), 5) if retry_after else 0.05 * (attempt + 1))
                attempt += 1
                continue
            if status >= 500:
                if attempt >= max_retries:
                    raise RuntimeError(f"marketplace API {status} (retries exhausted)")
                time.sleep(0.05 * (attempt + 1))
                attempt += 1
                continue
            if status >= 400:
                raise ValueError(f"marketplace API {status}: {response_body.decode(errors='replace')}")
            return json.loads(response_body) if response_body else {}

    def connector_health(self) -> dict[str, Any]:
        """Step 9Q.2 Part I - operational visibility into authentication state WITHOUT ever exposing the
        token/secret itself. Every subclass gets this for free; a subclass may extend the returned dict
        with its own extra fields (e.g. last-sync cursor) but should keep these three keys."""
        token = getattr(self.auth, "_token", None)
        expires_at = getattr(self.auth, "_expires_at", None)
        return {
            "connector": self.name,
            "authenticated": token is not None,
            "token_expires_at": expires_at,
        }
