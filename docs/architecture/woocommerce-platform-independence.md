# Real-Platform-Independence Test — WooCommerce

Status: `REAL EXTERNAL PLATFORM - LOCAL - PASS`

## Objective

Prove Sanocea's Commerce Operations core can integrate with a real, independently-implemented
ecommerce platform without contaminating canonical domain/business logic with WooCommerce-specific
behavior. Not a new Commerce module, not a WooCommerce feature-expansion project.

## Environment actually exercised

- **WordPress 7.1**, **WooCommerce 11.1.0**, **PHP 8.3.33** (all confirmed via `wp core version` /
  `wp plugin list` / `wp eval PHP_VERSION` against the running container — never assumed).
- Stood up via the official path identified in the OSS landscape audit: `@wordpress/env` (`wp-env`),
  Docker-based, config at `infra/woocommerce-dev/.wp-env.json`. Real WordPress + WooCommerce + the
  real `wc/v3` REST API + WooCommerce's real webhook subsystem (Action Scheduler-driven). No mocks.
- Docker Desktop was not previously installed on this machine; installed for this test (user-approved)
  via `winget install Docker.DockerDesktop`, using the already-enabled Hyper-V backend.
- Classification: **REAL EXTERNAL PLATFORM — LOCAL** (distinct from `SIMULATED EXTERNAL PLATFORM` and
  from `LIVE EXTERNAL PLATFORM — PRODUCTION MERCHANT`, which remains unclaimed for WooCommerce and for
  Shopify).

## Sanocea connector changes

All new code lives under `connectors/woocommerce/`:

- `connector.py` — `WooCommerceConnector(GuardedConnector)`. Implements the same protocol
  (`describe_capabilities`/`ingest_webhook`/`fetch`/`_execute_mutation`/`reconcile`) as
  `ShopifyConnector`, with every WooCommerce-specific behavior contained inside this one file:
  - **Authentication**: OAuth 1.0a "one-legged" (RFC 5849 minus the token), HMAC-SHA256, in
    `oauth1.py`. Empirically required — WooCommerce's `class-wc-rest-authentication.php` only accepts
    Basic Auth (header or query-string) when the store is served over HTTPS; this local store is
    plain HTTP, so it forces OAuth1. Verified against the real server before being treated as settled.
  - **Webhook verification**: `X-WC-Webhook-Signature` (base64 HMAC-SHA256 over the raw body, keyed
    by a per-merchant webhook secret) — a different header name and mechanism from Shopify's
    `X-Shopify-Hmac-SHA256`, but structurally the same shape, so the verification code itself was
    straightforward to mirror.
  - **Webhook idempotency without a delivery ID**: WooCommerce sends no equivalent of Shopify's
    `X-Shopify-Webhook-Id`. `ingest_webhook()` uses a SHA-256 checksum of the raw request body as the
    idempotency key instead — an exact-duplicate redelivery (identical bytes) is a no-op replay; a
    genuinely later delivery for the same order (different status/content) has a different checksum
    and is correctly processed as a new event. Proven live: replaying a captured real delivery twice
    produced zero additional canonical orders.
  - **Pagination**: not required for this connector's current action set (single-resource fetches by
    id/sku only) — WooCommerce's page-based `?page=&per_page=` pagination was inspected but not
    exercised; flagged as a real, currently-untested gap below.
  - **Order status representation**: WooCommerce's flat `status` field
    (pending/on-hold/processing/completed/cancelled/refunded/failed) is mapped to Sanocea's canonical
    two-dimension (status, payment_status) shape via `_STATUS_MAP`, entirely inside the connector.
  - **Product/variant representation**: WooCommerce's flat product object (`name`/`sku`/
    `regular_price`/`stock_quantity`) vs. Shopify's title+variants-array shape — normalized to the
    SAME connector-agnostic `{title, sku, price, status}` contract both connectors now return from
    `fetch("product", ...)` (see "Abstraction leak found and closed" below).
  - **Refund semantics**: `orders/{id}/refunds` defaults to an AUTOMATIC gateway refund attempt,
    which fails (`woocommerce_rest_cannot_create_order_refund`) for any gateway without one —
    including WooCommerce's own bundled Cash-on-Delivery, used in this test. The connector always
    sends `api_refund: false` (a manual/ledger refund), unlike Shopify where Sanocea is inherently
    talking to the real payment processor and a refund is automatically "real."
  - **No first-class Fulfillment resource**: unlike Shopify, WooCommerce core has no distinct
    tracking-number/fulfillment object. `create_fulfilment` transitions `order.status` to
    `processing`/`completed` — the closest native equivalent, documented via the `Capability.notes`
    field on `describe_capabilities()`, not silently pretended to be equivalent.

