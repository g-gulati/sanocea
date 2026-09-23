# Shopify Real Development-Store Certification — Preparation

Objective: move Shopify from `SIMULATED EXTERNAL PLATFORM` (the existing in-memory `ShopifyConnector`,
kept unchanged, with its own zero-tolerance fault-injection suite) toward
`REAL EXTERNAL PLATFORM — DEVELOPMENT STORE`, using Shopify's actual infrastructure — the same shape of
proof already delivered for WooCommerce (`docs/architecture/woocommerce-platform-independence.md`).

No Shopify credentials or development store exist in this environment. Everything below was prepared
**without** them: no credential was fabricated, no authentication was bypassed, and nothing is claimed
as live-certified. The one script that would exercise a real store (`scripts/run_shopify_dev_store_certification.py`)
was run exactly once, with no credentials set, to confirm it fails loudly (`BLOCKED`, exit code 1)
rather than producing any result — that is the only execution that has happened.

---

## Authentication verification addendum — CORRECTED

A follow-up verification pass against current `shopify.dev` docs found that section 1's original
"Admin API access" row below (and the config/ACTION REQUIRED sections that assumed it) described a
**deprecated** mechanism. Left in place with this correction rather than silently rewritten, per this
project's standing practice of reporting findings honestly rather than erasing what was initially
believed. **The corrected model, now implemented:**

