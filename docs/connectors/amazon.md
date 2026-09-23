# Amazon (India) connector

`connectors/amazon/` — a `MarketplaceConnector` subclass targeting Amazon India via the Selling Partner
API (SP-API). Built directly against Amazon's official SP-API model repository and primary
documentation, fetched and verified during Step 9Q.3 (not from memory, not secondhand):

- https://github.com/amzn/selling-partner-api-models (primary source for every endpoint path and field
  name below — the actual OpenAPI/JSON models, fetched directly, model families used: `listings-items-
  api-model`, `orders-api-model`, `fba-inventory-api-model`, `feeds-api-model`, `reports-api-model`,
  `notifications-api-model`, `finances-api-model`, `tokens-api-model`)
- https://developer-docs.amazon.com/sp-api/docs/connecting-to-the-selling-partner-api (LWA token
  contract)
- https://developer-docs.amazon.com/sp-api/docs/sp-api-endpoints (endpoint regions)
- https://developer-docs.amazon.com/sp-api/docs/marketplace-ids (India marketplace id)

## India specifics (data, not hardcoded logic)

- **Marketplace ID:** `A21TJRUUN4KGV` — confirmed directly.
- **Endpoint host:** `https://sellingpartnerapi-eu.amazon.com` — India is explicitly listed under the
  **Europe** SP-API endpoint region, not a region of its own or the North America host a US-focused
  implementation might assume. Both are `connectors/amazon/auth.py` module-level constants (data), and
  `marketplace_ids` is an `AmazonConnector` constructor parameter (defaults to India, overridable per
  merchant config) — never baked into request-building logic.

## Authentication

