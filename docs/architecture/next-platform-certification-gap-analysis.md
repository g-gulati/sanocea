# Third Platform Certification — Gap Analysis

Objective: not connector count. Identify which candidate platform most **materially challenges**
Sanocea's platform-independent architecture — and specifically, which assumptions in
`GuardedConnector`/`StorefrontConnectorRegistry`, the canonical commerce objects, the orchestrators, and
the certification-harness pattern itself, Shopify + WooCommerce have **not yet** forced us to confront.

Researched against each platform's current official developer documentation (September 2026). No
connector code written. No architecture changed.

---

## What Shopify + WooCommerce have already proven

Two different webhook-verification schemes (HMAC-SHA256 base64 over raw body, different headers); two
different auth models (client-credentials token refresh vs. OAuth1 request-signing) cleanly abstracted
per-merchant by `StorefrontConnectorRegistry`; two different variant shapes (Shopify's inline
variant/simple-product convention, WooCommerce's parent+separate-variations resource); two different
pagination models (GraphQL cursor vs. REST page-number); two different refund models (Shopify's
gateway-agnostic `refundCreate`, WooCommerce's ledger-only `api_refund=false`) — all real, all
independently certified.

## What they have NOT tested — the open gaps

1. **Eventual consistency as a systemic platform behavior.** Every real certification's "read back and
   confirm" check (`ProductPublicationService.verify()`, every `real_X_reflected` harness assertion) does
   **one immediate read after one mutation** and treats it as ground truth. The only retry loop that
   exists anywhere in either certification is for *async webhook delivery* (polling for the canonical
   order to appear) — a different kind of asynchrony (event-delivery lag) from *read-after-write
   staleness of the same resource via the same API*. `GuardedConnector` has no retry/backoff-on-staleness
   primitive at all. Neither Shopify (synchronous in practice) nor WooCommerce (only Action-Scheduler
   webhook *delivery* is async) forced this confrontation.
2. **Real multi-location inventory routing.** The canonical `Inventory.location_ref: str` field and
   `PostOrderOperationsService.reserve_inventory_for_order(..., location: str = "default")` exist, but
   every real flow built so far passes a single hardcoded `"default"`. Shopify *has* real Location-scoped
   inventory (we exercised it for real this session) but only ever against **one**, auto-discovered
   location. WooCommerce has no location concept at all. There is no orchestration logic anywhere for
   "which location fulfills this order," "split fulfillment across locations," or "reconcile inventory
   divergence per-location."
3. **A real multi-step payment transaction lifecycle.** Both certified connectors model refund as one
   flat action. Neither canonical `Refund`/`Payment` nor any orchestrator reasons about a genuine
   Authorize → Capture → Void/Refund state machine with capture as a distinct, separately-timed step.
4. **A platform with a genuinely fragmented, multi-generation API surface.** Both certified connectors
   talk to exactly one API surface (Shopify: one GraphQL version at a time; WooCommerce: one REST `v3`).
   Nothing has tested whether one connector cleanly spanning two structurally different live API
   generations for different resource types is actually workable within the current abstraction.
5. **Webhook-push as a non-default ingestion path.** `poll_changes` exists on both connectors but has
   only ever been exercised as a supplementary sync capability. Its viability as the *primary* real-order
   ingestion path (for a platform with no native webhooks at all) has never been proven.

---

## Platform findings

| | Wix eCommerce | Adobe Commerce / Magento OS | BigCommerce | PrestaShop |
|---|---|---|---|---|
| Free real dev/test env, no production merchant | ✅ free Dev Center "development site," full Stores/Payments/API | ⚠️ self-hostable free, but no official lightweight image (`markshust/docker-magento` is unofficial) | ✅ free Partner Portal sandbox store, non-transactional but full API+webhooks | ✅ official Docker Compose / "Flashlight" |
| Products/variants | Option→Choice→Variant (Catalog V3) | Configurable products, EAV attribute sets | Variant options + modifiers; every option-value combo created explicitly | "Combinations" (base + attribute rows) |
| Inventory/location | Real, but orders always deduct from the **default** location only | **Deepest**: Multi-Source Inventory, first-class Sources→Stocks | Real, first-class, **explicitly documented async** writes | Flat by default; "Advanced Stock Management" opt-in, API surface unclear |
| Refund/payment model | Real Authorize→Capture→Refund/Void state machine | Credit-memo via REST; offline test methods available | Two-call: quote, then execute | Hook-driven; no confirmed public refund API |
| Cancellation | First-class Orders API action | — | **No dedicated cancel mutation** — status transition only | Gated by order state, hook-driven |
| Returns/RMA | Not confirmed as a distinct API | **Adobe Commerce (paid) only — absent from Open Source** | No clean admin RMA API found | Disabled by default, hook-driven |
| Real webhooks | ✅ JWT-signed payload (not HMAC-over-body) | ❌ **Adobe Commerce/App Builder only — absent from Open Source** | ✅ Standard Webhooks spec (`webhook-id`/`timestamp`/`signature`) | ❌ **no native webhooks** — hooks are in-process PHP only; real HTTP webhooks need an unofficial marketplace module |
| Auth model | OAuth2 client-credentials + `instance_id` (3-part identity), 4h token | Admin token **or** OAuth **1.0a** (legacy) | Simple store-level API key **or** full OAuth app-install | Legacy Basic-Auth key **or** new OAuth2 AdminAPI (thin docs) |
| Idempotency directive | Not confirmed | Not confirmed | No formal directive; caller-managed via webhook `hash` | None |
| Documented eventual consistency | Yes, but for the generic Data/CMS layer — unconfirmed for commerce objects specifically | Yes, real and well-known (async indexers) | **Yes — explicitly, for inventory writes AND webhook-to-resource visibility, in the same docs Sanocea would build against** | Not documented (assumed synchronous, single-process) |
| Commercial relevance to SMB/DTC | Strong, growing (~7.4% share, India top-3 market) | Weak — enterprise/mid-market, declining SMB share | Mid-market/enterprise-leaning (75% ARR from enterprise) but real presence outside the US | Strong in France/Europe/LatAm, weak elsewhere |
| Effort estimate | **M** | **XL** | **M** | **L** |

Full per-criterion research (pagination, rate limits, exact API endpoints, citations) is preserved in
this session's fork transcripts; the table above is the material summary for the decision.

---

## NEXT PLATFORM RECOMMENDATION

**BigCommerce.**

## WHY THIS PLATFORM

It is the only candidate that delivers the two deepest, still-completely-unchallenged architectural gaps
in the same platform, with a certification path we already know how to execute (free sandbox, real
webhooks, no unofficial dependencies):

- **Eventual consistency is BigCommerce's own explicitly documented behavior** — "a short delay before
  data is updated," a `transaction_id` returned from location/inventory writes, and an explicit warning
  that a resource "may not be immediately available after a webhook notification." This is the single
  most authoritative, first-party confirmation of exactly the gap identified above, across all four
  candidates — not an inferred risk (Wix's eventual-consistency doc is for its generic Data/CMS layer,
  unconfirmed for commerce objects; Magento's is real but bundled with an XL-effort, webhook-less,
  wrong-commercial-segment platform).
- **Genuinely native, first-class multi-location inventory** (`/v3/inventory/locations`), a real second
  test of the canonical `Inventory.location_ref`/`reserve_inventory_for_order(location=...)` gap, at
  lower overall integration cost than Magento's MSI.
- A real, structurally fragmented **REST V2/V3 API surface** for one platform — a genuine test of whether
  one connector can cleanly span two live API generations, which no certified connector has had to do.
- Free, real, non-transactional **sandbox store** via the Partner Portal — same rigor as a Shopify dev
  store, no card, no production merchant, real webhooks (Standard Webhooks spec — itself a widely-adopted
  cross-industry standard worth Sanocea's webhook-verification code learning to speak).
- Real commercial relevance outside the pure Shopify/WooCommerce SMB overlap, without Magento's
  enterprise-only mismatch.

Wix is a strong second choice (JWT webhook verification, a real 3-part auth identity, a genuine
Authorize→Capture→Refund/Void lifecycle) and should be queued next after BigCommerce, not rejected.

## ARCHITECTURAL ASSUMPTIONS IT WILL TEST

1. **`GuardedConnector.fetch()`/`reconcile()` assume synchronous read-after-write consistency.** No
   retry/backoff-on-staleness primitive exists anywhere in the connector SDK today. BigCommerce will
   force one to exist.
2. **`Inventory.location_ref`/`reserve_inventory_for_order(location=...)` have never carried real
   multi-location semantics** — always a single hardcoded `"default"` in every certified flow so far.
3. **The connector-agnostic `create_refund` action shape (`{external_order_id, amount, reason}` →
   one `MutationResult`) has never absorbed a platform that needs an intermediate server-side step**
   (BigCommerce's quote-then-execute refund) — should work entirely inside `_execute_mutation()`, but
   is genuinely unproven.
4. **`Capability.api_versions: list[str]` has never actually needed to list more than one concurrent,
   structurally different API generation for one connector** — structurally supports it already
   (it's a list), but this would be the first real proof.
5. **The certification-harness pattern itself has never needed retry-with-backoff on a plain read-back
   check** (only ever on webhook-delivery polling) — a genuinely new harness convention, not just more
   of the same shape.
6. Cancellation-as-status-transition (BigCommerce has no dedicated cancel mutation) reconfirms the
   WooCommerce finding rather than testing something new — not novel here, noted for completeness.

## REAL-PLATFORM CERTIFICATION METHOD

1. Create a free BigCommerce sandbox store via the Partner Portal (no card required, non-transactional).
2. Start with a **store-level API account** (Settings → API Accounts) — matches WooCommerce's simplicity
   for a first real certification; the full OAuth app-install flow remains available later if
   app-distribution realism is ever needed.
3. Register real Standard Webhooks subscriptions against a real tunnel (the same `cloudflared tunnel
   --url http://localhost:8080` pattern already proven for Shopify), verifying the `webhook-id` /
   `webhook-timestamp` / `webhook-signature` scheme for real.
4. Certification harness introduces bounded retry-with-backoff specifically on read-back/reconciliation
   checks (inventory, webhook-to-resource visibility) — the new pattern item 5 above requires — while
   keeping the existing immediate-check shape for anything BigCommerce's own docs don't flag as async.
5. Same standard as Shopify/WooCommerce throughout: real product → independent read-back → update →
   real multi-location inventory operation → real order → real webhook delivery → duplicate-webhook
   idempotency → real fulfilment (multi-shipment) → cancellation (status-transition) → real two-call
   refund → reconciliation. Report every real BigCommerce behavior that differs from assumption, exactly
   as done for Shopify and WooCommerce — do not fabricate equivalence where BigCommerce's real behavior
   differs.

## EXPECTED CORE CHANGES

Deliberately minimal, and only where the gap is genuinely cross-cutting (not BigCommerce-specific):

- A small, generic **bounded-retry/backoff-on-staleness helper**, usable by any orchestration code that
  reads back a connector `fetch()` result to verify a just-made mutation (e.g.
  `ProductPublicationService.verify()`) — belongs in shared orchestration code, not inside a
  `BigCommerceConnector`, because deciding *whether and how long to retry a possibly-stale read* is a
  policy decision, not a platform-specific mechanic (mirrors Sanocea's own existing principle: connectors
  never own retry/idempotency policy — `IdempotencyService` and the uncertain-mutation-recovery pattern
  already live outside connector code for the identical reason).
- The certification harness's own retry-with-backoff convention for read-back checks (harness-layer, not
  domain code, but a new reusable pattern worth extracting once, not reinvented per platform).
- **Explicitly NOT required for a basic PASS:** a full multi-location *fulfillment-routing* policy (which
  location ships this order, split-shipment logic). The canonical model and orchestrator signature
  already accept a `location` parameter; wiring real routing logic is a separate, larger, discretionary
  decision — flagged here, not undertaken as part of reaching certification.

## WHAT SHOULD REMAIN CONNECTOR-ONLY

- BigCommerce's own auth mechanics (store-API-key or OAuth), its V2/V3 request routing internals, the
  refund quote-then-execute sequencing, cursor-pagination shape, and rate-limit header parsing/backoff —
  all connector-internal, exactly like every platform-specific mechanic in `ShopifyLiveConnector` and
  `WooCommerceConnector` today.
- Resolving a product/order to its BigCommerce-specific location/inventory identifiers via BigCommerce's
  own Locations API — connector-internal, mirroring `ShopifyLiveConnector._ensure_location_gid()` /
  `_inventory_item_for_product()`.
- Standard Webhooks signature verification — connector-internal, the same architectural slot Shopify's
  and WooCommerce's own (different) HMAC schemes already occupy.

## GO / NO-GO

**GO — BigCommerce**, as the next real-platform certification.

**NO-GO this round:**
- **Adobe Commerce / Magento Open Source** — no native webhooks and no RMA in the free edition (both
  Adobe Commerce/paid-only), XL effort, and a commercial segment (enterprise/mid-market, declining SMB
  share) that doesn't match Sanocea's likely target merchants.
- **PrestaShop** — no native outbound webhooks at all (hooks are in-process PHP only; real HTTP delivery
  needs an unofficial marketplace module), a split legacy/new API surface with thin documentation on the
  new side, L effort. Worth revisiting specifically as a deliberate **poll_changes-as-primary-ingestion**
  exercise later — a genuinely different, valuable test this platform is well-suited for — but not as
  "the next platform" by default.
- **Wix** — not rejected, queued as the strong second choice after BigCommerce (JWT webhook verification,
  3-part auth identity, real Authorize→Capture→Refund/Void lifecycle are all real, valuable, unproven
  assumptions worth testing next).

---

## Terminology update

WooCommerce is the ecommerce layer running on WordPress — its REST API is integrated with the WordPress
REST API, and WooCommerce itself supplies the commerce resources and webhook system Sanocea's connector
integrates with. Merchant-facing material should say **"WordPress/WooCommerce"**; the technical
connector, channel type, module path, and class name remain **WooCommerce**
(`connectors/woocommerce/`, `WooCommerceConnector`, `type: "woocommerce"`) — no rename, no separate
"WordPress connector." Applied this session: the `Channel.name` display label in the certification
scripts (`scripts/run_woocommerce_platform_independence.py`,
`scripts/run_multi_platform_isolation_proof.py`) now reads `"WordPress/WooCommerce"`; the convention
itself is documented in `docs/architecture/woocommerce-platform-independence.md`.