## Core changes required, and why

Every one of these is a small, individually-justified fix — none is a WooCommerce-specific
conditional anywhere in domain code.

1. **`packages/runtime/service_graph.py` / `apps/api/app.py`** — `build_service_graph()`/`create_app()`
   gained an optional `storefront_connector_factory` parameter (and `create_app()` also
   `storefront_webhook_path`), defaulting to `None`/`"shopify"` — **zero behavior change** for every
   existing caller (the production app remains `ShopifyConnector` at `/webhooks/shopify/...`,
   unchanged). This is the one seam a different storefront connector is swapped in through. Category:
   connector registration/configuration.
2. **`packages/post_order/operations.py`, `packages/product_onboarding/publication.py`,
   `packages/order_ops/monitoring.py`** — a real, pre-existing multi-platform bug: these three files
   hardcoded the literal string `"shopify"` (9 occurrences total) instead of deriving channel identity
   from the injected connector, in `InventoryObservation`/`FulfilmentObservation.source`,
   `ExternalIdMapping.external_system`, `ConnectorCommand.connector`, `ref.system` comparisons, and
   audit `source` fields. Fixed by reading `self.shopify.name` (every connector already exposes its
   own `.name`) instead. Zero behavior change for Shopify (`ShopifyConnector.name == "shopify"`
   already). `order_ops/monitoring.py`'s `OrderMonitoringService` is not wired into the current
   `apps/api` runtime (Phase 1/2-era, legacy-script-only) — fixed for consistency, not provable via
   this test's HTTP journey; the other two files' fixes ARE proven live (catalogue publication ran
   through the real WooCommerce store correctly labeled `external_system="woocommerce"`).
3. **`connectors/shopify/connector.py`'s `fetch("product", ...)` and
   `packages/product_onboarding/publication.py`'s `verify()`** — a genuine abstraction leak: `verify()`
   read Shopify's raw JSON shape directly (`variants[0]["sku"]`, the literal string `"ACTIVE"`).
   Closed by normalizing `fetch("product", ...)` to a connector-agnostic `{title, sku, price, status}`
   shape **inside each connector** (both `ShopifyConnector` and `WooCommerceConnector` do their own
   raw-to-normalized mapping); `verify()` now compares only the normalized shape. Proven live both
   ways: Shopify's existing mismatch-detection tests still pass unchanged, and WooCommerce's real
   read-back correctly detected a real price change.
4. **`packages/domain_contract/postgres_store.py`/`store.py`, `packages/onboarding/merchant.py`** —
   none required. Credential storage (`set_credential_ref`/`get_credential_ref`, env-var-backed
   locators) and channel/config onboarding were already fully generic — `woocommerce_consumer_key`/
   `_consumer_secret`/`_webhook_secret` and a `{"type": "woocommerce", ...}` channel needed zero schema
   changes, proving the onboarding layer was already platform-agnostic.

**Not required, deliberately not built (would be genuine scope expansion):** a connector registry
supporting multiple simultaneous storefront connectors within one running process for different
merchants — see the `single_connector_slot` finding below.

## Abstraction leak identified but NOT closed (reported, not hacked around)

`build_service_graph()`/`create_app()` construct exactly **one** storefront connector per process.
This test proves the connector is swappable (Shopify XOR WooCommerce, chosen per process instance via
`storefront_connector_factory`) — it does **not** prove simultaneous multi-platform routing within one
running Sanocea process serving different merchants on different platforms. That would require a
connector registry keyed by channel type (a real, larger architectural change), which was deliberately
not built — out of this test's explicit scope ("do not implement WooCommerce marketplace-specific
features... do not expand scope").

## Naming debt (reported, not fixed)

