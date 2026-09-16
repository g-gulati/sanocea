# Myntra direct-integration access verification — Step 9Q.5

Research only. No code, no connector, no generic core change. Objective: determine whether
`Merchant → Sanocea → Myntra` is evidenced as achievable without an OMS intermediary, and whether
Myntra should become Step 9Q.6.

## Evidence hierarchy used

1. Official Myntra-owned developer/API material
2. Official Myntra seller/partner material
3. Officially-linked third-party material (e.g. a Postman collection linked FROM an official Myntra page)
4. Mature integration-vendor documentation (Unicommerce, Vinculum, EasyEcom, Fynd) — secondhand
5. Credible secondary evidence (blogs, reconciliation-service marketing pages)

## Part A/B — Primary technical surfaces and access model

**`https://mmip.myntrainfo.com/` — "Welcome to Myntra Developer Centre".** Confirmed directly by fetch.
This is a genuine, Myntra-owned domain (`myntrainfo.com`) developer portal — the single strongest piece
of evidence found in this entire research pass, and materially stronger than anything found for Meesho
(no comparable official portal exists for Meesho at all). **Evidence class: Level 1/2 (official).**

The portal links to three distinct, named API families:
- **Omni and PPMP** — B2C marketplace: "manage inventory, orders, returns, and reconciliation"
- **Listing Management** — catalogue: "product listing creation, image updates, attribute management,
  status checking, and listing activation/deactivation"
- **B2B for International Brands (Myntra Global Partner Program / MGPP)** — "inventory, BO, & PO"

**Access model, confirmed directly from `mmip.myntrainfo.com/documentation/myntra-ppmp-api-v4`:**
> "Clients must get in touch with their account manager to enable the APIs for the seller, and once the
> APIs are enabled, sellers must share credentials that are mandatory to configure the Myntra PPMP
> channel."

This directly answers Part B's decisive question 7 ("Can production integration exist without another
OMS?"): **yes, architecturally** — the described path is Myntra's own account manager enabling API
access for a specific seller, then that seller's credentials being shared with whoever configures the
channel (Sanocea, in our shape) — there is no mention anywhere of a required OMS/intermediary. This is
gated (an account-manager relationship must be established) but is a **direct** route, structurally
similar to Flipkart's Partner Dashboard review, not an OMS dependency.

**Partner Portal:** `https://partnerportal.myntra.com/` — the seller-facing login/dashboard confirmed
linked from the developer portal.

**Not established from this pass:** whether Sanocea specifically (as a third-party technology provider,
not a single seller) can register as its OWN partner independent of any one merchant, or whether every
merchant's own account manager must separately enable API access per-merchant with no Sanocea-level
aggregator registration analogous to Flipkart's. The developer portal's front page mentions a "Sign up"
option but its exact registration flow (self-serve vs. sales-mediated, individual-merchant vs.
technology-partner) was not reachable in this pass — this is the single most important open question
for Part H's contact action.

## Part C — Operational capability matrix

