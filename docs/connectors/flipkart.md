# Flipkart connector

`connectors/flipkart/` — a `MarketplaceConnector` subclass. Built against Flipkart's own Seller API
documentation, fetched and verified directly during Step 9Q.2 (not secondhand), primarily:

- https://seller.flipkart.com/api-docs/FMSAPI.html (overview, OAuth, base host, endpoint index)
- https://seller.flipkart.com/api-docs/order-api-docs/OMAPIRef.html (shipments/orders/returns reference)
- https://seller.flipkart.com/api-docs/order-api-docs/NotifIntro.html (notification/webhook mechanism)

Two operating surfaces are modeled, per Step 9Q.1's explicit instruction not to assume the main
marketplace API automatically covers Flipkart Minutes:

- **Main marketplace** — `https://api.flipkart.net/sellers/v3/...`, `/sellers/v2/returns...`
- **HyperLocal** (Flipkart Minutes' underlying program name) — `https://api.flipkart.net/listings/v3/hyperlocal...`
  — catalogue/inventory/pricing only. Orders/fulfilment/returns/settlement for HyperLocal are
  `UNCONFIRMED` and not implemented.

## Base URL

`https://api.flipkart.net` — confirmed directly from the fetched overview page.

## Authentication

Confirmed at `/oauth-service/oauth/token`: `grant_type` accepts `client_credentials`,
`authorization_code`, and `refresh_token`; Basic Authentication (base64 `appId:appSecret`) on the token
request; `scope=Seller_Api`; response includes `access_token`/`token_type`/`expires_in`/`refresh_token`.

Two real auth paths exist, and Sanocea uses the second one in production:

- **Self-access (client credentials)** — a single seller's own app, on their own account. No separate
  partner approval. `connectors/flipkart/auth.py::self_issued_client_credentials_auth`.
- **Aggregator (authorization code + refresh)** — Sanocea's actual shape: registers once as an API
  Partner (Partner Dashboard, ~72hr review per Step 9Q.1's research), then each merchant separately
  authorizes Sanocea via a standard OAuth consent redirect at `/oauth-service/oauth/authorize`, yielding
  a per-merchant refresh token. `connectors/flipkart/auth.py::merchant_authorization_code_auth`. This
  consent redirect itself is a one-time, UI-driven merchant-onboarding action — not part of this
  connector's code.

## Endpoints implemented (main marketplace)

| Operation | Method + path | Evidence |
|---|---|---|
| Listing read/write | `GET`/`POST /sellers/v3/listings` | Base path confirmed (Level 1); exact sub-resource JSON field names (`skuId`, `sellingPrice`, `availableUnits`) are best-effort — the referenced separate "Listing Management API Reference" page could not be reached during this step's research budget. |
| Order/shipment search | `POST /sellers/v3/shipments/filter` | Confirmed (Level 1) — request filters (`states`, `sku`, `locationId`, date ranges), response (`shipments[]`, `nextPageUrl`). |
| Shipment fetch by id | `GET /sellers/v3/shipments?shipmentIds=` | Confirmed (Level 1). |
| Dispatch | `POST /sellers/v3/shipments/dispatch` | Confirmed (Level 1). |
| Self-ship dispatch | `POST /sellers/v3/shipments/selfShip/dispatch` | Confirmed (Level 1) — implemented, not covered by this step's automated test suite beyond capability declaration. |
| Cancellation | `POST /sellers/v3/shipments/cancel` | Confirmed (Level 1) — this is a real, seller-initiated cancellation endpoint; earlier secondhand research (Step 9Q.1) had this as UNCONFIRMED, corrected here after direct primary-source verification. |
| Returns read | `GET /sellers/v2/returns` | Confirmed (Level 1). |
| Return approve/reject/complete/pickup | `POST /sellers/v2/returns/{approve,reject,complete,pickup}` | Confirmed (Level 1) — approve/complete implemented as connector mutations; reject/pickup/pickupAttempt are documented and capability-listed but not separately wired into `_execute_mutation` this step (straightforward additive follow-up, same pattern). |
| Notification (webhook) subscription | `POST /sellers/v3/notification/subscription` | Confirmed real and documented (Level 1) — but marked `ACCESS_REQUIRED`: activation additionally requires a VAPT certificate for the receiver endpoint and a support-ticket-based enablement process, not obtainable through OAuth alone. `register_webhooks()` implements the request shape but is not capability-gated (matches `WooCommerceConnector.register_webhooks`'s own precedent of being a setup action, not a gated business mutation). |
| Settlement/payment data | — | **UNCONFIRMED.** No settlement/payment API endpoint was linked from Flipkart's own Seller API docs index reached during this step. Not implemented. |

## Endpoints implemented (HyperLocal / Flipkart Minutes)

| Operation | Method + path | Evidence |
|---|---|---|
| Create/update listing | `POST /listings/v3/hyperlocal`, `/listings/v3/hyperlocal/update` | Confirmed (Level 1, Step 9Q.1 research). |
| Read listing | `GET /listings/v3/{sku-ids}` | Confirmed (Level 1). |
| Update inventory | `POST /listings/v3/hyperlocal/update/inventory` | Confirmed (Level 1). |
| Update price | `POST /listings/v3/hyperlocal/update/price` | Confirmed (Level 1). |
| Orders/fulfilment/returns/settlement | — | **UNCONFIRMED**, not implemented, per Step 9Q.1 Part D's explicit instruction. |

## Order ingestion — poll-based, not webhook-based

Flipkart's notification/webhook mechanism exists and is documented (see table above) but requires
platform-side VAPT certification + a support ticket — `ACCESS_REQUIRED`, not usable purely from a
merchant's OAuth grant. `FlipkartConnector.sync_orders()` therefore pulls orders via
`POST /sellers/v3/shipments/filter` (paginated via the documented `nextPageUrl` field), upserting into
canonical `Order`/`OrderLine` with the same idempotent-by-external-id shape
`ShopifyConnector`/`WooCommerceConnector` already use for webhook ingestion.

## Status mapping — deliberately conservative

Flipkart's exact shipment-state enumeration was not confirmed within this step's research budget (the
`/sellers/v3/shipments/filter` docs mention a `states` filter parameter without listing every value).
Only `CANCELLED` and `DELIVERED` are mapped with confidence. Every other Flipkart status string is
preserved **verbatim** on `Order.status` (never guessed at) and raises
`ExceptionCategory.UNMAPPED_CHANNEL_STATUS` (new this step, `packages/exceptions/service.py`) so an
operator can extend `_CONFIRMED_STATUS_MAP` (`connectors/flipkart/connector.py`) once real shipment
payloads are observed.

## What was NOT built, and why

- No settlement ingestion (UNCONFIRMED — no endpoint evidence found).
- No live webhook receiver wiring (the subscription endpoint's own activation is `ACCESS_REQUIRED`).
- No exact listing-mutation field schema beyond the confirmed base path (best-effort field names,
  flagged inline in code comments and in `docs/connectors/flipkart-certification.md`).
- `reject_return`/`pickup`/`pickupAttempt`/label-generation/manifest/OTC-scanning endpoints are
  documented (see the Order Management API reference) and capability-worthy but not wired into
  `_execute_mutation` this step — same shape as the endpoints that ARE wired, straightforward to add
  once prioritized by real usage.

None of the above required guessing an undocumented schema to add — see
`docs/connectors/flipkart-certification.md` for the authoritative built/simulated/unconfirmed breakdown.