`PostOrderOperationsService`/`ProductPublicationService`/`OrderMonitoringService` still name their
storefront-connector constructor parameter and attribute `shopify_connector`/`self.shopify` —
functionally channel-agnostic now (duck-typed, holds whichever connector is configured), but the name
is misleading. Not renamed here to keep the diff minimal and mechanical; low-priority cleanup.

## Certification journey — real, measured evidence

`scripts/run_woocommerce_platform_independence.py`, run against the real HTTP boundary in both
directions: Sanocea driven via real `urllib` HTTP calls (never `TestClient`, never a direct service
call) against a real, network-bound `uvicorn` process (`scripts/_woocommerce_test_app.py`, built with
`create_app(storefront_connector_factory=...)`); WooCommerce driven via its real REST API. **Order
ingestion happens ONLY via a webhook WooCommerce itself delivers** — the script never calls
`ingest_webhook()` directly.

| Step | Result |
|---|---|
| Product create (catalogue ingest → approve → publish) | Real WooCommerce product id 37 created |
| WooCommerce read-back | title/sku/price/status all matched |
| Product update | price 499.00 → 549.00, confirmed on WooCommerce read-back |
| Inventory write | stock_quantity set to 15, confirmed on WooCommerce read-back |
| Order creation (WooCommerce REST API, real checkout-shaped order object) | order id 38 |
| **Real webhook delivery** (WooCommerce → Action Scheduler → real HTTP POST → Sanocea) | canonical `Order` created, correctly `external_refs=[{system: "woocommerce", external_id: "38"}]` |
| Duplicate/replayed webhook (captured real payload, replayed twice) | zero additional canonical orders |
| Fulfilment processing (order.status → processing, via the connector) | confirmed |
| Refund (WooCommerce real API, `api_refund: false`) | refund id 39, amount 500.00, confirmed on order read-back |
| Cancellation (separate order — see refund_eligibility finding) | status → cancelled, confirmed |
| Reconciliation | `reconcile()` compares canonical vs. real WooCommerce order status |

### Zero-tolerance results — 7/7 PASS

| Condition | Result |
|---|---|
| real_product_created_and_read_back | PASS |
| real_product_update_reflected | PASS |
| real_inventory_write_reflected | PASS |
| real_webhook_created_canonical_order | PASS |
| duplicate_webhook_no_duplicate_order | PASS |
| real_refund_via_woocommerce_api | PASS |
| real_cancellation_via_woocommerce_api | PASS |

## What testing against REAL WooCommerce exposed that the simulator never would have

This is the most valuable output of this test, listed in the order discovered:

1. **WordPress's `wp_http_validate_url()` SSRF protection blocks webhook delivery to
   `host.docker.internal`** — the Docker Desktop host gateway resolves to a private-range IP, which
   WordPress's own HTTP layer rejects by default (`http_request_host_is_external` filter). A real
   production WooCommerce store, webhooking a real public/routable Sanocea HTTPS endpoint, would never
   hit this — it is a genuine LOCAL-TESTING-ONLY obstacle, closed with a local-only mu-plugin
   (`infra/woocommerce-dev/mu-plugins-reference/`), never a Sanocea or WooCommerce code change.
2. **WordPress's HTTP layer additionally restricts destination ports to `{80, 443, 8080}` by
   default** (`http_allowed_safe_ports` filter) — the test Sanocea instance had to run on port 8080,
   not an arbitrary port, to avoid a second SSRF-adjacent rejection. Also local-environment-only.
3. **WooCommerce webhook delivery is asynchronous**, dispatched via Action Scheduler
   (`woocommerce_deliver_webhook_async`), not synchronous with the order-creation API call. A real
   production store's cron/Action Scheduler runner drains this continuously; this dev store only
   drains it on site traffic (WP-Cron "pseudo-cron") or an explicit trigger. This directly disproved
   an initial assumption that WooCommerce order/webhook processing is fully synchronous — it is
   synchronous for direct REST reads/writes, but webhook DELIVERY specifically is not. The
   certification script now explicitly triggers Action Scheduler rather than assuming synchronicity.
