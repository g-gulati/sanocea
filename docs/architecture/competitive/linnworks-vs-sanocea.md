# Linnworks vs. Sanocea — Competitive Capability Audit

Governed by [`../competitive/README.md`](./README.md) (the Sanocea Competitive Research Mandate, v1,
2026-09-11). This is the first per-competitor audit produced under that mandate.

## 0. Scope and evidentiary basis

Sections 1-6 below reuse the Linnworks-specific findings already verified with citations in Pass 3 of
`docs/architecture/sanocea-competitive-capability-audit.md` (a prior, deep, multi-query research pass —
10-15 tool calls specifically against Linnworks' official docs). Those findings are treated as
already-verified evidence per Mandate Section 13 and are re-cited here, reorganized into the mandate's
required question format, rather than re-researched from zero.

Sections 7 and 8 (customer-support operation depth, growth/marketing) are **genuinely new lenses** the
prior passes never applied to Linnworks. Three targeted searches were run this session to fill them
honestly rather than leave them fabricated:

- "Linnworks Helpdesk customer support email live chat WhatsApp ticketing"
- "Linnworks Amazon PPC advertising Google Ads marketing integration"
- "Linnworks customer self-service order tracking portal proactive shipment notification"

Findings from those three searches are cited inline in Sections 7-8. This is still a shallow pass (three
queries, not the ten-plus that produced Section 1-6's depth) — treat Sections 7-8 as directionally
reliable, not exhaustively verified. Anything not reached remains marked `UNKNOWN`, per the mandate's
evidentiary discipline: absence of evidence is never read as evidence of absence.

**Still `UNKNOWN` for Linnworks after this pass** (real gaps to close in a future session, not resolved
findings): tracking-events-to-carrier-API depth, cancellations, exception management, human-approval
gating, auditability, webhook handling, payment lifecycle, settlement reconciliation, COD, supplier
acknowledgement, inbound goods receipt, oversell prevention mechanics, API extensibility, merchant
onboarding friction, operational observability.

---

## 1. Executive summary — Linnworks vs. Sanocea

Linnworks is a mature, warehouse-and-multichannel-listing-first OMS with three genuinely deep,
production-hardened capability clusters Sanocea does not have in any form: **multi-location inventory
as a first-class API concept**, **warehouse pick/pack/dispatch execution** (wave/zone/batch picking, a
unified "TOTE" abstraction spanning trolleys/carts/roll cages/trays), and **a real, shipped, named AI
feature** (Spotlight AI) that does almost exactly what Sanocea's "AI-observes-repeated-decisions
→ promotes to deterministic rule" roadmap intention describes, except Linnworks already ships it with a
quantified customer outcome. Linnworks has no confirmed platform-enforced idempotency (searched
specifically — nothing surfaced) and no confirmed native customer-support-conversation execution
capability — both areas where Sanocea's architecture is either already stronger (idempotency) or
positioned to be stronger once built (support automation, per Section 7).

Linnworks is not a support/finance/procurement system in Sanocea's sense: it has real procurement (PO
auto-creation from min-stock thresholds, supplier portal) but no confirmed finance-reconciliation depth
and no native customer-conversation handling — its own ecosystem routes that need to third-party
helpdesk partners (Replyco, Gorgias). This is the single clearest opening for Sanocea's canonical,
cross-domain model: Linnworks solves the *operational* commerce problem deeply; Sanocea's differentiated
bet is solving the operational-*and*-financial-*and*-support problem as one system.

## 2. Capability-by-capability audit (A-J framework)

Only capabilities with real, cited Linnworks depth get the full nine-question treatment. Thinner
findings are folded into the summary table in Section 3.

### 2.1 Multi-Location Inventory (MLI)

- **A. Merchant problem:** a merchant with more than one stock location (own warehouse + 3PL, or two
  warehouses) needs one true stock number per SKU that's actually split correctly across locations, not
  a single flat count that goes wrong the moment a second location exists.
- **B. Why it exists:** flat single-location inventory silently overships or underships the moment a
  merchant's fulfilment footprint grows past one location — a failure mode expensive enough (oversells,
  refunds, marketplace suspensions) that mature OMSes treat it as core, not optional.
- **C. Relevance:** growing SMEs (the moment they add a second location or a 3PL) through
  high-volume/enterprise. Largely irrelevant to a single-location tiny merchant, but that's a phase, not
  a permanent segment.
- **D. India frequency:** high and rising — a 3PL-plus-own-warehouse or multi-warehouse-across-cities
  setup is common as Indian D2C merchants scale past their first year.
