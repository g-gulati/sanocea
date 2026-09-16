# Flipkart connector — certification status

**Overall state: FLIPKART CONNECTOR — IMPLEMENTED FROM FIRST-PARTY CONTRACT. CONTRACT TESTS PASS.
END-TO-END SYNTHETIC MERCHANT PASS. LIVE MERCHANT CERTIFICATION PENDING.**

Do not describe this connector as LIVE or CERTIFIED. No real Flipkart credentials, sandbox, or account
have been used at any point in this step. Every capability below is graded against ONE of these levels;
never assume a higher level than what is actually recorded.

- **BUILT FROM FIRST-PARTY CONTRACT** — implemented against Flipkart's own documentation, fetched and
  read directly this step (not secondhand).
- **SIMULATED / CONTRACT TESTED** — the above, plus a deterministic test exists proving the connector's
  own request-building/response-parsing/mapping logic against a synthetic, documented-shape response
  (`tests/unit/test_flipkart_connector.py`, `test_marketplace_connector_contract.py`,
  `test_flipkart_shopify_multichannel_merchant.py`). This is evidence the CODE is correct, never
  evidence the LIVE PLATFORM behaves this way.
- **REQUIRES MERCHANT CREDENTIAL** — code and tests both pass; needs a real `client_id`/`client_secret`
  (Sanocea's own Partner credentials) and a real per-merchant `refresh_token` (obtained via that
  merchant's OAuth consent) before any live call can be attempted.
- **REQUIRES FIRSTHAND SPEC CONFIRMATION** — the capability's existence is reasonably evidenced but its
  exact request/response schema could not be independently confirmed this step; implemented on a
  best-effort basis, must be re-verified against real responses before being trusted live.
- **NOT YET SUPPORTED / UNCONFIRMED** — no evidence of the capability's existence at all; not
  implemented; `CapabilityStatus.UNCONFIRMED`, refused at runtime by `require()`.

## Capability-by-capability breakdown

| Capability | Status | Certification level | Notes |
|---|---|---|---|
| `auth` (both grant types) | SUPPORTED | SIMULATED / CONTRACT TESTED, REQUIRES MERCHANT CREDENTIAL | Token endpoint/grant types/response shape Level 1 confirmed. Contract-tested against a fake transport for both grant types. |
| `catalogue_read`/`catalogue_write` (`publish_product`/`create_product`/`update_product`) | SUPPORTED | SIMULATED / CONTRACT TESTED, REQUIRES FIRSTHAND SPEC CONFIRMATION | Base path `/sellers/v3/listings` Level 1 confirmed; exact create/update JSON field names (`skuId`, `sellingPrice`) are best-effort — the dedicated Listing Management API Reference page could not be reached this step. |
| `inventory_read`/`inventory_write` (`update_inventory`) | SUPPORTED | Same as catalogue_write | Folded into the listings endpoint — no separate inventory-only endpoint was confirmed for the main marketplace. |
| `order_ingest` (`search`/`poll_changes`/`sync_orders`) | SUPPORTED | SIMULATED / CONTRACT TESTED, REQUIRES MERCHANT CREDENTIAL | `/sellers/v3/shipments/filter` request/response shape (including `nextPageUrl` pagination) Level 1 confirmed and directly fetched this step. |
| `fulfilment_update` (`dispatch_shipment`, `self_ship_dispatch`) | SUPPORTED | SIMULATED / CONTRACT TESTED (dispatch_shipment only — self_ship_dispatch capability-declared but not covered by an automated test this step), REQUIRES MERCHANT CREDENTIAL | Level 1 confirmed. |
| `cancellation` (`cancel_shipment`) | SUPPORTED | SIMULATED / CONTRACT TESTED, REQUIRES MERCHANT CREDENTIAL | Level 1 confirmed directly this step — corrects Step 9Q.1's earlier UNCONFIRMED classification, which was based on secondhand OMS-integrator summaries rather than Flipkart's own doc. |
| `return_refund` (`approve_return`, `complete_return`) | SUPPORTED | SIMULATED / CONTRACT TESTED (approve_return only), REQUIRES MERCHANT CREDENTIAL | Level 1 confirmed; `reject_return`/`pickup`/`pickupAttempt` documented but not wired into `_execute_mutation` this step. |
| `settlement_ingest` | UNCONFIRMED | NOT YET SUPPORTED / UNCONFIRMED | No settlement/payment API endpoint was linked from Flipkart's own Seller API docs index reached this step. Refused at runtime by `require()`. |
| `order_notifications` (webhook subscription) | ACCESS_REQUIRED | SIMULATED / CONTRACT TESTED (not covered by an automated test this step; request shape implemented), REQUIRES FIRSTHAND SPEC CONFIRMATION for the exact signature-header format | Endpoint Level 1 confirmed; activation additionally needs a VAPT certificate + Flipkart support ticket — not obtainable via OAuth alone. Refused at runtime by `require()` when checked via that path (not gated in `register_webhooks()` itself, matching WooCommerce's own precedent). |
| `hyperlocal_catalogue_read`/`hyperlocal_catalogue_write`/`hyperlocal_inventory_write`/`hyperlocal_pricing_write` | SUPPORTED | SIMULATED / CONTRACT TESTED, REQUIRES MERCHANT CREDENTIAL | Level 1 confirmed (Step 9Q.1 research: `/listings/v3/hyperlocal`, `/hyperlocal/update`, `/hyperlocal/update/inventory`, `/hyperlocal/update/price`, `GET /listings/v3/{sku-ids}`). |
| `hyperlocal_order_ingest`/`hyperlocal_fulfilment_update`/`hyperlocal_return_refund`/`hyperlocal_settlement_ingest` | UNCONFIRMED | NOT YET SUPPORTED / UNCONFIRMED | Per Step 9Q.1 Part D's explicit instruction: never assume the main marketplace's order/fulfilment/return/settlement APIs cover HyperLocal without separate confirmation. None found. Refused at runtime by `require()`. |

## Order status mapping — REQUIRES FIRSTHAND SPEC CONFIRMATION

Only `CANCELLED` and `DELIVERED` are mapped to canonical status with any confidence. Every other
Flipkart shipment status is preserved verbatim on `Order.status` and raises
`ExceptionCategory.UNMAPPED_CHANNEL_STATUS`. See `docs/connectors/flipkart.md` for the exact table and
extension point (`_CONFIRMED_STATUS_MAP` in `connectors/flipkart/connector.py`).

## What would need to happen for LIVE VERIFIED

1. Sanocea registers as a Flipkart API Partner (Partner Dashboard, ~72hr review per Step 9Q.1).
2. A real merchant completes the OAuth consent redirect, yielding a real `refresh_token`.
3. Every "REQUIRES FIRSTHAND SPEC CONFIRMATION" row above is re-verified against real API responses,
   and `_CONFIRMED_STATUS_MAP` is extended with the real observed status vocabulary.
4. A UAT pass against Flipkart's real (non-production, if one exists — not confirmed this step) or
   production environment for at least: listing create/update, order ingestion, dispatch, cancellation,
   return approval.

Only after all four are true should this connector's status change from "LIVE MERCHANT CERTIFICATION
PENDING" to "LIVE VERIFIED", and only after sustained real-traffic evidence to "CERTIFIED".
