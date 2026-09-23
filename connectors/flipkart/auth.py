from __future__ import annotations

from sanocea.packages.connector_sdk import (
    MarketplaceAuthStrategy,
    MerchantAuthorizationCodeAuth,
    SelfIssuedClientCredentialsAuth,
    Transport,
)

"""Flipkart auth wiring - both grant types are REAL, confirmed at `/oauth-service/oauth/token`
(https://seller.flipkart.com/api-docs/FMSAPI.html, fetched directly, Level 1): `grant_type` accepts
client_credentials, authorization_code, and refresh_token; Basic Authentication (base64 appId:appSecret)
on the token request itself; scope=Seller_Api; response includes access_token/token_type/expires_in/
refresh_token.

Sanocea's actual shape is a MULTI-TENANT AGGREGATOR (many merchants, one Sanocea deployment) - Flipkart's
own documented distinction is: a single seller's own self-issued app (client_credentials, no separate
partner approval) vs. a third-party aggregator acting for MANY sellers (authorization_code, requires
registering on Flipkart's Partner Dashboard as an API Partner, ~72hr review - see
docs/connectors/flipkart-certification.md). Sanocea's PRODUCTION auth mode is therefore
`merchant_authorization_code_auth` below, not the self-issued one - the self-issued strategy is kept and
exported here anyway because it is a real, independently useful mode (e.g. for a merchant who wants to
run their own isolated integration rather than go through Sanocea's aggregator registration), and because
proving BOTH strategies work is direct evidence that MarketplaceConnector's auth plug-point is genuinely
pluggable, not hardwired to one Flipkart-specific shape.
"""

TOKEN_URL = "https://api.flipkart.net/oauth-service/oauth/token"


def self_issued_client_credentials_auth(
    *, client_id: str, client_secret: str, transport: Transport | None = None,
) -> MarketplaceAuthStrategy:
    """A single seller's own self-access app acting on their own single Flipkart seller account."""
    return SelfIssuedClientCredentialsAuth(
        token_url=TOKEN_URL, client_id=client_id, client_secret=client_secret, transport=transport,
    )


def merchant_authorization_code_auth(
    *, client_id: str, client_secret: str,
    refresh_token: str | None = None, authorization_code: str | None = None, redirect_uri: str | None = None,
    transport: Transport | None = None,
) -> MarketplaceAuthStrategy:
    """Sanocea's actual production auth mode: Sanocea is registered once as a Flipkart API Partner
    (client_id/client_secret are SANOCEA'S OWN partner credentials, not per-merchant), and each merchant
    separately grants Sanocea access via the standard OAuth consent redirect at
    `/oauth-service/oauth/authorize` (that one-time, UI-driven consent step is merchant onboarding, not
    connector code - see docs/connectors/flipkart-certification.md), yielding a per-merchant
    refresh_token this strategy exchanges for access tokens indefinitely afterward."""
    return MerchantAuthorizationCodeAuth(
        token_url=TOKEN_URL, client_id=client_id, client_secret=client_secret,
        refresh_token=refresh_token, authorization_code=authorization_code, redirect_uri=redirect_uri,
        transport=transport,
    )
