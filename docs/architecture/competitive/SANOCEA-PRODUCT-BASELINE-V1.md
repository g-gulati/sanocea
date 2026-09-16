# Sanocea Product Baseline V1

**Analysis only.** No production code, connector, test, or script was touched to produce this document.
No recommendation in this file is implemented. No new competitor research was performed — this is a
consolidation of [`linnworks-vs-sanocea.md`](./linnworks-vs-sanocea.md),
[`unicommerce-vs-sanocea.md`](./unicommerce-vs-sanocea.md), [`easyecom-vs-sanocea.md`](./easyecom-vs-sanocea.md),
[`pipe17-vs-sanocea.md`](./pipe17-vs-sanocea.md), and (for background context only)
`docs/architecture/sanocea-competitive-capability-audit.md`.

**Why this document exists:** four deep competitor audits have accumulated enough evidence that
continuing to collect features without consolidating them risks producing a wishlist rather than a
product doctrine. This document answers **what should Sanocea actually be** — separating architectural
necessities from India-first commercial necessities, universal capabilities from later-stage ones,
deliberate non-goals from genuine differentiators, and ideas that no longer hold up as differentiators
from ones that still do. It supersedes no prior audit's findings; it organizes them into decisions.

This document is itself subject to revision as research continues — it is "V1," not the final word. It
is the authoritative roadmap-priority reference *until later research changes it* (Section 13).

**Amended after Competitor #5 — Gorgias AI Agent — 2026-09-11.** [`gorgias-ai-vs-sanocea.md`](./gorgias-ai-vs-sanocea.md)
was accepted as evidence and its Section 19 proposed changes were reviewed and selectively applied to
Section 5 (differentiators E and F), Section 6 (the human-labour thesis), and Section 8 (AI Roadmap
Stage 7), with the changes below applied at reduced confidence where the underlying evidence itself was
secondary-sourced rather than independently verified via Gorgias's own primary documentation.

**Amended after Competitor #6 — Rithum — 2026-09-11.** [`rithum-vs-sanocea.md`](./rithum-vs-sanocea.md)
was accepted as evidence and its Section 19 proposed changes were reviewed and selectively applied to
Section 5 (differentiator F, and a new future-differentiator item in Section 5.B), Section 10 (the
do-not-build list, for advertising and dropship-network design guidance), Section 13 (a new P2 priority
item), and Section 14 (Open Research Question #2, now closed for the current research program). Rithum
was the strongest test yet of differentiator F — the broadest individual-capability surface of any
competitor researched — and it survived, sharpening rather than weakening the claim. This document
remains **V1** — these are amendments, not a version bump; a deliberate V2 review would be its own
separate decision.

---

## 1. Correcting the Pipe17 destruction-test language

The Pipe17 audit's own Section 13 table is preserved exactly as historical evidence — do not edit that
file. But its own top-line framing ("nothing was fully DESTROYED... all ten differentiators came back
SURVIVES/PARTIALLY SURVIVES/UNKNOWN") undersells its own most important finding and is corrected here.

**The precise, corrected reading of differentiator G (human→AI→deterministic migration):**

> G is not merely "PARTIALLY SURVIVES." It is **PARTIALLY DESTROYED AS A NOVEL IDEA, while the
> underlying architecture survives.**

Two independent competitors now occupy the two halves of what Sanocea's roadmap describes as one idea:

- Linnworks' **Spotlight AI** occupies the *pattern-discovery* half — it observes repeated manual
  decisions and recommends turning them into a standing automation rule, shipped, named, with a
  quantified outcome (Linnworks audit, Section 2.9).
- Pipe17's **Pippen** occupies the *rule-authorship* half — it conversationally *writes* the deterministic
  rule the Automation Engine then executes without AI involvement on subsequent orders ("If code is
  needed, Pippen writes it") — a step Sanocea has never built any part of (Pipe17 audit, Section 13,
  row G).

Between the two, there is almost no unclaimed territory left in the *idea* of "AI watches humans/rules
repeat a pattern, then produces a deterministic artifact." What survives is not the idea's novelty — it
is Sanocea's specific combination of this idea with the cross-domain canonical model (differentiator F),
which nothing in the research program has challenged. **The correct sentence for any future positioning
document is: "the architecture survives; the claim to have invented or uniquely occupied it does not."**
This applies with the same force to differentiator C (AI only for ambiguity) for the identical reason —
Sanocea's `AIProvider` has never made a real inference call, while both competitors' equivalents are live
and shipped. Section 5 below (differentiator rewrite) applies this correction formally.

---

## 2. Architectural requirements — locked

Per the user's explicit instruction: where competitor convergence is strong enough, the research
*question* ("do we need this?") is closed. The *implementation* question (how, exactly) remains open in
every case below — closing the research question is not authorization to build.

| Capability | Status | Evidence |
|---|---|---|
| Canonical normalization layer (a single object model connectors map into) | **LOCKED** | Sanocea already has one, wider in cross-domain scope than any competitor's (orders+finance+procurement+support vs. Pipe17's orders+inventory+fulfilment-only "360" model). Pipe17 independently re-derived the same architectural answer to the same normalization problem — this validates the pattern as category-standard, not unique, and confirms it is necessary regardless of uniqueness (Pipe17 audit, Section 2). |
| First-class location identity | **LOCKED** | `Inventory.location_ref` already exists as a field; the question of whether locations need to be first-class is closed by four independent competitors treating them as such. |
| Location-scoped inventory | **LOCKED** | Same evidence as above — every one of the four competitors models inventory per-location, not as a flat global count. |
| Multi-location allocation | **LOCKED — the single most over-determined finding across all four audits.** | Independently validated by Linnworks (criteria-based Rules Engine + MLI), Unicommerce (network-wide "Smart Fill" fill-maximization + proximity allocation), EasyEcom (ZIP/distance + priority-rule routing), and Pipe17 (event-based real-time propagation + criteria/AI-hybrid routing) — four independently-built platforms, four different mechanisms, the same universal problem. Sanocea remains `ARCHITECTURAL ONLY` (`location="default"` always) on this after four confirmations. |
| Inventory reservations / ATS | **LOCKED (need), STRONG EVIDENCE (mechanism shape)** | Confirmed real at Linnworks (bin-type exclusion) and Unicommerce (Kafka-delta + snapshot reconciliation) — 2/3 of the traditional-OMS cluster, not independently re-verified for EasyEcom or Pipe17's inventory-state depth. The *need* is closed; the exact state-machine shape (sellable/reserved/quarantine/in-transit) is a design decision, not a further research question. |
| Deterministic policy/rule engine | **LOCKED** | Confirmed at all four competitors under different names (Rules Engine, Smart Fill/UniReco rules/Shipway rules, order-routing + Force Split rules, Automation Engine + Resolution Engine) — and already `IMPLEMENTED+PROVEN` in Sanocea. This is the least controversial locked item in the program: nobody disputes the need, Sanocea already has it, and no competitor's version is materially more advanced in kind (only in the specific rules configured). |
| Explicit mutation state machine | **LOCKED** | Sanocea's `ConnectorCommand.status` (`pending → approved → executing → succeeded/failed/uncertain/blocked`) is structurally near-identical to Pipe17's independently-confirmed connector-action lifecycle (`Submitted → Processing → Completed/Failed`) — two independently-built systems converged on the same pattern, which is strong validation that an explicit mutation state machine (vs. fire-and-forget) is a genuine architectural requirement, not a Sanocea idiosyncrasy. Already `IMPLEMENTED+PROVEN`. |
| Idempotency | **LOCKED (need), Sanocea ahead on evidenced depth** | No competitor showed platform-enforced idempotency with comparable mechanism depth to Sanocea's own `IdempotencyService.run_once` (explicit release-on-failure to permit genuine retry, confirmed by reading Sanocea's own source in the Pipe17 audit). Linnworks: `NF`. Rithum/Dsco (combined audit): caller-managed, not platform-enforced. Pipe17: a general claim exists, mechanism depth unverified. This stays **LOCKED as a requirement** and is a genuine, currently-provable Sanocea strength — the research question isn't "do we need it" (settled, Sanocea already has it) but "should we keep marketing it as differentiated" (yes, on the evidence gathered so far). |
| Retry/recovery | **LOCKED (need), STRONG EVIDENCE (pattern)** | Sanocea's recovery-runner and Pipe17's Resolution Engine (scheduled 3hr/24hr sweeps auto-resolving exceptions whose cause has cleared) independently converge on "don't rely on the first attempt succeeding, sweep periodically." Pipe17's specific scheduled-sweep mechanism is a genuine design input Sanocea doesn't yet have in this exact shape (Section 7 below). |
| Reconciliation/read-back before assuming success | **LOCKED (need — operational), STRONG EVIDENCE (financial dimension is where Sanocea is ahead)** | Every competitor's connector-mutation lifecycle assumes read-back/status-verification is necessary. Sanocea's *specific* dual-dimension (operational-truth vs. financial-truth) reconciliation model has no confirmed equivalent at any of the four competitors — Pipe17 explicitly stops at operational truth (Pipe17 audit, Section 9); Unicommerce/EasyEcom's UniReco/EasyReco are real but sit beside the OMS as separate products, not canonical fields. This is the strongest reconfirmation of a genuine Sanocea differentiator in the whole program (see Section 5, differentiator F). |
| Exception model | **LOCKED (need), STILL OPEN (remediation depth)** | The need to surface exceptions is closed and already `IMPLEMENTED+PROVEN` (`ExceptionRecord`). What remains genuinely open is *automated remediation* — `remediation_options` is suggestion-only today, and Pipe17's Automation/Resolution Engine pair is a real, concrete precedent for what auto-remediation could look like (Section 7). |
| Approval model | **LOCKED** | Sanocea's `Approval` model is already real and proven (support-conversation-triggered refunds through the same policy path an operator uses, Phase 4.6). Pipe17's universal confirm-before-execute gate on every AI-proposed mutation is independent validation that this exact pattern (never let AI act unattended on money/inventory/orders) is correct, not merely cautious (Pipe17 audit, Section 6, Section 13 row D). |
| External-ID mapping | **STILL OPEN** | Referenced as a real concern at Pipe17 (external IDs are part of its canonical model) but not independently deep-dived as a Sanocea gap or strength in any of the four audits at implementation-level detail. Genuinely under-researched, not resolved either way. |
| Connector capability declarations | **STRONG EVIDENCE (Sanocea's granularity may already exceed competitors'), STILL OPEN whether that granularity is sufficient** | Sanocea's `ConnectorCapabilities`/`Capability.status: SUPPORTED/UNSUPPORTED/ASYNC_ONLY` model is more granular than anything publicly documented for Pipe17 (which describes push/pull support at the object-type level, coarser). This is a tentative Sanocea strength — tentative because Pipe17's internal model may simply not be public, not because Sanocea's is confirmed superior in an apples-to-apples comparison. |

---

## 3. India-first product baseline

