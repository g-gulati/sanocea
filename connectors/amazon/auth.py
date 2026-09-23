from __future__ import annotations

import json
from typing import Any

from sanocea.packages.connector_sdk import MarketplaceAuthStrategy, MerchantAuthorizationCodeAuth, Transport

"""Amazon SP-API auth - Step 9Q.3, verified directly against Amazon's own primary documentation this
step (not secondhand, not from memory):

- LWA token endpoint: `https://api.amazon.com/auth/o2/token` (fetched directly from
  developer-docs.amazon/sp-api/docs/connecting-to-the-selling-partner-api).
- Grant type for a per-merchant aggregator (Sanocea's shape): `refresh_token`, with `client_id`/
  `client_secret` being SANOCEA'S OWN LWA application credentials (registered once), and `refresh_token`
  being the per-merchant token obtained the one time that merchant completes Amazon's seller
  authorization workflow - a one-time, UI-driven consent action, not this connector's concern.
- Response fields: access_token, token_type ("bearer"), expires_in, refresh_token (echoed).
- Access token usage: a bare `x-amz-access-token: <token>` header - NO "Bearer " prefix, and NO AWS
  Signature V4 signing for standard SP-API calls (confirmed from the same primary source: AWS SigV4 was
  a LEGACY SP-API requirement, since deprecated - do not reintroduce it from memory/outdated tutorials).

This is why LWA maps directly onto the EXISTING `MerchantAuthorizationCodeAuth` (RFC 6749 authorization-
code + refresh-token grant, already built for Flipkart) with only its header name/format parameterized
differently - see packages/connector_sdk/marketplace.py's Step 9Q.3 additions. No new generic auth class
was needed; this is a real, evidence-based confirmation that the existing abstraction generalizes,
exactly the "genuine cross-marketplace requirement" bar Step 9Q.3's mandate set.
"""

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# Confirmed directly (developer-docs.amazon/sp-api/docs/sp-api-endpoints): three SP-API endpoint
# regions exist; Amazon India ("Amazon India stores") is explicitly listed under the EUROPE region, not
# a region of its own. This is why India uses the EU host, not something India-specific.
REGION_HOSTS = {
    "NA": "https://sellingpartnerapi-na.amazon.com",
    "EU": "https://sellingpartnerapi-eu.amazon.com",
    "FE": "https://sellingpartnerapi-fe.amazon.com",
}

# Confirmed directly (developer-docs.amazon/sp-api/docs/marketplace-ids). Kept as DATA the connector
# reads, not hardcoded business logic - a merchant operating additional marketplaces supplies their own
# marketplaceIds in config; this is only the sensible default for an India-first deployment.
MARKETPLACE_ID_INDIA = "A21TJRUUN4KGV"
ENDPOINT_HOST_INDIA = REGION_HOSTS["EU"]


def merchant_lwa_auth(
    *, client_id: str, client_secret: str, refresh_token: str, transport: Transport | None = None,
) -> MarketplaceAuthStrategy:
    """Sanocea's production Amazon auth mode - one Sanocea-owned LWA application (client_id/secret),
    one refresh_token per merchant (obtained via that merchant's Amazon Seller Central authorization)."""
    return MerchantAuthorizationCodeAuth(
        token_url=LWA_TOKEN_URL, client_id=client_id, client_secret=client_secret,
        refresh_token=refresh_token, transport=transport,
        header_name="x-amz-access-token", header_format="{token}",
    )


class RestrictedDataTokenProvider:
    """Amazon-specific (Class A, per Step 9Q.3 Part B - solved inside connectors/amazon/, not
    generalized into MarketplaceConnector): Flipkart has no equivalent concept, so this is NOT promoted
    to a generic SDK primitive.

    Confirmed directly (developer-docs.amazon/sp-api/docs/tokens-api-v2021-03-01-reference, and the
    primary tokens_2021-03-01.json model): `POST /tokens/2021-03-01/restrictedDataToken` exchanges the
    connector's OWN main access token (NOT client credentials) for a short-lived Restricted Data Token
    scoped to ONE specific (method, path, dataElements) tuple - required only for Orders API operations
    that return PII (buyer name, shipping address, tax info). RDTs are deliberately NOT cached/reused
    across different operations the way the main access token is - a fresh one is requested per
    restricted call, matching Amazon's own single-purpose, short-lived design.
    """

    #: Confirmed dataElements values (Level 1, tokens_2021-03-01.json) - Orders API operations that can
    #: return PII must declare which of these they need.
    DATA_ELEMENTS = ("buyerInfo", "shippingAddress", "buyerTaxInformation")

    def __init__(self, *, host: str, main_auth: MarketplaceAuthStrategy, transport: Transport) -> None:
        self.host = host
        self.main_auth = main_auth
        self.transport = transport

    def request(self, *, method: str, path: str, data_elements: list[str]) -> str:
        unknown = set(data_elements) - set(self.DATA_ELEMENTS)
        if unknown:
            raise ValueError(f"unconfirmed RDT dataElements: {unknown} - only {self.DATA_ELEMENTS} are documented")
        headers = {"Content-Type": "application/json", **self.main_auth.auth_headers()}
        body = json.dumps({"restrictedResources": [{"method": method, "path": path, "dataElements": data_elements}]}).encode()
        status, _headers, response_body = self.transport("POST", f"{self.host}/tokens/2021-03-01/restrictedDataToken", headers, body)
        if status == 429:
            raise RuntimeError("Amazon RDT request 429 rate limited")
        if status >= 500:
            raise RuntimeError(f"Amazon RDT request {status}")
        if status >= 400:
            raise ValueError(f"Amazon RDT request rejected: {status}")
        parsed: dict[str, Any] = json.loads(response_body)
        return parsed["restrictedDataToken"]
