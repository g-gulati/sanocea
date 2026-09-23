# Ecommerce Platform Testing Infrastructure — OSS Landscape Audit

Status: `RESEARCH ONLY — NO CODE CHANGES MADE`

Requested before any further Shopify/WooCommerce test infrastructure work, to determine whether Sanocea
should compose existing OSS instead of expanding its own simulators. No repos were cloned; nothing was
implemented. This is the recommendation, not an implementation.

## Method

Investigated the specifically named candidates (`Shopify/cli`, `sayjava/mock-shopify`,
`ctrlaltdylan/mock-bridge`, `woocommerce/woocommerce`, `woocommerce/woocommerce-e2e-boilerplate`) plus
broader search for Shopify mock/emulator/webhook-simulator/test-data-generator projects, WooCommerce
Docker/e2e harnesses, and generic ecommerce API contract-testing frameworks (Pact/Prism/WireMock).
Evaluated each against Sanocea's actual connector contract
(`packages/connector_sdk`: `Capability`/`MutationRequest`/`MutationResult`/`GuardedConnector`) — Admin
vs Storefront API, read/write per resource, webhooks, auth, rate limits, pagination, duplicate-event
handling, eventual consistency, failure injection, current API-version compatibility, maintenance,
Docker/self-hostability, license.

## Findings by candidate

### Shopify side

| Candidate | What it actually is | Verdict |
|---|---|---|
| `Shopify/cli` | Official app-development CLI (scaffolding, `shopify app dev` tunnel, deploy). **Not a mock** — dev tooling around a real store connection. | Not applicable to this question. |
| `sayjava/mock-shopify` | Mocks the **Storefront API** (shopper-facing cart/checkout), not the Admin API Sanocea needs. No orders/fulfilments/refunds/webhooks. No state persistence. Targets API version 2023-07 (3 years stale). 1 star, 6 commits. | Wrong surface + effectively abandoned. Do not use. |
| `ctrlaltdylan/mock-bridge` | Mocks Shopify **App Bridge** (embedded-admin-UI iframe: modals, toasts, session tokens). Sanocea is a headless backend integration with no embedded UI. | Solves a problem Sanocea doesn't have. Do not use. |
| "Shopify/cli-graphql-examples" | Could not locate a repo under this name. | Not found. |
| Shopify's own official tooling | Shopify publishes **no** official Admin API mock/sandbox. Their own answer to "test without a real merchant" is explicitly the dev-store + Bogus Gateway + generated-test-data path. | Confirms there is no vendor-provided alternative to a real dev store. |
| Broader search (webhook simulators, GraphQL emulators, test-data generators, fulfilment/refund harnesses) | Only small personal utility scripts found (test-data seeders) — all of which **still require a real dev store and real credentials** to seed; they are convenience seeders, not emulators. | None viable as a substitute for a real store. |

**No OSS project combines Admin GraphQL write support (products/orders/fulfilments/refunds) + webhook
delivery with correct HMAC + rate-limit/pagination fidelity + current (2025+) API-version compatibility.**
That combination doesn't exist as adoptable infrastructure. Building a genuinely faithful one internally
would itself be a substantial, high-maintenance project chasing a target that moves every quarter
(Shopify ships a new Admin API version every three months) — exactly the kind of "reinventing
ecommerce-platform testing infrastructure" this audit was requested to avoid.

### WooCommerce side