- **E. Sanocea status:** `ARCHITECTURAL ONLY`. `Inventory.location_ref` and `location: str = "default"`
  exist on the model; no real order has ever been allocated across two real locations in any Sanocea
  certification to date.
- **F. Canonical fit:** the field already exists; the gap is behavioral (allocation logic), not
  structural. Likely supportable without a schema change — needs verification once attempted.
- **G. Implementation location:** canonical domain (the allocation decision belongs in core, since
  "which location fulfills this line" is not platform-specific) with connector-level location mapping.
- **H. Core-logic risk:** low, if scoped as "assign to one of N real locations by an explicit rule" —
  high if scoped as a full warehouse-routing optimizer prematurely.
- **I. Human work eliminated:** the manual "which warehouse do I ship this from" decision an operator
  currently makes by hand for every multi-location merchant.
- **J. Priority: P0** — this is already Sanocea's own highest-priority architectural risk (see Section
  10 of the combined audit); Linnworks' first-class MLI API confirms mature platforms treat this as
  non-optional, not a nice-to-have.

*Evidence:* Linnworks Multi-Location Inventory API
([apidocs.linnworks.net/docs/multi-location-inventory](https://apidocs.linnworks.net/docs/multi-location-inventory)).

### 2.2 Order allocation/routing (Rules Engine)

- **A.** Which location and which carrier should fulfil a given order, automatically, without a human
  picking it manually every time.
- **B.** Manual per-order routing decisions don't scale past a handful of orders/day; mature platforms
  externalize the decision into a rule set an ops person configures once.
- **C.** Growing SMEs onward — irrelevant below a second location/carrier.
- **D.** High — most Indian merchants above tiny-SKU scale use more than one courier for cost/serviceability reasons.
- **E. Sanocea status:** `ARCHITECTURAL ONLY` (`location="default"` always — no real routing decision has
  ever executed).
- **F.** Fits Sanocea's existing deterministic-policy-engine pattern directly — this is exactly the shape
  of decision Sanocea's policy layer already handles for other domains (refund approval gates, etc.).
- **G.** Deterministic engine / policy, with merchant-configurable rule inputs (not canonical-domain
  hardcoding).
- **H.** Low risk if the rule *shape* (location/carrier selection by explicit criteria) is generic; would
  become risky only if a specific carrier's own routing logic leaked into the core rule evaluator.
- **I.** Yes — removes the manual "who ships this" triage an ops person currently does per order.
- **J. Priority: P0/P1** — sequenced right after 2.1 (allocation is meaningless without a location model
  to allocate across).

*Evidence:* Linnworks Rules Engine explicitly routes orders to fulfilment location/carrier by criteria
(cited in Pass 3 research; no coding required, per Linnworks' own positioning).

### 2.3 Available-to-sell via bin-type exclusion rules

- **A.** Prevent overselling stock that is physically present but not actually sellable (in quarantine,
  in returns processing, in deep storage awaiting putaway).
- **B.** A naive "count all units in the warehouse as sellable" model oversells the moment any stock sits
  in a non-sellable state — a recurring, expensive failure (customer refunds, marketplace penalties) that
  forced mature platforms to build bin-type-aware ATS math.
- **C.** Relevant once a merchant has any physical inventory-handling process beyond "everything on the
  shelf is sellable" — SME onward.
- **D.** Moderate-high — returns-in-transit and QC-hold stock are common in Indian D2C given COD-driven
  return volume.
- **E. Sanocea status:** `PARTIAL` — a flat inventory count exists; no reserved/committed/quarantine
  formula has been proven.
- **F.** Fits cleanly as an extension of the existing `Inventory` model — a stock **state** dimension
  (sellable / reserved / quarantine / in-transit), not a new object.
- **G.** Canonical domain (the state field) + deterministic engine (the ATS formula).
- **H.** Low — this is a generic inventory-state concept, not platform-specific.
- **I.** Yes — removes the manual "is this stock actually available" judgment call.
- **J. Priority: P1** — directly reduces oversell risk, which is a real financial/reputational cost.

*Evidence:* Linnworks bin-type rules automatically exclude deep-storage/quarantine/returns stock from
ATS (Pass 3 research).

### 2.4 Composite Items (bundles/kits)

- **A.** Sell a bundle of several distinct SKUs as one purchasable listing while keeping accurate stock
  for the underlying components.
- **B.** Bundling is a routine merchandising pattern (gift sets, "buy the pair," multi-packs); without a
  parent/child stock model, merchants either oversell the bundle or manually track it in a spreadsheet.
- **C.** Relevant to nearly every merchant segment — even a tiny merchant sells bundles.
- **D.** High — bundling is extremely common in Indian D2C (combo offers, festival gift sets).
- **E. Sanocea status:** `MISSING` — `Variant.option_values` has no concept of a parent SKU composed of
  child SKUs at all.
- **F.** Not supportable cleanly today — genuinely needs a canonical-model addition (a parent-SKU-with-
  child-SKU-quantities concept), not a policy or connector-level workaround.
- **G.** Canonical domain (the composite relationship itself) + deterministic engine (derived stock
  calculation).
- **H.** Low, if designed generically — the risk is in the failure mode, not the concept: Linnworks'
  own composite parent SKU **cannot itself be warehouse-transferred, only children can**
  ([Composite Items](https://docs.linnworks.com/articles/#!documentation/inventory-composite-items)) —
  a real, documented constraint worth designing around deliberately (an explicit, opinionated rule for
  what happens when a bundle's components aren't co-located) rather than assuming graceful degradation
  is free.
- **I.** Yes — removes manual spreadsheet-based bundle stock tracking.
- **J. Priority: P2** — commercially important (nearly universal merchant need) but not an architectural
  blocker the way multi-location allocation is.

*Evidence:* [Linnworks Composite Items](https://docs.linnworks.com/articles/#!documentation/inventory-composite-items).

### 2.5 Split and merge orders

- **A.** Split: fulfil part of an order now (in-stock lines) and the rest later/from elsewhere, without
  losing the customer's single-order mental model. Merge: combine what the customer experiences as
  separate orders into one shipment to save shipping cost/effort.
- **B.** Partial stock availability and duplicate/rapid-fire customer orders are routine, high-frequency
  events at any real order volume; without split/merge, they become manual order-desk work every time.
- **C.** SME onward — rare at tiny/hobby scale, routine at growing-SME-and-above volume.
- **D.** High — partial stock and repeat same-day orders are common in Indian D2C, especially around
  flash sales/festival spikes.
- **E. Sanocea status:** `MISSING` — zero code path for either.
- **F.** Genuinely non-trivial: Linnworks' own merge eligibility is a narrow, explicit rule list (same
  source+subsource, paid, matching currency/shipping-service/name/address, not on hold, no invoice/label
  printed yet) — this is not a simple flag, and any Sanocea implementation should expect comparably real
  mechanical complexity, not assume it's a one-line feature.
- **G.** Deterministic engine (the eligibility rule set) + canonical domain (an order-lineage/relationship
  concept linking split/merged orders back to their originals).
- **H.** Moderate — the risk is building eligibility rules so specific to one payment/shipping model that
  they stop being generic; keep the rule *shape* configurable, not hardcoded.
- **I.** Yes — removes manual order-desk triage for partial-stock and duplicate-order scenarios.
- **J. Priority: P2/P3** — real, recurring pain, but behind multi-location allocation and bundles in
  sequencing since it compounds on top of both.

*Evidence:* Linnworks split (multi-line despatch, quantity splitting, per-box labels with grouped
tracking) and merge (narrow, explicit eligibility list) mechanics, Pass 3 research.

### 2.6 Warehouse pick/pack/dispatch execution

- **A.** Get a picker to the right physical stock, correctly, at any real order volume, without relying
  on memory or a paper list.
- **B.** Manual, unstructured picking doesn't scale past a small warehouse — mis-picks, wasted walking
  time, and no batching are all real, expensive failure modes mature platforms address with structured
  wave/zone/batch picking.
- **C.** Relevant only to merchants running their own warehouse floor — irrelevant to a merchant using a
  3PL/dropship model exclusively.
- **D.** Moderate in India specifically — many D2C merchants below a certain scale use a 3PL rather than
  running their own warehouse, which caps how much of this segment actually needs full WMS depth.
- **E. Sanocea status:** `MISSING` entirely — Sanocea models fulfilment *observation* and command
  *initiation*, never warehouse-floor *execution*.
- **F.** This would require real new canonical concepts (bins, zones, pick waves) that don't exist today
  — a large addition, not an extension.
- **G.** Would span canonical domain (bin/zone model) + deterministic engine (wave/batch assignment) +
  a genuinely new execution surface (a picker-facing interface), which is out of scope for a
  backend-orchestration OS unless a real merchant with a real multi-bin warehouse is on the roadmap.
- **H.** High risk of scope creep — full WMS parity is explicitly a feature-bloat trap (see Section 9 of
  the combined audit) for Sanocea's likely SMB/DTC target segment, most of whom use a 3PL.
- **I.** Yes, but only for the subset of merchants who run their own warehouse — for 3PL/dropship
  merchants this capability is irrelevant, which matters for prioritization.
- **J. Priority: DO NOT BUILD now / P3 later** — only reconsider once a specific merchant with a real
  multi-bin warehouse is actually on the roadmap; building speculative WMS depth ahead of that need is
  the textbook feature-bloat trap this category invites.

*Evidence:* Linnworks wave/zone/batch picking, bin-level availability-rule exclusion, unified "TOTE"
abstraction (trolleys/carts/roll cages/trays as one scannable concept) — Pass 3 research.

### 2.7 Demand planning / forecasting

- **A.** Know when to reorder before stocking out, without a human staring at a spreadsheet of sales
  history.
- **B.** Reactive reordering (waiting until stock hits zero) causes lost sales and rushed, expensive
  restocking; mature platforms turn sales-history-plus-seasonality into a proactive reorder signal.
- **C.** SME onward — a tiny merchant can eyeball their own stock; it stops being feasible manually once
  SKU count or order volume grows.
- **D.** High — stockouts around festival/sale-season demand spikes are a well-known Indian D2C pain
  point.
- **E. Sanocea status:** `PARTIAL` — a velocity-lookback replenishment recommendation exists
  (`ProcurementService.recommend_replenishment`), no seasonal-trend factoring.
- **F.** Fits cleanly as an extension of the existing procurement recommendation logic — add a
  seasonality factor, not a new subsystem.
- **G.** Deterministic engine (the forecasting formula) reading canonical sales-history data.
- **H.** Low — a generic sales-velocity-plus-seasonality formula is not platform-specific.
- **I.** Yes — removes manual "when do I reorder" judgment calls, especially before demand spikes.
- **J. Priority: P2** — real and valuable, but Sanocea already has a partial version; this is
  incremental improvement, not a from-zero build.

*Evidence:* Linnworks "Stock Forecasting & Demand Planning" using sales history + seasonal trends —
Pass 3 research.

### 2.8 Rules Engine (general workflow automation)

- **A.** Encode routine operational decisions (routing, carrier selection, replenishment triggers) once,
  so they execute automatically instead of being re-decided manually every time.
- **B.** Same root cause as 2.2 — manual per-event decision-making doesn't scale; mature platforms
  externalize repeated decisions into configurable rules.
- **C.** SME onward.
- **D.** High — any merchant past early stage accumulates repeated operational decisions worth
  automating.
- **E. Sanocea status:** `IMPLEMENTED+PROVEN` — Sanocea's own deterministic-first policy engine already
  covers this pattern (refund approval, exception routing, etc.), measured via
  `ai_dependency_rate`/`deterministic_first_resolution_rate`.
- **F.** N/A — already implemented.
- **G.** N/A.
- **H.** N/A.
- **I.** Already yes.
- **J.** Not a gap — this is a confirmed strength (Section 5, differentiator A of the combined audit),
  though not a *unique* one: Linnworks' Rules Engine, Sellercloud's Order Rule Engine, Cin7's automation
  engine, and ChannelEngine's feed/repricing rules are all the same underlying pattern under different
  names. Sanocea's version is more explicitly named and measured, which is a real engineering-discipline
  edge, not a novel idea.

### 2.9 Spotlight AI

- **A.** Find the manual decisions an ops team keeps repeating and turn them into a standing automation
  rule, without the merchant having to notice the pattern themselves.
- **B.** Ops teams often don't realize how much of their own work is a repeated pattern until someone
  (or something) points it out — Linnworks built an AI feature specifically to surface that blind spot.
- **C.** Relevant to any merchant with an ops team large enough to have repeated manual decisions worth
  automating — SME onward.
- **D.** Moderate-high, as Indian D2C merchants scale their ops teams.
- **E. Sanocea status:** `ARCHITECTURAL ONLY` — no real AI inference exists anywhere in the codebase;
  `DeterministicAIProvider` is a stub that never calls a real model. This is precisely the pattern
  Sanocea's own roadmap intention (differentiator J: "AI observes → gets promoted to deterministic rule")
  describes — Linnworks already ships it, named, with a quantified outcome ("30+ hrs/month saved" per
  [itbrief.co.uk](https://itbrief.co.uk/story/linnworks-unveils-spotlight-ai-to-cut-ecommerce-toil)).
- **F.** Fits Sanocea's existing `AIProvider` Protocol abstraction once a real provider is wired in — the
  interface is designed for this, it has just never been exercised with a live model.
- **G.** AI interpretation layer, reading from the same operational-event log Sanocea's policy engine
  already produces, surfacing recommendations for human review (not auto-applying rules).
- **H.** Low, if scoped as "recommend a rule for human approval" rather than "silently rewrite policy" —
  the latter would risk exactly the kind of AI-as-default-execution-engine drift the mandate's automation
  hierarchy (Section 10) explicitly warns against.
- **I.** Yes, potentially significant — this is exactly the kind of pattern-detection a human currently
  has to notice themselves.
- **J. Priority: P1** — Sanocea should not claim differentiator J externally until something like this
  exists; a real `AIProvider` implementation is already P1 in the combined audit's roadmap, and this
  gives it a concrete, scoped first use case (recommend, don't auto-execute) rather than an open-ended
  "wire in AI somewhere" mandate.

### 2.10 RBAC / permissions

- **A.** Let different staff roles (warehouse picker vs. finance approver vs. admin) see and do only what
  their role should.
- **B.** A binary admin/non-admin model breaks down the moment more than a couple of people touch the
  system — mature platforms gate this behind role/permission granularity.
- **C.** Relevant once a merchant has more than one or two staff members touching the system — SME
  onward.
- **D.** Moderate — smaller Indian D2C teams often have 2-5 people sharing system access across
  functions.
- **E. Sanocea status:** `PARTIAL` — two roles (operator/service), coarse.
- **F.** Fits as an extension of the existing role concept — add role granularity, not a new subsystem.
- **G.** Policy / merchant configuration.
- **H.** Low — generic role/permission modeling is not platform-specific.
- **I.** Yes, once support/finance/procurement approval flows are used by more than one human role per
  merchant.
- **J. Priority: P1** — becomes load-bearing exactly when approval-gated flows (refunds, exceptions) are
  used by more than one person per merchant, which will be routine even at Sanocea's initial India
  target segment.

*Evidence:* Linnworks base tier is binary Admin/permission-tree; user/group-level granularity requires
"Advanced or higher" paid plans
([docs.linnworks.com/articles/documentation/settings-permissions](https://docs.linnworks.com/articles/documentation/settings-permissions))
— worth noting as a **contrast**, not a pattern to copy: per the mandate's Section 1 commercial
principle, Sanocea should not gate RBAC granularity behind a paid tier the way Linnworks does.

## 3. Thinner-evidence capability summary

Confirmed real, but not carried to full A-J depth here (already summarized in the combined audit's
matrix, Linnworks column):

| Capability | Linnworks status | Note |
|---|---|---|
| Catalogue/PIM, bulk product ops, marketplace/channel listing, channel mapping, inventory sync | Confirmed real | Table-stakes; no differentiated mechanic surfaced beyond baseline. |
| 3PL / dropshipping | Confirmed real — dedicated "Fulfilment Centre" concept, FTP/URL-post order export, status/tracking import | [apidocs.linnworks.net](https://apidocs.linnworks.net/docs/useful-3pl-integration-endpoints) |
| Returns/exchanges | Confirmed real — unified RMA, "Resend" creates a new Open Order for a different item | Refunds are embedded in the RMA flow, not a separate mechanism. |
| Procurement/POs | Confirmed real — PO auto-creation from min-stock thresholds, supplier portal, supplier performance monitoring | Supplier acknowledgement and goods-receipt depth not reached this pass. |
| Reporting/BI | Confirmed real — customizable dashboards, stock/sales/supplier/operational reports | Not sales-analytics/profitability depth; not reached in detail. |
| Rate limits | Confirmed but dated — 250→150 calls/minute change documented in a 2020 GitHub issue; current numbers not reconfirmed | Should be re-verified before any integration work assumes these numbers. |
| Idempotency | `NF` — searched specifically, no platform-enforced idempotency documentation found | A genuine Sanocea advantage (Section 6). |
| Connector architecture | Confirmed real | No further differentiation surfaced. |

## 4. Customer support — operate vs. provide (Mandate Section 7)

Linnworks does **not** natively execute customer-conversation support. Its own ecosystem routes that
need to third-party helpdesk partners:

- **Replyco** — a dedicated helpdesk product marketed as running "directly from within the Linnworks
  platform or on its own," explicitly for coordinating customer-service communications
  ([replyco.com/linnworks-helpdesk](https://replyco.com/linnworks-helpdesk/)).
- **Gorgias** — another third-party helpdesk integration positioned the same way
  ([gorgias.com/apps/linnworks](https://www.gorgias.com/apps/linnworks)).
- Linnworks' own support center (`help.linnworks.com`) is Linnworks supporting *its own merchant
  customers* (using Linnworks), not a feature for merchants to support *their* end customers — the exact
  distinction the mandate calls out.

What Linnworks **does** provide natively, confirmed:

- A "Track My Order" self-service widget embeddable on a merchant's website/shipping emails, plus
  automated shipping-status notification emails
  ([linnworks.com/features/order-management](https://www.linnworks.com/features/order-management/)).
- Tracking-URL generation pointing to the carrier's own tracking page, includable in despatch emails
  ([help.linnworks.com — Shipping: Tracking URLs](https://help.linnworks.com/support/solutions/articles/7000091567-shipping-tracking-urls)).
- Predictive delivery-issue alerting is referenced in third-party post-purchase integrations (e.g.
  LateShipment.com — [lateshipment.com/integrations/linnworks](https://www.lateshipment.com/integrations/linnworks/)),
  again as an **integration**, not a native Linnworks capability.

**Classification against the mandate's report/suggest/respond/execute/autonomously-resolve scale:**

| Channel | Linnworks capability | Classification |
|---|---|---|
| Order-status/shipment enquiries | Native tracking widget + automated notification emails | `AUTOMATED EXECUTION` (notification only — not a two-way conversation) |
| Email/live chat/WhatsApp/social conversations | Not native — requires Replyco/Gorgias | `INTEGRATION ONLY` |
| Address changes, cancellations, returns, exchanges, refund requests, complaints, NDR interaction | Not confirmed native to the support-conversation flow (returns/exchanges exist as an *operational* RMA mechanism, Section 3, but not as a customer-facing conversational resolution path) | `UNKNOWN` / likely `INTEGRATION ONLY` via the same third-party helpdesk layer |
| Human handoff | Implicit (any third-party helpdesk provides this) | `INTEGRATION ONLY` |

**Implication for Sanocea:** this is a real, evidenced gap in Linnworks' own product, not just an
unresearched cell. Sanocea's existing Chatwoot-based, real-webhook-proven support integration
(`IMPLEMENTED+PROVEN` per the combined audit) combined with the canonical model's ability to trigger a
real refund from a support conversation through the same policy/approval path an operator uses
(proven in Phase 4.6) is a genuine, currently-true differentiator against Linnworks specifically — not
merely a roadmap intention. This should be stated plainly in any Linnworks-facing positioning: Linnworks
requires a third-party helpdesk bolt-on to operate customer conversations at all; Sanocea's support
handling is native and canonically connected to the same operational/financial truth as every other
domain.

## 5. Growth/marketing — observed only (Mandate Section 8)

No native or integrated advertising-execution capability surfaced for Linnworks in this pass. Linnworks'
own marketing surface (search results, positioning pages) is entirely about *order/inventory/warehouse*
operations — nothing found regarding Amazon PPC, Google Ads, Meta Ads, SEO, listing optimization, email/
SMS/WhatsApp campaigns, or attribution.

**Classification: `NOT FOUND`** for every growth/marketing capability in the mandate's checklist, for
Linnworks specifically. This is consistent with Linnworks' positioning as an OMS/WMS, not a marketing
platform — advertising/growth is simply outside its product scope, not a capability gap it's trying to
fill and failing at. No contribution-margin loop (ad spend → orders → margin → fees → logistics →
returns → contribution) was found or expected here; that closed-loop pattern, if it exists anywhere in
this research universe, is more likely to surface at a platform with an explicit marketplace-operations
or retail-media angle (Rithum is the more plausible candidate per the combined audit's landscape
discovery — not yet verified).

## 6. After buying Linnworks, what does the merchant still need a human to do? (Mandate Section 9)

Based on confirmed gaps and constraints above, a merchant running Linnworks still needs a human (or a
separate tool) for:

- **Every customer-conversation channel** — email, live chat, WhatsApp, social — since Linnworks itself
  has no native conversational support; a human (or a bolted-on Replyco/Gorgias operator) still handles
  every customer message.
- **Bundle/kit warehouse-transfer exceptions** — Linnworks' composite parent SKU cannot itself be
  warehouse-transferred; a human must manually move/reconcile child SKUs when a bundle needs to relocate.
- **Split-order and merge-order edge cases outside the documented eligibility rules** — e.g. an order
  that fails Linnworks' narrow merge-eligibility list (different currency, on hold, label already
  printed) still needs a human to resolve it manually.
- **RBAC/permission administration beyond the base tier** — granular role/permission setup is gated
  behind an "Advanced or higher" paid plan; below that, a human is doing informal access control by
  convention, not by system enforcement.
- **Reconciliation against external financial truth** — no confirmed settlement-reconciliation or
  fees/charges-reconciliation depth was found for Linnworks in this pass (`UNKNOWN`); if that gap is
  real rather than just unresearched, a human is still manually reconciling payouts against orders.
- **Any advertising/growth operation whatsoever** — entirely outside Linnworks' scope (Section 5); a
  human or a separate tool runs every ad platform.
- **Acting on Spotlight AI's own recommendations** — Spotlight AI *surfaces* repeated-decision patterns;
  a human still has to review and decide whether to actually turn each recommendation into a standing
  rule (this is explicitly the correct pattern per the mandate's automation hierarchy, not a criticism of
  Linnworks — but it means "buying Spotlight AI" does not remove the human from the loop, it changes what
  the human is doing).
- **Everything the combined audit already found missing entirely** at Linnworks or `UNKNOWN` this pass:
  cancellations, exception management, human-approval gating specifics, payment lifecycle, COD, supplier
  acknowledgement, inbound goods receipt — each of these, if genuinely absent rather than merely
  unresearched, is a human doing that work manually today.

**Strategic reading (per mandate Section 9):** the realistic Sanocea opportunity against Linnworks
specifically is not "replace Linnworks' warehouse/listing depth" — that would take years and Linnworks
has a real head start there. It is "operate Linnworks (or a comparable OMS) *plus* the customer-
conversation layer *plus* the finance-reconciliation layer *plus* procurement as one canonically
connected system" — i.e. Linnworks itself, and the third-party tools (Replyco/Gorgias, a reconciliation
spreadsheet, an ads tool) a Linnworks merchant currently stitches together by hand, become the surface
Sanocea unifies. This reinforces, rather than replaces, the combined audit's own final-answer framing
(Section 12 of `sanocea-competitive-capability-audit.md`).

## 7. Automation hierarchy — does Linnworks change the differentiation? (Mandate Section 10)

Re-testing Sanocea's deterministic → AI → human hierarchy specifically against Linnworks:

- **Deterministic-first** is not unique — Linnworks' Rules Engine is the same pattern under a different
  name (Section 2.8). Sanocea's edge here is explicit naming/measurement (`ai_dependency_rate`), not the
  underlying idea.
- **AI only for ambiguity** is currently *weaker* for Sanocea than for Linnworks specifically — Spotlight
  AI is real, shipped, and named; Sanocea's `AIProvider` is a non-inferencing stub. This should not be
  claimed as a current Sanocea advantage until a real provider exists (Section 2.9).
- **Human only for genuine uncertainty/risk** — Linnworks provides no equivalent blocking-approval
  mechanism in the evidence gathered this pass (unlike Cin7's confirmed credit-hold gate in the combined
  audit); Sanocea's `Approval`/`ExceptionRecord` model, once support-conversation-triggered refunds are
  counted (Phase 4.6, proven), is a real point of difference specifically against Linnworks.
- **Net assessment:** against Linnworks specifically, Sanocea's genuine edge is not the automation
  hierarchy in the abstract (Linnworks has its own version), but the **scope** the hierarchy is applied
  across — orders + finance + procurement + support as one canonical system, versus Linnworks' orders/
  warehouse/listing scope with support and financial reconciliation pushed outside the core product
  entirely (Sections 4-6 above). This matches, and is now reinforced by, the combined audit's own
  differentiator D/I finding.

## 8. Capabilities Sanocea should absorb

Absorb the underlying pattern; do not copy Linnworks' implementation, API shape, or documentation text.

| # | Merchant problem | Competitor evidence | Why useful | Sanocea current state | Generic design principle | Canonical-model impact | Implementation location | Human workload eliminated | India relevance | Global relevance | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | One SKU's true stock split correctly across &gt;1 real location | Linnworks MLI API (first-class) | Prevents oversell/undership the moment a merchant has &gt;1 location | `ARCHITECTURAL ONLY` | A location is a first-class stock-holder; every stock mutation is location-scoped, never global | Behavioral extension of existing `Inventory.location_ref`, not a new field | Canonical domain + connector location mapping | Manual "which warehouse ships this" decision | High — 3PL+own-warehouse setups common as merchants scale | High — universal OMS need | **P0** |
| 2 | Automatic location/carrier selection per order | Linnworks Rules Engine | Removes manual per-order routing triage | `ARCHITECTURAL ONLY` | Routing is a deterministic-policy decision over explicit, merchant-configurable criteria, never hardcoded to one carrier/location | Fits existing policy-engine pattern directly | Deterministic engine / policy | Manual per-order "who ships this" triage | High — most Indian merchants use multiple couriers | High | **P0/P1** |
| 3 | Prevent overselling non-sellable stock (quarantine, in-transit, returns-pending) | Linnworks bin-type ATS exclusion rules | Directly reduces oversell-driven refunds/marketplace penalties | `PARTIAL` (flat count only) | Inventory carries an explicit sellability *state*, not just a quantity; ATS math is state-aware by construction | Extend `Inventory` with a state dimension | Canonical domain + deterministic engine | Manual "is this actually available" judgment | Moderate-high — high COD-return volume in India | High | **P1** |
| 4 | Sell a bundle/kit while tracking real component stock | Linnworks Composite Items (with the documented parent-cannot-transfer constraint) | Near-universal merchandising need; Linnworks' constraint is a real cautionary precedent for the failure-mode design | `MISSING` | A composite is a parent SKU with explicit child-SKU quantities; the failure mode for "components span locations" is an explicit, deliberate rule — not silent degradation | Genuine canonical-model addition (parent/child SKU relationship) | Canonical domain + deterministic engine | Manual spreadsheet-based bundle stock tracking | High — combo/gift-set offers are common | High | **P2** |
| 5 | Split partially-available orders / merge duplicate orders | Linnworks split (per-box labels, grouped tracking) and merge (narrow eligibility list) | Confirms real, non-trivial mechanics — a design cue, not a shortcut | `MISSING` | Split/merge produce an explicit order-lineage relationship back to the originals; eligibility rules are merchant-configurable, not hardcoded to one payment/shipping model | Canonical domain (order-lineage concept) + deterministic engine (eligibility rules) | Canonical domain + deterministic engine | Manual order-desk triage for partial stock/duplicate orders | High — common around flash sales/festival spikes | High | **P2/P3** |
| 6 | Seasonally-aware reorder signal, not just a lookback average | Linnworks Stock Forecasting & Demand Planning | Reduces stockouts ahead of demand spikes | `PARTIAL` (lookback only) | Extend the existing replenishment formula with a seasonality factor sourced from canonical order history | Incremental extension, no new subsystem | Deterministic engine | Manual "when do I reorder" judgment ahead of spikes | High — festival/sale-season spikes are a known India pain point | High | **P2** |
| 7 | Surface repeated manual decisions as candidate automation rules | Linnworks Spotlight AI (recommend, human reviews) | Gives Sanocea's own "AI-observes → promotes to rule" roadmap intention a concrete, scoped first use case | `ARCHITECTURAL ONLY` (no real AI provider exists) | AI recommends a rule for explicit human approval; never silently rewrites policy — preserves the mandate's automation hierarchy | Reads existing operational-event log; no schema change | AI interpretation layer, output reviewed via existing `Approval` model | The pattern-noticing work a human currently has to do themselves | Moderate-high as ops teams scale | High | **P1** |
| 8 | Native order-status self-service + proactive shipment notification | Linnworks "Track My Order" widget + automated notification emails | Confirms this specific slice (status/tracking, one-way) is table-stakes even for a platform with no full conversational-support capability | `IMPLEMENTED+PROVEN` (Sanocea's Chatwoot-based support integration already exceeds this — two-way, canonically connected) | No absorption needed — Sanocea's existing capability is already ahead of Linnworks here; noted for completeness, not as a gap | N/A | N/A | N/A | N/A | N/A | **Not a gap — confirmed existing strength** |

## 9. Summary verdict

Nothing in this Linnworks-specific pass changes the combined audit's overall conclusions (its Sections
1-12 remain the authoritative cross-competitor synthesis); it sharpens two things specifically:

1. **Multi-location allocation remains the correct P0**, now reconfirmed with full A-J reasoning rather
   than a matrix cell.
2. **Linnworks' own product boundary — no native customer-conversation support, no advertising/growth
   scope — is a genuine, evidenced opening for Sanocea's canonical, cross-domain model**, not previously
   stated this explicitly. This is the sharpest new finding this pass adds: Linnworks merchants are
   already stitching together Linnworks + a helpdesk tool + (implicitly) a reconciliation process by
   hand — exactly the fragmentation Sanocea's "provably the same fact across systems" positioning
   (Section 12 of the combined audit) is built to remove.

**Per the mandate: this audit is now complete. Do not automatically begin Brightpearl, Pipe17, or any
other competitor — the next target should be named explicitly after this file is reviewed.**