Confirmed directly: LWA token endpoint `https://api.amazon.com/auth/o2/token`; `grant_type=refresh_token`
for a per-merchant aggregator (Sanocea's shape); request fields `client_id`/`client_secret`/
`refresh_token`; response `access_token`/`token_type`("bearer")/`expires_in`/`refresh_token`. The access
token is sent as a **bare `x-amz-access-token` header — no `Bearer ` prefix, and no AWS Signature V4
signing** for standard SP-API calls (SigV4 was a legacy requirement, since deprecated — confirmed from
the same primary source; do not reintroduce it from older tutorials/memory).

This maps directly onto the existing `MerchantAuthorizationCodeAuth` (built for Flipkart) — see
`docs/architecture/connectors/marketplace-connector.md` for the one small, genuinely-justified generic
change this required (a configurable auth-header name/format, since Flipkart's `Authorization: Bearer`
and Amazon's bare `x-amz-access-token` are both real, confirmed, and different).

### Restricted Data Token (RDT) — Amazon-specific, not generalized

Confirmed directly (`tokens_2021-03-01.json`): `POST /tokens/2021-03-01/restrictedDataToken` exchanges
the connector's main access token for a short-lived token scoped to ONE specific
`(method, path, dataElements)` tuple, required only for Orders API operations that return PII. Confirmed
`dataElements` values: `buyerInfo`, `shippingAddress`, `buyerTaxInformation`. Implemented as
`connectors/amazon/auth.py::RestrictedDataTokenProvider` — kept **inside** the Amazon package (Part B
classification: Amazon-specific concept, no Flipkart equivalent, not promoted to `MarketplaceConnector`).

## Endpoints implemented

| Area | Endpoint(s) | Evidence |
|---|---|---|
| Listings read/write/delete | `GET`/`PUT`/`PATCH`/`DELETE /listings/2021-08-01/items/{sellerId}/{sku}`, `GET /listings/2021-08-01/items/{sellerId}` (search) | Confirmed directly from the official `listingsItems_2021-08-01.json` model. |
| FBA inventory (read only) | `GET /fba/inventory/v1/summaries` | Confirmed directly. Write endpoints (`createInventoryItem`, `deleteInventoryItem`, `addInventory`) are explicitly documented **sandbox only** — no production seller-writable FBA inventory endpoint exists; marked `UNSUPPORTED`, not implemented. |
| Merchant-fulfilled inventory | Same as listings write (`fulfillmentAvailability` attribute) | Kept as a distinct capability name only to avoid conflating it with FBA stock levels — genuinely the same endpoint. |
| Orders (read) | `GET /orders/v0/orders`, `/orders/{orderId}`, `/orders/{orderId}/orderItems` | Confirmed directly from `ordersV0.json`, including the full `OrderStatus` enum. |
| Order PII (RDT-gated) | `GET /orders/{orderId}/buyerInfo`, `/address` | Confirmed directly; requires an RDT (above), not the main access token. |
| Fulfilment (MFN) | `POST /orders/{orderId}/shipment` (confirmShipment) | Confirmed directly. |
| Notifications | `POST /notifications/v1/subscriptions/{notificationType}`, `/destinations` | Confirmed directly from `notifications.json` — real, self-serve, OAuth-gated API. **Actually receiving events additionally requires a real AWS SQS queue or EventBridge bus** the merchant/Sanocea provisions — an infrastructure prerequisite this connector does not attempt to satisfy (no AWS SDK dependency added); consuming that queue is future, separate work. |
| Feeds (async) | `POST /feeds/2021-06-30/documents`, `POST`/`GET`/`DELETE /feeds/2021-06-30/feeds{,/{feedId}}` | Confirmed directly from `feeds_2021-06-30.json`, including the full processing-status enum. |
| Reports (async) | `POST`/`GET`/`DELETE /reports/2021-06-30/reports{,/{reportId}}`, `GET /reports/2021-06-30/documents/{id}` | Confirmed directly from `reports_2021-06-30.json`, same status enum shape as Feeds. |
| Settlement/reconciliation | `GET /finances/v0/orders/{orderId}/financialEvents`, `GET /finances/v0/financialEventGroups` | Confirmed directly from `financesV0.json` — this is the authoritative reconciliation source, order-scoped exactly like Sanocea's existing `reconcile()` pattern for every other connector. |

## Deliberately NOT implemented — genuinely absent, not assumed symmetric with Flipkart

- **`cancellation`** — no order-cancellation REST endpoint exists anywhere in the Orders API model, and
  no cancellation `feedType` is documented in the Feeds API model's own description. `UNCONFIRMED`.
- **`return_refund`** — the official SP-API models repository's own top-level `models/` directory
  listing (fetched directly) contains **no returns/refunds model family at all**. `UNCONFIRMED`.
- **`merchant_fulfillment_shipping`, `easy_ship_scheduling`** — `merchant-fulfillment-api-model` and
  `easy-ship-model` directories are confirmed to exist in the models repository, but their exact
  endpoint contracts were not independently fetched/verified this step — `UNCONFIRMED` rather than
  guessed at (`REQUIRES FIRSTHAND SPEC CONFIRMATION`, not "no evidence at all" — a real but weaker
  evidence grade than the fully-implemented capabilities above).

## Async job handling — never model-level polling

`get_feed_status(feed_id)` / `get_report_status(report_id)` (`connectors/amazon/connector.py`, using
`connectors/amazon/reports.py::interpret_async_status`) each make exactly ONE status check and return
the current state. Nothing in this connector loops or waits for a job to finish — a caller (a bounded
harness, or a future scheduled worker) owns any repetition, matching this session's standing "bounded
harness owns repetition" rule. A submission (`create_feed`/`create_report`) is reported with Sanocea's
existing `ConnectorCommand.status = "executing"`, never `"succeeded"`, until a subsequent status check
confirms it.

## Order status mapping

Unlike Flipkart's Step 9Q.2 mapping (necessarily partial — the exact shipment-state vocabulary was
never fully enumerated in what was reached), Amazon's `OrderStatus` enum **is** fully documented and
fetched directly this step: `PendingAvailability`, `Pending`, `Unshipped`, `PartiallyShipped`, `Shipped`,
`InvoiceUnconfirmed`, `Canceled`, `Unfulfillable` — all eight are mapped in
`connectors/amazon/mappings.py::ORDER_STATUS_MAP`. The same safety net as Flipkart's still applies: any
future/unrecognized status is preserved verbatim on `Order.status` and raises
`ExceptionCategory.UNMAPPED_CHANNEL_STATUS` rather than being guessed at — "complete today" is not the
same claim as "permanently complete."
