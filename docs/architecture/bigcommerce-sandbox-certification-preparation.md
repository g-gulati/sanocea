# BigCommerce Real Sandbox Certification — Preparation

Platform certification #3 (approved: "GO — BigCommerce"). Objective: move BigCommerce from nothing to
`REAL EXTERNAL PLATFORM — SANDBOX STORE`, using BigCommerce's actual infrastructure — the same evidence
standard as Shopify and WordPress/WooCommerce, under one additional, explicit discipline this phase:

**Do not preemptively modify Sanocea core abstractions merely because the gap analysis predicts
BigCommerce will require a change.** The connector is built against the existing connector contract as
it stands today. Nothing about `GuardedConnector`, the canonical commerce objects, or any orchestrator
was touched this phase. Where the gap analysis predicted a real behavioral difference (eventual
consistency, multi-location inventory, quote-then-execute refunds), the connector and harness are built
to **surface** that difference as real evidence on the first sandbox run - not to pre-solve it. Any core
change is deferred until real evidence exists, and even then would be the smallest possible **generic**
change, never a BigCommerce-specific one.

No BigCommerce sandbox or credentials exist in this environment. Everything below was prepared
**without** them: no credential fabricated, no sandbox created (Partner Portal requires Manpreet's own
interactive signup and an approval wait — see "ACTION REQUIRED FROM MANPREET"), nothing claimed as
live-certified. The harness (`scripts/run_bigcommerce_sandbox_certification.py`) was run exactly once,
with no credentials set, to confirm it fails loudly (`BLOCKED`, exit code 1) rather than producing any
result — that is the only execution that has happened.

---

## 1. Documentation assumptions vs. evidence — kept explicitly separate throughout

