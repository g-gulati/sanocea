# Unicommerce vs. Sanocea — Competitive Capability Audit

Governed by [`../competitive/README.md`](./README.md) (the Sanocea Competitive Research Mandate, v1,
2026-09-11). Second per-competitor audit produced under that mandate. Per the mandate's Section 11
execution log, this follows [`linnworks-vs-sanocea.md`](./linnworks-vs-sanocea.md) — Linnworks findings
are referenced only in Section 9 (priority reconciliation), not re-researched here.

**Explicit reminder carried over from the user's instruction:** this audit is evidence and analysis
only. Nothing in Sections 2, 5, 6, or 8 below authorizes any Sanocea implementation work. No production
code, connector, test, or script was touched to produce this file.

## 0. Scope, evidentiary basis, and the group-vs-product classification discipline

Unicommerce eSolutions Ltd (NSE: `UNICOMMERCE`, listed August 2024) is a holding structure, not one
product. This audit tags every capability found with exactly one of:

1. **Native Unicommerce/Uniware** — part of the core OMS/WMS product.
2. **Another Unicommerce-owned/acquired product** — a separately branded, separately built product now
   owned by the group (confirmed this pass: **Shipway** and **Convertway**).
3. **Third-party integration** — not Unicommerce-owned.
4. **Manual workflow** — no tooling found; a human does it by hand.
5. **Unknown/not publicly established**.