| Area | Classification | Evidence |
|---|---|---|
| Inventory push (facility-wise, incremental) | DIRECT-EVIDENCED (existence + operational constraints), TECHNICAL-CONTRACT-INCOMPLETE (no exact endpoint path/JSON schema) | Official portal: batch size 10, rate limit 100 req/min, "no decimals allowed in values." |
| Inventory search (by seller SKU) | SECONDHAND-ONLY | Third-party Postman workspace snippet: up to 100 SKUs/call, retrievable in batches of 20 — not independently confirmed from the official portal itself. |
| Order discovery/detail ("Get Order by Id") | DIRECT-EVIDENCED (existence), TECHNICAL-CONTRACT-INCOMPLETE | Official portal names "Create Order & Update Order calls"; exact request/response fields not reachable (Postman documenter pages are JS-rendered, unreachable via direct fetch in this pass). |
| Order status lifecycle (RTD, Shipped, Delivered, Hold) | DIRECT-EVIDENCED | Official portal: RTD (Ready to Dispatch) at order-line level; Shipped/Delivered status updates keyed on packet ID; hold/unhold on order and line IDs; "no cancellation before RTD is now mandatory"; auto-cancellation after 3 days if an order stays open. |
| Cancellation | DIRECT-EVIDENCED (constraint only, not the operation's own contract) | Same official source — a real, specific business rule, but the cancellation call's own request/response shape not reached. |
| Returns | DIRECT-EVIDENCED (status enum) | Official portal: Create Return, Return-in-transit, Return-Closed endpoints named; status values CONFIRMED, READY_FOR_PICKUP, DELIVERED, DECLINED; Return ID in request body. |
| RTO | UNCONFIRMED | Not distinguished from ordinary returns in what was reached — no separate RTO lifecycle description found. |
| Listing/catalogue creation, images, attributes, QC/rejection | DIRECT-EVIDENCED (existence only) | Official portal names the "Listing Management" API family exactly for this; no field-level schema or rejection-code detail reached. |
| Pricing/discount rules | DIRECT-EVIDENCED (one constraint) | Official portal: "Discount date ranges cannot exceed 6 months." |
| Settlement/finance | **PORTAL-ONLY** | Consistent, independent secondhand corroboration from THREE unrelated sources (Cointab, Recarya, Unicommerce), none of which mention an API: settlement statements/revenue reports are accessed via seller LOGIN, and third-party reconciliation SaaS products exist specifically because sellers must reconcile portal-downloaded reports themselves. Commission fee is category/brand-dependent and refundable on returns via a "Reversal PG Settlement Report." No API or file-feed mechanism evidenced anywhere. |
| Events/webhooks | UNCONFIRMED | Not mentioned in any source reached this pass. |
| SFTP/file exchange | UNCONFIRMED | Not mentioned in any source reached this pass. |

## Part D — Contract completeness

**Incomplete for implementation.** What's missing across every capability above: exact endpoint paths,
HTTP methods, full request/response JSON field names, authentication header/token mechanism, and
pagination convention. The official portal's own documentation page reached in this pass is a
high-level integration/business-rules guide, not a technical API reference — the actual technical
reference is Postman-hosted (linked from the official portal) and was not extractable via direct fetch
in this research pass (JS-rendered SPA pages returned no usable content, the same limitation
encountered for Flipkart/Amazon's own Postman-hosted pages in earlier steps). **This is a genuinely
solvable gap** — logging into the official portal or obtaining the credential-gated technical reference
through the account-manager process described above would very likely resolve it — unlike Meesho, where
no official technical reference is known to exist at all.

## Part E — Postman investigation

Two distinct things were found, and they must not be conflated:
1. **Official, portal-linked Postman documentation** — `mmip.myntrainfo.com` itself links its three API
   families to Postman-hosted pages (e.g. a `documenter.getpostman.com/view/9567931/...` style URL was
   found independently). This is the OFFICIAL technical reference, evidence class Level 1/2 by
   association with the official portal, but its content was not extractable in this pass (JS-rendered).
2. **A third-party individual's public workspace** — `postman.com/piyush27/piyush-kantilal-jani-s-public-workspace/...`,
   titled "Myntra Seller API V3/V4 Latest." This is **NOT Myntra-owned** — it is an individual's public
   workspace, evidence class Level 5/6 (unofficial republication or independent documentation of the
   same API, not a Myntra-authorized source). It IS useful as corroboration (its endpoint names and
   response-code ranges — 1000-1009 success, 401/403/1008/2000/2001 error — are specific enough to read
   as genuine, not generic filler) but must never be cited as an official contract on its own, per the
   mandate's explicit warning.

## Part F — Third-party corroboration (secondhand, for context only)

Unicommerce, Vinculum, and Fynd all independently describe a real Myntra PPMP/Omni integration
(inventory/order/return sync), consistent with — and never contradicting — the official portal's own
description. None of these vendor sources describe HOW they obtained their own access (partner
agreement vs. per-merchant credential), so they cannot answer Part B's decisive questions on their own;
they are corroborating evidence that the API family is real and actively integrated against in
production, not a source for Sanocea's own access route.

## Part I — Architecture fit (no code)

| Sanocea concept | Fit | Classification |
|---|---|---|
| `MarketplaceConnector`/`MarketplaceAuthStrategy` | Likely fits — access model description ("account manager enables API, seller shares credentials") reads as static or semi-static credentials rather than OAuth, similar in shape to Meesho's `StaticSupplierCredentialsAuth`, not confirmed identical | ADAPTER-LOCAL (pending confirmed auth mechanism) |
| Multi-storefront resolution | Fits unchanged — same channel-type-per-merchant shape as every other connector | ADAPTER-LOCAL |
| `Order`/`OrderLine`, RTD/Hold/packet-ID concepts | Fits — RTD maps naturally onto an existing pre-fulfilment status; packet-ID-scoped Shipped/Delivered updates map onto `Shipment`/order-line fulfillment status the same way Flipkart's shipment-scoped updates did | ADAPTER-LOCAL |
| Returns (CONFIRMED/READY_FOR_PICKUP/DELIVERED/DECLINED) | Fits Sanocea's existing `Return` status-mapping pattern directly (same shape as Flipkart/Amazon's own status-map modules) | ADAPTER-LOCAL |
| RTO as distinct from ordinary Return | Not evidenced as distinct in what was reached — cannot classify yet | UNKNOWN UNTIL SPEC |
| Finance reconciliation (`SettlementBatch`/`SettlementEntry`) | Portal/report-only, no API — would need a REPORT-INGESTION boundary (file/report parsing), not an API-polling connector method, if ever built | GENERIC MARKETPLACE GAP (report ingestion is not yet a first-class MarketplaceConnector concept — no channel implemented so far has needed one; Flipkart/Amazon/Meesho are all API-only for settlement where they have anything at all) |
| `ConnectorCommand`/`ExceptionRecord` | Fits unchanged | ADAPTER-LOCAL |

No canonical domain gap was found requiring a stop-and-document decision — every fit question above is
either adapter-local or blocked on missing technical spec, not a mismatch with Sanocea's existing
domain semantics.

## Part J — Lightweight AJIO/Nykaa/JioMart comparison (not a full audit)

| Channel | Direct machine integration evidenced? | Primary docs discoverable? | Independent tech-partner route? | Merchant-authorized route? | Likely contract availability |
|---|---|---|---|---|---|
| **AJIO** | Yes (per-seller POB ID credential, per Unicommerce/Vinculum) | **No** — no official developer portal found (unlike Myntra's `mmip.myntrainfo.com`) | Not evidenced | Yes (credential issued per seller) | Low — secondhand-only, no official technical reference located |
| **Nykaa** | Yes (Username/Password/Seller ID per brand) | Partial — a `dev-sellerportal.nykaa.com` subdomain exists (suggests SOME technical portal) but no content reached; brand-approval-gated (category-curated, not open) | Not evidenced | Yes, after brand/category approval | Low-medium — a dev subdomain exists but unverified this pass |
| **JioMart** | Yes (category-manager-issued credentials) | **No** general developer portal found; one narrow "JioMart → Haptik" Postman workspace exists for a NAMED partner integration, not general third-party documentation | Not evidenced as generally open | Yes, after seller registration | Low — no general technical reference located |
| **Myntra** | Yes | **Yes** — `mmip.myntrainfo.com`, Myntra-owned | Ambiguous (open question, see Part H) | Yes (account-manager-mediated) | **Medium** — official portal + business-rule specifics confirmed; exact endpoint schemas still gated |

**Myntra is the clear evidence leader of these four** — it is the only one with a confirmed, Myntra-owned
developer portal at all.

## Meesho retention

**ACCESS EXISTS / BUSINESS CONTRACT BLOCKED** — unchanged from Step 9Q.4. Direct credential issuance is
real and evidenced (email-based), but no technical contract for any business operation was ever found,
official or secondhand.

## Sources (full list, with evidence class)

- `https://mmip.myntrainfo.com/` — **Level 1/2, official.**
- `https://mmip.myntrainfo.com/documentation/myntra-ppmp-api-v4` — **Level 1/2, official.**
- `https://partnerportal.myntra.com/` — **Level 1/2, official** (existence confirmed via link, content not fetched).
- `https://myntrascmuistatic.myntassets.com/partner-assets/partners/Sell_V1.pdf` — official-hosted asset (Myntra's own asset CDN domain), content not extractable (file too large for direct fetch) — **Level 1/2 by hosting domain, unread**.
- `https://documenter.getpostman.com/view/9567931/SWLfaSoW` ("Myntra Seller API V4") — likely official (linked pattern consistent with the portal's own Postman references), content not extractable (JS-rendered) — **Level 1/2 by inference, unverified content**.
- `https://www.postman.com/piyush27/piyush-kantilal-jani-s-public-workspace/...` — **Level 5/6, NOT Myntra-owned**, used only as corroboration, per the mandate's explicit caution.
- Unicommerce (`unicommerce.com/blog/sell-on-myntra/`), Vinculum (`docs.vineretail.com/myntra-integration/`, `myntra-omni/`), Cointab, Recarya — **Level 5, secondhand**, used only for settlement/reconciliation corroboration and general context.
- AJIO: Unicommerce (`support.unicommerce.com/.../integration-with-ajio*`), Vinculum (`docs.vineretail.com/ajio-integration-user-manual/`), Fynd (`partners.fynd.com/extensions/ajio-vms`) — **Level 5**.
- Nykaa: `seller.nykaa.com`, `dev-sellerportal.nykaa.com` (existence only), EasyEcom KB — **Level 2 (domain existence) / Level 5 (process description)**.
- JioMart: `identity.seller.jiomart.com`, Unicommerce KB, a named "JioMart → Haptik" Postman workspace — **Level 2 (domain existence) / Level 5-6**.
