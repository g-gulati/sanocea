# MarketplaceConnector — architecture

Added Step 9Q.2, following Step 9Q.1's research conclusion: Amazon, Flipkart, Meesho, Myntra, AJIO,
Nykaa and JioMart share a stable enough operational shape (auth → catalogue → inventory → orders →
fulfilment → returns → settlement) to justify one connector family with pluggable authentication,
while their auth/onboarding friction differs sharply per channel.

## What it is

`packages/connector_sdk/marketplace.py` defines:

- **`MarketplaceAuthStrategy`** (Protocol) — `auth_headers() -> dict[str,str]`, `invalidate() -> None`.
  Two concrete implementations exist today, both real OAuth2 grant types (RFC 6749), not
  Flipkart-specific:
  - `SelfIssuedClientCredentialsAuth` — client-credentials grant. A single seller/merchant's own
    self-issued app acting on their own single account.
  - `MerchantAuthorizationCodeAuth` — authorization-code grant + refresh token. A multi-tenant
    aggregator's mode (Sanocea's actual production shape): one Sanocea-owned client_id/secret,
    per-merchant refresh tokens obtained via a one-time OAuth consent redirect during onboarding.
- **`MarketplaceConnector(GuardedConnector)`** — the base every marketplace connector subclasses.
  Standardizes:
  - the auth plug-point (`self.auth`, injected, never hardwired to one channel's auth shape)
  - `_request(method, url, body=, params=, extra_headers=, max_retries=, simulate=)` — one HTTP call
    with auth headers, JSON encode/decode, 401→one forced re-auth retry, 429/5xx→bounded retry with
    `Retry-After` awareness, then the SAME `TimeoutError`/`RuntimeError` vocabulary the rest of the
    codebase already uses for consequential-mutation semantics (see Step 9's mutation-recovery work,
    `packages/post_order/operations.py`) — a future read-back/recovery pass over marketplace order
    mutations can reuse that exact discipline unchanged.
  - `connector_health()` — authentication state (token present? expiry?) without ever exposing the
    token/secret itself.
  - `STANDARD_CAPABILITIES` — a naming convention (not an enforced enum) subclasses should use for the
    cross-channel-comparable capability groups Step 9Q.1's Output 3 asked for.

## What it deliberately is NOT

- **Not a generic "call any marketplace" abstraction.** Each connector still owns its own wire-format
  translation, status-vocabulary mapping, and `describe_capabilities()` — exactly as
  `GuardedConnector`'s existing docstring already establishes for Shopify/WooCommerce. Step 9Q.1's
  Output 3 explicitly separated the MarketplaceConnector family from the QuickCommerceVendorConnector
  family (PO received, not solicited; ack-as-fulfilment-signal where it exists at all; no
  seller-initiated cancellation typically) precisely because their semantics differ enough that forcing
  one shape onto both would misrepresent the second family. Nothing quick-commerce-shaped was built
  under this base — that remains future, separate work if evidence justifies it.
- **Not a capability-status enforcement engine.** `CapabilityStatus` gained two new values this step
  (`ACCESS_REQUIRED`, `UNCONFIRMED`) and `ConnectorCapabilities.require()` now refuses both distinctly
  (`CapabilityAccessRequired`, `CapabilityUnconfirmed`) rather than only the pre-existing `UNSUPPORTED`
  → `UnsupportedCapability`. This is a small, backward-compatible SDK extension (every existing
  connector's capabilities default to `SUPPORTED`/`UNSUPPORTED`, unaffected) — not a new subsystem.

## Multi-storefront-per-merchant resolution (a real, pre-existing gap this step exposed and closed)

Before this step, `StorefrontConnectorRegistry.resolve(merchant_id)` and `as_resolver()`
(`packages/runtime/storefront_registry.py`) assumed exactly one storefront channel per merchant — true
for every merchant/test built before Step 9Q.2, since no scenario had ever combined two storefronts on
one merchant. `resolve_for_channel_type`/`resolve_for_channel_id` and `as_channel_resolver()` were added
additively (existing methods/behavior unchanged) so `ProductPublicationService.publish()`/`verify()` —
which already carried a specific `Publication.channel_id` — resolve the CORRECT connector for a
merchant running Shopify AND Flipkart simultaneously, rather than "whichever channel happens to be
first". See `tests/unit/test_flipkart_shopify_multichannel_merchant.py` for the proof.

## Step 9Q.3 addition — configurable auth header (Class B: proven by two real channels)

Amazon's SP-API confirmed contract (fetched directly, `developer-docs.amazon.com/sp-api/docs/
connecting-to-the-selling-partner-api`) sends its LWA access token as a **bare `x-amz-access-token`
header, no `Bearer ` prefix, and no AWS Signature V4 signing** for standard calls — materially
different from Flipkart's standard `Authorization: Bearer <token>`. `SelfIssuedClientCredentialsAuth`
and `MerchantAuthorizationCodeAuth` both gained an additive `header_name`/`header_format` constructor
parameter (default: Flipkart's exact prior behavior, fully backward compatible) rather than a new
Amazon-only auth class — this is the one Class B change Amazon's implementation required, proven
genuinely necessary by two real channels' documented contracts, not hypothetical. No other Amazon
mismatch reached this bar: RDT (Restricted Data Token) has no Flipkart equivalent and stays entirely
inside `connectors/amazon/auth.py`; async feed/report job semantics are interpreted by
`connectors/amazon/reports.py`, reusing the *existing* `ConnectorCommand.status` field rather than
adding a new one.

## Step 9Q.4 — no generic change required (a third auth shape, already accommodated)

Meesho's evidenced auth model (`connectors/meesho/auth.py::StaticSupplierCredentialsAuth`) is static,
per-supplier-location credentials with **no token exchange and no expiry at all** — a third, materially
different shape from Flipkart/Amazon's OAuth token exchange. It satisfies `MarketplaceAuthStrategy`'s
existing Protocol (`auth_headers()`/`invalidate()`) exactly as written, with `invalidate()` simply
documented as a no-op (there is nothing to refresh). This is real, positive evidence the auth
abstraction generalizes without needing a third constructor-parameter dance — the Protocol shape itself,
not any one concrete implementation, was already general enough. `connector_health()`'s generic
token-expiry assumption did NOT generalize as cleanly (it would always report `authenticated: False` for
a connector with no token concept) — `MeeshoConnector` overrides it locally (Class A, adapter-specific),
since a static-credential connector's idea of "healthy" is legitimately different, not a bug in the base
method's assumption for the OAuth-based channels it was designed for.

## Where the domain layer stays channel-neutral

`tests/unit/test_architecture_connector_boundary.py` (pre-existing, extended this step by adding
`"flipkart"` to `FORBIDDEN_LITERALS`) AST-checks that no domain-layer file (`packages/post_order`,
`packages/product_onboarding`, etc.) imports a connector implementation directly or hardcodes a
platform-name string literal. `FlipkartConnector` was added without touching any of those files' logic —
only `packages/runtime/service_graph.py` (the composition root) registers it.