**Corporate structure found this pass, which changes the classification exercise materially versus
Linnworks:** Unicommerce acquired **Shipway** in two tranches — 42.76% in November 2024 (₹68.4 crore
cash) and the remaining 57.24% in March 2025 (an equity swap of 60.3 lakh Unicommerce shares) — making
Shipway a **wholly-owned subsidiary**, not a third-party bolt-on
([inc42.com](https://inc42.com/buzz/unicommerce-to-acquire-remaining-57-24-stake-in-shipway/)). Shipway
itself operates **Convertway**, an AI-enabled marketing-automation platform, as its own sub-product
([scanx.trade](https://scanx.trade/stock-market-news/corporate-actions/unicommerce-esolutions-completes-full-acquisition-of-shipway-strengthening-e-commerce-solutions-portfolio/4081237)).
So the real structure is: **Uniware** (native OMS/WMS, built in-house) + **Shipway** (acquired
courier-aggregation/logistics platform, now wholly owned) + **Convertway** (marketing automation, owned
by Shipway, owned by Unicommerce). A merchant researching "does Unicommerce do X" for logistics or
marketing-automation capability is, in every case checked this pass, actually being routed to a
group-owned but architecturally and commercially distinct product — this is category 2, not category 1,
and the distinction matters for anything Sanocea might absorb (a canonical model shouldn't assume "one
vendor" implies "one system," even when the vendor is the same legal entity).

No new searches were run to re-verify prior Pass-3 Unicommerce findings already cited in
`docs/architecture/sanocea-competitive-capability-audit.md` (UniReco named leakage categories/UTR-level
matching, 11,350+ warehouses managed, pigeonhole/bundled sorting with FIFO/FEFO picking, dynamic
bundles, no public AI claim found on the core OMS product page, no idempotency claim found, "same-day COD
settlement" not reconfirmed) — those are reused and, where this pass's fresh research corroborates or
extends them, noted explicitly.

**One correction to a prior-pass claim:** the combined audit cited "Smart Facility Allocation" by that
exact name. This pass could not find that exact term in current Unicommerce material. What was found
instead: a **"Smart Fill" rule-based allocation engine** that evaluates all pending orders against
available inventory across the warehouse network simultaneously to maximize fully-fulfilled orders, and
a separately named **"proximity-based facility allocation"** feature that routes orders to the nearest
facility to the customer
([support.unicommerce.com — Proximity based facility allocation](https://support.unicommerce.com/index.php/knowledge-base/proximity-based-facility-allocation/)).
The underlying capability (multi-warehouse order-to-facility routing) is real and well-evidenced either
way; the specific name "Smart Facility Allocation" should not be cited going forward — use "Smart Fill" /
"proximity-based facility allocation" instead. This is the same disclosure discipline the combined audit
applied to its own prior-pass errors (Section 0 of `sanocea-competitive-capability-audit.md`).

**Still `UNKNOWN` after this pass** (real gaps, not resolved findings): backorder/preorder as a named
workflow (searched specifically, nothing surfaced beyond generic industry explainer content); API
idempotency guarantees (carried forward from the combined audit's Pass 3 — searched specifically then,
nothing found); webhook architecture/rate limits; RBAC granularity beyond the plan-tier role counts found
in pricing research (Section 2.12); exception-management/human-approval-gate specifics; auditability;
supplier-acknowledgement depth beyond the PO lifecycle stages found.

---

## 1. Executive summary — Unicommerce vs. Sanocea

Unicommerce is the deepest, most India-specific commerce-operations platform researched in this program
so far — and it is the first competitor where the mandate's group-vs-product classification discipline
turns out to matter immediately: "Unicommerce" as a merchant experiences it is really three products
(Uniware, Shipway, Convertway) under one shareholder, each with its own capability boundary, its own
history (two are acquisitions), and — as far as public evidence shows — no confirmed single canonical
data model spanning all three the way Sanocea's own architecture spans orders/finance/procurement/
support in one system. This is a structural echo of the Linnworks finding (Linnworks + Replyco/Gorgias),
except here the "bolt-on" is group-owned rather than a genuine third party — a materially different, and
in some ways stronger, competitive position for Unicommerce (it captures the revenue and can integrate
more tightly) but not evidence that the three products share one canonical operational-and-financial
truth.

Three things are genuinely deeper here than anything found in the Linnworks pass, and all three are
India-market-specific in a way Linnworks' UK/global-first research never surfaced: **marketplace-specific
operational-exception handling by name** (Amazon, Flipkart, Myntra, Meesho, plus quick-commerce
platforms Blinkit and Zepto, across 151+ pre-integrated channels), **COD-remittance and marketplace-
commission reconciliation at genuinely granular, named-fee-category depth** (UniReco), and **NDR/RTO
management as a named, dedicated workflow** (via Shipway) rather than an unconfirmed capability the way
it was for Linnworks. Conversely, Unicommerce's own public material shows **no evidence of a canonical,
cross-domain data model** — reconciliation (UniReco), logistics (Shipway), and marketing (Convertway) all
read as separate systems integrated at the product level, not unified at the data-model level, which is
exactly the shape of fragmentation Sanocea's positioning is built to remove (Section 12 of the combined
audit; reinforced, not contradicted, by this pass).

## 2. Capability-by-capability audit (A-J framework)

### 2.1 Marketplace-specific integration and operational-exception depth (Amazon, Flipkart, Myntra, Meesho, quick-commerce)

- **A. Merchant problem:** each Indian marketplace has its own listing rules, order-state machine, return
  policy, and settlement format; a merchant selling on 4-5 channels cannot manually reconcile each
  channel's quirks without constant staff attention.
- **B. Why it exists:** marketplace-specific breakage (a Flipkart-only field, a Meesho-only return
  workflow) is a real, recurring cost of doing business in Indian ecommerce; a platform that doesn't
  abstract this forces every merchant to rediscover each marketplace's exceptions independently.
- **C. Relevance:** every segment that sells on more than one Indian marketplace — which is most Indian
  D2C brands past their first channel.
- **D. India frequency:** very high — this is the single most universal Indian-merchant need in this
  entire research program.
- **E. Sanocea status:** `PARTIAL` — three real, certified connectors exist (WooCommerce, Shopify,
  BigCommerce-in-prep per the combined audit) but zero Indian-marketplace connector (Amazon India,
  Flipkart, Myntra, Meesho) has ever been built or certified.
- **F.** Fits the existing connector-architecture pattern directly — this is "more connectors," not a
  canonical-model change, *provided* marketplace-specific quirks stay in the connector/adapter layer per
  Mandate Section 2 and never leak into canonical domain logic.
- **G.** Connector, explicitly — this is the textbook case the mandate's Section 2 principle exists for.
- **H.** High risk if done carelessly: the temptation to special-case "if Meesho then..." inside core
  order logic is exactly what the mandate warns against. Low risk if every marketplace quirk is resolved
  to a canonical order/exception shape before it reaches core.
- **I.** Yes, substantially — this is precisely the "still pay a human" work confirmed in Section 6 below
  (channel link/unlink setup, sync/mapping troubleshooting).
- **J. Priority: P1** — an Indian-marketplace connector (starting with Amazon India or Flipkart) is
  arguably a sharper P1 for an India-first launch than anything in the Linnworks-only research surfaced,
  since Sanocea currently has zero India-marketplace evidence at all (Section 9).

*Evidence:* Unicommerce integrates with Amazon, Flipkart, Myntra, Meesho, Lazada, JioMart, AJIO, CRED,
PharmEasy, and 151+ marketplaces total, plus quick-commerce platforms Blinkit and Zepto
([unicommerce.com/blog/best-order-management-software-system-for-ecommerce-india-2026](https://unicommerce.com/blog/best-order-management-software-system-for-ecommerce-india-2026/));
no specific per-marketplace *exception-handling* documentation (e.g. a Meesho-specific return-workflow
quirk) surfaced in public material this pass — the breadth of integration is well-evidenced, the
depth of named per-marketplace exception logic is not, and should be marked `UNKNOWN` rather than
assumed.

### 2.2 COD remittance reconciliation (UniReco)

- **A.** Match cash collected by a courier for a COD order against the actual order value, and catch
  short/missing/delayed remittance before it becomes a silent revenue leak.
- **B.** COD is a large share of Indian ecommerce volume; courier-collected cash reconciliation is
  error-prone at scale and a well-known source of merchant revenue loss if done manually or late.
- **C.** Any merchant offering COD — SME onward, and especially high-volume COD-heavy categories
  (fashion, mobile accessories).
- **D. India frequency:** very high — COD is a defining feature of Indian ecommerce in a way it is not
  for Linnworks' UK/global-first market.
- **E. Sanocea status:** `IMPLEMENTED+PROVEN` per the combined audit for WooCommerce COD specifically, but
  that is order-creation-side COD handling, not remittance-reconciliation. Remittance reconciliation
  itself is closer to `MISSING` — Sanocea's dual-status reconciliation model (`Refund.status` vs.
  `Refund.financial_reconciliation_status`) is the right *shape* but has never been exercised against a
  real COD-remittance data feed.
- **F.** Fits the existing dual-dimension reconciliation pattern (Section 6 of the combined audit)
  directly — COD remittance is another instance of "operational truth vs. financial truth," not a new
  concept.
- **G.** Reconciliation (canonical field) + connector (courier remittance-feed ingestion).
- **H.** Low, if the remittance-matching logic stays generic (match collected amount to expected order
  value with a tolerance/delta) rather than hardcoding one courier's feed format into the core.
- **I.** Yes, directly — this is confirmed real manual/Excel work today (Section 6).
- **J. Priority: P1** for an India-first launch — COD volume makes this more load-bearing for Sanocea's
  initial market than for a UK/global-first competitor.

*Evidence:* UniReco's COD Remittance Reconciliation module automates COD collection-to-order matching,
pre-calculates channel fees, tracks order-wise settlement, and flags discrepancies in real time so sellers
can dispute erroneous marketplace charges before claim windows close
([support.unicommerce.com/knowledge-base/unireco](https://support.unicommerce.com/index.php/knowledge-base/unireco/)).
Reconciliation statuses are genuinely granular: `RECONCILED`, `RECONCILED BY DELTA` (tolerance-based
matching), `RECONCILED MANUALLY`, `PARTIAL PAYMENT`, `PAYMENT DISPUTED` — a real state machine, not a
binary flag.

### 2.3 NDR/RTO management (via Shipway — group-owned, not native Uniware)

- **A.** When a courier fails to deliver (NDR) and the shipment risks returning to origin (RTO), the
  merchant needs to quickly decide re-attempt vs. accept the return, and ideally intervene with the
  customer before that decision is forced.
- **B.** RTO is one of the most expensive failure modes in Indian ecommerce (reverse shipping cost,
  restocking, lost sale) — mature Indian-market platforms treat active NDR intervention as core, not
  optional.
- **C.** Any merchant shipping physical goods with any COD component — SME onward, acutely felt at
  high-volume.
- **D. India frequency:** very high — NDR/RTO is a defining Indian-logistics pain point in a way it
  simply wasn't surfaced for Linnworks (UK returns/delivery-failure dynamics are different).
- **E. Sanocea status:** `MISSING` — the combined audit marked NDR/RTO `MISSING` for Sanocea outright;
  this pass finds nothing to change that.
- **F.** Needs a real workflow (an NDR state with re-attempt/RTO branching, tied to courier webhook/
  polling data) — not supportable as a trivial extension of the existing `Shipment` model, but the
  underlying shape (a shipment-exception state machine) is generic enough to design cleanly.
- **G.** Deterministic engine (re-attempt vs. RTO decision rules) + canonical domain (an NDR exception
  concept on `Shipment`) + connector (courier NDR-event ingestion).
- **H.** Moderate — real risk of designing this around one courier's NDR event shape; the mandate's
  connector/canonical split should keep courier-specific NDR codes in the connector, resolving to a
  generic NDR state in the core.
- **I.** Yes, significant — proactive NDR intervention (customer contact before RTO) is real, evidenced
  human/ops work today.
- **J. Priority: P1 for India-first** — this is the single clearest capability this pass found that
  Linnworks' research never exposed as India-relevant at this depth, precisely because Linnworks is not
  an India-first platform (Section 9).

*Evidence, and explicit classification:* NDR/RTO management is delivered via **Shipway by Unicommerce**
— confirmed compatible with NDR data from Delhivery, Bluedart, and Xpressbees, with an NDR panel showing
undelivered orders and two actions (re-attempt request, RTO request)
([blog.shipway.com/ndr-management-system](https://blog.shipway.com/ndr-management-system/);
[support.unicommerce.com — Shipway by Unicommerce](https://support.unicommerce.com/index.php/knowledge-base/shipway-by-unicommerce-shipment-tracking-and-notifications/)).
Per Section 0's classification discipline, this is **category 2 (another Unicommerce-owned product)**,
not native Uniware — the same distinction the combined audit already applied ("Shipway by Unicommerce, a
distinct sub-brand — not the core OMS/WMS product itself"), now confirmed structurally by the acquisition
history in Section 0.

### 2.4 Courier aggregation and smart courier selection (via Shipway)

- **A.** Choose the right courier per shipment automatically (cost, serviceability, COD support, SLA)
  instead of a human picking manually or defaulting to one courier regardless of fit.
- **B.** No single courier covers all of India at competitive rates/SLAs for every pincode; multi-courier
  management without automation becomes a manual spreadsheet exercise at any real volume.
- **C.** SME onward — irrelevant to a merchant using exactly one courier by choice, common quickly past
  that.
- **D. India frequency:** high — 19,000+ pincode coverage claims and multi-courier necessity are a
  specifically Indian-logistics-market reality (fragmented courier landscape, COD-serviceability
  variance by pincode).
- **E. Sanocea status:** `MISSING`/`ARCHITECTURAL ONLY` — `Shipment.carrier: str` is free-text, never
  chosen by Sanocea (confirmed weakness in the combined audit, Section 4).
- **F.** Fits the deterministic-policy pattern directly, same shape as order/location routing (Section
  2.1 of the Linnworks audit).
- **G.** Deterministic engine / policy, reading courier-rate/serviceability data from a connector.
- **H.** Low, if courier-selection criteria stay generic (cost/serviceability/COD/SLA weights,
  merchant-configurable) rather than hardcoding one courier aggregator's rate-card format into core.
- **I.** Yes — removes manual per-shipment courier choice.
- **J. Priority: P1/P2** — real and India-relevant, but sequenced behind NDR/RTO and marketplace
  connectors since it compounds on top of having real shipment data flowing at all.

*Evidence, and explicit classification:* Shipway (Unicommerce-owned, category 2) integrates multiple
courier partners, fetches real-time rates, and automatically selects couriers based on serviceability,
weight, COD availability, SLA, and cost
([unicommerce.com — courier partner management](https://unicommerce.com/everything-ecommerce/how-do-i-manage-multiple-courier-partners-without-increasing-operational-complexity/)).
This is explicitly Shipway's capability, acquired rather than built by Unicommerce/Uniware — the group
now owns the capability, but it did not originate as a native Uniware feature.

### 2.5 Facility/warehouse order allocation (Smart Fill / proximity-based allocation)

- **A.** Assign each order's fulfilment to the right warehouse automatically, maximizing fully-fulfilled
  orders across the network rather than manually picking a facility per order.
- **B.** Same root failure mode as Linnworks' MLI/allocation gap (Section 2.1-2.2 of the Linnworks
  audit) — manual multi-warehouse allocation doesn't scale, and naive nearest-warehouse-only logic can
  strand orders that a network-wide view would have fully filled.
- **C.** Growing SME onward (once a merchant has more than one facility).
- **D. India frequency:** high, and rising with quick-commerce dark-store models (Blinkit/Zepto
  integration, Section 2.1, implies even more granular multi-location fulfilment than a typical
  two-warehouse D2C setup).
- **E. Sanocea status:** `ARCHITECTURAL ONLY` — same status as identified against Linnworks; this pass
  reconfirms the priority rather than changing it (Section 9).
- **F.** Same as the Linnworks-audit finding — the field exists, the allocation *behavior* has never been
  exercised.
- **G.** Canonical domain + deterministic engine, same as Linnworks Section 2.1-2.2.
- **H.** Low if scoped as an explicit rule set; Unicommerce's own "maximize fully-fulfilled orders across
  the network" framing (as opposed to pure nearest-warehouse) is a genuinely more sophisticated framing
  worth considering for Sanocea's own design, without copying the implementation.
- **I.** Yes — same manual-allocation-decision elimination as the Linnworks finding.
- **J. Priority: P0** — **independently reconfirmed** by a second mature platform with a different
  allocation philosophy (network-wide fill-maximization vs. Linnworks' criteria-based routing). This
  raises confidence that multi-location allocation is a universal, not platform-idiosyncratic, problem
  (Section 9).

*Evidence:* "Smart Fill" is described as a rule-based allocation engine evaluating all pending orders
against available network-wide inventory simultaneously to maximize fully-fulfilled orders; a separate
"proximity-based facility allocation" feature routes orders to the nearest facility to the customer via
channel-based configuration
([support.unicommerce.com/knowledge-base/proximity-based-facility-allocation](https://support.unicommerce.com/index.php/knowledge-base/proximity-based-facility-allocation/)).
Both are native Uniware/WMS capability (category 1) — unlike Sections 2.3-2.4, this one sits in the core
product, not an acquired subsidiary.

### 2.6 Available-to-sell / oversell prevention

- **A.** Prevent a marketplace listing from showing more stock than actually exists once orders,
  reservations, and multi-channel sales are accounted for.
- **B.** Oversell on a marketplace risks account penalties/suspension in addition to the direct refund
  cost — a sharper consequence on Indian marketplaces (Amazon/Flipkart account-health metrics) than for
  a merchant selling only on their own site.
- **C.** Any merchant selling on more than one channel simultaneously.
- **D. India frequency:** high — real-time sync across many Indian marketplaces (Section 2.1) makes this
  a constant operational surface.
- **E. Sanocea status:** `PARTIAL` — same finding as against Linnworks (Section 2.3 of the Linnworks
  audit); a flat count exists, no reserved/committed formula is proven.
- **F/G/H/I.** Same reasoning as the Linnworks-audit ATS finding (Section 2.3 there) — this is not a new
  design question, it is the same one reconfirmed.
- **J. Priority: P1** — reconfirmed, not changed.

*Evidence:* Unicommerce syncs inventory across marketplaces in real time using Kafka-powered delta
updates plus off-peak snapshot reconciliation, explicitly framed as protecting sellers from marketplace
penalties and poor ratings
([unicommerce.com — inventory management system](https://unicommerce.com/inventory-management-system/)).
The specific *mechanism* (Kafka delta + snapshot reconciliation) is architecturally interesting as a
pattern (real-time event stream plus periodic full-reconciliation as a safety net) but should be absorbed
as a *principle* (never trust a stream alone; always reconcile against a full snapshot periodically), not
copied as an implementation detail.

### 2.7 Bundles, kits, and BOM — three distinct, named constructs

- **A.** Sell a combination of products as one purchasable unit, with the right stock-tracking behavior
  for how that combination is actually fulfilled (assembled ahead of time vs. assembled at pick time vs.
  manufactured as its own trackable unit).
- **B.** A single "bundle" concept is too coarse: pre-assembled multi-packs need different stock logic
  than pick-time combos, and a manufactured combo (with its own yield/cost) is different again from
  either.
- **C.** Relevant to nearly every merchant segment, same as the Linnworks finding — but Unicommerce's
  three-way distinction suggests real merchants hit this nuance often enough to justify three named
  constructs, not one.
- **D. India frequency:** high — combo/gift-set offers are common in Indian D2C (Section 2.4 of the
  Linnworks audit already established this).
- **E. Sanocea status:** `MISSING` — same as against Linnworks; this pass sharpens *what* is missing
  rather than changing the verdict.
- **F.** Genuinely needs a canonical-model addition, and this pass's finding is more specific than the
  Linnworks pass's: the addition likely needs to distinguish *when* stock is decremented (at bundle-sale
  time, dynamically, vs. at kit-assembly time, statically) rather than assuming one generic
  parent/child relationship covers every case.
- **G.** Canonical domain (the composite relationship, now with an explicit assembly-timing attribute) +
  deterministic engine (derived stock calculation, timing-aware).
- **H.** Low if the assembly-timing distinction is itself generic (a boolean or enum on the composite
  relationship), not hardcoded to Unicommerce's specific "Bundle vs. Kit vs. BOM" terminology.
- **I.** Yes, same as the Linnworks finding.
- **J. Priority: P2** — reconfirmed, with a sharper design cue for *how* to build it than the Linnworks
  pass alone provided (Section 9).

*Evidence:* Unicommerce distinguishes three constructs — a **Bundle** is assembled at order-processing
time from individually-stocked component items, availability derived from component availability, no
standalone SKU identity; a **Kit** is pre-assembled ahead of time and put away into stock as its own
unit, ready for faster dispatch; a **BOM** is "a combo with defined quantity of its own as an item
itself" — i.e. a manufactured/assembled product with its own SKU and cost, distinct from either
([unicommerce.com/blog/product-bundling-types-benefits-challenges](https://unicommerce.com/blog/product-bundling-types-benefits-challenges/);
[support.unicommerce.com — Kitting](https://support.unicommerce.com/index.php/knowledge-base/kitting/)).
Component inventory auto-adjusts on bundle sale; real-time item-level visibility is provided for every
component within a bundle.

### 2.8 Procurement and purchase-order lifecycle

- **A.** Get the right stock from the right supplier at the right time, with a real audit trail from
  "we decided to buy" to "it's in the warehouse."
- **B.** Ad hoc supplier ordering without a lifecycle (cart → PO → approval → send → receipt) loses
  visibility into what's pending, what's been approved, and what's actually arrived vs. ordered.
- **C.** SME onward — any merchant sourcing from more than one supplier.
- **D. India frequency:** high — multi-vendor sourcing (including the same SKU from different suppliers
  at different price points) is common in Indian D2C/retail.
- **E. Sanocea status:** `IMPLEMENTED+PROVEN` per the combined audit — Sanocea already has real
  procurement/PO/supplier-acknowledgement/inbound-shipment capability.
- **F/G/H.** N/A — not a gap.
- **I.** Already yes.
- **J.** Not a gap, but worth noting the specific lifecycle-stage naming found here (`PO created → PO
  Approved → PO sent → Order Received at Warehouse (GRN)`) as a useful external validation that Sanocea's
  existing stage model is the right shape, not a novel invention.

*Evidence:* Unicommerce's procurement module supports a Purchase Cart (select products/quantities before
raising a PO), a defined PO lifecycle (`PO created → PO Approved → PO sent → GRN`), per-SKU multi-vendor
catalogs with vendor-specific pricing/preference, and backorder checking during procurement
([support.unicommerce.com/knowledge-base/procurement](https://support.unicommerce.com/index.php/knowledge-base/procurement/);
[support.unicommerce.com — Purchase Orders and its Lifecycle](https://support.unicommerce.com/index.php/knowledge-base/purchase-orders-2/)).

### 2.9 Marketplace commission/fee reconciliation (UniReco, non-COD side)

- **A.** Confirm a marketplace actually paid what it owed for a settled order, catching under-payment on
  commission, shipping-fee, or other deduction lines before the marketplace's own dispute-window closes.
- **B.** Marketplace settlement statements are dense and marketplace-favorable-by-default; without
  line-item reconciliation, merchants absorb silent margin leakage they never notice.
- **C.** Any merchant selling on commission-charging marketplaces — SME onward, more consequential at
  higher volume.
- **D. India frequency:** very high — Amazon/Flipkart/Myntra/Meesho commission structures are named
  explicitly as UniReco's reconciliation targets.
- **E. Sanocea status:** `IMPLEMENTED+PROVEN` in *shape* (dual-dimension reconciliation is a confirmed
  genuine Sanocea strength per the combined audit, Section 6) but **not proven against any real Indian
  marketplace settlement feed** — the proven instances are WooCommerce/Shopify/BigCommerce-shaped, not
  marketplace-commission-shaped.
- **F.** The canonical dual-status model should extend cleanly — this is the same "operational vs.
  financial truth" pattern, applied to a new *source* of financial truth (a marketplace settlement
  report) rather than a new concept.
- **G.** Reconciliation (canonical field, already exists) + connector (marketplace settlement-feed
  ingestion, new).
- **H.** Low — the reconciliation *logic* is already generic; the fee-category vocabulary
  (Commission Fee, Commission Override Fee, Fixed Fee, Payment Gateway Collection Fee, Pick and Pack Fee,
  Refund Commission Fee, Shipping Fee) is marketplace-specific and belongs in connector-level
  configuration, not hardcoded into the canonical model.
- **I.** Yes, directly — this is the deepest confirmed reconciliation depth found in this program so far.
- **J. Priority: P1** for India-first — the fee-category vocabulary found here is a genuinely useful,
  concrete design input for whatever Sanocea eventually builds against a real Indian marketplace
  settlement feed.

*Evidence:* UniReco tracks Commission Fee, Commission Override Fee, Fixed Fee, Payment Gateway Collection
Fee, Pick and Pack Fee, Refund Commission Fee, and Shipping Fee as distinct reconciliation categories,
supports SKU-level commission overrides, provides UTR-level (transaction-reference) matching to identify
missing payments or overcharges, and explicitly targets Flipkart, Amazon, Myntra, and Meesho by name
([unicommerce.com/payment-reconciliation-solution-unireco](https://unicommerce.com/payment-reconciliation-solution-unireco/);
[unicommerce.com/blog/marketplace-payment-reconciliation-the-invisible-margin-leak-killing-your-profitability](https://unicommerce.com/blog/marketplace-payment-reconciliation-the-invisible-margin-leak-killing-your-profitability/)).
This reconfirms and deepens the combined audit's existing UniReco citation. **Category 1** — UniReco is
positioned as a Unicommerce (not Shipway/Convertway) product across all sources found.

### 2.10 Claims/disputes management

- **A.** When a marketplace/buyer disputes an order (item not received, wrong/damaged/incomplete), the
  merchant needs to counter with evidence before a refund/penalty is auto-applied.
- **B.** Marketplaces default to buyer-favorable resolution absent a timely, evidenced counter — a
  process failure (missed dispute window, no evidence on hand) is a direct revenue loss.
- **C.** Any merchant on a marketplace with a buyer-dispute mechanism — SME onward.
- **D. India frequency:** high, implied by the same marketplace-commission depth as 2.9, though the
  claims/disputes evidence found this pass is thinner than the reconciliation evidence.
- **E. Sanocea status:** `MISSING`/`UNKNOWN` — the combined audit did not evidence a Sanocea
  claims/disputes mechanism distinct from its general exception/approval model.
- **F.** Plausibly an extension of the existing `ExceptionRecord`/`Approval` pattern (a dispute is a
  specific exception type requiring evidence attachment and a deadline), not a wholly new concept.
- **G.** Canonical domain (dispute as an exception type with a deadline field) + human exception (evidence
  gathering is not automatable without a real image/video-capture integration).
- **H.** Low — generic dispute-with-deadline-and-evidence modeling is not marketplace-specific, provided
  the evidence-format requirements (which vary per marketplace) stay in the connector layer.
- **I.** Yes, potentially — a deadline-aware exception queue is exactly the kind of thing a human
  currently tracks manually or misses.
- **J. Priority: P2** — real, but this pass's evidence is thinner than for reconciliation/NDR, so
  confidence is lower; worth a dedicated research pass before committing higher priority.

*Evidence:* found via a Unicommerce blog title ("Win More Claims With Marketplace Dispute & Claims
Management") and general framing ("Marketplace disputes are formal complaints raised by buyers or
marketplaces... result in refunds, claim deductions, or seller penalties unless countered") rather than
a dedicated product page with mechanism-level detail
([unicommerce.com/blog/marketplace-dispute-claims-management-solutions](https://unicommerce.com/blog/marketplace-dispute-claims-management-solutions/)).
Whether this is a genuinely dedicated module or a UniReco-adjacent feature is **`UNKNOWN`** — flagged
honestly rather than asserted.

### 2.11 Order cancellation — a real, timing-dependent state machine

- **A.** Cancel an order cleanly regardless of *when* the cancellation request arrives relative to
  invoicing/dispatch, without leaving inventory or marketplace state inconsistent.
- **B.** A naive "just cancel it" model breaks the moment the order has already been invoiced or shipped
  — inventory has to be put away correctly, and a dispatched item becomes a courier-return case, not a
  simple cancellation.
- **C.** Every segment — cancellation is universal.
- **D. India frequency:** high — cancellation-after-dispatch is common enough with COD orders (customer
  refuses at the door) that it interacts directly with the NDR/RTO surface (Section 2.3).
- **E. Sanocea status:** `IMPLEMENTED+PROVEN` (3 real platforms) per the combined audit, but the
  *timing-dependent branching* (pre-invoice / post-invoice-pre-dispatch / post-dispatch) found here is
  more explicit than anything documented as proven in Sanocea's own certifications — worth verifying
  Sanocea's cancellation logic actually branches this precisely, rather than assuming "cancellation
  works" covers all three cases equally well.
- **F.** Likely already fits the canonical model if `OrderStatus`/`Shipment` state transitions are rich
  enough — this is a verification task, not necessarily new design.
- **G.** Canonical domain (state-transition rules) + connector (marketplace cancellation-event posting).
- **H.** Low.
- **I.** Already yes, if the verification in F holds.
- **J. Priority:** not a new gap — a **verification item**: confirm Sanocea's cancellation logic branches
  correctly for the post-dispatch/courier-return case specifically, since that's the case most likely to
  be under-tested (it's the least common path in normal certification testing).

*Evidence:* pre-invoice cancellation requires no additional action; post-invoice-pre-dispatch requires a
putaway process (`PUTAWAY_CANCELLED_ITEM`); post-dispatch cancellation is treated as a courier-returned
item requiring return-manifest addition and a different putaway code
(`PUTAWAY_COURIER_RETURNED_ITEMS`); cancellation is posted back to the originating marketplace at the
same time it's processed in Uniware; item-wise (partial) cancellation is supported
([documentation.unicommerce.com/docs/post-orders-cancel.html](https://documentation.unicommerce.com/docs/post-orders-cancel.html);
[documentation.unicommerce.com/docs/post_cancel_to_uc.html](https://documentation.unicommerce.com/docs/post_cancel_to_uc.html)).
**Category 1**, native Uniware.

### 2.12 Pricing/packaging — a direct contrast to Sanocea's commercial principle

- **A.** N/A — this section documents competitor pricing structure, not a merchant problem.
- **Findings:** Unicommerce publishes three named plans gated by **both** facility count and SKU-count
  ceiling, with features added at each tier:
  - **Standard:** 1 facility, 100,000 SKUs, basic returns management only.
  - **Professional:** 2 facilities, 300,000 SKUs, adds returns management, **payment reconciliation**,
    mobile app, **9 user roles**, purchase management, SKU-level barcoding.
  - **Enterprise:** 3+ facilities, unlimited SKUs, unlimited/customizable user roles, item-level
    barcoding, same reconciliation/purchase-management feature set as Professional.
  - Overall billing is described as a **pay-per-order model** with custom, quotation-based final pricing
    ([saasworthy.com/product/unicommerce/pricing](https://www.saasworthy.com/product/unicommerce/pricing);
    [itqlick.com/unicommerce/pricing](https://www.itqlick.com/unicommerce/pricing)). No specific ₹/month
    figures were found in reliable public material — treat exact numbers as
    `UNKNOWN — no reliable public pricing evidence found`, per the mandate's instruction not to rely on
    unverified third-party comparison sites.
- **Direct tension with Sanocea's commercial principle (Mandate Section 1):** Unicommerce's own tiering
  gates **payment reconciliation** — arguably the single most operationally valuable capability in its
  entire product line (Section 2.9) — behind the Professional tier, not available on Standard. This is
  precisely the "Starter reconciliation / Advanced reconciliation" tiering pattern the mandate explicitly
  instructs Sanocea **not** to build. Unicommerce is a real, evidenced example of a mature competitor
  doing exactly what the mandate warns against — useful as a **negative** design reference: Sanocea's
  "price by SKU capacity, not capability" positioning is a genuine, verifiable point of difference against
  Unicommerce specifically, not just a Linnworks contrast (Section 2.10 of the Linnworks audit made the
  same point about RBAC gating; this is the same pattern, applied to reconciliation instead).
- **J. Priority:** not a build item — a **positioning** input. Sanocea should feel confident stating "even
  Unicommerce gates reconciliation behind a paid tier; Sanocea does not" as a differentiated, evidenced
  claim once reconciliation ships for every merchant regardless of plan.

---

## 3. Thinner-evidence capability summary

| Capability | Unicommerce status | Classification | Note |
|---|---|---|---|
| Catalogue/PIM, bulk product ops, inventory sync | Confirmed real, deep (Kafka delta + snapshot reconciliation) | Native (1) | Table-stakes, with a genuinely useful reliability *pattern* (stream + periodic full-reconciliation safety net) worth absorbing as a principle. |
| FBA / dropship / 3PL fulfilment-model integration | Confirmed real — FBA addable as a channel; platform explicitly unifies dropship/3PL/FBA/omnichannel fulfilment models | Native (1) | Not independently deep-dived at Linnworks' level of mechanism detail this pass. |
| Quick-commerce (Blinkit, Zepto) integration | Confirmed real, named | Native (1) | An India-specific fulfilment surface Linnworks' research never touched — dark-store/rapid-delivery order dynamics likely have their own exception shapes, `UNKNOWN` in depth. |
| Reporting/BI, "Excel replacement" positioning | Confirmed real — automated opening/closing balance reports, product-level ledgers for audit, customizable dashboards | Native (1) | Positioning claim ("Excel replacement") is marketing framing; the underlying reporting depth is real but not independently deep-dived. |
| WhatsApp/SMS order notifications (status/tracking, one-way) | Confirmed real — claims up to 80% WISMO-query reduction | **Convertway/Shipway (2)**, not native Uniware | Same "notification, not conversation" shape as Linnworks' Track-My-Order widget, but delivered through a group-owned marketing-automation product rather than the core OMS. |
| WhatsApp chatbot (FAQs, order tracking, return-initiation, product recommendations) | Confirmed real — no-code bot builder, 24/7, "pre-purchase, post-purchase and support queries" | **Convertway (2)**, not native Uniware, not Shipway | See Section 4 — this is a materially different finding from Linnworks and deserves its own discussion. |
| AI voice agent "Catalyst" (abandoned-checkout recovery calls) | Confirmed real, bilingual, launched by Convertway | **Convertway (2)** | Growth/conversion tool, not an operations AI feature — see Section 5. |
| RBAC/permissions | Confirmed real, but **capability-gated by pricing tier**, not by a coherent permission model — Professional=9 roles, Enterprise=unlimited/customizable | Native (1) | See Section 2.12 — a real contrast point against the mandate's commercial principle. |
| Idempotency | `NF` carried forward from the combined audit's Pass 3 — searched specifically then, nothing found | N/A | A genuine Sanocea advantage, reconfirmed rather than newly researched this pass. |
| AI-assisted *operations* (not marketing) | `NF` — no public claim found for Uniware/Shipway specifically (Catalyst is a Convertway growth tool, not an ops-AI feature) | N/A | Consistent with the combined audit's Pass-3 finding of no core-OMS AI claim; the group *does* have real AI (Catalyst), but it sits in the marketing product, not operations — a meaningfully different pattern from Linnworks' Spotlight AI, which is an *operations* AI feature. |

## 4. Customer support — operate vs. provide (Mandate Section 7)

This is the sharpest divergence from the Linnworks finding. Where Linnworks had **zero** native or
group-owned conversational-support capability (100% third-party, via Replyco/Gorgias), Unicommerce's
group **does** own a conversational-support-adjacent product — but it sits in the marketing-automation
subsidiary, not the core OMS, and its own marketing language blurs "support" and "conversion" together in
a way worth calling out explicitly rather than accepting at face value.

**What was found, and how it's classified:**

- **Convertway's WhatsApp chatbot** (category 2, Unicommerce-group-owned via Shipway) automates "FAQs,
  order tracking, return management, and product recommendations" for end customers, using a no-code bot
  builder, and is marketed as providing "24/7 assistance for pre-purchase, post-purchase and support
  queries"
  ([theconvertway.com/whatsapp-chatbot](https://www.theconvertway.com/whatsapp-chatbot/);
  [d7networks.com — WhatsApp order tracking use case](https://d7networks.com/whatsapp-chatbot/use-case/real-time-order-tracking-on-whatsapp/)).
  Per the mandate's report/suggest/respond/execute/autonomously-resolve scale, order-tracking and FAQ
  responses read as `AUTOMATED EXECUTION` for those specific narrow intents; "return management" as a
  chatbot flow is not detailed enough in public material to confirm whether it *executes* a return
  (creates the RMA, generates a label) or merely *informs* the customer how to initiate one — this
  specific gap is `UNKNOWN`, not assumed either way.
- **Unicommerce's own support portal chat** (`support.unicommerce.com`) is, exactly as with Linnworks'
  `help.linnworks.com`, Unicommerce supporting *its own merchant customers*, not a feature for merchants
  to support *their* end customers
  ([support.unicommerce.com — chat support](https://support.unicommerce.com/index.php/knowledge-base/reach-out-to-unicommerce-in-the-simplest-way/)).
  This distinction, called out in the Linnworks audit, holds equally here — do not conflate the two.
- No evidence surfaced of native email/live-chat/Instagram-social handling for end-customer support
  anywhere in the Uniware/Shipway/Convertway stack — the WhatsApp chatbot is the only channel with real,
  cited depth.

**Classification table:**

| Channel | Unicommerce-group capability | Classification |
|---|---|---|
| WhatsApp — order-status/FAQ/tracking | Convertway chatbot, no-code bot builder | `AUTOMATED EXECUTION` (group-owned, category 2) |
| WhatsApp — return initiation | Convertway chatbot flow named "return management" | `UNKNOWN` — execute vs. inform not confirmed |
| Email/live chat/Instagram-social conversations | Not found anywhere in the stack | `NOT FOUND` |
| Proactive NDR-related customer contact | Present via Shipway's NDR/branded-follow-up notifications (Section 2.3) | `AUTOMATED EXECUTION` for notification; re-attempt *decision* still requires a human/ops action in the Shipway NDR panel |
| Human handoff | Not confirmed for the Convertway chatbot specifically | `UNKNOWN` |

**Implication for Sanocea:** Unicommerce's group is meaningfully ahead of Linnworks on *breadth* of
customer-facing automation (a real, group-owned WhatsApp chatbot beats Linnworks' zero native
conversational capability), but it is not confirmed to be canonically connected to the same operational/
financial truth Uniware and UniReco use — there is no public evidence the Convertway chatbot's "return
management" flow writes into the same reconciliation state UniReco reads. If that gap is real (not just
unresearched), it is the same fragmentation pattern as Linnworks+Replyco, just with better individual
components. Sanocea's proven (Phase 4.6) ability to trigger a real refund from a support conversation
through the *same* policy/approval path an operator uses remains a genuine, currently-true differentiator
against Unicommerce specifically — arguably sharper here than against Linnworks, precisely because
Unicommerce's pieces look more impressive individually, which makes the absence of confirmed cross-system
canonical connection a more consequential, not less consequential, gap.

## 5. Growth/marketing — observed only (Mandate Section 8)

Unlike Linnworks (`NOT FOUND` across the board), Unicommerce's group has a real, dedicated
growth/marketing product: **Convertway**, an AI-enabled marketing-automation platform for abandoned-cart
recovery, WhatsApp/SMS/RCS campaigns, and — as of this pass's research — a bilingual AI voice agent
("Catalyst") that places outbound calls to recover abandoned checkouts
([marketscreener.com — Convertway Catalyst launch](https://www.marketscreener.com/news/unicommerce-s-convertway-rolls-out-bilingual-ai-voice-agent-catalyst-for-e-commerce-brands-ce7e58dfde8af420);
[theconvertway.com](https://www.theconvertway.com/)).

**Classification against the mandate's checklist:**

| Growth/marketing capability | Finding | Classification |
|---|---|---|
| Abandoned-cart recovery (WhatsApp/SMS) | Confirmed real, cross-platform (Shopify, WooCommerce, Magento, PrestaShop, Wix, custom checkouts) | `AUTOMATED EXECUTION` (Convertway, category 2) |
| Outbound AI voice-call recovery ("Catalyst") | Confirmed real, bilingual, recently launched | `AUTOMATED EXECUTION` (Convertway, category 2) |
| WhatsApp/SMS campaign sending | Confirmed real | `AUTOMATED EXECUTION` (Convertway, category 2) |
| Amazon PPC, Flipkart Ads, Myntra advertising, Meta/Google Ads, SEO, listing optimization, A+ content, pricing/promotions engine | No evidence found in this pass | `NOT FOUND` |
| Closed-loop ad-spend → order → margin → fees → logistics → returns → contribution-margin attribution | No evidence found | `NOT FOUND` |

**Assessment:** Convertway is real and more capable than anything found for Linnworks, but its scope is
**conversion/retention automation** (recover an abandoned cart, notify about an order), not **ad-spend
management or attribution** — it does not touch the paid-advertising side of growth at all in the
evidence gathered. The closed-loop contribution-margin question the mandate specifically asks about
remains unanswered by this pass, for this competitor, same as for Linnworks. This is consistent with the
combined audit's landscape-discovery flag that Rithum remains the more plausible candidate for that
pattern, not yet verified.

## 6. After buying Unicommerce, what does the merchant still pay a human to do? (Mandate Section 9)

**Direct evidence from real Indian job listings** (searched via "Naukri Unicommerce ecommerce executive,"
"Unicommerce marketplace executive operations executive job responsibilities India"): a live listing for
"Ecommerce Operations Executive" posted directly by **Unicommerce E Solution Limited** itself (Noida,
₹18,000-₹26,000/month) confirms the company employs its own operations-executive roles
([workindia.in](https://www.workindia.in/jobs/ecommerce_operations_executive-sector_2_noida-delhi-7032337/)).
More directly relevant — merchant-side job listings surfaced requiring **"strong working knowledge of
Unicommerce OMS (mandatory)"** with listed responsibilities including: managing the OMS for daily order
processing across all online sales channels; **handling channel link/unlink setup** for marketplaces
including Amazon, Flipkart, Meesho, Myntra, and Tata Cliq; **troubleshooting sync and mapping issues**;
and **Excel skills for reporting and data handling** — evidence gathered from aggregated job-search
results (Naukri/Indeed/WhatJobs listings for "Unicommerce" roles) rather than one single verbatim posting,
so treat the specific phrasing as representative of a real, recurring pattern across multiple listings,
not a single verified quote.

**Separated per the mandate's required breakdown:**

- **Physically unavoidable human work:** none identified specifically from Unicommerce's own capability
  set beyond what any OMS requires (physical picking/packing still needs a human hand unless a real WMS-
  execution layer is added — same finding as against Linnworks).
- **Repetitive deterministic work (candidate for automation):** channel link/unlink setup when adding or
  reconfiguring a marketplace connector; sync/mapping-issue troubleshooting between Uniware and each
  marketplace; reconciling COD remittance discrepancies flagged by UniReco but not yet auto-resolved (the
  tool flags the discrepancy — a human still decides and acts on the dispute, per Section 2.2's
  `PAYMENT DISPUTED` status existing as a queue, not an auto-resolution); manual putaway-code selection
  during the cancellation state machine (Section 2.11) at the specific timing branches.
- **Ambiguous work suitable for AI:** interpreting *why* a specific marketplace commission line looks
  wrong before filing a dispute (a genuinely ambiguous judgment call UniReco flags but does not resolve);
  deciding whether an NDR should get a re-attempt or go straight to RTO based on context UniReco/Shipway's
  panel doesn't automate (Section 2.3) — the tool presents the two options, a human still chooses.
- **Approval/risk work:** the `PAYMENT DISPUTED` and dispute-filing decision itself (Section 2.10) is a
  real financial-risk judgment call no automation was confirmed to make on the merchant's behalf.
- **Advertising/growth work:** entirely outside Uniware/Shipway/UniReco's scope, and only partially inside
  Convertway's scope (cart recovery, not ad-spend/attribution) — a human or separate tool still runs any
  actual paid-advertising operation (Section 5).
- **Work caused by gaps between systems:** the clearest finding of this section. Because Uniware, Shipway,
  UniReco, and Convertway are separate products under one shareholder (Section 0) rather than one
  canonical system, a human is very plausibly the one bridging them today — e.g., manually confirming
  that a Convertway-initiated "return management" WhatsApp flow actually resulted in the RMA/refund state
  UniReco's reconciliation expects to see, since no evidence was found of that connection being automatic.
  This specific gap is inferred from the corporate/product-boundary evidence in Section 0, not directly
  observed in a job listing — flagged as inference, not confirmed fact.

**Strategic reading:** Unicommerce's group has individually strong pieces (best-in-program marketplace
breadth, COD/NDR/RTO depth, and a real customer-facing WhatsApp automation product) but the same
structural opportunity as Linnworks: a human is very likely the integration layer between Uniware,
Shipway, and Convertway today, exactly the role Sanocea's canonical, single-system model is built to
remove. The job-listing evidence (channel link/unlink setup, sync/mapping troubleshooting, Excel
reporting) is real, concrete confirmation that "deploy Unicommerce" does not mean "no more ops executive"
— it means a differently-scoped ops executive, still doing meaningful manual/deterministic work.

## 7. Automation hierarchy — does Unicommerce change the differentiation? (Mandate Section 10)

- **Deterministic-first** — Unicommerce's Smart Fill/proximity allocation, UniReco's rule-based fee
  pre-calculation, and Shipway's rule-based courier selection are all the same deterministic-first pattern
  under different names, in a different product each time. This reconfirms (does not weaken or
  strengthen) the Linnworks-audit finding that deterministic-first automation is industry-standard, not
  Sanocea-unique.
- **AI only for ambiguity** — genuinely different picture than Linnworks: Unicommerce's confirmed AI
  feature (Catalyst) sits in the *marketing* subsidiary, not operations. No AI-assisted *operational*
  decision (allocation, reconciliation-dispute judgment, NDR re-attempt/RTO choice) was found anywhere in
  Uniware/Shipway/UniReco. This means Sanocea's "AI only for ambiguity, applied to *operations*" framing
  is **not** pre-empted by Unicommerce the way Linnworks' Spotlight AI pre-empted it — but Sanocea's own
  `AIProvider` is still a non-inferencing stub, so this is a *relative* opening, not a current Sanocea
  capability advantage. State plainly: against Unicommerce specifically, "AI for operational ambiguity" is
  an open field, not a race Sanocea is already behind in the way it is against Linnworks.
- **Human only for genuine uncertainty/risk** — the dispute-filing decision (Section 6) and the NDR
  re-attempt/RTO choice (Section 2.3/6) are both real human-decision points Unicommerce's tools surface
  but do not resolve — structurally similar to Cin7's credit-hold gate (combined audit) and consistent
  with Sanocea's own `Approval`/`ExceptionRecord` pattern, reinforcing that this is a real, recurring
  industry pattern worth keeping, not something to abandon under "agentic" pressure.
- **Net assessment:** against Unicommerce specifically, Sanocea's differentiated bet is sharper than
  against Linnworks on the AI axis (no operational-AI precedent to catch up to) and equally sharp on the
  canonical-cross-domain-system axis (Section 4, Section 6) — but weaker on raw India-market-specific
  operational depth (marketplace breadth, COD/NDR/RTO, commission-fee granularity), none of which Sanocea
  has built or proven yet.

## 8. Capabilities Sanocea should absorb

Absorb the underlying pattern; do not copy Unicommerce/Shipway/Convertway's implementation, API shape,
UI, or documentation text. **This table is a proposal for review — nothing here is authorized for
implementation** (per the user's explicit instruction).

| # | Merchant problem | Competitor evidence | Why useful | Sanocea current state | Generic design principle | Canonical-model impact | Implementation location | Human workload eliminated | India relevance | Global relevance | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | COD cash-remittance reconciled against expected order value, with tolerance-aware matching | UniReco COD Remittance Reconciliation, with a real state machine (`RECONCILED` / `RECONCILED BY DELTA` / `RECONCILED MANUALLY` / `PARTIAL PAYMENT` / `PAYMENT DISPUTED`) | Confirmed India-critical financial-leakage pattern with a genuinely well-designed status vocabulary | `MISSING` for remittance specifically (dual-status *shape* exists, never exercised against a COD feed) | COD remittance is another instance of Sanocea's existing operational-vs-financial-truth reconciliation, with an explicit tolerance/delta concept and a distinct disputed-but-unresolved state | Extend existing reconciliation status enum with a tolerance-matched state; no new object | Reconciliation (canonical) + connector (courier remittance feed) | Manual/Excel COD-remittance matching | Very high | Moderate (COD is less universal outside India but not absent) | **P1** |
| 2 | Named per-marketplace exception handling (Amazon India, Flipkart, Myntra, Meesho, quick-commerce) | Unicommerce's 151+ marketplace integrations with quick-commerce (Blinkit/Zepto) breadth | Confirms this is the single most universal India-merchant need in the program so far | `PARTIAL` — zero India-marketplace connector exists yet | Marketplace quirks resolve to a canonical order/exception shape at the connector boundary; core never special-cases a named marketplace | Connector only, if disciplined per Mandate Section 2 | Connector | Manual channel link/unlink setup, sync/mapping troubleshooting (confirmed via job listings, Section 6) | Very high | Low directly, high as a template for other regional marketplaces | **P1** |
| 3 | NDR re-attempt vs. RTO decision workflow, with proactive customer contact before RTO | Shipway's NDR panel (Delhivery/Bluedart/Xpressbees compatibility, two named actions) | Confirmed high-cost Indian-logistics failure mode with no Sanocea coverage at all today | `MISSING` | An NDR exception state on `Shipment`, with re-attempt/RTO as explicit, policy-gated branches, courier-specific codes resolved at the connector | Canonical domain (new exception-state concept) + deterministic engine + connector | Canonical domain + deterministic engine + connector | Manual NDR triage and customer-contact decisions | Very high | Moderate (RTO dynamics are less severe outside high-COD markets) | **P1** |
| 4 | Network-wide, fill-maximizing multi-warehouse allocation (not just nearest-warehouse) | Unicommerce's "Smart Fill" framing — evaluate all pending orders against all available inventory simultaneously | Independently validates (with Linnworks) that multi-location allocation is universal, and adds a sharper allocation *philosophy* (maximize network fill, not just proximity) worth considering in Sanocea's own design | `ARCHITECTURAL ONLY` | Allocation considers the full order backlog and full network inventory as one optimization, not order-by-order greedy assignment — a design nuance to weigh, not a mandate to copy | Canonical domain + deterministic engine (same P0 item as the Linnworks audit, sharpened) | Canonical domain + connector | Manual "which warehouse ships this" decision | High | High | **P0** (reconfirmed, unchanged from Linnworks audit) |
| 5 | Marketplace commission/fee reconciliation with a named fee-category vocabulary | UniReco's fee categories (Commission Fee, Commission Override Fee, Fixed Fee, Payment Gateway Collection Fee, Pick and Pack Fee, Refund Commission Fee, Shipping Fee) and UTR-level matching | Concrete, real-world fee taxonomy to design a connector-level settlement-feed parser against, once a real marketplace connector exists | `IMPLEMENTED+PROVEN` in shape, `MISSING` against any real marketplace feed | Fee-category vocabulary lives in connector configuration (marketplace-specific), reconciliation logic itself stays generic | Connector (fee-category mapping) + reconciliation (existing canonical field) | Connector + reconciliation | Manual settlement-statement line-item checking | Very high | Moderate (the specific fee names are India-marketplace-specific; the pattern is universal) | **P1** |
| 6 | Three distinct bundle/kit/BOM stock-timing behaviors, not one generic "bundle" concept | Unicommerce's explicit Bundle (dynamic, pick-time) / Kit (static, pre-assembled) / BOM (own SKU, manufactured) distinction | Sharper design input than the Linnworks composite-item finding alone — suggests the eventual Sanocea composite-SKU model needs an assembly-timing attribute, not just a parent/child relationship | `MISSING` | A composite relationship carries an explicit assembly-timing attribute (dynamic-at-sale vs. static-pre-assembled vs. independently-manufactured), generic across merchants | Canonical domain (composite relationship + timing attribute) + deterministic engine | Canonical domain + deterministic engine | Manual bundle/kit stock tracking | High | High | **P2** (reconfirmed from Linnworks audit, design sharpened) |
| 7 | A real-time sync stream backed by periodic full-reconciliation, never trusting the stream alone | Unicommerce's Kafka-delta-plus-off-peak-snapshot-reconciliation inventory-sync pattern | A concrete reliability principle directly relevant to Sanocea's own webhook-plus-polling architecture (already partially proven per the combined audit's "1 real defect found+fixed" polling/recovery finding) | `PARTIAL` | Every real-time sync path has a periodic, independent full-reconciliation pass as a structural safety net, not an optional afterthought | Deterministic engine / operational-reliability principle, not a new canonical object | Deterministic engine | Reduces silent inventory drift a human would otherwise discover only after an oversell | High | High | **P2** |
| 8 | Multi-channel WhatsApp customer notification + basic chatbot for order-status/FAQ intents | Convertway's WhatsApp chatbot (no-code bot builder, order-tracking flow) | Confirms WhatsApp-first customer communication is now table-stakes in the Indian market specifically, beyond the one-way notification Sanocea already has via other channels | Sanocea's Chatwoot-based support is `IMPLEMENTED+PROVEN` but not confirmed WhatsApp-specific | WhatsApp is one more channel into the same canonical intent→policy→execute/AI/human flow (Mandate Section 7) — never a separate, disconnected chatbot product bolted on after the fact | Connector (WhatsApp Business API channel) — no canonical-model change, since the existing support-conversation model is channel-agnostic by design | Connector | Reduces WISMO-style customer-status queries a human currently answers manually via other channels | Very high | Moderate-high (WhatsApp dominance is more pronounced in India/APAC than in Linnworks' UK/global market) | **P1** — sharper for India-first than any Linnworks finding, since it's a channel gap, not a new capability |

## 9. Priority reconciliation vs. Linnworks

**Explicitly for review, not for implementation.** This section compares the two completed audits per the
user's instruction, and changes nothing in either audit's own file.

**Capabilities both mature systems independently validate** (higher confidence these are real, universal
merchant problems, not one platform's idiosyncrasy):

- **Multi-location/multi-warehouse order allocation** — Linnworks' MLI+Rules-Engine and Unicommerce's
  Smart Fill+proximity-allocation are architecturally different approaches (criteria-based routing vs.
  network-wide fill-maximization) to the *same* problem. This is now validated by two independent mature
  platforms with different philosophies, which is stronger evidence than either alone — **P0 status is
  reconfirmed, not just carried forward.**
- **Bundles/kits as a real, non-trivial merchant need requiring more than one construct** — Linnworks'
  parent-cannot-transfer constraint and Unicommerce's three-way Bundle/Kit/BOM distinction are different
  specific mechanics pointing at the same underlying truth: a single generic "bundle" concept is
  insufficient. This raises confidence in Section 8, item 6 above.
- **Deterministic-first automation as industry-standard, not Sanocea-unique** — reconfirmed a third time
  (Linnworks' Rules Engine, Unicommerce's three separate rule engines across Smart Fill/UniReco/Shipway).

**India-specific capabilities Linnworks' research never exposed:**

- COD remittance reconciliation (Section 2.2) — not applicable to Linnworks' UK/global-first market at
  the volume/severity found here.
- NDR/RTO as a named, dedicated workflow (Section 2.3) — Linnworks was `UNK` on this entirely; Unicommerce
  confirms it as real, named, and India-critical.
- Named per-marketplace (Amazon India/Flipkart/Myntra/Meesho/quick-commerce) integration depth (Section
  2.1) — Linnworks' marketplace integrations were confirmed real but not researched at this
  India-specific granularity.
- Marketplace commission-fee reconciliation at a named-category level (Section 2.9) — Linnworks had no
  equivalent finding; Sellercloud's channel-scoped reconciliation report (combined audit) is the closer
  analogue, but even that lacked UniReco's fee-category granularity.
- WhatsApp-native customer automation (Section 4, Section 8 item 8) — a real capability gap between the
  two audits driven by market, not platform maturity: Linnworks' market doesn't demand WhatsApp the way
  India's does.

**Linnworks capabilities that look less important specifically for an India-first launch:**

- **Full warehouse pick/pack/dispatch execution (wave/zone/batch picking, TOTE abstraction)** — already
  marked `DO NOT BUILD now` against Linnworks on the reasoning that most of Sanocea's likely SMB/DTC
  target merchants use a 3PL rather than running a multi-bin warehouse. Unicommerce's own confirmed depth
  here (pigeonhole/bundled sorting, FIFO/FEFO, per the combined audit) plus its explicit multi-fulfilment-
  model unification (3PL/dropship/FBA/quick-commerce all as first-class options, Section 3) reinforces
  rather than weakens that judgment — if even the most India-specific mature platform treats 3PL/dropship
  as a fully first-class alternative to running your own warehouse, that's more evidence a minimal Sanocea
  merchant doesn't need deep in-house WMS execution, not less.
- **RBAC granularity as a P1** — both platforms gate RBAC behind pricing tiers (Linnworks: paid-plan-gated
  permission granularity; Unicommerce: role-count-gated by SKU/facility tier, Section 2.12). This doesn't
  change RBAC's priority for Sanocea, but it sharpens the *positioning* angle: Sanocea not gating RBAC
  behind price tier is now a differentiator against **two** competitors, not one.

**Recommendations whose priority should shift:**

- **Indian-marketplace connector work moves to a firmer P1** than the Linnworks-only research alone would
  have suggested — Section 6's job-listing evidence (channel link/unlink setup, sync/mapping
  troubleshooting) is concrete, current, real-world confirmation that this exact gap costs merchants real
  ongoing labor today, not a hypothetical.
- **A real `AIProvider` implementation (Linnworks Section 2.9 audit, priority P1)** should be read as
  *lower urgency specifically for operational parity* against Unicommerce (no operational-AI precedent
  found here to catch up to) but the underlying architectural gap (Sanocea has zero real AI inference
  anywhere) is unchanged — do not lower its priority outright, but note the competitive-parity argument
  for it is weaker against this specific competitor than against Linnworks.
- **WhatsApp as a support/notification channel** is a new, India-specific P1 (Section 8, item 8) that
  neither the Linnworks audit nor the combined audit surfaced with this level of evidence — this is
  arguably the single most concrete *new* priority this pass adds relative to the Linnworks-only
  baseline.

**Capabilities Sanocea should eventually absorb from Unicommerce specifically** (superset already listed
with full detail in Section 8): COD remittance reconciliation with tolerance-aware matching; named
per-marketplace connector depth; NDR/RTO as an explicit workflow; network-wide fill-maximizing allocation
as a design input (alongside Linnworks' criteria-based routing) for the shared P0 allocation item;
marketplace commission-fee-category vocabulary as a connector-design input; the three-way bundle/kit/BOM
assembly-timing distinction as a design input for the shared P2 bundle item; the stream-plus-periodic-
reconciliation reliability principle; and WhatsApp as a support/notification channel.

**Per the mandate and the user's explicit instruction: none of the above is implemented by this audit.
This report is now complete. Do not automatically begin EasyEcom, Brightpearl, Pipe17, or any other
competitor — the next target should be named explicitly after this file is reviewed.**