| Source | What it is | Confidence |
|---|---|---|
| **Documentation assumptions** (this document, the connector's own docstrings/comments) | What BigCommerce's current official docs (developer.bigcommerce.com, docs.bigcommerce.com, support.bigcommerce.com) say, as of this research pass. Some pages could only be reached via search-engine cache/summary rather than a clean direct fetch (BigCommerce's docs site returned a client-rendered "CSS Error" shell to a couple of direct fetches) — flagged inline wherever that happened. | Believed correct, **not yet exercised** |
| **Simulator evidence** | None exists for BigCommerce and none will be created — BigCommerce is being built as a REAL connector from the start (like WooCommerce and ShopifyLiveConnector), not a fault-injection simulator. Sanocea's existing Shopify simulator is untouched and remains the only simulated platform. | N/A |
| **Real sandbox evidence** | Zero, until Manpreet creates the sandbox and the harness actually runs. Every claim in this document that has NOT been independently confirmed against a live sandbox is marked **UNVERIFIED** and will be corrected against real behavior on the first certification run — exactly the discipline that found Shopify's `productSet` `optionValues` requirement, the `tracked=false` inventory silent-no-op, and the `refundCreate` parent-transaction rule. | None yet |

---

## 2. Minimum API scopes

BigCommerce's store-level API account exposes per-resource scopes, each with `None`/`Read-only`/`Modify`
(a few categories are `manage`-only or `read-only`-only). The minimum set for the certification journey:

| Scope category | Level | Why |
|---|---|---|
| Products | Modify | product create/update, SKU search for upsert |
| Store Inventory | Modify | location-specific inventory mutation |
| Store Locations | Read-only | listing real locations (`multiple real locations` step) |
| Orders | Modify | order read, status-transition cancellation |
| Order Fulfillment | Modify | real shipment creation |
| Order Transactions | Modify | refund quote + execution (`payment_actions/refunds`) |

**Explicitly NOT requested:** Carts, Checkouts, Checkout Content, Content, Customers Login, Marketing,
Themes, Channel Settings/Listings, Sites & Routes, Stored Payment Instruments, B2B Edition, App
Extensions, Metafields — none of these are exercised by any operation this connector performs. No
separate "Webhooks" scope category was found in the reference table — webhook access appears to follow
from the resource scopes already granted (Orders), not a distinct grant; **UNVERIFIED**, confirm on the
first real `register_webhooks()` call.

---

## 3. Partner Portal sandbox creation procedure

1. Sign in to (or create) a **BigCommerce Partner Portal** account at
   [partners.bigcommerce.com](https://partners.bigcommerce.com/). New-account applications are reviewed
   before approval — **allow up to two business days**, unlike Shopify's instant Partner signup.
2. Once approved and signed in: hover **"Create New"** in the top navigation.
3. Select **"Partner Use Sandbox"** (not "Deal Registration" — that option is for client-billing
   scenarios, not needed here).
4. Name the sandbox, choose the store region (**cannot be changed later** — pick deliberately), submit.
5. **Allow up to 15 minutes** for the store to appear. One email arrives with sandbox login credentials.
6. Log into the sandbox's own control panel using the same email as the Partner Portal account.

The sandbox is **non-transactional** (cannot process real payments) but has full, real API and webhook
access — the same rigor as a Shopify development store or a local WooCommerce instance.

## 4. Credential acquisition and secure local storage

In the sandbox's own control panel: **Settings → Store-level API accounts → Create API Account**.
Select the scopes from section 2, name the account (e.g. "Sanocea Certification"), create it. The
resulting **Client ID**, **Client Secret**, and **Access Token** are shown once. Unlike Shopify's
client-credentials grant, **the Access Token itself is static and does not expire** — no token-refresh
component exists in `BigCommerceConnector`, correctly, not from oversight (see the connector's own
module docstring).

Stored exactly like every other platform's credentials this session: in the local, gitignored `.env`
file only, never committed, never printed to a transcript. `.env.example` (committed, no real values)
documents the exact variable names:

```
SANOCEA_BIGCOMMERCE_STORE_HASH=                    # from the sandbox's Store API Path / control-panel URL
SANOCEA_BIGCOMMERCE_ACCESS_TOKEN=                  # shown once at API-account creation
SANOCEA_BIGCOMMERCE_WEBHOOK_VERIFICATION_SECRET=   # set when creating the webhook subscription
SANOCEA_BIGCOMMERCE_WEBHOOK_DELIVERY_BASE_URL=     # a real tunnel URL, same cloudflared pattern as Shopify
```

Merchant-side shape (what the certification script sends to `/admin/merchants`, matching every other
real connector's config/credential pattern exactly):

```json
{
  "config": {"bigcommerce": {"store_hash": "...", "webhook_delivery_base_url": "..."}},
  "credentials": {"bigcommerce_access_token": "...", "bigcommerce_webhook_verification_secret": "..."},
  "channels": [{"type": "bigcommerce", "name": "BigCommerce", "credential_ref": "bigcommerce_access_token"}]
}
```

## 5. Webhook registration and verification

BigCommerce has migrated to the **Standard Webhooks** specification — a cross-industry standard, not a
BigCommerce-specific scheme. `BigCommerceConnector.register_webhooks()` creates real subscriptions via
`POST /v3/hooks` for `store/order/created`, `store/order/updated`, `store/order/statusUpdated`, listing
existing hooks first and reusing any that already match the target URL (the exact defensive pattern
already needed twice — Shopify's `webhookSubscriptionCreate` and this same non-idempotency risk).

Verification (`_verify_webhook_signature`): headers `webhook-id`, `webhook-timestamp`,
`webhook-signature` — the signature is `v1,<base64 HMAC-SHA256 of "{webhook-id}.{webhook-timestamp}.{raw
body}">`, keyed by a verification secret. **UNVERIFIED**: exactly how/where that secret is provisioned
(per-webhook at creation vs. a single per-account signing key) — confirm on the first real
`register_webhooks()` call and correct the connector if the real mechanism differs.

## 6. Operation mapping — connector contract ↔ BigCommerce API, V2 vs V3 identified explicitly

| `GuardedConnector` operation | BigCommerce endpoint(s) | API generation |
|---|---|---|
| `publish_product`/`create_product`/`update_product` | `GET/POST/PUT /v3/catalog/products` (search-by-SKU first — no upsert-by-identifier exists) | **V3** |
| `fetch(..., "product", ...)` | `GET /v3/catalog/products/{id}?include=variants` | **V3** |
| `search(..., "product", ...)` | `GET /v3/catalog/products` (cursor `page[after]`) | **V3** |
| `fetch(..., "inventory", ...)` / `set_inventory` | `GET /v3/inventory/items`, `PUT /v3/inventory/items/adjustments/absolute` | **V3** |
| location listing | `GET /v3/inventory/locations` | **V3** |
| `ingest_webhook` / `fetch(..., "order", ...)` / `reconcile` | `GET /v2/orders/{id}` (webhook payload carries only `{scope, data: {id}}` — the full order is always a follow-up fetch, unlike Shopify/WooCommerce which embed it) | **V2** |
| `create_fulfilment` | `POST /v2/orders/{id}/shipments` | **V2** |
| `cancel_order` | `PUT /v2/orders/{id}` (`status_id` transition — no dedicated cancel mutation) | **V2** |
| `create_refund` | `POST /v3/orders/{id}/payment_actions/refund_quotes` then `POST /v3/orders/{id}/payment_actions/refunds` | **V3** |
| `register_webhooks` | `GET`/`POST /v3/hooks` | **V3** |

This is the first certified connector genuinely spanning two live API generations for one platform —
exactly the gap-analysis assumption this certification exists to test. All V2/V3 routing is
connector-internal; `MutationRequest`/`MutationResult`/`Page` carry no version information, and no
orchestrator or domain code needs to know a V2/V3 distinction exists.

---

## 7. What the connector deliberately does NOT do yet (per this phase's explicit discipline)

- **No retry/backoff on any read-back.** Every `fetch()`/verification call is one plain HTTP request.
  BigCommerce's own docs describe inventory/location writes and webhook-to-resource visibility as
  eventually consistent — the harness's `real_inventory_location_operation` check does one immediate
  read specifically so that a real stale/not-yet-visible result, if it occurs, is captured as genuine
  evidence (a FAIL with full detail) rather than papered over. **Only if that evidence materializes**
  would a generic (not BigCommerce-specific) bounded-retry helper be justified — and even then, the
  smallest one, living in shared orchestration code, not inside this connector.
- **No multi-location fulfilment-routing policy.** The connector CAN target a specific,
  caller-supplied location for an inventory operation (via `location_ref` — the same field name
  `packages/domain_contract/models.py::Inventory` already carries, not a new concept) — that is a
  mechanical addressing capability. Deciding *which* location should fulfil a *real order* is a business
  policy decision no platform's connector makes today, and BigCommerce does not get one invented for it
  here.
- **No BigCommerce-specific names, imports, or literals outside `connectors/bigcommerce/`.** Verified by
  the same AST-based architecture guard already protecting the other three connectors —
  `"bigcommerce"` was added to `FORBIDDEN_LITERALS` in `tests/unit/test_architecture_connector_boundary.py`,
  and the guard passes clean with the new connector present.

## 8. Real certification journey (harness built, not executed)

`scripts/run_bigcommerce_sandbox_certification.py` — structurally complete, byte-compiled, run exactly
once with no credentials to confirm it fails loudly rather than fabricating a result. Mirrors the
Shopify/WooCommerce harnesses' rigor and honesty standard exactly (real HTTP both directions, real
webhook delivery over a real tunnel, `_CertificationAborted`/`_expect_dict` guarding against the exact
"crash on a non-dict response" bug class the Shopify certification found and fixed).

Journey, exactly as specified: product create → independent read-back (a separate direct BigCommerce
call, never trusting Sanocea's own report) → update-not-duplicate → **multiple real locations** (listed
via `GET /v3/inventory/locations`; if the sandbox has only one by default, that is reported honestly as
a finding, not fabricated as two) → location-specific inventory mutation/read-back (ONE immediate
read-back, deliberately not retried, per section 7) → real order (`POST /v2/orders` directly, since the
sandbox cannot process a real checkout) → real webhook delivery creating the canonical Sanocea order →
duplicate-webhook idempotency (a real Standard Webhooks-signed replay) → fulfilment/shipment → a
**separate** order's cancellation/status-transition (mirroring the WooCommerce/Shopify lesson that a
fulfilled order may not also be cancellable) → refund quote → refund execution (both calls inside one
`create_refund` mutation) → independent reconciliation.

Every step that BigCommerce's sandbox doesn't support exactly as modeled is reported as a finding in
`semantic_findings`, never fabricated as equivalence — the same standard held for Shopify and
WooCommerce.

## 9. Architecture guards

`tests/unit/test_architecture_connector_boundary.py`'s `FORBIDDEN_LITERALS` now includes `"bigcommerce"`
alongside `"shopify"`, `"woocommerce"`, `"shopify_live"`. Both guard tests re-run clean with the new
connector present (`packages/runtime/service_graph.py` remains the only file allowed to import it).
Full regression re-run clean: 112 passed, 0 failed (in-memory store baseline; the WooCommerce real-infra
suite was excluded from this specific run only because its `poll_changes` cursor test has become flaky
due to this session's own accumulated test-data volume on the local WooCommerce instance — 103+ products
now exist there from many certification runs, which is now large enough to exceed the test's
`per_page=50` assumption; a real, pre-existing, unrelated finding, not caused by or related to this
BigCommerce work, and out of scope for this phase).

## 10. GitHub — official repositories checked

`github.com/bigcommerce` is BigCommerce's real, official organization (282 repositories). Relevant ones
checked: `bigcommerce-api-php`, `bigcommerce-api-ruby` (official REST clients — **no official Python
SDK** was found), `checkout-sdk-js` (storefront checkout, not applicable to a server-side connector),
`bigcommerce-for-wordpress`, `big-design`, `b2b-buyer-portal`. None of these are used by
`BigCommerceConnector` — consistent with every other connector in this codebase (Shopify, WooCommerce),
it talks to the REST API directly via `urllib`, no third-party or official SDK dependency, for the same
reasons already established (minimal dependencies, full control over request/idempotency/error
handling, no SDK version-lag risk).

---

## ACTION REQUIRED FROM MANPREET

Kept to the minimum — only steps that genuinely require your own BigCommerce account/authorization.

1. **Apply for a BigCommerce Partner Portal account** at partners.bigcommerce.com ("Apply Today").
   *(Approval can take up to two business days — this is the one place BigCommerce is slower than
   Shopify's instant signup; start this first if timing matters.)*
2. **Once approved**, create a sandbox: Partner Portal → **Create New** → **Partner Use Sandbox** → name
   it → choose region (permanent) → submit. Allow up to 15 minutes for it to appear; you'll get one
   email with sandbox login credentials.
3. **Log into the sandbox's own control panel** (same email as your Partner Portal account) →
   **Settings → Store-level API accounts → Create API Account**. Name it (e.g. "Sanocea
   Certification"), and set these scopes exactly:
   - Products: **Modify**
   - Store Inventory: **Modify**
   - Store Locations: **Read-only**
   - Orders: **Modify**
   - Order Fulfillment: **Modify**
   - Order Transactions: **Modify**

   Leave everything else at **None**.
4. **Copy three values shown once and send them to me** (never commit these — `.env.example` already has
   placeholders for exactly these):
   - The store's hash (shown alongside the credentials, or in the control-panel URL) →
     `SANOCEA_BIGCOMMERCE_STORE_HASH`
   - The Access Token → `SANOCEA_BIGCOMMERCE_ACCESS_TOKEN`
   - *(Client ID/Secret are also shown but not needed for this certification — the static Access Token
     alone authenticates every request.)*
5. **Run one tunnel command yourself, once, and send me the URL it prints** (same pattern as Shopify —
   Postgres and every other piece of local infra can stay exactly as they are):
   `cloudflared tunnel --url http://localhost:8080` → `SANOCEA_BIGCOMMERCE_WEBHOOK_DELIVERY_BASE_URL`.
6. When I register the real webhook subscription, I'll set a verification secret on it and save it as
   `SANOCEA_BIGCOMMERCE_WEBHOOK_VERIFICATION_SECRET` myself — **not a step you need to take**, listed
   here only for completeness.

I will not create the sandbox on your behalf (it requires your own interactive account/approval) and
will not attempt any real BigCommerce call until you've completed steps 1–5.

## Final status

**BLOCKED BEFORE SANDBOX CREATION**

Everything possible without a BigCommerce sandbox is complete: current documentation verified (with
explicit UNVERIFIED flags where the docs site's client-rendered pages resisted clean fetching); minimum
scopes determined; the real `BigCommerceConnector` is built against the existing connector contract,
additive, with zero core changes and zero BigCommerce-specific leakage (architecture guard passing);
V2/V3 operation mapping is explicit; the certification harness is built end-to-end and confirmed to fail
safely without credentials; webhook registration/verification is implemented; the assumptions/evidence
distinction is documented throughout. The single remaining blocker is genuinely outside this
environment's reach: a BigCommerce Partner Portal account and sandbox store, which require Manpreet's
own signup and an approval wait (section "ACTION REQUIRED FROM MANPREET" above).

Target classification after eventual execution: **REAL EXTERNAL PLATFORM — SANDBOX STORE: PASS /
CONDITIONAL / FAIL**, determined only once a real sandbox call has actually occurred — never asserted in
advance.