| Candidate | What it actually is | Verdict |
|---|---|---|
| `woocommerce/woocommerce` | The real plugin source (GPL-3.0, ~10.5k stars, actively maintained, 72k+ commits). No hand-rolled `docker-compose.yml` at the root; current e2e tooling (`plugins/woocommerce/tests/e2e-pw`) uses **Playwright + `wp-env`** (WordPress's official environment-management CLI, itself Docker-based under the hood). REST API v3 (`wp-json/wc/v3`) confirmed current. | **This is the real thing, and `wp-env` is the correct, low-effort way to run it locally** — not a separate repo. |
| `woocommerce/woocommerce-e2e-boilerplate` | **Archived** (2025-05-18), read-only, 18 stars. Explicit README deprecation notice — superseded by the in-tree Playwright suite above. | Dead. Do not use. |
| Broader search | Only generic, unofficial WordPress+WooCommerce Docker starter templates — nothing purpose-built beyond `wp-env`. | `wp-env` remains the answer. |

**WooCommerce wire-contract, confirmed distinct from Shopify's:**
- Webhook headers: `X-WC-Webhook-Topic`/`-Resource`/`-Event`/`-Signature` (HMAC-SHA256, base64) — completely different naming from `X-Shopify-*`; no shared verification code possible.
- No delivery-ID header equivalent to `X-Shopify-Webhook-Id` — idempotency dedup needs a different key (resource ID + event + payload hash) than the delivery-ID approach `ShopifyConnector` uses today.
- No platform rate limiting (self-hosted, no throttling layer).
- Synchronous, single-MySQL consistency — no eventual-consistency behavior to simulate.
- Page-number REST pagination, not cursor-based GraphQL.

### Generic contract-testing frameworks (Pact, Prism, WireMock)

Mature, well-maintained, **not ecommerce-specific**. Pact needs the provider (Shopify/WooCommerce) to
publish or verify a contract — neither does, so it's not usable without their cooperation. Prism/WireMock
mock an API from a spec **you already wrote yourself**, which adds no ecommerce-domain value over what
Sanocea's own connector tests already assert. Not a meaningful alternative here.

## Sanocea's own simulators, characterized precisely

Every existing Sanocea connector (Shopify, suppliers, payments, logistics) shares a **uniform
fault-injection vocabulary**: `429`, `500`, `timeout_before_mutation` (mutation never reached the
provider), `timeout_after_mutation` (mutation succeeded but the response was lost), plus
`duplicate_event`/`stale_event` on the supplier simulator's webhook side. This is not incidental — it is
purpose-built to exercise exactly the invariants this project's zero-tolerance framework measures:
idempotent replay, uncertain-mutation recovery (read-truth-first, never blind-retry), and stale-event
rejection. **No OSS mock, however good, would replicate this** — these are artificial hooks for testing
*Sanocea's own* recovery logic, not properties of any real platform's behavior. Conversely, Sanocea's
simulators enforce whatever Sanocea's own connector code assumes about the platform contract — they
cannot catch a connector bug in how it actually talks to real Shopify (wrong mutation field, wrong
scope, wrong header), because the simulator and the connector share the same (possibly wrong)
assumptions. That gap can only be closed by a real platform.

## Four-way comparison

| Approach | Proves | Cannot prove | Cost/friction |
|---|---|---|---|
| **A. Sanocea's own simulators** | Sanocea's own recovery/idempotency/staleness logic, deterministically, fast, in CI, with zero external dependency | Real API contract fidelity (schema, mutation syntax, pagination, rate limits, webhook payload shape, eventual consistency) | None — already built, already the backbone of every phase's regression suite |
| **B. OSS Shopify emulator/mock** | Nothing at adequate fidelity — no viable candidate exists | Everything a real platform would; adopting a low-fidelity one would create false confidence | N/A — not viable |
| **C. Real local WooCommerce (`wp-env`)** | Genuine platform-independence: a second real platform with a structurally different auth model (REST + Basic Auth vs GraphQL + token header), different webhook contract, no rate limits, synchronous consistency, page-based pagination — the sharpest available test of whether Sanocea's connector abstraction is genuinely reusable or has Shopify-shaped assumptions baked in | Shopify readiness itself (different platform) | Low — free, official, Docker-based, **no external account/credentials needed**, fast to stand up/tear down repeatedly |
| **D. Real Shopify development store** | The only source of genuine Shopify Admin GraphQL contract fidelity, real webhook delivery/HMAC, real rate limits, real eventual consistency | N/A — this is the ground truth Shopify certification requires | Moderate — free, but requires Partner/Dev Dashboard account creation and (per the separate Shopify platform research) possible identity-verification friction Shopify introduced mid-2026; a tunnel is needed for webhook delivery during development |

## Recommendation

- **Retain A in full.** Sanocea's own simulators are not redundant with anything else on this list — they test a different property (Sanocea's own failure handling) than any real or mocked platform would, and should stay the default/CI-speed test layer. Do not weaken or replace them.
- **Do not adopt or build B.** No OSS Shopify Admin API mock meets the bar, and building a faithful one internally would be exactly the "reinventing ecommerce-platform testing infrastructure" this audit was meant to avoid — a permanent maintenance burden chasing a quarterly-moving target, for a fidelity level a real dev store gives for free.
- **C (real local WooCommerce via `wp-env`) is worth doing, and is genuinely low-cost** — no account creation, no external credentials, official tooling, free. It is the best available empirical test of the connector abstraction's real reusability (a question this session's earlier code inspection could only partially answer by reading, not by proving). Recommend sequencing it as a low-priority, high-signal parallel track — not blocking or urgent, and independent of Shopify credential availability.
- **D (real Shopify dev store) remains the only path to genuine Shopify certification.** No substitute exists. This still requires the Dev Dashboard/Partner account creation and dev-store setup already scoped in the pending Shopify live-certification investigation from earlier this turn — that research is complete and ready to be written up as the certification package on request.

No repos were cloned or implemented. Stopping here per instruction.