4. **Refund creation defaults to an automatic gateway refund attempt**, which fails outright for any
   gateway without one (including WooCommerce's own bundled Cash-on-Delivery) — `api_refund: false`
   is required. Not documented prominently; found only by attempting a real refund and reading the
   real error (`woocommerce_rest_cannot_create_order_refund`).
5. **A cancelled order cannot also carry a refund** (a real WooCommerce business rule enforced
   server-side) — the certification uses two separate orders for the two scenarios rather than
   fabricating a single order that legitimately cannot exercise both.
6. **`manage_stock: true` without an explicit `stock_quantity` leaves the product `stock_status:
   "outofstock"` with `stock_quantity: null`** — WooCommerce does not default an unset quantity to 0
   sellable stock; the connector must always pass an explicit quantity when managing stock.
7. **This Docker-Desktop-on-Windows WordPress instance is genuinely slow** — individual REST API
   calls observed taking 10-15+ seconds even for simple reads (filesystem-translation overhead of
   Docker Desktop's Windows backend, not a Sanocea or WooCommerce defect). The connector's HTTP client
   timeout was set to 60s specifically because of this empirically-observed latency; a Linux-hosted
   WooCommerce store would not exhibit this.
8. **Timestamps**: WooCommerce sends both a "local" (`date_modified`) and `_gmt` suffixed UTC variant
   for every date field, with no explicit timezone offset on the non-GMT one — the connector uses only
   the `_gmt`-suffixed fields for staleness comparison (`_upsert_order`'s out-of-order check), avoiding
   an ambiguous local-time parse.
9. **Pagination was never actually exercised** by this connector's current action set (all fetches are
   by a known id or a single-result sku search) — flagged as an honest, untested gap, not silently
   assumed to work.

None of items 1-3, 6, or 8 could have been discovered from Sanocea's own simulator, which does not
model WordPress's SSRF protections, WooCommerce's async webhook dispatch, or WooCommerce's own
stock-status defaulting — this is exactly why the OSS-landscape-audit's recommendation to test against
a REAL local platform, not merely expand the simulator, was correct.

## Regression proof

Full pytest suite: **122 passed, 9 skipped** (identical skip set — MinIO/live-credential-gated, unrelated
to this work), **0 failed**, both before and after every change in this test. Phase 4.5 and Phase 4.6
Shopify-based integrated workload scripts (`run_phase45_integration_workload.py`,
`run_phase46_integration_workload.py`) both re-run and still **PASS** with all zero-tolerance conditions
green — the Shopify-configured production `create_app()` default path is byte-for-byte behaviorally
unchanged.

## Remaining WooCommerce limitations (explicitly out of this test's scope)

- No pagination support exercised (see finding 9 above).
- No `poll_changes`/incremental sync implemented (only single-resource fetch + webhook ingestion).
- No variable-product (`type: "variable"` + `/products/{id}/variations`) support — only simple products
  were exercised; WooCommerce's variant model is structurally different from Shopify's (a genuinely
  different sub-resource, not an inline array) and was out of this test's minimum-connector scope.
- No connector registry for simultaneous multi-platform operation (see "Abstraction leak identified but
  NOT closed" above).
- Webhook registration (`POST /wc/v3/webhooks`) was done manually via direct REST calls during this
  test's setup, not through `GuardedConnector.register_webhooks()` (which `WooCommerceConnector`
  doesn't implement) — a real merchant onboarding flow would need this wired, tracked as debt.

## Verdict

**PLATFORM-INDEPENDENCE: PASS**

## Could a third ecommerce platform now be added primarily by implementing another connector, without modifying Sanocea's Commerce-domain logic?

**YES**, with one named, honest caveat: the SAME class of channel-identity leak found and fixed for
WooCommerce (hardcoded platform-name literals) could recur if a third connector is added without
re-checking for it — there is no automated guard (e.g., a lint rule) preventing a new hardcoded
`"shopify"`/`"woocommerce"` literal from creeping into a domain file. Structurally, though: the
`GuardedConnector`/`Capability`/`MutationRequest`/`MutationResult` protocol, the credential-storage
layer, the onboarding config/channel mechanism, and (after this test's fixes) the channel-identity
derivation are all genuinely platform-agnostic today — a third connector's entire job is producing/
consuming that same protocol and normalizing its own platform's payload shapes internally, exactly as
`WooCommerceConnector` does. Finance, Procurement, Support, and the policy engine required **zero**
changes for this test, and none would be required for a third platform either.