Legacy admin-created custom apps (Settings → Apps → Develop apps) used to show a static `shpat_…` token
once, in the Shopify admin — that mechanism was **deprecated 2026-01-01** and cannot be used for new
apps. A current Dev Dashboard app never displays a token in its UI at all. The verified, current
mechanism for a headless integration acting on a store in its own organization is the **client
credentials grant**: exchange Client ID + Client Secret for a short-lived (~24h) access token via
`POST https://{shop}.myshopify.com/admin/oauth/access_token`, `grant_type=client_credentials` — no
redirect URI, no per-request merchant approval, but the token must be refreshed proactively before its
~24h expiry. Source: [Authenticate an app for stores in your organization](https://shopify.dev/docs/apps/build/dev-dashboard/get-api-access-tokens).

**Implemented** (SHOPIFY CLIENT-CREDENTIALS AUTH HARDENING): `connectors/shopify_live/auth.py`'s
`ShopifyAccessTokenManager` obtains and caches this token itself, proactively refreshes it (a 60s
margin before expiry), is concurrency-safe (a single lock serializes simultaneous callers onto one
fetch), and on an auth-shaped (401/403) API failure invalidates the cached token and retries the failed
call exactly once with a fresh token — bounded, never an unbounded loop. The token is treated as
ephemeral runtime state only: never persisted, never logged, never included in any audit/error message.
Because the retry happens entirely inside one `_execute_mutation()` call — the same call
`IdempotencyService.run_once()` treats as a single operation — a token refresh can never register as a
logically new mutation (proven in `tests/unit/test_shopify_live_connector_auth.py`). Sections 1/4 and
"ACTION REQUIRED FROM MANPREET" below are corrected accordingly; there is no longer an access-token
value for Manpreet to copy anywhere.

---

## 1. Current Shopify development workflow (verified against official docs, September 2026)

Sourced from `shopify.dev` directly (Dev Dashboard app-creation flow, API versioning, webhooks,
access-scopes, GraphQL mutation references, CLI networking docs) plus current third-party
confirmation of the Partner/store-creation flow shopify.dev's own pages don't spell out end-to-end.

| Step | Current mechanism |
|---|---|
| Developer account | Join the [Shopify Partner Program](https://www.shopify.com/partners) (free) — required before any development store or Dev Dashboard app can be created. |
| Dev Dashboard app | From the Partner Dashboard → Dev Dashboard → **Create app** → "Start from Dev Dashboard" → name it. An app needs at least one **version** (App URL, webhook API version, scopes) before it can be installed. |
| Development store | Partner Dashboard → **Stores** → **Add store** → **Create development store** → choose purpose ("test and build" for this use case) → name it (this fixes the permanent `*.myshopify.com` domain) → choose region → **Create development store**. Free on any Partner account. |
| Install/authorize the app | From the app's Dev Dashboard **Home** → **Install app** → select the development store just created → confirm. This is the interactive OAuth consent step — it must be a human action; no CLI flag replaces it. |
| Admin API access | ~~After install, Dev Dashboard Settings exposes a static access token~~ **CORRECTED — see the addendum above.** Dev Dashboard **Settings** exposes **Client ID** and **Client secret** only. `ShopifyLiveConnector` exchanges these for a short-lived Admin API access token itself, via the client credentials grant, and refreshes it automatically. |
| Admin API version | Current stable: **2026-07** (quarterly releases at 5pm UTC on the 1st of Jan/Apr/Jul/Oct; each stable version is supported ≥12 months with ≥9 months overlap with the next — `2026-10` becomes available imminently but `2026-07` is not going anywhere soon). `connectors/shopify_live/connector.py` defaults to `2026-07`, configurable per merchant. |
| Access scopes | Declared on the app's released version in the Dev Dashboard (or `shopify.app.toml` if using Shopify CLI's app scaffolding — not required for this integration style). See section 3 for the exact minimal set Sanocea needs. |
| Webhook subscriptions | Two mechanisms: (a) declared in the app config, applied to every installing shop automatically; (b) created per-shop via the `webhookSubscriptionCreate` GraphQL mutation. Sanocea uses (b) — `ShopifyLiveConnector.register_webhooks()` — exactly mirroring how `WooCommerceConnector.register_webhooks()` already works, for the same reason: per-merchant delivery URLs. |
| Test orders/payments | **Bogus Gateway**: Settings → Payments → Additional payment methods → Add "Bogus Gateway". Simulates a transaction with no real money and no Shopify Payments account needed. **Distinct** from Shopify Payments' own test card numbers — the two are not interchangeable; Bogus Gateway does not accept Shopify Payments' test cards and vice versa. Orders placed this way show a "Test Mode" banner. |
| Test data | Products/orders created via the Admin API on a development store are inherently test data — no separate "test mode" flag needed beyond the payment method above. |
| App URLs / callback requirements | The app's **App URL** (set on its version) is where Shopify redirects after OAuth install/embedding — since Sanocea is not building an embedded admin-UI app, this can point anywhere reachable (even a placeholder) and is unrelated to webhook delivery URLs, which are set independently per-subscription via `webhookSubscriptionCreate`'s `uri` field. |

Sources: [Create apps using the Dev Dashboard](https://shopify.dev/docs/apps/build/dev-dashboard/create-apps-using-dev-dashboard), [About Shopify API versioning](https://shopify.dev/docs/api/usage/versioning), [webhookSubscriptionCreate](https://shopify.dev/docs/api/admin-graphql/latest/mutations/webhookSubscriptionCreate), [Verify webhook deliveries](https://shopify.dev/docs/apps/build/webhooks/verify-deliveries), [Admin API access scopes](https://shopify.dev/docs/api/usage/access-scopes), [Shopify Development Store Guide 2026](https://appshopo.com/blog/shopify-development-store-guide/), [How to Test Payments in Shopify](https://www.browserstack.com/guide/how-to-test-payments-in-shopify).

---

## 2. Connector audit: simulator assumptions vs. the real current Admin GraphQL API

Every Shopify operation Sanocea's existing in-memory `ShopifyConnector` (`connectors/shopify/connector.py`)
models was mapped against the real, current Shopify Admin GraphQL API. **The simulator itself was not
changed** — it never made a real HTTP call to begin with (confirmed by reading its full implementation:
every "mutation" just writes to an in-process dict), so there was no working code to disturb, and its
own zero-tolerance fault-injection suite (`scripts/run_phase11_simulation.py`, currently PASS) is
untouched. What follows are the findings that shaped `connectors/shopify_live/connector.py` — the new,
additive, real-HTTP connector this phase built.

| Sanocea assumption (simulator / prior architecture) | Real current Shopify API | Consequence |
|---|---|---|
| Product create/update via a hand-built `{title, productType, variants, metafields}` shape | The current recommended mutation is **`productSet`** (`ProductSetInput`), not the older two-step `productCreate` + `productVariantsBulkCreate`, and not REST | `shopify_live` builds a `ProductSetInput` inside the connector from Sanocea's neutral payload (the same `{title, sku, price, currency, product_type, attributes}` shape multi-platform hardening already established — no new leak reintroduced) |
| Inventory as a flat `{sku, available}` value | Inventory is genuinely **location-scoped**: `InventoryItem` + `Location` + `InventoryLevel`, set via `inventorySetQuantities` (a compare-and-swap mutation; the older plain-quantity fields are deprecated as of 2026-01/removed from 2026-04) | `shopify_live` requires a `default_location_gid` per merchant — there is no sensible default to fabricate; this is the one piece of real store state that genuinely cannot be prepared without a real store existing (see section 4/10) |
| Fulfilment as "flip a status flag on the order" | Fulfilment goes through the **FulfillmentOrder** API — query the order's open `fulfillmentOrders`, then call `fulfillmentCreate` (not the deprecated `fulfillmentCreateV2`) against those | `shopify_live.create_fulfilment` performs the query-then-mutate sequence; a genuinely different shape from both the simulator and from WooCommerce's flat order-status transition |
| Refund as an unconditional mutation | `refundCreate` **requires** an `@idempotent(key: "uuid")` directive as of API version 2026-04 | `shopify_live` derives a stable UUID5 from Sanocea's own `idempotency_key` (`uuid.uuid5(NAMESPACE_URL, "sanocea:"+key)`) so a Sanocea-side retry is idempotent on Shopify's side too — a clean fit, not a workaround |
| Order webhook payload carries an `updated_sequence` integer used to detect stale/out-of-order deliveries | **No such field exists on a real Shopify webhook.** This is a Sanocea test-payload convenience invented for deterministic simulator/workload testing, not something Shopify ever sends | `shopify_live` compares `updated_at` timestamps instead — the identical technique `WooCommerceConnector` already uses for `date_modified` (WooCommerce also has no sequence field), so this isn't a new pattern, just newly-confirmed necessary for the real Shopify path too |
| Cancel order as a status write | `orderCancel` mutation, scope `write_orders`; genuinely irreversible, and Shopify enforces its own preconditions (no pending payment auth, no active returns, etc. — not fully enumerable without a real store to test edge cases against) | Implemented; preconditions are Shopify's own server-side validation, surfaced as `userErrors`, not re-implemented client-side |
| Webhook HMAC verified per-merchant against a stored "webhook secret" | Real Shopify HMAC is computed with the **app's Client Secret** (one value per app, not per shop) | `shopify_live` still accepts it as a per-merchant credential ref (`shopify_live_client_secret`) for interface consistency with every other connector, even though in practice every merchant using this one app would store the same value — harmless, not a fabricated abstraction |
| REST-style numeric resource IDs everywhere | Admin GraphQL API uses **global IDs** (`gid://shopify/Product/123`) for every API call, while webhook payload bodies still carry plain numeric `id` fields (REST-shaped delivery body, GraphQL-shaped API) | `shopify_live` has explicit `_product_gid`/`_order_gid`/`_inventory_item_gid` helpers converting webhook-delivered numeric IDs into the GIDs the API calls need |
| Rate limiting as a flat request-count 429 | GraphQL Admin API rate limiting is **cost-based** (a leaky bucket against calculated query cost, surfaced as a `THROTTLED` GraphQL error code with `extensions.cost`, not primarily HTTP 429s) | `shopify_live._graphql()` inspects `errors[].extensions.code` for `THROTTLED` and raises distinctly from a generic HTTP error — real handling, not assumed |

**Not changed, because nothing was wrong:** webhook dedup via `X-Shopify-Webhook-Id` (the simulator
already modeled this correctly); HMAC-SHA256/base64 verification algorithm (already correct); the
overall webhook → canonical-order upsert shape (already correct in structure, just needed the
sequence-field fix above); `MutationRequest`/`MutationResult`/`Page`/`GuardedConnector` protocol (no
change needed — this is exactly the abstraction the prior multi-platform hardening phase built for a
third connector to slot into without touching it).

**Fixed only what could be established without credentials:** every row above is a documented,
citable current-API fact, not a guess. What could **not** be established without credentials — and is
therefore explicitly flagged `UNVERIFIED` in `describe_capabilities()`'s notes and left for the first
real certification run to confirm — is whether the real store's schema accepts every field exactly as
written (e.g. `ProductSetInput`'s complete field set was only partially visible through documentation
tooling; schema introspection against the real store is the authoritative source and should be the
first thing the certification run does).

---

## 3. Minimum access scopes (least privilege)

| Scope | Required for |
|---|---|
| `read_products`, `write_products` | `productSet` (create/update), product read-back verification |
| `read_orders`, `write_orders` | Receiving order webhooks, `orderCancel`, `refundCreate`'s underlying order access |
| `read_inventory`, `write_inventory` | `inventorySetQuantities`, inventory read-back |
| `read_merchant_managed_fulfillment_orders`, `write_merchant_managed_fulfillment_orders` | Querying `fulfillmentOrders` and calling `fulfillmentCreate` for orders fulfilled by the merchant themselves (the relevant case for a development store — no third-party/assigned fulfillment service is involved) |

**Explicitly NOT requested:** `read_all_orders` (only needed for pre-install order history — every
order this certification creates happens after install, so default post-install order access is
sufficient); `read_assigned_fulfillment_orders`/`write_assigned_fulfillment_orders` and
`read_third_party_fulfillment_orders`/`write_third_party_fulfillment_orders` (only relevant if Sanocea
were acting as a third-party fulfillment service, which it is not); `read_customers`/`write_customers`
(Sanocea only ever reads an email address already present on the order payload — it never queries or
mutates the Customer object directly); any marketing/discount/checkout/theme/POS scope (out of scope
per instruction 9 and not needed by anything this connector does).

---

## 4. Sanocea configuration interface

Added to `.env.example` (no secrets committed — every value is either a placeholder or a non-secret
default). These are read **only** by `scripts/run_shopify_dev_store_certification.py`, which POSTs them
into a merchant's own `config`/`credentials` via `/admin/merchants` — identical to how the WooCommerce
certification already works. The running production app never reads Shopify credentials from process
environment variables; they live per-merchant in Postgres via `store.set_credential_ref()`, exactly like
every other connector's credentials.

```
SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN=            # OBTAIN FROM SHOPIFY - the dev store's *.myshopify.com domain
SANOCEA_SHOPIFY_LIVE_CLIENT_ID=              # OBTAIN FROM SHOPIFY - the app's Client ID (Dev Dashboard > Settings)
SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET=          # OBTAIN FROM SHOPIFY - the app's Client secret (same page) - used for BOTH the client-credentials grant and webhook HMAC verification
SANOCEA_SHOPIFY_LIVE_API_VERSION=2026-07     # current stable - not secret, has a safe default
SANOCEA_SHOPIFY_LIVE_WEBHOOK_DELIVERY_BASE_URL=  # the tunnel's public HTTPS URL - see section 5
```

No access-token or location-gid variable (see the addendum above and section 2's correction): the
access token is obtained and refreshed by `ShopifyAccessTokenManager` itself; the default Location gid
is discovered programmatically by `ShopifyLiveConnector` on first use.

Merchant-side shape (what the certification script sends to `/admin/merchants`, matching the existing
`config.woocommerce.base_url` / `credentials.woocommerce_*` pattern exactly):

```json
{
  "config": {"shopify_live": {"shop_domain": "...", "api_version": "2026-07", "webhook_delivery_base_url": "..."}},
  "credentials": {"shopify_live_client_id": "...", "shopify_live_client_secret": "..."},
  "channels": [{"type": "shopify_live", "name": "Shopify (dev store)", "credential_ref": "shopify_live_client_id"}]
}
```

`packages/runtime/service_graph.py::_shopify_live_factory` reads exactly this shape and raises a clear
`ValueError` if `shop_domain` is missing — no value is ever defaulted or fabricated. The factory is
registered by default alongside `shopify`/`woocommerce`, but — like `woocommerce` — is entirely lazy:
it is never invoked, and no config is ever required, unless a specific merchant is onboarded onto the
`shopify_live` channel. No existing merchant, test, or workload is affected (confirmed: full regression
still 119 passed / 32 skipped, architecture guard still PASS, after registering it).

---

## 5. Real webhook ingress

Shopify's cloud must reach a real, public HTTPS endpoint to deliver webhooks during certification — this
machine's `localhost` is not reachable from Shopify's servers.

**Recommended: Shopify CLI's own tunnel.** `shopify app dev` (via `npx shopify` — the same
`npx --yes @wordpress/env` pattern already used for WooCommerce's Docker tooling, no separate install
needed) opens a **Cloudflare Quick Tunnel** by default — a free, official, Shopify-supported mechanism
specifically for this purpose, requiring no account or configuration. It exposes only the port Sanocea's
own app is listening on (the same real production `apps.api.app:app`, unmodified, via `uvicorn`, exactly
as run for every other real-infra certification this project has done) — nothing else on this machine is
exposed. Alternative supported by Shopify CLI 3.80+: `--use-localhost`, which serves via `127.0.0.1` with
a self-signed HTTPS cert (mkcert) instead of tunneling — viable if Shopify's webhook delivery can reach a
self-signed-cert localhost endpoint from its own infrastructure (it typically cannot for cloud-originated
webhook POSTs, only for OAuth-redirect flows in a browser on the same machine — so the Quick Tunnel is the
correct choice specifically for webhook delivery, not `--use-localhost`).

**Security posture, preserved exactly as designed:** the tunnel only forwards to Sanocea's own bound
port; real Shopify HMAC-SHA256 verification (`ShopifyLiveConnector._verify_hmac`, using the app's real
Client Secret) still runs before any payload is trusted, identical in structure to the existing
Shopify-simulator and WooCommerce HMAC verification; idempotency via `X-Shopify-Webhook-Id` still applies
before any canonical mutation. The tunnel changes nothing about trust — it only solves reachability.

Sources: [Select a networking option for local development](https://shopify.dev/docs/apps/build/cli-for-apps/networking-options) *(fetch attempt returned 404 at the specific sub-path tried; corroborated instead via multiple current community/changelog sources — [Cloudflare Quick Tunnels — Shopify Dev forum](https://community.shopify.dev/t/cloudflare-quick-tunnels/5246), [`shopify app dev` CLI networking discussion](https://community.shopify.com/t/cloudflare-tunnel-shopify-app-dev/573469))*.

---

## 6. Certification harness — built, not executed

`scripts/run_shopify_dev_store_certification.py` — structurally complete, byte-compiles cleanly, and was
run exactly once with no credentials to confirm its only legitimate current behavior: fail loudly
(`verdict: "BLOCKED"`, exit code 1, explicit list of missing environment variables) rather than
proceeding. It has never made a single real network call.

Mirrors `scripts/run_woocommerce_platform_independence.py`'s structure and honesty standard exactly —
same `_check()`/dataclass-report/`OUT` pattern, same rigor (real polling for async webhook delivery,
real duplicate-delivery replay using a captured real payload, real per-step PASS/FAIL/UNVERIFIED
evidence, real `semantic_findings` for anything Shopify does differently than assumed). It clearly
separates:

- **Actions through Sanocea** (`_sanocea()`): catalogue ingest/publish, order listing, webhook delivery
  endpoint (`/webhooks/shopify_live/{merchant_id}`) — real Sanocea HTTP API, unmodified production app.
- **Setup/verification actions directly against Shopify** (`_shopify_graphql()`, and the standalone
  `ShopifyLiveConnector` `probe` instance used for update/inventory/fulfilment/cancel/refund/reconcile) —
  real Shopify Admin GraphQL API, used exactly the way `run_woocommerce_platform_independence.py` uses
  its `_wc()` helper and `probe_connector` for the same reason: independent verification.

Journey implemented end-to-end: product create → Shopify read-back → product update (verified via a
second independent read-back, not just Sanocea's own claim) → inventory/location operation (verified via
`fetch("inventory", ...)`) → real test order (via `orderCreate`, with a recorded finding that this should
be cross-checked against a Bogus-Gateway storefront checkout once a real store exists) → real Shopify
webhook delivery polled for (not assumed synchronous) → canonical Sanocea Order → webhook replay for
idempotency (using the captured real order payload, not a fabricated one) → fulfilment via the real
FulfillmentOrder API → cancellation on a separate order (mirroring the WooCommerce certification's
"can't cancel a refunded/fulfilled order" lesson, verified live rather than assumed identical) → refund
via the Bogus Gateway path where the store permits it → reconciliation via the connector's own
`reconcile()`.

---

## 7. Evidence standard for the eventual real run

When credentials exist, the harness captures, per step:

**From Sanocea:** the canonical `Order` id and state (via `GET /merchants/{id}/orders`); its
`external_refs` (system=`shopify_live`, external_id = the real numeric Shopify order id); the
`ConnectorCommand`/`PublicationAttempt` rows the catalogue-publish path already writes; `AuditLedger`
events (`order_webhook_ingested`, `duplicate_webhook_ignored`, etc. — unchanged, already-proven
machinery); and the `reconcile()` call's own result.

**From Shopify:** the real product/order/inventory state read back via **independent** GraphQL queries
(never trusting Sanocea's own report of success — `readback`/`readback2`/`inventory_readback` in the
harness are separate calls from the mutations that created the state); the real Shopify order gid/name;
the real `fulfillmentCreate`/`orderCancel`/`refundCreate` response payloads.

A passing simulator run cannot satisfy this gate — the harness never calls `ingest_webhook()` directly,
never fabricates a Shopify response, and every `PASS` in its `zero_tolerance` section requires a real
Shopify-side read-back or mutation response, not merely a Sanocea-side claim.

---

## 8. Existing testing layers — unchanged

`connectors/shopify/connector.py` (the simulator) and its zero-tolerance suite
(`scripts/run_phase11_simulation.py`, currently **PASS**) are untouched — confirmed via the full
regression re-run above. `connectors/woocommerce/` and its real local-WooCommerce certification are
untouched. Shopify Dev Store becomes a **third**, additive, complementary layer
(`connectors/shopify_live/`, channel type `"shopify_live"`), registered the same lazy, per-merchant way
`woocommerce` already is — exactly the extension point the prior multi-platform hardening phase built
and asked "could a third platform be added this way?" about. Answer, now demonstrated: yes.

## 9. Scope discipline

No marketing, CRM, BI, WhatsApp, marketplace, payment-provider, logistics-provider, supplier
integration, or UI work was touched. Everything built this phase is: one new connector file, one new
config/credential surface (additive, follows the existing per-merchant pattern exactly), one new
unexecuted certification script, and this document.

---

## ACTION REQUIRED FROM MANPREET — VERIFIED

Superseded and corrected against a dedicated live-documentation re-verification pass (Dev Dashboard
store-creation flow, the client-credentials auth model above, orderCreate/refundCreate specifics, and
the webhook-tunnel choice). Kept to the absolute minimum — only steps that genuinely require your own
Shopify authorization.

1. **Join the Shopify Partner Program** (partners.shopify.com), if you don't already have one.
2. **Create a development store**: Dev Dashboard → Stores → Create store → type **Dev** → name it. Send
   me the resulting `*.myshopify.com` domain → `SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN`.
3. **Create the app**: Dev Dashboard → Create app → name it → create a version → set scopes to exactly:
   `read_products,write_products,read_orders,write_orders,read_inventory,write_inventory,read_merchant_managed_fulfillment_orders,write_merchant_managed_fulfillment_orders`
   → Release.
4. **Install it**: app's Home → Install app → select the store from step 2 → confirm. (One click — same
   organization, no OAuth consent screen.)
5. **Declare data use for Protected Customer Data** (a one-time Dev Dashboard prompt that appears once
   the app has `read_orders`): select which customer data fields you use. No review/approval wait — this
   requirement is waived for an app installed only on a development store.
6. **Copy two values from the app's Settings page and send them to me — nothing else**:
   - **Client ID** → `SANOCEA_SHOPIFY_LIVE_CLIENT_ID`
   - **Client secret** → `SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET`
   *(No access token to copy — `ShopifyAccessTokenManager` obtains and refreshes it itself via the
   client-credentials grant.)*
7. **(Optional, recommended) Enable Bogus Gateway**: store admin → Settings → Payments → Additional
   payment methods → Add "Bogus Gateway". No value to send — just a toggle. (`orderCreate` can attach a
   real transaction directly, so this is a fallback for realism, not a hard blocker.)
8. **Run one tunnel command yourself, once, and send me the URL it prints**:
   `cloudflared tunnel --url http://localhost:8080` → `SANOCEA_SHOPIFY_LIVE_WEBHOOK_DELIVERY_BASE_URL`.
   *(Standalone `cloudflared`, not `npx shopify app dev`'s bundled tunnel — Sanocea is a plain
   FastAPI/uvicorn backend, not a Shopify-CLI-scaffolded app project, so the CLI's dev-server tunnel
   doesn't apply; running the same underlying tool directly is simpler and needs no CLI app project at
   all. Keep it running only for the duration of the certification run.)*

Not on this list, correctly: an access token (obtained/refreshed by Sanocea itself) and the default
Location gid (discovered by Sanocea itself via GraphQL once the token exists).

---

## Real Dev Store certification run - results

Executed against `sanocea-commerce-os-dev.myshopify.com`, the real Admin GraphQL API, and a real
Cloudflare Quick Tunnel, through the real, unmodified `apps.api.app:app` on a real uvicorn process.
Iterated live: each real failure was root-caused against the actual store (never assumed from docs) and
fixed in `connectors/shopify_live/connector.py`/the harness before retrying - full evidence in
`tests/fixtures/phase11_merchant/generated/shopify_dev_store_certification_report.json`.

**PASS (4/8 real, independently-verified checks):**
- `real_product_created` - `productSet` via Sanocea's real catalogue-publish API, real product gid returned.
- `real_product_read_back_independently` - a SEPARATE direct GraphQL query confirmed title/sku/status.
- `real_product_update_reflected` - a second `productSet` call on the same SKU updated the SAME product gid (not a duplicate).
- `real_inventory_location_operation` - real inventory set to 15, confirmed via a separate read.

**BLOCKED (account-level, not a code defect):** the app has not completed the Protected Customer Data
declaration in the Dev Dashboard (flagged in advance in the ACTION REQUIRED section above - Manpreet
has not yet done this step). Every remaining check (order create/webhook/idempotency/fulfilment/
cancellation/refund/reconciliation) requires Order object access, which Shopify outright denies until
that declaration exists: `"This app is not approved to access the Order object"` (code `ACCESS_DENIED`).
This is not something Sanocea's code can work around - it is Shopify's own data-protection gate.

### Real Shopify behaviors that differed from simulator/documentation assumptions

1. **`productSet` requires `variants[].optionValues`** even for a plain single-SKU product with no real
   variant dimension - "Expected value to not be null." Fixed by declaring one option named "Title"
   with value "Default Title" (Shopify's own simple-product convention), at both the product
   (`productOptions`) and variant (`optionValues`) level.
2. **`productSet` has no implicit upsert-by-SKU.** Without an `identifier`, every call - including one
   Sanocea intends as an "update" - creates a brand-new product. Fixed by querying
   `productVariants(query: "sku:...")` for an existing product first and passing `identifier: {id: ...}`
   when found - mirroring the role `WooCommerceConnector._find_product_by_sku` already plays for the
   real WooCommerce connector.
3. **`InventorySetQuantitiesInput` has no `ignoreCompareQuantity` field** in this store's current
   schema - a documentation-sourced assumption that didn't hold. It instead REQUIRES
   `changeFromQuantity` (the currently-known quantity) for every quantity write - there is no
   unconditional absolute-set path.
4. **The `@idempotent` directive requirement is broader than documented** - not only `refundCreate`
   (the only mutation the public docs highlighted), but also `inventorySetQuantities`,
   `inventoryActivate`, and `inventoryItemUpdate` all rejected requests outright without it: `"The
   @idempotent directive is required for this mutation but was not provided."`
5. **A freshly created variant's `InventoryItem` has no `InventoryLevel` at any location at all** - not
   a level with quantity 0, no record - until explicitly activated there via `inventoryActivate`.
6. **The deepest, most consequential finding: a `productSet`-created variant's `InventoryItem.tracked`
   defaults to `false`.** While untracked, BOTH `inventoryActivate` and `inventorySetQuantities` return
   a full success payload - zero `userErrors`, a real `inventoryAdjustmentGroup`/`inventoryLevel` id -
   and have **zero effect** on the item's actual quantity, which silently stays 0 regardless of what was
   requested. This is the kind of failure class a simulator can never surface: a real platform accepting
   a mutation as valid while quietly not doing what it appears to do. Root-caused via direct, isolated
   live queries (confirmed the SAME literal-vs-variable argument syntax was a red herring from a less
   isolated test) down to the `tracked` flag specifically. Fixed by unconditionally calling
   `inventoryItemUpdate(input: {tracked: true})` before every activate/set call.
7. **Real Shopify order webhook/order-create payloads carry no monotonic sequence number** - confirmed
   by inspecting the real Admin GraphQL `Order` object's own fields (`updatedAt`, no `updated_sequence`
   equivalent exists). `updated_at` timestamp comparison is used instead (matching
   `WooCommerceConnector`'s existing approach for the identical reason).
8. **`orderCreate`'s `priceSet.shopMoney.currencyCode` must match the shop's own currency exactly** -
   Sanocea's project-wide default (INR, used throughout every simulator workload) does not match this
   real store's actual currency (USD, queried via `shop { currencyCode }`, never assumed).
9. **Order/Customer access requires an explicit, one-time Protected Customer Data declaration** in the
   Dev Dashboard, even for a development-store-only app (no review/approval wait, but the declaration
   itself is mandatory and was not yet completed for this app) - `ACCESS_DENIED` otherwise, with a
   direct link to the relevant docs page in the error itself.
10. A harness-side finding, not a Shopify one: a `orderCreate` mutation call that omits `userErrors` from
    its own selection set gets a silently-unexplained `null` result on any real rejection - Shopify does
    not force-include `userErrors` in the response; the CALLER must request it to see why a mutation
    silently no-opped. Fixed in the certification harness for both order-creation call sites.

---

## Resumed after Protected Customer Data approval - additional findings and full completion

Once the Protected Customer Data declaration was completed (Manpreet, in the Dev Dashboard), the
certification resumed and surfaced three more real, genuine issues before reaching a clean run:

11. **The harness never actually called `register_webhooks()`.** The very first resumed attempt failed
    order-webhook delivery for the mundane reason that no subscription existed at all - a real gap in
    the certification script itself (not a Shopify behavior), now fixed: `register_webhooks()` is called
    explicitly, against the real tunnel URL, before the test order is created.
12. **`webhookSubscriptionCreate` is not idempotent** - a second call for the exact same (topic, uri)
    pair on a re-run against an unchanged tunnel URL fails outright: `"Address for this topic has
    already been taken."` Fixed by having `register_webhooks()` list existing subscriptions first and
    reuse any that already match, rather than blindly creating (or fabricating success).
13. **A genuine connector bug, not a Shopify finding:** the `refundCreate` mutation string declared only
    `$input` in its operation signature while also using `$idempotencyKey` in the `@idempotent` directive
    - GraphQL requires every variable used anywhere in an operation, including directive arguments, to
    be declared. Fixed by adding the missing `$idempotencyKey: String!` declaration.
14. **A refund transaction on any gateway other than `cash`/`store-credit`/`exchange-credit` requires a
    `parentId`** referencing the order's original sale transaction - confirmed live
    ("Transactions not on 'store-credit', 'exchange-credit', or 'cash' gateways require a parent_id"),
    and an order with **no** captured payment transaction at all has no parent to reference regardless
    of gateway (`"Unable to find parent transaction"`) - a genuine business rule (nothing to refund money
    from), not a defect. Fixed two ways: `create_refund` now defaults to gateway `"cash"` (Shopify's own
    sanctioned manual/ledger gateway - matching the same concept `WooCommerceConnector`'s
    `api_refund=false` already models for COD orders), and the certification harness now attaches a real
    `SALE`/`SUCCESS` transaction when creating its test order, so there is a legitimate transaction to
    refund against later.

## Final status

**REAL EXTERNAL PLATFORM — DEVELOPMENT STORE: PASS**

All 9 real, independently-verified checks passed against the real store, through the real production
app, over the real tunnel: product create, independent read-back, update-not-duplicate, location-scoped
inventory, real Shopify webhook delivery creating the canonical Sanocea order, webhook-replay
idempotency (no duplicate order), real fulfilment via the FulfillmentOrder API, real cancellation, and a
real refund with a real parent transaction. Full machine-readable evidence:
`tests/fixtures/phase11_merchant/generated/shopify_dev_store_certification_report.json` (the final,
all-PASS run). Full regression re-confirmed clean (130 passed, 0 failed) after every fix in this
document. Fourteen genuine, real-store-confirmed behavioral findings were surfaced and fixed along the
way - exactly the signal a simulator-only test suite could never have produced.