This is the launch bar, not the final global product. Being "launch required" here does not imply a
capability is unimportant globally later — it is a scoping decision for what a *credible first India
merchant* needs, distinct from what a mature, fully-built Sanocea eventually has.

| Capability | Classification | Why |
|---|---|---|
| Shopify/WooCommerce | **LAUNCH REQUIRED** | Already `IMPLEMENTED+PROVEN` — real, certified connectors exist today. Not a gap; stated for completeness of the baseline. |
| Amazon India | **EARLY POST-LAUNCH** | Zero connector exists (`PARTIAL` per the Unicommerce audit, Section 2.1) but this is the single most universal Indian-merchant marketplace need found across the program — should be the first India-marketplace connector built, but does not need to exist on day one if Shopify/WooCommerce alone can carry an initial cohort. |
| Flipkart | **EARLY POST-LAUNCH** | Same reasoning as Amazon India — named explicitly across both Unicommerce and EasyEcom's marketplace-exception research as a top-tier priority. |
| Myntra | **LATER** | Real and named, but a narrower (fashion-vertical) marketplace than Amazon India/Flipkart — sequence behind the two broader marketplaces. |
| Meesho | **LATER** | Same reasoning — real, India-specific, high-COD-volume relevance, but not the first marketplace connector to build; Meesho's specific return-code/exception vocabulary (flagged `UNKNOWN` in the Unicommerce audit, Section 2.1) is itself a research gap before it's a build item. |
| Quick-commerce relevance (Blinkit/Zepto) | **LATER** | Confirmed real integration depth at both Unicommerce and EasyEcom (Section 9 of the EasyEcom audit: `2/3 VALIDATED, INDIA-SPECIFIC`), but dark-store/rapid-delivery order dynamics likely carry their own exception shapes not yet researched — a genuinely later-stage capability, not a launch blocker. |
| COD | **LAUNCH REQUIRED** | Already `IMPLEMENTED+PROVEN` for WooCommerce COD order-creation specifically (combined audit) — COD is a defining feature of Indian ecommerce; a launch without it is not a credible India-first launch. |
| COD-remittance reconciliation | **EARLY POST-LAUNCH** | The order-creation side is launch-ready; the remittance-matching side (`MISSING`, per the Unicommerce audit Section 2.2) is high-value but not required for the first transacting merchant — it becomes urgent within the first few months of real COD volume, not on day one. |
| NDR/RTO | **EARLY POST-LAUNCH** | `MISSING` entirely (Linnworks: `UNK`; Unicommerce: named, dedicated workflow via Shipway; confirmed as the single clearest India-specific gap Linnworks' research never exposed). High-cost failure mode, but a merchant's first orders can ship before this exists — it becomes load-bearing the moment real courier-failure volume starts accumulating, which is fast in India but not instant. |
| Courier selection | **LATER** | `MISSING`/`ARCHITECTURAL ONLY` (`Shipment.carrier: str` is free-text). Real and India-relevant (fragmented courier landscape, pincode-level serviceability variance), but sequenced behind NDR/RTO and marketplace connectors since it compounds on top of having real shipment data flowing at all (Unicommerce audit, Section 2.4). |
| Marketplace settlement reconciliation | **LATER** | Depends on having a real marketplace connector first (Section 2.9/2.1 of the Unicommerce audit) — cannot be launch-required because there is nothing to reconcile against until a marketplace connector exists. |
| Marketplace fee reconciliation | **LATER** | Same dependency as above. |
| Returns/refunds/exchanges | **LAUNCH REQUIRED** | Already `IMPLEMENTED+PROVEN` (logistics-pushed, policy-gated, 3 real platforms per the combined audit) — a launch without this is not credible for any market, India or otherwise. |
| WhatsApp | **EARLY POST-LAUNCH** | `MISSING` as a connector; the single sharpest India-specific gap the Unicommerce audit surfaced that neither Linnworks' nor EasyEcom's research validated with a working competitor equivalent as strong (only Unicommerce's Convertway has real depth here; EasyEcom, also India-first, showed nothing — Section 9 of the EasyEcom audit tags this `1/3 ONLY, INDIA-SPECIFIC`). WhatsApp's dominance in Indian ecommerce communication is a market fact independent of competitor validation (EasyEcom-audit Section 10) — real, but not required for the very first transacting merchant, who can be served through existing channels initially. |
| Customer support | **LAUNCH REQUIRED** | Already `IMPLEMENTED+PROVEN` (Chatwoot-integrated, real webhooks, proven to trigger a real refund through the same policy/approval path an operator uses, Phase 4.6) — this is a genuine existing strength, not a gap, and should ship day one as a differentiator, not be treated as optional. |
| Bundles/kits | **LATER** | `MISSING`, confirmed as a near-universal merchant need (3/3-adjacent convergence per the EasyEcom audit Section 9) but genuinely requires a canonical-model addition (Section 2 of this document — not yet a "locked, ready to build" item; the *need* is locked, the *design* is still being sharpened by each successive audit). Not launch-required because a merchant can sell single SKUs first and add bundles once the model is designed properly, rather than rushed. |
| Basic procurement | **LAUNCH REQUIRED** | Already `IMPLEMENTED+PROVEN` — a genuine existing strength (confirmed across all three traditional-OMS audits as a shape Sanocea's existing PO lifecycle already matches, Unicommerce audit Section 2.8, EasyEcom audit Section 2.5). Not a gap. |
| Basic replenishment | **LAUNCH REQUIRED** | `PARTIAL` (velocity-lookback exists) — sufficient for launch; seasonal-trend enhancement (Linnworks' specific contribution) is a later refinement, not a launch blocker. |
| Multi-location | **NOT REQUIRED FOR INITIAL SEGMENT (but architecturally must be fixed before scaling past it)** | This is the one entry in this table that inverts the pattern: the *research question* is LOCKED (Section 2 — everyone needs this eventually), but the *initial India segment* Sanocea is targeting (a ₹599/month, ≤50-SKU merchant) plausibly starts single-location. The danger is treating "not required for the very first merchant" as "not urgent" — it is P0 precisely because the canonical model has never been pressure-tested with a real second location, and every week that goes by without testing it is a week of false confidence accumulating (combined audit, Section 8). Do not delay fixing the architecture; do delay requiring multi-location *support* from the very first merchant. |
| RBAC | **EARLY POST-LAUNCH** | `PARTIAL` (2 coarse roles) — becomes load-bearing the moment more than one human at a merchant touches the system, which is common quickly past the very first weeks (Linnworks/Unicommerce both confirmed to gate this behind pricing tiers — a real positioning opportunity for Sanocea once built, Section 5 below). |
| Exception handling | **LAUNCH REQUIRED** | Already `IMPLEMENTED+PROVEN` for surfacing; not required to have full auto-remediation (Section 7) at launch. |
| Reporting | **LATER** | `PARTIAL` (attention-dashboard only) — real gap relative to every competitor's dashboards/reports, but not a launch blocker; a merchant can operate manually via the attention query initially. |

---

## 4. Universal vs. India-specific

Explicit separation to prevent India-specific semantics leaking into the canonical model (Mandate
Section 2). The pattern in every row below: **the underlying primitive is universal; its specific
vocabulary/configuration is India-specific and belongs at the connector/policy boundary.**

### Universal commerce primitives (belong in the canonical model)

- **A location-scoped inventory model with an explicit sellability state** (sellable / reserved /
  quarantine / in-transit) — universal need (Section 2), regardless of which courier or marketplace
  triggered the state change.
- **A shipment-exception state machine** (a generic "delivery attempt failed" concept with configurable
  branches) — the *concept* of a failed-delivery-attempt exception is universal; "NDR" is the Indian name
  for it. A UK merchant has the identical underlying problem under different terminology and different
  failure-rate economics.
- **A settlement-reconciliation canonical field** (operational-truth vs. financial-truth, already
  Sanocea's dual-status pattern) — universal; UniReco/EasyReco/Sellercloud's channel-scoped report are
  all separate implementations of the identical underlying need.
- **Location/carrier allocation as a deterministic-policy decision** — universal, confirmed by four
  independently-built platforms with four different specific mechanisms (Section 2).
- **A support-conversation-to-canonical-truth intent pathway** — universal; WhatsApp is one channel into
  it, not a special case requiring its own logic.
- **Payment-truth as a canonical concept distinct from operational fulfilment truth** — universal,
  confirmed sharpest by Pipe17 explicitly *not* modeling this canonically and handing it to Xero/NetSuite
  instead (Pipe17 audit, Section 9) — this is exactly the gap Sanocea's dual-status model already closes.
- **An evidence-attachment relationship on an order/return/exception record** — universal (any
  marketplace anywhere can require dispute evidence); EasyVMS is India's specific implementation of a
  universal need (Section 9 below).

### India-first configuration/connector priorities (belong in connectors, policy, jurisdiction modules)

- **COD prevalence** — a payment-method configuration and volume assumption, not a canonical-model
  concept; COD is "a payment method with a remittance-reconciliation step," which the canonical model
  already supports in shape.
- **Delhivery/Bluedart/Xpressbees NDR event-code mapping** — courier-specific event vocabulary resolved
  to the generic shipment-exception state at the connector boundary (Unicommerce audit, Section 2.3's own
  explicit warning against designing this around one courier's event shape).
- **Flipkart/Amazon India/Myntra/Meesho fee vocabulary** (Commission Fee, Commission Override Fee, Fixed
  Fee, Payment Gateway Collection Fee, Pick and Pack Fee, Refund Commission Fee, Shipping Fee) —
  marketplace-specific naming resolved to the generic reconciliation canonical field (Unicommerce audit,
  Section 2.9).
- **Meesho/marketplace-specific return codes** — connector-level translation into the generic
  return/exception model.
- **GST** — a jurisdiction/tax-policy module, not a canonical order concept.
- **WhatsApp priority** — a channel-selection/configuration priority (which channel a merchant's
  customers actually use), not a change to the support-conversation model itself, which is already
  channel-agnostic by design.
- **Quick-commerce (Blinkit/Zepto) dark-store dynamics** — a connector/fulfilment-node configuration
  concern once researched, not a new canonical concept (pending Section 3's "LATER" classification).

---

## 5. Sanocea differentiators — rewritten

The old differentiator list has now been pressure-tested against six competitors, three of which (Pipe17,
Gorgias AI Agent, Rithum) were specifically chosen because they might occupy Sanocea's architectural
thesis directly — Pipe17 on the canonical-model/deterministic/AI-hierarchy side, Gorgias on the
support-conversation/mutation side, Rithum on the commerce-operations + supplier-network + marketplace-
economics + advertising breadth side. Per the user's instruction: be strict. Good architecture does not
automatically survive as a *unique* claim.

### A. Genuine current differentiators (must exist and be evidenced today)

1. **Finance + operations + procurement + support against one cross-domain canonical operating truth
   (old differentiator F).** The single most robustly reconfirmed finding across all six audits, and
   Sanocea's **primary anchor differentiator overall** (amended after Gorgias AI Agent, 2026-09-11;
   strengthened further after Rithum, 2026-09-11). Prefer the phrase **"cross-domain canonical operating
   truth"** over the bare phrase "one canonical model" when describing this claim — per Section 5.C item
   1, having *any* canonical model at all is now confirmed category-standard, not differentiated; what is
   differentiated is specifically the *domain span* the same canonical truth reaches across, and the
   consequences that flow from it.

   Linnworks: support and finance both pushed entirely outside the core product. Unicommerce: three
   separate products (Uniware/Shipway/Convertway) under one shareholder with no confirmed shared canonical
   data model. EasyEcom: four native modules, one company, still no confirmed shared canonical model
   across them. Pipe17 — architecturally sophisticated — explicitly stops at operational fulfilment truth
   and hands finance to Xero/NetSuite/QuickBooks, has no support-conversation modeling at all, and narrow
   procurement. Gorgias — the strongest direct test of the customer-operations slice specifically —
   confirms no canonical commerce model, no financial-reconciliation truth, no procurement, and no
   settlement/marketplace-fee state. **Rithum — now the strongest test overall, and importantly a
   different kind of test than Gorgias or Pipe17: not "does a narrow specialist lack breadth" but "does the
   single broadest individual-capability surface researched in this program still lack the linkage."**
   Rithum has real, confirmed, individually deep capability in catalogue/order/inventory truth,
   fulfilment truth, dropship/supplier-network truth, and advertising-spend truth — more of differentiator
   F's individual components confirmed than any prior competitor (Rithum audit, Section 16). **And it
   still survives**, specifically because Rithum shows no common canonical linkage across those domains
   (multiple coexisting systems — ChannelAdvisor-heritage, OrderStream, Dsco, RithumIQ, plus a third-party
   partner ecosystem — connected at the integration/UI layer, not the data-model layer) and no
   customer-support truth at all (Rithum audit, Section 16, components G and E).

   **This changes what the claim precisely rests on, and the correction matters:** Sanocea's
   differentiation is **not** that competitors lack deep individual capabilities — Rithum disproves that
   reading outright, and should be cited as the reason not to make it. The differentiated hypothesis is
   specifically **the combination + the canonical linkage + the cross-domain consequence** — that the
   *same* operating truth connects consequences across commerce operations, finance/reconciliation,
   procurement, and customer operations (and potentially, later, growth economics — see the new item in
   Section 5.B below). Six competitors deep, including one built specifically to attack the
   customer-operations slice (Gorgias) and one with the broadest capability surface tested (Rithum), this
   combination-plus-linkage claim remains uncontested.

   **Currently proven Sanocea capability, distinguished from full future cross-domain ambition:**
   *Currently proven*: orders, finance (dual-status reconciliation), procurement, and support share one
   canonical object model, and a support-triggered refund is proven to flow through the same
   policy/approval path an operator-initiated refund uses and land in the same
   `Refund.financial_reconciliation_status` field (Phase 4.6). *Full future ambition, not yet exercised
   end-to-end*: every downstream consequence of a cross-domain event (a support-triggered refund's effect
   on inventory availability, a replenishment signal, settlement-level reconciliation) is architecturally
   possible on the same canonical model but has not been independently proven for every combination. This
   is real, evidenced, and today's strongest Sanocea claim — precisely because it is stated at the level
   of evidence that actually exists, not inflated to claim more than has been proven.
2. **Support-triggered operation → same canonical commerce truth → financial reconciliation →
   inventory/fulfilment consequence → procurement/replenishment consequence → continued support state
   (old differentiator E, revised after Competitor #5 — Gorgias AI Agent, 2026-09-11).** The narrower
   claim that "a support conversation causes an operational mutation" is **no longer differentiated in
   isolation** — Gorgias AI Agent is confirmed to execute real, production-scale Shopify mutations
   (cancellation, refund, address change, subscription actions) from live customer conversations, across
   many real merchants, meeting or exceeding Sanocea's own single-organization Phase-4.6 proof on
   conversation-ingestion breadth and mutation-execution volume (Gorgias audit, Sections 2-3, 14). Sanocea
   should no longer claim "support-triggered mutation" as differentiated on its own.

   What remains differentiated is item 1's *combination*: a support-triggered mutation that is also
   canonically connected to financial-truth reconciliation, inventory/fulfilment consequence,
   procurement/replenishment consequence, and continued support state — all through the same canonical
   model every other domain uses. Gorgias has zero canonical cross-domain model, zero
   financial-reconciliation dual-status equivalent, and zero procurement/finance footprint (Gorgias
   audit, Sections 5-6, 15) — the combination, not the trigger-to-mutation link alone, is what no
   competitor researched, including Gorgias, has been shown to do. **Differentiator F (item 1 above)
   is the primary anchor of this claim; this item survives only in combination with it, not
   independently.**

   **Currently proven, distinguished from architectural scope, so this is never overclaimed:** *Currently
   proven* (Phase 4.6): a support conversation can trigger a real refund through the same policy/approval
   path an operator uses, with the resulting `Refund.financial_reconciliation_status` distinct from
   `Refund.status` on the same canonical object. *Architectural scope, not separately proven*: that the
   same support-triggered event also produces a visible inventory/fulfilment consequence, a
   procurement/replenishment signal, and a continued, canonically-consistent support state — the
   canonical model is *shaped* to support all of this (same object graph, same reconciliation pattern),
   but each individual downstream consequence has not been independently exercised. Do not present the
   full chain as uniformly proven; present the refund-reconciliation link as proven and the rest as
   architectural scope the model is built for, not yet demonstrated.
3. **DB-enforced idempotency as a canonical-layer guarantee, with a specific, evidenced mechanism
   (release-on-failure to permit genuine retry).** No competitor showed comparable mechanism depth;
   Pipe17's general idempotency claim exists without confirmable mechanism detail (Pipe17 audit, Section
   3). This remains real and current, not aspirational.
4. **Real, adversarial, documented real-platform certification methodology.** No competitor's public
   material demonstrates an equivalent self-critical verification discipline (combined audit, Section 3;
   reconfirmed by nothing in any of the four newer audits challenging it).
5. **Not gating capability behind pricing tier (the commercial principle itself, once genuinely
   shipped).** This is conditional — it is a differentiator *once reconciliation, RBAC, and other
   capabilities actually ship for every merchant regardless of plan* — but it is a genuinely evidenced
   contrast today: Linnworks gates RBAC granularity behind paid tiers; Unicommerce gates payment
   reconciliation (arguably its single best capability) behind its Professional tier; Pipe17 lists
   "automation workflows" and "support tier" as separate paid axes. Three of four competitors researched
   do exactly what the mandate tells Sanocea not to do (Section 12 below).

### B. Plausible future differentiators (architecturally credible, not yet proven)

1. **AI-observes-repeated-pattern → deterministic-rule promotion, combined with the cross-domain
   canonical model.** Per Section 1's correction: the *idea* in isolation is now occupied in both its
   halves by Linnworks (Spotlight AI) and Pipe17 (Pippen). What remains a plausible, not-yet-disproven
   differentiator is the *combination* with differentiator F — no competitor does this pattern *across*
   finance/procurement/support, only within operations. Building toward this is legitimate; claiming it
   as already differentiated is not.
2. **Auto-remediation of exceptions via an explicit resolution-condition + scheduled sweep.** Pipe17's
   Automation Engine + Resolution Engine is a real, working precedent for exactly the shape Sanocea's own
   `ExceptionRecord.remediation_options` gap needs to grow into (Pipe17 audit, Section 4.2, Section 14
   item 1) — plausible and well-precedented, but Sanocea has not built it.
3. **A generic `OperationalEvidence` primitive spanning order/fulfilment/shipment/return/exception/goods-
   receipt.** No competitor has this generalized; EasyVMS solves the narrower marketplace-dispute case
   only (Section 9 below). If built generically, this would be genuinely novel — but it does not exist
   yet anywhere in Sanocea, so it is a future claim, not a current one.
4. **India-specific operational depth (COD remittance, NDR/RTO, marketplace fee reconciliation,
   WhatsApp) delivered through the same canonical model rather than as bolted-on regional products** —
   plausible precisely because every India-specific competitor (Unicommerce, EasyEcom) delivers this
   depth through separate products/subsidiaries, not one canonical system. Sanocea could plausibly do
   India-depth *and* stay canonically unified in a way no India-first competitor currently does — but this
   is unbuilt.
5. **Canonical operational truth + financial truth + advertising spend → contribution economics →
   policy-bounded decision → execution (added after Competitor #6 — Rithum, 2026-09-11).** Explicitly a
   **plausible future differentiator, not a current one** — do not promote it to Section 5.A merely
   because Rithum happens to lack it. The Rithum audit classifies this exact territory as **PARTIALLY
   OCCUPIED** (Rithum audit, Section 17), and that specific classification is what makes this a real, but
   narrow, opening rather than either a solved problem or a wide-open one. Rithum has real per-order/
   per-SKU profitability calculation with real cost inputs, and real advertising bid/budget automation
   (Amazon Ads, Walmart Connect, Target Roundel) — the deepest instance of each found in this program. A
   third-party partner (MarginDriver, not native Rithum) has a genuine rule-based margin-threshold closed
   loop at the order level. **None of these individual primitives is novel** — profitability calculation
   exists, advertising automation exists, margin-threshold rules exist, all as real, shipped capability
   somewhere in the category. **The potential differentiation lies specifically in the *connection*
   between them against one canonical economic truth** — no native or partner mechanism was found, at
   Rithum or any prior competitor, wiring contribution-margin truth (not revenue/ROAS) into an
   advertising-spend decision (Rithum audit, Sections 6-7, 17). Building toward this remains legitimate
   future-roadmap thinking, consistent with the mandate's explicit decision to keep advertising/growth
   out of Commerce OS core scope for now (Section 10) — this item does not authorize building it, and
   should not be read as changing that.

### C. Not differentiators — industry patterns or competitor-occupied ideas Sanocea should stop
presenting as unique

1. **A canonical/common data model, in the abstract.** Pipe17 independently arrived at the same
   architectural answer (Commerce 360 Data Model) to the same normalization problem. Having *any*
   canonical model is now confirmed category-standard for this class of platform, not a Sanocea
   invention. (Sanocea's *scope* of canonical modeling — Section A.1 above — remains differentiated; the
   mere existence of canonicalization does not.)
2. **Deterministic-first execution, as an idea.** Confirmed at all four competitors under different
   names (Rules Engine, Smart Fill/UniReco rules/Shipway rules, order-routing + Force Split, Automation
   Engine). Industry-standard, not Sanocea-unique — this was already the Linnworks audit's own conclusion
   and nothing since has reversed it.
3. **"AI only for ambiguity," presented as a Sanocea idea.** Both halves of this pattern are now
   independently shipped elsewhere (Section 1's correction). Sanocea's honest position: correct
   architectural intention, currently unproven — not a differentiated capability, and should not be
   marketed as one until `AIProvider` executes a real inference.
4. **Idempotency, presented as something no competitor has thought about.** Multiple competitors
   explicitly push idempotency responsibility onto the caller (a real, if weaker, design choice, not an
   absence of the concept). Sanocea's advantage is mechanism depth and platform-enforcement, not having
   invented the concept of exactly-once processing.
5. **MCP/agent access to commerce data, presented as futuristic.** Pipe17 shipped a public MCP server
   with 40+ tools in September 2025, ahead of anything Sanocea has built. This is not a future Sanocea
   differentiator to claim — it is a capability class a competitor already occupies more completely than
   Sanocea does today.
6. **Human→AI→deterministic migration, as a novel Sanocea roadmap concept.** Per Section 1: partially
   destroyed as a novel idea. State the correction plainly in any external positioning, not just
   internally.
7. **Config-only merchant onboarding with zero code changes, presented as unusual.** Real and proven for
   Sanocea (Phase 4.5), but Linnworks/Sellercloud/ChannelEngine/Pipe17's no-code rule builder all pursue
   the identical goal (config over code) — Sanocea's specific *evidentiary proof* of it (a real audit
   trail across independently-built platforms) remains a genuine strength, but the underlying idea of
   config-driven SaaS is not novel.

### D. Product-doctrine lesson from Rithum (added after Competitor #6, 2026-09-11)

**CALCULATION ≠ DECISION ≠ EXECUTION.** Rithum is the clearest evidence this program has found that a
system can possess excellent economic calculation (real per-order/per-SKU profit, real cost inputs) and
excellent execution automation (real advertising bid/budget automation) as two separately mature
capabilities, while still requiring a human — or a third-party partner product — to connect them into an
actual decision (Rithum audit, Sections 6, 17). Sophistication in one stage does not imply sophistication
in, or connection to, another.

For future Sanocea design, distinguish these stages explicitly rather than collapsing them into the
single word "automation":

```
OBSERVE → CALCULATE → DECIDE → AUTHORIZE → EXECUTE → VERIFY → RECONCILE
```

A capability claim should always specify which of these stages it actually reaches. This is a doctrine
note for how future Sanocea capability claims (and future competitor audits) should be framed — it is not
an implementation item, and it does not itself add or change any priority in Section 13.

---

## 6. The human-labour thesis

Normalizing across all four audits' "after buying this competitor, what does the merchant still pay a
human to do?" sections into recurring categories, each classified per the required scheme.

| Recurring category | Classification | Evidence across the four audits |
|---|---|---|
| Connector/channel-link setup and sync/mapping troubleshooting | **DETERMINISTICALLY AUTOMATABLE (the setup), HUMAN APPROVAL (contested mapping conflicts)** | Confirmed via real Indian job listings for Unicommerce (channel link/unlink setup, sync/mapping troubleshooting named explicitly) and inferred for EasyEcom from user-review evidence of "occasional inventory sync and integration delays." The initial setup is deterministic (map field X to field Y); ongoing conflict resolution when two systems disagree needs a human decision. |
| Exception investigation (why did this order/inventory/routing decision go wrong) | **AI-SUITABLE, with HUMAN APPROVAL before any fix executes** | Pipe17's Pippen is the concrete precedent: root-cause diagnosis is exactly the shape of ambiguous, context-heavy work AI is well-suited to, but every fix Pippen proposes is gated by human confirmation (Pipe17 audit, Section 5.2) — the labor moves from investigation to review, not to zero. |
| Inventory investigation (is this stock actually available/correct) | **DETERMINISTICALLY AUTOMATABLE (state-checking), AI-SUITABLE (root-cause of drift)** | The ATS/state-checking itself is a formula (Section 2, locked); *why* a discrepancy exists (sync lag, a miscounted return, a damaged unit) is the ambiguous residual. |
| Shipment/NDR decisions (re-attempt vs. RTO) | **HUMAN APPROVAL today, AI-SUITABLE as a future recommendation layer** | Confirmed as a real, unresolved human decision point at Unicommerce (Shipway's NDR panel presents two options, a human chooses) — no competitor in this program has automated the *decision* itself, only the *presentation* of the choice. |
| Reconciliation discrepancy review and dispute-filing decisions | **HUMAN APPROVAL (the filing decision), DETERMINISTICALLY AUTOMATABLE (the matching/flagging)** | Confirmed at both Unicommerce (`PAYMENT DISPUTED` as a queue a human acts on) and EasyEcom (EasyReco's claimed auto-filing step is unverified marketing language, treated as `PLAUSIBLE, not independently verified` — the honest baseline assumption should be that a human still decides). |
| Claims/disputes evidence review (does this footage/photo actually support our case) | **AI-SUITABLE (a judgment call over captured evidence), HUMAN APPROVAL (the final submission)** | New category surfaced only by EasyEcom's EasyVMS finding (Section 9 below) — no prior audit anticipated this specific labor category. |
| Support conversations (email/chat/WhatsApp/social) | **Amended after Competitor #5 — Gorgias AI Agent (2026-09-11): OUTSIDE SCOPE entirely at the traditional OMS/WMS platforms (Linnworks/EasyEcom/Pipe17); SUBSTANTIALLY AI-AUTOMATABLE at a dedicated conversational-AI specialist — AI-SUITABLE (the bulk of routine conversation-to-mutation work), HUMAN APPROVAL (financial-risk residual and failed-action recovery), OUTSIDE SCOPE (policy design, procurement, reconciliation, marketplace operations, physical work)** | Traditional OMS/WMS platforms leave essentially all customer-conversation labor untouched — a human or a bolted-on third-party/subsidiary tool does it (Unicommerce's Convertway is a partial, unconfirmed-canonical-connection exception among the traditional platforms). Gorgias AI Agent demonstrates that a dedicated conversational-AI specialist can remove a substantial share of that labor at real production scale — executing real Shopify mutations (cancellation, refund, address change, subscription actions) from live conversations across many merchants (Gorgias audit, Sections 2-3, 16). **The refined finding, replacing the prior framing that support conversations inherently remain human work after buying commerce software:** traditional commerce-operations platforms leave customer-conversation labor untouched, while dedicated conversational-AI platforms can automate a large portion of it — but even the most capable one researched still leaves policy design, difficult/ambiguous support cases, failed-action recovery, financial reconciliation, procurement, marketplace operations, and physical work outside its scope (Gorgias audit, Section 16). Sanocea's own capability here is differentiated specifically in combination with cross-domain canonical connection (Section 5.A's revised item 2), not in raw conversation-automation volume, where Gorgias's production-scale evidence now meets or exceeds Sanocea's own single-organization proof. |
| Reporting/Excel work | **DETERMINISTICALLY AUTOMATABLE where reporting exists (EasyEcom's margin-analytics, Linnworks' dashboards); still real at Sanocea (`PARTIAL` — attention-dashboard only)** | Confirmed real, recurring, named ("Excel skills for reporting and data handling") in Unicommerce job-listing evidence specifically — a genuine, evidenced, ongoing human-labor category even after buying a mature competitor. |
| Rule/automation configuration (initial design of routing/hold/exception rules) | **AI-SUITABLE (conversational rule-authoring, per Pippen), HUMAN APPROVAL (activating the rule)** | Pipe17 shows this can be conversational rather than manual, but a human still designs *what* the rule should do and reviews it before activation — automation reduces the labor, does not eliminate the decision. |
| Approval/risk work generally (credit holds, dispute-filing, RTO decisions, AI-mutation confirmation) | **HUMAN APPROVAL, by design, everywhere researched** | Confirmed as a deliberate, universal pattern — Cin7's credit-hold gate (combined audit), Pipe17's universal AI-mutation confirmation gate, Unicommerce/EasyEcom's dispute-filing decisions. No competitor automates this category away; the mandate's own hierarchy (Section 10) says this is correct, not a gap to close. |
| Advertising/growth operations | **OUTSIDE SANOCEA SCOPE (explicitly, per the mandate's Section 1 and Section 8)** | Confirmed entirely outside every competitor's core scope except Unicommerce's Convertway (cart-recovery/retention only, not ad-spend management) — consistent with the mandate's own decision to keep this out of Commerce OS core pricing/scope. |
| Physical warehouse work (picking/packing/QC/putaway) | **PHYSICALLY HUMAN, unconditionally** | Confirmed unanimously — no competitor automates the physical act, only the information/routing layer around it (even EasyEcom's "no proprietary hardware" framing lowers adoption cost, not the need for a human hand). |
| Cross-system integration work (bridging a group's own separate products, or third-party couriers/accounting) | **DETERMINISTICALLY AUTOMATABLE if genuinely unified; HUMAN APPROVAL for exceptions at the seam** | The single most strategically important row in this table. Confirmed as real, ongoing labor at every OMS/WMS competitor researched precisely *because* none of them share one canonical model across their own product portfolio (Unicommerce's Uniware/Shipway/Convertway; EasyEcom's native modules connecting to third-party couriers/accounting; even Pipe17's returns-intake-via-Loop/Happy-Returns-into-Xero pipeline). **This is the single strongest evidence for Sanocea's core commercial hypothesis (Mandate Section 9): the opportunity is not replacing any one competitor's operational depth, it is removing the human labor of being the integration layer between systems that were never designed to share one truth.** |

---

## 7. Exception autonomy model

Pipe17 exposed a valuable design principle (Automation Engine's time-boxed holds + Resolution Engine's
scheduled sweep). This section defines the **generic** Sanocea pattern this suggests — conceptual only,
no implementation, no schema change proposed as final.

```
EXCEPTION
  → CAUSE (what specifically triggered this — a classification, not free text)
  → RESOLUTION CONDITION (an explicit, checkable predicate: "resolved when X becomes true")
  → RECHECK POLICY (how often, and by what mechanism, the resolution condition is re-evaluated)
  → SAFE REMEDIATION (an action taken only when the resolution condition and the recheck policy both
    permit it — deterministic where possible, AI-proposed-with-confirmation where genuinely ambiguous,
    per the mandate's hierarchy)
  → ESCALATION IF UNRESOLVED (a deadline past which a human must be notified, not indefinitely deferred)
```

**How this relates to existing Sanocea concepts, conceptually:**

- **`ExceptionRecord`** is the natural home for `CAUSE` and `RESOLUTION CONDITION` — today it carries
  `remediation_options` as suggestion strings; this pattern suggests those strings should eventually
  become structured, checkable predicates instead (a design direction, not a schema proposed here).
- **`Approval`** is the natural gate for `SAFE REMEDIATION` when the remediation is not purely
  deterministic — consistent with Pipe17's confirmed universal confirm-before-execute gate (Section 5.A,
  differentiator D's continued strength).
- **`ReconciliationWorker`** and the existing recovery runner are the natural home for `RECHECK POLICY` —
  Pipe17's fixed 3hr/24hr schedule is one possible shape; Sanocea's existing worker infrastructure
  already runs on a comparable periodic-check pattern, so this is closer to an *extension* of existing
  infrastructure than a new subsystem.
- **`ConnectorCommand`** is where `ESCALATION IF UNRESOLVED` would interact with connector-level retry
  state, since an unresolved exception is often (not always) tied to a stuck or repeatedly-failing
  mutation.

**Whether schema work would eventually be needed:** almost certainly yes, but scoped narrowly —
`ExceptionRecord` likely needs a resolution-condition field richer than a string, and a recheck-schedule
concept needs to exist somewhere (either on the record itself or in the worker that processes it). This
is flagged as a real, eventual design task (Section 13, priority list), not designed in detail here, per
the user's explicit instruction not to over-design in this synthesis document.

---

## 8. AI roadmap — reset based on real competitors

Not "add AI" — a specific, staged sequence, informed by what Linnworks (Spotlight AI) and Pipe17
(Pippen + MCP) actually ship today. Each stage names its own risk, value, required guardrails,
competitor precedent, and an honest recommendation on whether Sanocea should build it. **Stage 7 is not
assumed desirable — it is included to be explicitly rejected, not endorsed.**

| Stage | Description | Risk | Value | Required guardrails | Competitor precedent | Should Sanocea build it? |
|---|---|---|---|---|---|---|
| 0 | No real model (current state) | None | None — but the interface (`AIProvider` Protocol) exists and is well-designed, per the combined audit | N/A | N/A | N/A — this is where Sanocea is today, honestly stated |
| 1 | Read-only diagnosis over canonical truth (an AI that answers "why did this happen" using existing data, mutates nothing) | Low — prompt-injection risk exists (untrusted customer/support text reaching a real provider for the first time, per the combined audit's own flagged risk) but no mutation risk | Real, immediate — removes the "hunt across multiple screens" labor Pipe17's MCP server explicitly targets | Cost/latency monitoring (unexercised at Sanocea per the combined audit); careful handling of untrusted text reaching the model | Pipe17's MCP read-only tool categories (order/fulfilment/inventory/exception/customer-service lookups) are exactly this stage, shipped | **Yes — the safest, most precedented first real step.** This should be the actual Stage 1 milestone, not an abstraction. |
| 2 | Recommendation (AI suggests an action; nothing executes without a separate, deliberate human step) | Low-moderate — the recommendation itself could be wrong or misleading, but nothing changes state | Real — matches Spotlight AI's shipped pattern exactly | The recommendation must be visibly labeled as unexecuted; no UI pattern that makes acting on it feel automatic | Linnworks' Spotlight AI (recommend a rule; human reviews) | **Yes**, as the natural extension of Stage 1 |
| 3 | Deterministic-rule proposal (AI drafts a rule in the existing policy-engine's rule language, not free-form code) | Moderate — a badly-drafted rule could be activated by a human without fully understanding it | High — this is Pippen's confirmed, shipped capability ("Routing, holds, modifications, exceptions, custom mappings... Pippen writes it") | The proposed rule must be reviewable in the same format a human-authored rule would be (no black-box logic); a dry-run/simulation step before activation is a reasonable guardrail worth designing, not assumed here | Pipe17's Pippen | **Yes, cautiously** — real precedent exists, but Sanocea should not skip the dry-run step Pipe17's own public material does not confirm it has either |
| 4 | Human-approved rule activation (the drafted rule from Stage 3 goes live only after explicit human approval) | Low, given Stage 3's guardrails | Real — this closes the loop Spotlight AI + Pippen together represent | Exactly the existing `Approval` model — no new mechanism needed, just a new *source* of proposals (AI, rather than only human-authored) | Both competitors implicitly require this step (neither claims a rule activates without some human involvement) | **Yes** — this is where Sanocea's existing `Approval` infrastructure already fits without modification |
| 5 | Mutation proposal (AI proposes a one-off action — cancel this order, issue this refund — not a standing rule) | Moderate — proposing the wrong mutation on a specific real order/customer is higher-stakes than proposing a rule | Real — this is the shape of Pipe17's MCP mutation-capable tools (cancel/split/reroute orders, modify inventory, trigger returns/refunds) | Every proposal must summarize its intended effect before any confirmation step, per Pipe17's confirmed pattern ("the system summarizes what it's about to do and confirms with the user") | Pipe17's MCP server + Pippen | **Yes, once Stage 1-4 are real and proven** — do not skip ahead to this stage before the earlier ones are actually shipped and trusted |
| 6 | Human-confirmed mutation (the Stage 5 proposal executes only after explicit per-instance confirmation) | Low, given Stage 5's guardrails | Real — this is Pipe17's confirmed universal pattern ("every action is confirmed by you, permission-checked, and audit-logged") | Reuse `ConnectorCommand`'s existing `policy_decision="REQUIRE_APPROVAL"` default rather than inventing a parallel mechanism (Pipe17 audit, Section 14 item 2) | Pipe17, universally, for every AI-proposed mutation with no exceptions found | **Yes** — and notably, Sanocea's own `Approval`/`ConnectorCommand` model already defaults toward this; the design lesson is "don't build something new when Pipe17 already validated that the existing default is the right one" |
| 7 | Policy-bounded autonomous mutation (an AI-proposed mutation executes without per-instance human confirmation, within some pre-approved policy envelope) | **High in general** — this would be unattended AI mutation execution against real money/inventory/orders; **moderate for the specific narrow shape described in the amendment below**, where the risk is bounded by a hard deterministic gate rather than AI judgment | Uncertain in general — theoretically higher throughput, but evidence across five audits establishes this is rarely needed rather than routinely useful | Would require, at minimum: a proven track record of Stage 5-6 accuracy over real volume; a hard, narrow policy envelope (e.g., "only for orders under ₹X, only for a pre-approved action type"); full rollback capability; real-time anomaly detection to halt the envelope if error rate rises — none of which exist today | **Amended after Competitor #5 — Gorgias AI Agent (2026-09-11):** one narrow, moderate-confidence, secondary-sourced precedent now exists — Gorgias's "Autonomous Refunds" toggle, gated by a hard dollar cap (<$50) **and** an independently-verified deterministic condition ("Returned to Sender" tracking status), with no confirmed human or customer confirmation step (Gorgias audit, Section 13, Section 19 proposed change 1). This is a single, narrowly-scoped data point sourced from secondary 2026-guide content, not confirmed via Gorgias's own primary documentation this pass — it is **not** general precedent for AI-judgment-authorized mutation. Pipe17 still confirms the opposite (universal confirm-before-execute, no exceptions found) for everything else researched across five competitors. | **General Stage 7 remains DO NOT BUILD.** The mandate's hierarchy (Section 10) still says human-only-for-genuine-risk, and Stage 7 in general is exactly the "AI as default execution engine" pattern the mandate warns against — this conclusion is unchanged. **However:** a narrowly deterministically-bounded exception may deserve a dedicated, separate future proposal — never a default rollout — if **all** of the following hold: (1) a hard monetary/value cap; (2) an independently-verified deterministic trigger condition, not an LLM judgment call; (3) an explicitly pre-authorized action type the merchant opts into per action, not a blanket grant; (4) the LLM performs intent/parameter extraction only and does **not** perform risk authorization; and (5) idempotency, read-back verification, audit logging, and recovery are all proven for that specific action first. |

**Critical distinction, added after Gorgias — these two architectures must never be treated as the
same, and conflating them is the single most likely way this section could be misread going forward:**

- **AI-AUTHORIZED AUTONOMY** — an LLM's own judgment (a confidence score, a semantic assessment) is what
  permits a real mutation to execute. No hard, independently-verifiable deterministic condition gates it.
  Gorgias's Cancel Order action, on the lower-confidence secondary evidence gathered (Gorgias audit,
  Section 13), appears to work this way — an LLM confidence threshold, not a human or a deterministic
  monetary/state cap, is the only gate found on a real, apparently uncapped-value cancellation-plus-refund
  mutation. **This is the pattern Sanocea's roadmap rejects, at every stage, including any future narrow
  exception to Stage 7.**
- **DETERMINISTIC POLICY-BOUNDED AUTONOMY WITH AI ONLY ASSISTING INTENT/PARAMETER EXTRACTION** — a
  merchant has pre-authorized a specific, narrow action class under specific, hard, checkable conditions
  (a dollar cap, a specific tracking-status value); the AI's only role is recognizing that an incoming
  message matches an already-authorized case and extracting the mutation's parameters (which order, which
  amount) — the AI never decides *whether* the mutation class itself is permitted. Gorgias's Autonomous
  Refunds toggle, on the evidence gathered, appears closer to this shape. **This is the only shape any
  future narrow Stage-7 exception proposal should take**, and even then only after the five conditions
  listed in the table row above are independently satisfied and proven for the specific action in
  question.

**The concrete, actionable recommendation from this section:** Sanocea's real first AI milestone should
be **Stage 1** (read-only diagnosis), not an abstract "add AI" initiative — this is the lowest-risk,
best-precedented, most immediately valuable step, and it directly closes the sharpest AI gap identified
against Linnworks and Pipe17 without touching any mutation path at all.

**Human-only-for-genuine-risk, reconfirmed with a caveat (amended after Gorgias, 2026-09-11):**
Human-only-for-genuine-risk remains Sanocea's correct design principle, and is independently reconfirmed
by Pipe17's universal confirm-before-execute gate — but it is **not universal industry practice even
among AI-forward competitors**: Gorgias's Cancel Order action (2026, moderate confidence, secondary-
sourced) appears to gate a real, apparently uncapped-value refund-triggering mutation by AI confidence
score alone, with no confirmed human or deterministic monetary safeguard (Gorgias audit, Section 13).
This should be read as a **cautionary competitor example reinforcing why Sanocea's stricter default is
the right choice**, not as evidence the stricter default is unnecessary or old-fashioned. Sanocea's
stricter design principle is unchanged by this finding.

**Customer self-confirmation — a third safety tier, added after Gorgias (conceptual note only, not a
roadmap implementation item — the `Approval` schema is not being redesigned here):** Gorgias's
mechanism for customer-requested, customer-verifiable changes (shipping-address change, item removal,
item replacement) exposed a useful middle tier this roadmap had not named: the customer confirms their
own requested parameters before execution, distinct from both "no confirmation at all" and "an operator
approves it." The resulting conceptual hierarchy, for future design discussion:

```
A. Deterministic no-confirmation action — only genuinely low-risk, explicitly pre-authorized cases
B. Customer self-confirmation — low/moderate-risk, customer-requested mutations where the customer
   can verify the exact requested change before it executes
C. Operator approval — financial, fraud, policy, or materially risky mutations
D. Human investigation — unresolved ambiguity / genuine exception
```

This is recorded as a conceptual addition to how Sanocea should eventually think about mutation-safety
tiers — it does not change any Stage 0-7 recommendation above, and no schema or implementation work is
proposed here.

---

## 9. Generic operational evidence

EasyEcom's EasyVMS (video/image capture linked to every order ID for marketplace-dispute evidence)
exposed a broader concept than "video management" specifically. This section evaluates a generic future
canonical concept — deliberately not designing the full schema, per the user's instruction.

**Concept: `OperationalEvidence`** — a generic attachment relationship, not a video-specific one.

**Candidate links** (per the user's list, evaluated rather than designed):

- `Order`, `Fulfilment`, `Shipment`, `Return`, `Refund`, `Dispute`, `Exception`, `GoodsReceipt` — every
  one of these already exists (or is a near-term candidate, per Section 3's return/refund/exception
  status) as a canonical concept or record type Sanocea has, needs, or is building toward. The evidence
  concept would attach *to* these, not replace or duplicate them.

**Candidate evidence types**: photo, video, document, carrier proof, packing proof, return-unboxing
proof, supplier document, marketplace correspondence — all structurally identical from the canonical
model's point of view (a typed reference to externally-stored content, with a timestamp and a link back
to the record it evidences). The *capture mechanism* (which camera, which warehouse workflow, which
courier's own proof-of-delivery API) is a connector/physical-integration concern in every case — the
mandate's own connector/canonical-domain split (Section 2 of the mandate) applies directly here.

**Does making evidence a generic primitive prevent future platform-specific hacks?** Yes, plausibly,
and this is the strongest argument for treating it as a named concept now rather than solving it
ad hoc later: without a generic `OperationalEvidence` concept, the natural failure mode is that "attach
proof to this dispute" gets bolted onto `ExceptionRecord` one field at a time (a `video_url` field here,
a `carrier_pod_reference` field there), each specific to the capability that happened to need it first —
exactly the kind of platform-specific special-casing the mandate warns against (Mandate Section 2,
Section 6 of this document's own differentiator analysis on avoiding merchant/platform-specific logic in
the core). A generic evidence-attachment relationship, designed once, would let EasyVMS-style
video-dispute-evidence, carrier proof-of-delivery, and supplier goods-receipt discrepancy photos all be
instances of the same underlying concept rather than three separate ad hoc fields.

**Priority and status, consistent with the EasyEcom audit's own finding (Section 8, item 2 there):**
`MISSING`, real and novel merchant need (India-relevant via marketplace seller-protection-program
requirements, but not India-*specific* — any marketplace anywhere can require dispute evidence),
dependent on a physical-capture integration Sanocea has no foundation for yet. This stays a **P2** item
in Section 13's consolidated stack, not elevated by this synthesis, but the framing as a *generic*
primitive rather than a video-specific feature is this document's own contribution — worth carrying
forward into whatever future design work actually happens.

---

## 10. Do-not-build list

Explicit, reasoned exclusions — protection against competitor-driven feature bloat. Every item below has
real competitor evidence behind it; the decision not to build is deliberate, not a gap.

| Capability | Reason for exclusion |
|---|---|
| Full WMS floor execution (wave picking, zone picking, TOTE abstractions, hands-free scanning hardware integration) | Confirmed real, deep, production-hardened at all four competitors researched (Linnworks' wave/zone/batch/TOTE, Unicommerce's pigeonhole/FIFO/FEFO, EasyEcom's lower-hardware-barrier scan-based approach, and implicitly required by Pipe17's own inventory-accuracy focus) — but explicitly relevant only to merchants running their own multi-bin warehouse floor. Sanocea's likely initial India segment (SMB/DTC, ₹599/month, ≤50 SKUs) plausibly uses a 3PL rather than running one. Building this now would be years of engineering effort aimed at a segment Sanocea's initial pricing/positioning does not target. Reconsider only once a specific real merchant with a real multi-bin warehouse is actually on the roadmap — not speculatively. |
| Manufacturing ERP (multi-tier BOM/Production-BOM/MRP, per Cin7's confirmed three-tier depth in the combined audit) | Out of scope for a Commerce Operations OS — this is a different product category (manufacturing planning) that happens to share a "bill of materials" vocabulary with the much narrower composite-SKU/bundle concept Sanocea actually needs (Section 2, Section 13). Building manufacturing-grade BOM/MRP would solve a problem Sanocea's target merchant (a DTC/SME seller, not a manufacturer) mostly does not have. |
| General ledger/accounting system | Confirmed as explicitly out of scope even for the most finance-adjacent competitors researched: Brightpearl has a native accounting ledger (a different architectural choice, per the combined audit) but Unicommerce/EasyEcom/Pipe17 all integrate to or export toward real external accounting products (Tally/SAP/QuickBooks/Xero/NetSuite) rather than building their own ledger. Sanocea's dual-status reconciliation *field* is the correct scope — a canonical fact about operational-vs-financial truth, not a competing general ledger. Building a GL would duplicate what Tally/Zoho Books/QuickBooks already do well and merchants already have. |
| Native courier network (owning courier relationships/fleet, as opposed to integrating with couriers) | Confirmed as a real, two-sided-marketplace problem (recruiting and vetting courier partners), not primarily an engineering one — the combined audit's own "dropship supplier network" feature-bloat-trap reasoning applies identically here. Unicommerce's Shipway is the one example of a competitor owning this layer via acquisition, not organic build; EasyEcom deliberately integrates with third-party aggregators instead. Sanocea should integrate with couriers/aggregators, not become one. |
| Advertising platform / ad-spend management | Explicitly out of scope per the mandate itself (Section 1, Section 8) — may become a separately priced Sanocea service later, but building it now would violate the mandate's own explicit "observe only, do not build" instruction. This remains unchanged after Rithum, the deepest advertising-automation platform researched (real bid/budget/pacing automation across Amazon Ads, Walmart Connect, Target Roundel) — its own evidence is a reason to stay out for now, not a reason to enter: Rithum's advertising and its own real profitability-calculation product were found to be unconnected (Rithum audit, Sections 6-7, 17; Section 5.B item 5 above), a specific, evidenced category-wide gap, not a solved problem to catch up to. **Design constraint for if this is ever authorized as a future service:** do not build profitability analytics and advertising automation as two parallel, disconnected products the way Rithum's own evidence suggests happened — any future advertising decision layer should be designed from inception to consume actual contribution economics where reliable data exists, per the doctrine note in Section 5.D. This is future design guidance only; it does not authorize building advertising now. |
| Complex enterprise planning (S&OP-grade demand planning, multi-echelon network optimization) | No competitor researched at Sanocea's likely target scale needs this — even Linnworks' "Stock Forecasting & Demand Planning" and Cin7's two-tier reorder system (the most sophisticated forecasting found) are SME-appropriate sales-velocity-plus-seasonality models, not enterprise S&OP. Building enterprise-grade planning would be solving a problem several tiers above Sanocea's initial target merchant. |
| Heavy BI (a full analytics/data-warehouse product, as opposed to an operational attention surface) | Confirmed real at Linnworks ("customizable dashboards") and Brightpearl ("hundreds of reports") but explicitly not something any of the four newer audits found evidence Sanocea's target merchant is under-served by a good operational attention-query + basic reporting layer for. Sanocea's `operator_summary()` — "what needs attention right now" — is the right *shape* of tool for this segment; a full BI product is a different, larger undertaking with its own vendor category (Power BI, Looker, etc.) merchants can already reach if genuinely needed. |
| A general-purpose pricing/repricing/promotions engine | ChannelEngine's confirmed repricing depth (combined audit — Price rules v2/Repricing v2 with a hard-constraint price floor) is a genuine specialty product in itself. Building a shallow version risks a permanently-half-built module rather than a real capability, and it is not on the critical path to any confirmed Sanocea differentiator. |
| A dropship supplier network / retailer-side supplier-network orchestration | Same two-sided-marketplace reasoning as the courier-network exclusion above (combined audit, Section 9) — Dsco's (Rithum-owned) confirmed core specialty requires recruiting/vetting suppliers, not primarily engineering. **Sharpened after Competitor #6 — Rithum, 2026-09-11**: Rithum's confirmed dropship/supplier-network product (compliance scorecards, automated financial chargebacks for EDI/ASN/labeling violations — Rithum audit, Section 9) exposed a real, distinct capability class this exclusion should name precisely rather than lump in with generic "procurement." **Sanocea procurement**: a merchant cooperatively buys from suppliers it selected — a trust-based, merchant-initiated relationship, already `IMPLEMENTED+PROVEN` and explicitly not the thing being excluded here. **Rithum-style network orchestration**: a retailer *governs and polices* a network of suppliers it does not fully control, including automated financial penalties for non-compliance — an adversarial-incentive, two-sided-marketplace business, not an engineering extension of procurement. These are different trust models and different businesses; do not contaminate Sanocea's generic, cooperative procurement model trying to represent the latter. |
| Autonomous AI mutation execution without per-instance human confirmation (AI Roadmap Stage 7) | Zero competitor precedent found anywhere in the program, including at Pipe17 — the most AI-forward competitor researched confirms the opposite pattern (universal confirm-before-execute). Building this would be inventing a risk profile no evidence justifies (Section 8). |

---

## 11. Product boundaries

What Sanocea Commerce OS owns canonically versus orchestrates versus connects to versus explicitly leaves
out of scope.

| Domain | Boundary | Reasoning |
|---|---|---|
| Orders | **OWN CANONICALLY** | Already the core of the canonical model; every competitor researched treats this identically. |
| Inventory | **OWN CANONICALLY** | Same reasoning; location-scoped inventory is a locked architectural requirement (Section 2). |
| Fulfilment/shipment | **OWN CANONICALLY** | Already canonical; the NDR/RTO/carrier-selection gaps (Sections 3-4) are implementation gaps within an owned domain, not a scope question. |
| Payments (truth about what was charged/refunded) | **OWN CANONICALLY** | The dual-status reconciliation model already makes payment truth a canonical field — this is a confirmed genuine differentiator (Section 5.A) and should stay owned, not delegated. |
| Settlement state (marketplace/COD/commission reconciliation) | **OWN CANONICALLY (the field), ORCHESTRATE (the feed ingestion)** | The reconciliation *fact* (matched/disputed/partial) is canonical; the raw settlement feed itself comes from a marketplace/courier/gateway and is ingested via connector, per the mandate's connector/canonical split. |
| Support conversations | **OWN CANONICALLY** | The single sharpest confirmed differentiator in the program (Section 5.A.2) — this must stay owned, not delegated to a Chatwoot-like bolt-on with no canonical connection, which is exactly the fragmentation pattern found at every competitor researched. |
| Supplier/procurement state | **OWN CANONICALLY** | Already `IMPLEMENTED+PROVEN`; confirmed as a real Sanocea strength across all three traditional-OMS audits (Section 3). |
| Accounting ledger (general ledger, GST filing, statutory books) | **CONNECT TO** | Per Section 10's do-not-build reasoning — this is Tally/Zoho Books/QuickBooks territory; Sanocea should export/integrate cleanly, not compete here. |
| Carrier physical network (owning courier relationships or fleet) | **CONNECT TO** | Per Section 10 — a two-sided-marketplace problem, not an engineering one; connect to couriers/aggregators, do not become one. |
| Warehouse robotics/physical WMS execution hardware | **OUT OF SCOPE** | Per Section 10's WMS-floor-execution exclusion — Sanocea observes and initiates fulfilment commands; it does not operate warehouse-floor physical execution. |
| Advertising media-buying | **OUT OF SCOPE (for now)** | Per the mandate's own explicit decision (Section 1, Section 8) — may become a separate paid service, deliberately not Commerce OS core. |
| Marketplace listing/catalogue hosting itself | **ORCHESTRATE** | Sanocea pushes/syncs listings to marketplaces via connector; it does not host the marketplace itself (not applicable as an "own" concept — this is inherently orchestration by nature of what a marketplace connector is). |
| Video/photo evidence capture hardware or workflow | **CONNECT TO (the capture mechanism), OWN CANONICALLY (the evidence-attachment relationship, per Section 9)** | Consistent with Section 9's reasoning — the generic evidence concept is canonical; the camera/warehouse-capture-workflow is a physical-integration/connector concern. |

---

## 12. Pricing principle recheck

**"Price determines capacity, not capability."** Rechecked against all four competitors — has research
produced any reason to abandon this principle?

**No. If anything, the evidence strengthens the case for keeping it.**

- **Linnworks** gates RBAC granularity behind an "Advanced or higher" paid plan tier (Linnworks audit,
  Section 2.10) — a real, confirmed example of exactly the capability-tiering pattern the mandate warns
  against.
- **Unicommerce** gates payment reconciliation — arguably its single most operationally valuable
  capability — behind its Professional tier, not available on Standard (Unicommerce audit, Section
  2.12). This is the sharpest, most concrete real-world example of "Starter reconciliation / Advanced
  reconciliation" tiering found anywhere in the program — precisely the pattern named as a negative
  example in the mandate itself (Mandate Section 1).
- **Pipe17** lists "automation workflows" and "support tier" as separate named cost drivers alongside
  legitimate capacity axes (order volume, connector count) — a subtler version of the same pattern
  (Pipe17 audit, Section 12): some of its pricing is genuinely capacity-based (compliant with Sanocea's
  principle), and some is capability-gated (would violate it if Sanocea did the same).
- **EasyEcom** provides no public evidence either confirming or refuting capability-gating — its
  sales-led, fully quote-based pricing model simply doesn't disclose enough to make the comparison
  either way (EasyEcom audit, Section 2.9). This is a genuine gap in the evidence, not a data point
  either for or against the principle.

**Net finding: three of four competitors researched either confirm or plausibly practice exactly the
capability-tiering pattern the mandate instructs Sanocea to avoid; none provide a reason to abandon the
principle.** If anything, this is now a stronger, more evidenced *positioning* claim than when the
mandate was first written — Sanocea can truthfully say "even [Linnworks/Unicommerce/Pipe17] gate
[RBAC/reconciliation/automation] behind a paid tier; Sanocea does not" once the relevant capabilities
actually ship for every merchant regardless of plan (this is conditional — see Section 5.A.5's own
caveat that this differentiator requires genuine shipping first, not just the stated intention).

**No change to the principle is recommended.** Exact rupee figures remain unfinalized, per the mandate's
own instruction (Mandate Section 1) — this recheck confirms the *principle*, not specific prices.

---

## 13. V1 priority stack

One consolidated stack. Every capability appears exactly once, even where multiple audits independently
confirmed it — the priority-reconciliation and convergence sections in the underlying audits (Linnworks
Section 9-ish framing, Unicommerce Section 9, EasyEcom Sections 9-10, Pipe17 Section 15) are the source
material; this is their single merge. This becomes the authoritative roadmap-priority reference until
later research changes it.

### P0 — architectural blocker

| Capability | Why | Evidence strength | Merchant segment | India relevance | Canonical impact | Current Sanocea state |
|---|---|---|---|---|---|---|
| Multi-location order allocation (real, not placeholder) | The single most over-determined finding across the entire research program — four independently-built platforms, four different mechanisms, the same universal problem (Section 2) | Very high — 4/4 confirmed | Growing SME onward | High | Behavioral fix to existing `Inventory.location_ref`/`location="default"` field — canonical domain + deterministic engine | `ARCHITECTURAL ONLY` |

### P1 — important for initial India product

| Capability | Why | Evidence strength | Merchant segment | India relevance | Canonical impact | Current Sanocea state |
|---|---|---|---|---|---|---|
| Indian-marketplace connectors (Amazon India, Flipkart first; Myntra, Meesho later) | The single most universal India-merchant need found in the program; confirmed via real job-listing evidence that this gap costs merchants ongoing labor today (Unicommerce audit, Section 6) | High — confirmed named at Unicommerce and EasyEcom | SME onward selling on >1 channel | Very high | Connector only, if disciplined (Mandate Section 2) | `PARTIAL` (3 real non-India connectors) |
| Marketplace/COD/commission reconciliation, with a design target of auto-filing disputes, not just flagging | Deepest confirmed reconciliation depth in the program (UniReco/EasyReco); EasyEcom's claimed auto-filing step sharpens the ambition | High for the need, moderate for the "auto-file" specific mechanism (EasyEcom's claim is unverified marketing language) | Any merchant on commission-charging marketplaces | Very high | Extends existing dual-status canonical field + new connector work | `IMPLEMENTED+PROVEN` in shape, `MISSING` against any real feed |
| COD remittance reconciliation specifically | A defining feature of Indian ecommerce with a well-evidenced, genuinely tolerance-aware state machine to design against (UniReco) | High | Any merchant offering COD | Very high | Same reconciliation extension as above, applied to a courier remittance feed | `MISSING` for remittance specifically |
| NDR/RTO as an explicit workflow | One of the most expensive Indian-logistics failure modes; confirmed named/dedicated only at Unicommerce (via Shipway) — EasyEcom thinner, Linnworks/Pipe17 not applicable to this market in the same way | Moderate — rests specifically on Unicommerce's finding, not a triple-confirmation; the underlying merchant problem doesn't depend on competitor documentation volume | Any merchant shipping with a COD component | Very high | New canonical exception-state concept on `Shipment` + deterministic engine + connector | `MISSING` |
| A real `AIProvider` implementation, scoped to Stage 1 (read-only diagnosis) first | Zero real AI inference exists anywhere in Sanocea; two competitors (Linnworks, Pipe17) have shipped, named, operational AI features occupying real territory | High that the gap is real; the "falling behind competitors broadly" framing should now be scoped specifically to Linnworks and Pipe17, not stated as industry-wide (only 2/4 competitors show this) | Any merchant, scales with ops-team size | Moderate | AI interpretation layer reading existing canonical model; no schema change for the read-only version (Section 8) | `ARCHITECTURAL ONLY` (non-inferencing stub) |
| RBAC granularity beyond the binary operator/service split | Becomes load-bearing the moment more than one person touches the system, which is common quickly; two of four competitors confirmed to gate this behind pricing tiers, sharpening Sanocea's positioning opportunity once built | High for the need; the "don't gate behind price" positioning claim is now supported by 2/4 confirmed instances | SME onward, once >1 human role uses the system | Moderate | Extension of existing role concept — policy/merchant configuration | `PARTIAL` (2 coarse roles) |
| WhatsApp as a support/notification channel | WhatsApp's dominance in Indian ecommerce communication is a market fact independent of how many competitors have built it; only 1/3 traditional-OMS competitors (Unicommerce) show real depth, so the "competitors validate this" framing should cite Unicommerce specifically, not be stated as broad convergence | Moderate — 1/4 confirmed with real depth, but the underlying market need is independently strong | Any merchant communicating with Indian customers | Very high | Connector only — existing support-conversation model is already channel-agnostic by design | `MISSING` as a connector |
| Exception auto-remediation via resolution-condition + scheduled recheck (Section 7) | Pipe17's Automation/Resolution Engine is a real, working precedent for exactly the shape Sanocea's own `remediation_options`-is-suggestion-only gap needs to grow into | High for the pattern's value; the specific Sanocea design is not yet worked out (Section 7 is conceptual, not a schema proposal) | Any merchant with real order/exception volume | Moderate | Extends `ExceptionRecord` + existing worker infrastructure (`ReconciliationWorker`/recovery runner) | `IMPLEMENTED+PROVEN` for surfacing, `MISSING` for auto-remediation |
| AI-mutation safety gate, designed before any AI mutation capability ships | Pipe17's universal confirm-before-execute pattern should be the default from day one of any real mutation-capable AI feature, not retrofitted later | High — this is a design-sequencing recommendation, not a new mechanism (reuses existing `Approval`/`ConnectorCommand` defaults) | Any merchant, once AI mutation capability exists | Low (universal, not India-specific) | No new mechanism — reuse `ConnectorCommand`'s existing `policy_decision="REQUIRE_APPROVAL"` default | N/A — a sequencing principle for future work, not a current gap |

### P2 — commercially important as merchants grow

| Capability | Why | Evidence strength | Merchant segment | India relevance | Canonical impact | Current Sanocea state |
|---|---|---|---|---|---|---|
| Bundles/kits/BOM, with an explicit assembly-timing attribute (dynamic-at-sale vs. static-pre-assembled vs. independently-manufactured) | Near-universal merchant need; Unicommerce's explicit three-way distinction and Linnworks' parent-cannot-transfer constraint both sharpen the design beyond a single generic "bundle" concept | High for the need (confirmed at 2-3 of 4 competitors with real mechanics); the specific design (assembly-timing attribute) is a synthesis insight, not independently reconfirmed everywhere | Nearly every merchant segment | High | Genuine canonical-model addition (parent/child SKU relationship + timing attribute) | `MISSING` |
| Courier selection (rate/serviceability/COD/SLA-based) | Fragmented Indian courier landscape with real pincode-level serviceability variance; sequenced behind NDR/RTO and marketplace connectors since it depends on real shipment data flowing first | Moderate-high | SME onward | High | Deterministic engine/policy reading connector-supplied courier data | `MISSING`/`ARCHITECTURAL ONLY` (`Shipment.carrier` is free-text) |
| Video/image evidence capture for marketplace disputes, as a generic `OperationalEvidence` primitive (Section 9) | Genuinely novel capability class this program hadn't anticipated before EasyEcom's EasyVMS finding; addresses margin protection via a different mechanism than reconciliation | High for the need's existence, but depends on a physical-capture integration Sanocea has no foundation for yet — sequenced behind items that extend existing patterns more directly | Any merchant with marketplace dispute/return-fraud exposure | High (COD/RTO-heavy exposure) but not India-exclusive | Genuine canonical addition (evidence-attachment relationship) | `MISSING` |
| Split orders (packing-station-re-evaluable, per EasyEcom's "Force Split" design cue) | Routine, high-frequency partial-availability events; EasyEcom's specific mechanic (split eligibility re-checked at multiple fulfilment-lifecycle points, not just order-creation time) sharpens the design | High for the need (confirmed at 3-4 competitors); moderate-high specifically for split, lower for merge (Section 13 note below) | Every segment | High (flash-sale/festival-spike relevance) | Canonical order-lineage relationship + deterministic engine, re-evaluable at multiple lifecycle points | `MISSING` |
| Demand forecasting with a seasonality factor | Sanocea's existing velocity-lookback logic is validated as the right shape by 3/3 traditional-OMS competitors; seasonality (Linnworks' specific contribution) is the clearest remaining enhancement | High for the shape, moderate for the seasonality-specific enhancement (only Linnworks confirmed it explicitly) | SME onward | High (festival/sale-season spike relevance) | Incremental extension of existing `ProcurementService.recommend_replenishment` — no new subsystem | `PARTIAL` (lookback only) |
| Stream-plus-periodic-reconciliation as a structural reliability principle for inventory sync | A concrete reliability pattern (never trust a real-time stream alone; always reconcile against a full snapshot periodically) directly relevant to Sanocea's existing webhook-plus-polling architecture | Moderate — one clear example (Unicommerce's Kafka-delta + snapshot pattern), a design principle more than a specific feature | Any merchant at real sync volume | High | Deterministic-engine/operational-reliability principle, not a new canonical object | `PARTIAL` |
| A conversational read-only interface over the canonical model (AI Roadmap Stage 1-2) | Genuinely new capability class for Sanocea; well-precedented by Pipe17's MCP read tools and Linnworks' Spotlight AI | High for the precedent, none of it built yet at Sanocea | Ops teams of any size once repeated multi-screen lookups become real labor | Moderate | AI interpretation layer over existing canonical model + audit ledger; no schema change for the read-only version | `MISSING` |
| Inbound-receipt variance/damage fields (explicit, not a single boolean "received" status) | Pipe17's Receipts/Arrivals/Transfers entities explicitly capture variance/damage at receipt time — a superior design insight for an already-implemented Sanocea capability | Moderate | Any merchant sourcing from suppliers | Moderate-high | Extension of existing inbound-receipt canonical concept, not a new entity | `IMPLEMENTED+PROVEN` for basic inbound, missing explicit variance/damage fields |
| Per-order/per-SKU profitability read model (added after Competitor #6 — Rithum, 2026-09-11) | Rithum's confirmed profitability-reporting product (real FBA/WFS fees, settlement-derived fees, product-level margin) demonstrates this is a real, valued merchant need — knowing true profit, not just revenue, per order/SKU (Rithum audit, Section 3, Section 18 item 1) | Moderate-high for the need; the design itself (a computed view, not a new source-of-truth entity) is a synthesis judgment, not independently reconfirmed at every competitor | Nearly every merchant segment, more valuable as SKU count and channel count grow | High once a real Indian-marketplace fee-reconciliation connector exists; moderate today | **Explicitly a computed/read-model layer over existing canonical economic facts (revenue, COGS, discount, marketplace fees, payment fees, fulfilment/shipping cost, refund/return economic consequence, advertising attribution when available) — do NOT create a new canonical source-of-truth entity for calculated profitability at this stage.** Depends on reliable marketplace-fee reconciliation and cost inputs landing first (already P1 from the Unicommerce/EasyEcom audits). | `MISSING` — no per-order/per-SKU profitability calculation exists today |

### P3 — useful later

| Capability | Why | Evidence strength | Merchant segment | India relevance | Canonical impact | Current Sanocea state |
|---|---|---|---|---|---|---|
| Merge orders (narrow, explicit eligibility-rule model, per Linnworks) | Real, confirmed mechanics, but only 1/4 competitors (Linnworks) show real merge-specific evidence — weaker convergence than split | Low-moderate (1/4) | Every segment, lower frequency than split | Moderate | Canonical order-lineage relationship + deterministic engine (shared design with split, above) | `MISSING` |
| Shipping label generation | Real at several competitors, but a smaller, more mechanical gap than carrier selection itself | Moderate | SME onward | Moderate | Connector-level, minimal canonical impact | `MISSING` |
| A real reporting/BI surface beyond the attention dashboard | Real gap relative to every competitor's dashboards, but not load-bearing for an initial launch (Section 3) | Moderate | Growing SME onward | Moderate | New reporting surface, reads existing canonical data | `PARTIAL` |
| Deeper warehouse execution (pick lists, bin locations) — minimal version only | Real, deep at all four competitors, but explicitly a feature-bloat trap for Sanocea's likely 3PL-using target segment unless a specific real merchant with a real multi-bin warehouse is on the roadmap | High for competitor maturity, low for near-term Sanocea relevance | Only merchants running their own warehouse floor | Moderate (many Indian D2C sellers use 3PL) | Large canonical addition (bins/zones/pick-waves) — deliberately deferred | `MISSING` |
| A more granular exception-remediation execution model (moving beyond Section 7's conceptual pattern into a specific executable schema) | Real direction, but Section 7 explicitly stops at the conceptual level — actual schema design is future work | Moderate (the need is P1-adjacent per Section 13's own P1 list; the *execution-model* granularity specifically is P3) | Any merchant with real exception volume | Moderate | Deep extension of `ExceptionRecord` | `ARCHITECTURAL ONLY` |

### DO NOT BUILD NOW

See Section 10 for full reasoning per item: full WMS floor execution (hands-free scanning, cycle
counting); manufacturing ERP (multi-tier BOM/MRP); general ledger/accounting system; native courier
network; advertising platform/ad-spend management; complex enterprise planning (S&OP-grade); heavy BI;
general-purpose pricing/repricing/promotions engine; a proprietary dropship supplier network; autonomous
AI mutation execution without per-instance human confirmation (AI Roadmap Stage 7).

---

## 14. Open research questions

Only questions another competitor audit could genuinely resolve — not questions already over-determined
by four audits (multi-location allocation, deterministic-first-as-industry-standard, and similar are
closed; do not re-research them).

1. **Is there a competitor with truly native finance+ops+procurement+support under one canonical model?**
   Zero of four competitors researched confirm this — the strongest reconfirmed Sanocea differentiator in
   the program (Section 5.A.1) rests on an absence, not a presence. A fifth audit that finally found one
   would be the single most consequential result possible at this point — worth actively hunting for,
   not merely tolerating as unresolved.
2. ~~Is there a mature, closed-loop contribution-margin/ad-spend attribution system?~~ **CLOSED FOR THE
   CURRENT RESEARCH PROGRAM as of Competitor #6 — Rithum, 2026-09-11.** Rithum, the most plausible
   remaining candidate per the combined audit's own landscape discovery, has been directly audited.
   **No competitor researched in this program has demonstrated a confirmed native closed loop in which
   advertising spend is automatically changed using contribution-margin economics rather than primarily
   revenue/ROAS** (Rithum audit, Sections 6-7, 17) — this is stated precisely as an absence within this
   program's research, not as a claim that no platform in the market does this; six audits cannot establish
   universal market absence. What is confirmed: Rithum has the deepest per-order/per-SKU profitability
   calculation researched (real cost inputs) and the deepest advertising bid/budget automation researched
   (Amazon Ads, Walmart Connect, Target Roundel) — two separate, genuinely mature capabilities. No
   confirmed native mechanism wires contribution-margin truth into advertising execution. A third-party
   partner, MarginDriver, provides a genuine rule-based margin-threshold mechanism (an automated
   order-level profitability judgment), but it is a partner product, not native Rithum, and it does not
   establish the full contribution-margin → advertising-decision loop. **Classification: CLOSED FOR
   CURRENT PROGRAM — REOPEN ONLY ON NEW POSITIVE EVIDENCE.** Do not select another competitor merely to
   continue searching for absence; reopen this question only if a credible product, paper, documentation
   source, merchant case study, or other evidence specifically claims margin/profit-driven automated
   advertising execution. See Section 5.B item 5 for how this informs Sanocea's own future-differentiator
   thinking (a plausible future differentiator, explicitly not a current one).
3. **Who has the best marketplace claims/dispute automation** — does any competitor's claims-management
   capability go beyond EasyVMS's video-evidence-capture and UniReco's dispute-status-flagging to a
   genuinely end-to-end automated claim lifecycle? EasyReco's "auto-files the claim" marketing language is
   unverified; a dedicated audit of a claims-specialist platform (if one exists distinct from general
   OMS/WMS) could resolve this.
4. **Does anyone permit safe autonomous AI mutations without universal human confirmation, and if so,
   under what guardrails?** Zero of four competitors researched do this (Section 8, Stage 7) — Pipe17,
   the most AI-forward competitor found, confirms the opposite. A future audit finding a genuine
   counter-example would materially change Section 8's conclusion; absent that, this question should stay
   open but not actively drive research priority (the current answer — "nobody does this, and Sanocea
   shouldn't either without real evidence" — is itself a strong, useful finding).
5. **Is support→operational-mutation (a customer conversation directly causing a policy-controlled
   mutation against commerce truth) implemented natively anywhere else?** Zero of four competitors
   confirmed — this is Sanocea's single strongest, most consistently reconfirmed differentiator (Section
   5.A.2). Worth one more genuine attempt to falsify before treating it as settled — a platform explicitly
   positioned as "conversational commerce" or "AI customer service for ecommerce" (distinct from a general
   helpdesk) would be the right kind of target to test this against.
6. **What does Vinculum, Increff, or a genuinely different-shaped India-market platform add beyond what
   Unicommerce/EasyEcom already established?** Given how much convergence the first three traditional-OMS
   audits already produced, a fifth India-specific OMS/WMS audit risks low marginal value unless it can be
   shown to target one of the open questions above specifically (e.g., does it have finance+support
   modeling Unicommerce/EasyEcom lack? Does it have a closed-loop ad-attribution system?) rather than being
   selected merely because it's next on a list.

---

## 15. Recommend competitor #5

**Do not begin researching this — naming only, per the user's explicit instruction.**

**Recommended: a platform explicitly positioned as "AI customer service for ecommerce" or "conversational
commerce," distinct from a general order-management/helpdesk tool** — for example, a dedicated AI-native
customer-support-for-ecommerce product (the specific target to be confirmed at authorization time, not
committed here).

This is chosen because it is the single sharpest way to genuinely test Open Research Question #5 —
Sanocea's currently strongest, most consistently reconfirmed differentiator (support conversation →
operational execution through the same canonical policy path) has now survived four audits *by absence of
a competitor*, not by having been tested against the single most likely category of competitor to
actually occupy it. Every audit so far tested this differentiator against OMS/WMS platforms for which
customer support was a peripheral, bolted-on concern (Replyco/Gorgias at Linnworks, Convertway at
Unicommerce, nothing at EasyEcom/Pipe17) — none of the four were built by a company whose entire product
thesis is customer-conversation automation. A platform built specifically around that thesis is the
genuinely hardest test available, and the most informative one: if Sanocea's differentiator survives
contact with a dedicated conversational-commerce specialist, it is a far stronger claim than surviving
contact with four OMS/WMS platforms for whom support was never the point.

---

## 16. Stop condition

This synthesis document is complete. Per the user's explicit instruction: no capability in Sections 8,
10, 13, or anywhere else in this document is authorized for implementation. No production code,
connector, test, or script was modified. No new competitor research was performed. Competitor #5 is named
in Section 15 but not begun.

The mandate's execution log (`README.md`, Section 11) should be updated to note this synthesis exists and
link to it, so a future session finds it before starting competitor #5.
