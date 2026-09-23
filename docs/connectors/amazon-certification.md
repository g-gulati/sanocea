# Amazon connector — certification status

**Overall state: SIMULATED EXTERNAL PLATFORM + REAL LOCAL INFRASTRUCTURE.**
No real Amazon credentials, sandbox, or seller account have been used at any point in this step. Do not
describe this connector as certified or live.

Two INDEPENDENT dimensions must be tracked, never conflated:

**Capability status** (does the operation exist / is it usable):
- `SUPPORTED` — implemented against confirmed documentation.
- `UNSUPPORTED` — confirmed NOT to exist (e.g. FBA inventory write in production).
- `ACCESS_REQUIRED` — exists, implemented, but needs infrastructure/credentials beyond OAuth alone.
- `UNCONFIRMED` — no evidence, or insufficient evidence, of the exact contract.

**Verification level** (how much has actually been proven):
- `IMPLEMENTED` — code exists, matches the documented request/response shape.
- `TESTED_SIMULATED` — the above, plus a deterministic test proves the connector's own request-
  building/response-parsing logic against a synthetic response shaped like Amazon's real documented
  fields. Evidence the CODE is correct — never evidence Amazon's live platform behaves this way.
- `REAL_ACCOUNT_CERTIFIED` — proven against a real Amazon seller account. **Nothing in this connector
  has reached this level.**

## Capability-by-capability breakdown

| Capability | Capability status | Verification level | Notes |
|---|---|---|---|
| `auth` | SUPPORTED | TESTED_SIMULATED | LWA token contract Level 1 confirmed; `x-amz-access-token` header (no Bearer prefix) tested explicitly (`test_lwa_uses_bare_header_no_bearer_prefix`). |
| `catalogue_read`/`catalogue_write`/`catalogue_delete` | SUPPORTED | TESTED_SIMULATED | Level 1 confirmed from the official `listingsItems_2021-08-01.json` model — the strongest schema evidence of any capability in either Flipkart or Amazon's connectors so far (real OpenAPI JSON, not an HTML doc page). |
| `fba_inventory_read` | SUPPORTED | TESTED_SIMULATED | Level 1 confirmed. |
| `fba_inventory_write` | **UNSUPPORTED** | N/A | Confirmed sandbox-only from the official model — this is a definitive negative finding, not an absence of research. |
| `merchant_fulfilled_inventory_write` | SUPPORTED | TESTED_SIMULATED | Same endpoint as `catalogue_write`. |
| `order_ingest` | SUPPORTED | TESTED_SIMULATED | Level 1 confirmed; full `OrderStatus` enum tested (`test_all_confirmed_order_statuses_map_without_exception`). |
| `order_buyer_info_read`/`order_address_read` | SUPPORTED | TESTED_SIMULATED | Level 1 confirmed, including the RDT gating mechanism (`test_restricted_data_token_used_for_buyer_info`). |
| `fulfilment_update` (confirm_shipment) | SUPPORTED | TESTED_SIMULATED | Level 1 confirmed. |
| `cancellation` | UNCONFIRMED | N/A | No endpoint found anywhere researched — a genuine negative finding, do not assume Flipkart symmetry. |
| `return_refund` | UNCONFIRMED | N/A | No model family exists in the official models repository at all. |
| `merchant_fulfillment_shipping` / `easy_ship_scheduling` | UNCONFIRMED | N/A | Model family confirmed to exist; exact contract not independently verified this step. |
| `order_notifications` | SUPPORTED | IMPLEMENTED (not covered by an automated test beyond the subscription/destination create calls) | Subscription API itself is self-serve/OAuth-only; real event delivery additionally needs a provisioned AWS SQS/EventBridge resource — not obtainable from this connector alone. |
| `feed_submit`/`report_submit` + status/document retrieval | SUPPORTED | TESTED_SIMULATED | Level 1 confirmed, including the full async-status enum and the STILL_UNKNOWN/CONFIRMED_SUCCEEDED/CONFIRMED_NOT_APPLIED verdict mapping. |
| `settlement_ingest` | SUPPORTED | TESTED_SIMULATED | Level 1 confirmed — order-scoped financial events, the authoritative reconciliation source. |

## Async operations — explicit lifecycle, no fake synchronous success

`create_feed`/`create_report` return `MutationResult(status="accepted", ...)` immediately — this is
Amazon accepting the SUBMISSION, never Sanocea claiming the mutation applied. `get_feed_status`/
`get_report_status` return one of:
- `STILL_UNKNOWN` (`IN_QUEUE`/`IN_PROGRESS`, or any unrecognized future status) — `ConnectorCommand`
  equivalent `"executing"`.
- `CONFIRMED_SUCCEEDED` (`DONE`) — `"succeeded"`.
- `CONFIRMED_NOT_APPLIED` (`CANCELLED`/`FATAL`) — `"failed"`.

No caller of this connector should ever read a `create_feed`/`create_report` result as evidence the
underlying catalogue/inventory change actually took effect — only a subsequent status check can say
that. See `tests/unit/test_amazon_connector.py::test_feed_submission_is_not_equivalent_to_applied_mutation`.

## PII / RDT boundary

- Only `buyerInfo`, `shippingAddress`, `buyerTaxInformation` are documented `dataElements` — the RDT
  provider (`RestrictedDataTokenProvider.request`) raises `ValueError` on any other value rather than
  forwarding an unconfirmed data-element request to Amazon (`test_rdt_rejects_unconfirmed_data_elements`).
- Ordinary order operations (`order_ingest`, status sync, reconciliation) never request an RDT and never
  touch buyer PII — only `order_buyer_info_read`/`order_address_read` do, and only when a caller
  explicitly invokes them. Sanocea's own order sync (`sync_orders`) does not request PII by default.
- `connector_health()` never exposes the access token or RDT (`test_connector_health_never_exposes_the_token`).
- Explicit tests assert no token/secret leaks into audit records or exception records
  (`test_no_secrets_or_tokens_leak_into_audit_or_exceptions`).
- No Amazon customer PII is persisted into any Sanocea canonical model by this connector — `sync_orders`
  never calls the buyer-info/address endpoints; a caller that separately fetches buyer info is
  responsible for that data's handling, same as any other consequential decision this codebase already
  requires explicit opt-in for.

## What would need to happen for REAL_ACCOUNT_CERTIFIED

1. Sanocea registers an LWA application (client_id/client_secret) — a one-time developer registration
   at Amazon's Developer Console.
2. A real Amazon India seller completes SP-API authorization for that application (Seller Central →
   authorize third-party application), yielding a real per-merchant `refresh_token`.
3. A UAT pass against a real seller account for at minimum: listing read/write with real validation
   `issues[]`, order ingestion against real order data, `confirmShipment` against a real order,
   feed/report submission and status resolution, and `financialEvents` reconciliation against a real
   settlement.
4. If notifications are needed: provision a real AWS SQS queue or EventBridge bus and verify event
   delivery end to end (out of scope for this connector's own code, which stops at subscription
   management).

Only after all four should this connector's state change from SIMULATED to REAL_ACCOUNT_CERTIFIED, and
only incrementally, capability by capability — not as one blanket status flip.
