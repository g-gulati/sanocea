# Meesho connector

`connectors/meesho/` — a `MarketplaceConnector` subclass. **Materially different evidence situation
from Flipkart/Amazon**: no Meesho-owned primary documentation (developer portal, official API
reference, official SDK/Postman collection, official engineering blog) was reachable during this
step's direct research, despite genuine attempts. Every technical detail below traces back to
secondhand (Level 5) sources — this is disclosed throughout, not upgraded.

## Evidence sources checked (Step 9Q.4)

**Attempted, failed to reach official material:**
- `supplier.meesho.com/api-docs` — HTTP 403.
- `developers.meesho.com` — HTTP 404.
- `tech.meesho.com` (Meesho's own engineering blog) — DNS resolution failure.
- `postman.com/meesho` — page returned no content (likely a JS-rendered SPA shell).
- `github.com/OpenDataPoint/meesho_api` — checked directly; this is an **unofficial RapidAPI wrapper
  for Meesho's consumer-facing product-catalog pages**, unrelated to seller/supplier operations. Not
  used as evidence for anything in this connector.
- Targeted web searches for official API documentation, PDF specs, and `client-id`/`secret-key` header
  documentation on `meesho.com`/`supplier.meesho.com` — no official technical documentation surfaced.

**Level 5 sources actually used** (mature integration-vendor technical documentation, corroborated
independently by two or more sources where noted):
- [Register on the Meesho Supplier Panel — Fynd Documentation](https://documentation.fynd.com/konnect/channels/marketplaces-webstores/meesho/register-on-meesho) — the most technically specific source found: header names, base URLs, credential-issuance process.
- [Integration with Meesho — Unicommerce Support Portal](https://support.unicommerce.com/index.php/knowledge-base/integration-with-meesho/) — independently corroborates "API Version V2", catalogue/inventory sync, order-status-sync-only (no seller order actions), facility-wise inventory.
- [Integrating Meesho-API with EasyEcom](https://support.easyecom.io/portal/en/kb/articles/integrating-meeshoapi-with-easyecom) — describes a broader operational picture (order confirmation, cancellation window, label/manifest generation) but with **zero technical (header/endpoint/field) detail**, and it is ambiguous whether the described actions are real API calls or EasyEcom automating Meesho's own supplier portal on the seller's behalf.
- [Meesho Order Management API Documentation.pdf — Course Hero](https://www.coursehero.com/file/146402530/Meesho-Order-Management-API/) — title/existence only; content not accessed.

## Access model (real, evidenced — this is NOT the blocker)

Direct, per-supplier credential issuance is evidenced and available to Sanocea: email
`meesholink-integration@meesho.com` with location-specific supplier identifiers; Meesho issues
static `client-id`/`secret-key` credentials, no formal multi-week partner-approval process described
anywhere. This is meaningfully **easier** than Flipkart's 72-hour Partner Dashboard review or Amazon's
LWA application registration — see `docs/connectors/meesho-certification.md`'s access-requirements
section and Part M's exact action steps.

## Auth (implemented — Level 5 evidence, one detail genuinely unknown)

Static per-supplier-location credentials, sent as request headers on every call: `merchant`
(client-id), `security` (secret-key or a derived value — see below), `timestamp`, `supplier_identifier`.
**No token exchange, no expiry, no refresh cycle** — materially different from Flipkart/Amazon's OAuth
shape. Base URLs: production `https://merchant.meesho.com`, sandbox `https://merchant.meeshotest.in`.

**Genuinely unknown and NOT guessed at:** how the `security` header value is derived from the
secret-key (raw copy? HMAC over the timestamp? something else?). No source describes this mechanism.
`StaticSupplierCredentialsAuth` (`connectors/meesho/auth.py`) accepts the final header value as an
already-computed credential rather than fabricating a signing algorithm.

## Why almost nothing else is implemented

Every business capability (catalogue, inventory, orders, fulfilment, cancellation, returns, settlement,
notifications) is described only as **existing** by secondhand sources — none of them publish an
endpoint path, request body, or response schema. Per the mandate's explicit rule ("no capability may be
marked SUPPORTED merely because another integration vendor claims it exists") and "do not fabricate a
contract to make the connector appear complete," none of these were implemented. See
`docs/connectors/meesho-certification.md` for the full per-capability breakdown, including the specific,
disclosed operational facts that ARE known (e.g. Meesho generates its own shipping labels; seller
cancellation is only possible before order confirmation and is disabled entirely once API integration
is active) even where no schema exists to act on them.

## What this connector proves architecturally

`StaticSupplierCredentialsAuth` satisfies `MarketplaceAuthStrategy`'s existing Protocol
(`auth_headers()`/`invalidate()`) with zero changes to `MarketplaceConnector` or the SDK — a genuine,
evidenced confirmation that the auth abstraction already accommodates a THIRD materially different
auth shape (OAuth token exchange for Flipkart/Amazon; static, non-expiring credentials for Meesho).
See `docs/architecture/connectors/marketplace-connector.md`.
