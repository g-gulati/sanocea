# Rithum vs. Sanocea — Competitive Capability Audit

Governed by [`../competitive/README.md`](./README.md). Competitor #6, following
[`linnworks-vs-sanocea.md`](./linnworks-vs-sanocea.md), [`unicommerce-vs-sanocea.md`](./unicommerce-vs-sanocea.md),
[`easyecom-vs-sanocea.md`](./easyecom-vs-sanocea.md), [`pipe17-vs-sanocea.md`](./pipe17-vs-sanocea.md), and
[`gorgias-ai-vs-sanocea.md`](./gorgias-ai-vs-sanocea.md). Reference:
[`SANOCEA-PRODUCT-BASELINE-V1.md`](./SANOCEA-PRODUCT-BASELINE-V1.md) (amended after Gorgias) — **not edited
by this audit**; Section 19 below proposes changes only.

**Explicit reminder, carried over from every prior audit in this program:** evidence and analysis only.
Nothing here authorizes Sanocea implementation work. No production code, connector, test, or script was
touched. This audit deliberately does not re-litigate generic OMS/WMS questions already closed by
competitors #1-#5 (multi-location allocation, basic marketplace connectivity, basic WMS) — it targets the
one open research question those five audits could not resolve: whether a mature platform already closes
the economic loop from advertising spend through to contribution margin, and whether Rithum specifically
(the combined audit's own flagged candidate, inherited from ChannelAdvisor) is that platform.

---

## 0. Scope and evidentiary basis

Roughly 20 real WebSearch queries and several direct WebFetch pulls of Rithum's own site
(`rithum.com`), press releases, and a partner page were run this pass, targeting: corporate/product
structure and heritage; retail-media/advertising mechanics; profitability/margin-reporting mechanics;
marketplace settlement reconciliation; dropship/supplier-network compliance; returns economics; canonical
architecture claims; customer support; India relevance; pricing; and job-market evidence. A fee-calculation
PDF fetch failed (returned corrupted/encoded content, not usable) — pricing evidence below relies on
secondary sources for exact figures, disclosed as such.

**Still `UNKNOWN` after this pass** (real gaps, not resolved findings): exact mechanism detail for
RithumIQ's ad-bidding algorithm (does it ever ingest margin data, or only revenue/ROAS signals — inferred
rather than directly confirmed, see Section 5-7); whether Commerce Suite/Delivery Suite actually replaced
or unified the legacy ChannelAdvisor/CommerceHub/Dsco data layers, or merely sit alongside them with a
shared UI (Rithum's own press release on this explicitly avoids architecture language — Section 10);
exact current pricing figures (the one primary-source PDF found could not be parsed; all figures below are
secondary-sourced); whether any claims/dispute-filing mechanism exists with EasyVMS/UniReco-comparable
automation depth (no evidence surfaced either way).

---

## 1. Corporate/product structure first

"Rithum" in 2026 is the product of two mergers, not one company's native build — a structurally
different, and more complex, history than any prior competitor in this program (Unicommerce's
Uniware+two-acquisitions is the closest analogue, but Rithum has more distinct heritage lines feeding into
it).

**Timeline, confirmed:** CommerceHub (founded 1997, dropship-network pioneer for retailers like Home
Depot, QVC, Nordstrom) acquired ChannelAdvisor (a marketplace-listing/advertising platform, itself with a
long independent public-company history) for $23.10/share in November 2022. The combined company rebranded
as **Rithum** in December 2023, simultaneously absorbing **Dsco** (an API-first dropship/marketplace
platform CommerceHub had separately acquired) and **Cadeera** (a multi-modal AI/computer-vision company)
([businesswire.com](https://www.businesswire.com/news/home/20231212998038/en/Leading-Global-Commerce-Companies-CommerceHub-ChannelAdvisor-and-Dsco-Become-Rithum);
[rithum.com/blog](https://www.rithum.com/blog/leading-global-commerce-companies-commercehub-channeladvisor-and-dsco-become-rithum/)).
The combined audit's own note that an earlier "Cadeera" AI-feature-name citation was fabricated/
misattributed is now resolved with real evidence: **Cadeera is real — it is the company Rithum acquired for
AI capability**, not a fabricated product name; the earlier audit's caution not to cite "Cadeera" as a
Rithum AI *feature* was correct (the feature is branded **RithumIQ**, launched September 2025, built using
Cadeera's underlying technology).

**Classification of what actually exists today, per the mandate's product-boundary discipline:**

| Product/capability | Heritage | Classification |
|---|---|---|
| Marketplace listings, catalogue syndication, order management (brand-side) | ChannelAdvisor | **CURRENT NATIVE RITHUM** — rebranded, still the core brand-facing product |
| Retail-media/advertising management (Amazon Ads, Walmart Connect, Roundel) | ChannelAdvisor | **CURRENT NATIVE RITHUM** — real, current, actively developed (Q2 2026 product update cited below) |
| "OrderStream" — enterprise dropship/retailer EDI+SFTP integration | CommerceHub (legacy) | **CURRENT SEPARATE RITHUM PRODUCT/MODULE** — explicitly named as a distinct system in current architecture descriptions, not unified into one order-management core |
| Dsco — API-first dropship/marketplace/BOPIS | Dsco (CommerceHub-acquired, pre-Rithum) | **CURRENT SEPARATE RITHUM PRODUCT/MODULE** — coexists with OrderStream, not merged into it |
| RithumIQ — AI layer (category mapping, content optimization, ad bidding/keyword automation, fulfilment insights) | Cadeera (acquired for AI capability) | **CURRENT NATIVE RITHUM** — launched Sept. 2025, positioned as a cross-product AI layer, not a separate purchasable product |
| Commerce Suite (unified dropship+marketplace connection) | New, 2026 | **CURRENT NATIVE RITHUM** — but see Section 10: no confirmed evidence this unifies the underlying *data model*, only the *connection setup* experience |
| Delivery Suite (rate shopping, label generation, tracking, predictive delivery) | New, 2026 | **CURRENT NATIVE RITHUM** |
| MarginDriver (multichannel profitability/accounting-journal automation) | Independent company | **PARTNER/THIRD-PARTY** — critical finding, detailed in Section 3 |
| Amazon Advertising, Walmart Advertising "Managed Services" | Rithum-provided, but delivered as a **human-staffed managed service**, not self-serve software | **CURRENT NATIVE RITHUM, but a services offering, not pure automation** — see Section 5 |

([cahoot.ai — What Is Rithum](https://www.cahoot.ai/what-is-rithum/);
[businesswire.com](https://www.businesswire.com/news/home/20231212998038/en/Leading-Global-Commerce-Companies-CommerceHub-ChannelAdvisor-and-Dsco-Become-Rithum);
[rithum.com — Commerce Suite/Delivery Suite press release](https://www.rithum.com/press/rithum-introduces-new-commerce-suite-and-delivery-suite-solutions-as-part-of-its-trusted-commerce-network/)).

**The single most important structural finding, echoing (and sharpening) the Unicommerce/EasyEcom pattern:**
Rithum's own architecture descriptions explicitly name **OrderStream** and **Dsco** as coexisting systems
under one umbrella ("The platform now operates three core systems under the Rithum umbrella"), not one
unified order-management engine. Scale confirmed: 40,000+ brands/retailers/suppliers, $50B+ annual GMV,
2.4B+ transactions daily, 420-600+ marketplaces/channels (figures vary slightly by source —
[cahoot.ai](https://www.cahoot.ai/what-is-rithum/);
[businesswire.com — RithumIQ launch](https://www.businesswire.com/news/home/20250908237558/en/Rithum-Introduces-RithumIQ-Defining-AIs-Impact-Across-Commerce-Complexity-Marketplace-Growth)).

## 2. Marketplace operations (proportionate treatment — not re-litigated)

Confirmed real and mature at Amazon, Walmart, eBay, Target, TikTok Shop, and Shopify, plus 420-600+
channels total. Nothing here changes any conclusion already reached against Linnworks/Unicommerce/EasyEcom
on listing/catalogue/inventory-sync mechanics — this capability class is closed research per the baseline.
The one economically-relevant new item: Rithum is "the first Roundel integration partner," bringing
**Target's** retail-media network into the platform alongside Amazon/Walmart advertising
([rithum.com — Q2 2026 product updates](https://www.rithum.com/blog/q2-2026-product-updates/)) — relevant
to Section 5, not to basic marketplace-connector questions.

**No India-specific marketplace connectors found** (Amazon India, Flipkart, Myntra, Meesho) — see Section
14.

## 3. Economic truth — highest priority

**Rithum does calculate real per-order/per-product gross profit with real cost inputs — this is
confirmed, not marketing language, and it is deeper than anything found for Linnworks, Pipe17, or
Gorgias.** Rithum's own "Commerce Insights for Brands" / profitability-reporting material states plainly:
"Rithum consolidates all cost and revenue data in one reporting solution to discover true gross profit
and margins for every order on every sales channel, with capabilities to help users identify and
eliminate unprofitable orders," and separately confirms **granular profitability data including FBA/WFS
fees, settlement reports, product-level margin reports, and other cost drivers**
([rithum.com — Commerce Insights](https://www.rithum.com/products/brands/commerce-insights-reporting/);
search-aggregated marketing copy, cross-confirmed across two independent result snippets). Cost inputs
confirmed by name: FBA/WFS fees, settlement-report-derived fees, product-level COGS (implied by "gross
profit" framing). Not independently confirmed by name in Rithum's own primary material: payment-gateway
fees, shipping cost specifically, advertising spend, or expected-return cost as line items *within the
same profitability calculation* — these may be included, but no source found spells out the full cost
stack the way UniReco's named fee-category list did for Unicommerce.

**Critical distinction found on direct primary-source fetch:** the dedicated
[Rithum Profitability Reporting](https://www.rithum.com/resources/rithum-profitability-reporting/) page
itself, fetched directly, does **not** list specific cost/fee inputs — it describes the feature only at
the level of "quick access to product, order and marketplace profitability reports... allowing you to
make better decisions for your business in less time," and explicitly frames this as **human decision
support** ("determine which of your products are profitable," "evaluate when it's the right time to
increase investment in a product") — **not** an automated decision system. **This is REPORTING/
CALCULATION, evidenced; it is not confirmed to feed any automated action on its own** (Section 6 tests
this precisely).

**SKU/order/channel profitability: CONFIRMED, calculation-level.** **Campaign profitability: PARTIALLY
CONFIRMED** — the advertising product's own language ties "spend directly to sales at the ASIN level for
profitability measurement" (Section 5), but the stated optimization *objective* is revenue/sales
performance, not an explicit contribution-margin figure (Section 7 tests this precisely — do not conflate
"profitability measurement" as a reporting output with "profitability" as the optimization *target*).

## 4. Marketplace financial reconciliation

**Weaker evidence than expected given ChannelAdvisor/CommerceHub's heritage, and weaker than UniReco
(Unicommerce) or EasyReco (EasyEcom).** No dedicated Rithum reconciliation product with a named
discrepancy-state vocabulary (comparable to UniReco's `RECONCILED`/`RECONCILED BY DELTA`/`PAYMENT DISPUTED`
states) was found anywhere in Rithum's own current material. What was found:

- **Settlement-report ingestion is real and confirmed** — it feeds the profitability-reporting product
  (Section 3) as a cost-data source.
- **A real customer case study confirms data reconciliation as a genuine capability**: "Contorion
  initiates automated data reconciliation via Rithum to ensure transaction data flows smoothly from
  marketplaces back into their ERP system" ([rithum.com case study](https://www.rithum.com/case-studies/contorion-2/),
  via search snippet) — this is real, but describes flowing marketplace transaction data *into* an
  external ERP for reconciliation there, structurally identical to Pipe17's confirmed pattern (data
  orchestration into a real accounting system, not a native discrepancy-taxonomy engine).
- **No claims/dispute/chargeback-filing product was found for marketplace-seller-side commission/fee
  disputes** (distinct from the *retailer-side* dropship chargeback-compliance system, which is real and
  separately confirmed in Section 9 — these are two different chargeback concepts and must not be
  conflated).

**Classification: REPORTING + CALCULATION, confirmed. RECONCILIATION, confirmed only in the
"flows data into an external ERP" sense (Contorion case study), not in the UniReco/EasyReco sense of a
named, tolerance-matched, dispute-tracked internal state machine. EXCEPTION DETECTION, CLAIM GENERATION,
CLAIM EXECUTION, AUTONOMOUS REMEDIATION: `NOT FOUND` for marketplace financial settlement specifically.**
This is a genuinely weaker position than Unicommerce/EasyEcom on this specific axis, despite Rithum's
advertising/economic depth being stronger elsewhere — a real, evidenced asymmetry worth stating plainly
rather than assuming a "bigger" platform is deeper everywhere.

## 5. Advertising/retail media — highest priority

**Real, current, and the deepest advertising-automation capability found in this entire research
program.** Confirmed via direct fetch of Rithum's own Retail Media Advertising product page: "Set your
goals, create campaigns, and let our automated tools handle the heavy lifting—from bidding to updates,"
with explicit "bid automation" and "budget allocation with scalable, commerce-focused automation"
([rithum.com/products/brands/retail-media-advertising](https://www.rithum.com/products/brands/retail-media-advertising/)).
Confirmed to span Amazon Ads (including Amazon DSP, "bid adjustments to performance automation"), Walmart
Connect (unified with Walmart Marketplace and Fulfillment), and — new in 2026 — Target's Roundel network
([rithum.com — Q2 2026 updates](https://www.rithum.com/blog/q2-2026-product-updates/)).

**Classification against the mandate's checklist, per action:**

| Action | Confirmed? | Evidence |
|---|---|---|
| REPORTS | Yes | "closed-loop reporting," unified performance dashboards across retailers |
| RECOMMENDS | Yes (implied, not separately isolated from automation) | RithumIQ recommends alongside automating (Section 11) |
| CREATES CAMPAIGNS | Yes | "create campaigns... let our automated tools handle the heavy lifting" |
| SETS BIDS / CHANGES BIDS | Yes | "bid automation," "real-time bid adjustments," Amazon DSP "bid adjustments to performance automation" |
| SETS BUDGETS / CHANGES BUDGETS | Yes | "budget allocation with scalable... automation," "pacing" |
| SELECTS KEYWORDS | Partially confirmed | RithumIQ described as powering "keyword strategies" (Section 11); mechanism depth not independently verified |
| SELECTS PRODUCTS | Partially confirmed | "incorporate product-level data" into automation; not confirmed as a fully autonomous product-selection mechanism |
| PAUSES ADS / REALLOCATES SPEND | **NOT independently confirmed** — the fetched product page does not explicitly state this, only bidding/pacing automation | Genuinely unconfirmed, not assumed |
| AUTOMATES EXECUTION | Yes, for bidding/pacing/budget specifically | Confirmed as above |

**This is real advertising automation, not merely an ad-platform integration** — a materially different
finding from every prior competitor in this program (none had confirmed bid/budget-automation mechanics
at this depth). **However, a real portion of the "Amazon Advertising"/"Walmart Advertising" offering is
delivered as a human-staffed "Managed Services" product** (confirmed by dedicated Rithum resource pages
titled "Rithum Managed Services for Walmart Advertising" and "...for Amazon Advertising") — meaning some
of what reads as "Rithum automates this" is, for at least part of the offering, Rithum's own staff running
campaigns as a paid service, not pure software automation. **This distinction matters directly for Section
12 (human-labour test): Rithum's own business model depends on human ad-operations labor still being
necessary/valuable for at least some merchants, which is itself evidence about the limits of the
automation.**

## 6. Closed-loop profitability test — the central destruction test

**Classification: HUMAN DECISION SUPPORT, with one real but third-party exception.**

The full loop (sell SKU → revenue → subtract COGS → subtract marketplace fees → subtract payment fees →
subtract fulfilment/shipping → account for return cost → subtract ad spend → contribution margin → change
an advertising/price/promotion/inventory decision) is **not confirmed as a native, automated Rithum
capability**. What is confirmed:

- **Native Rithum**: real per-order/per-product gross-profit reporting with real cost inputs (Section 3)
  — but explicitly framed as a human-read report ("make better decisions... in less time"), not an
  automated trigger.
- **Native Rithum advertising**: real bid/budget automation (Section 5) — but optimized against
  revenue/sales outcomes, not a confirmed contribution-margin input (Section 7).
- **Third-party partner (MarginDriver, NOT native Rithum)**: this is where a genuine rule-based closed
  loop was found — "Deficient Orders tool... helps businesses determine your optimum gross profit margin
  and eliminate orders fulfilled at a loss or below your minimally accepted gross profit margin," plus
  automated general-ledger journal-entry posting
  ([rithum.com/partners/margindriver](https://www.rithum.com/partners/margindriver/), confirmed via direct
  fetch). **This is a real RULE-BASED CLOSED LOOP** (margin threshold → automated order-level
  profitability judgment) **but it lives in a third-party partner product integrated with Rithum, not in
  Rithum itself** — the identical "don't collapse a partner ecosystem into the core platform's own
  capability" error this program has repeatedly guarded against (Shipway/Convertway at Unicommerce,
  EasyVMS's own-subdomain distinction at EasyEcom).

**No evidence found, native or partner, of the loop closing all the way through to an *advertising*
decision** (e.g., "this SKU's contribution margin dropped below X, therefore its ad budget was
automatically reduced") — the closest evidence is generic industry-level explanation of how profit-aware
bidding *could* work if margin data were passed to ad platforms (Section 7), not a confirmed Rithum-specific
mechanism doing this.

**Verdict: REPORTING ONLY + HUMAN DECISION SUPPORT is the honest classification for native Rithum. A
genuine RULE-BASED CLOSED LOOP exists, but only via a third-party partner (MarginDriver), and even that
loop stops at order-level profitability judgment — it has not been shown to extend into an advertising
decision.** This is a materially more nuanced finding than a simple "yes/no" — the loop's pieces mostly
exist, scattered across native-Rithum and partner-ecosystem boundaries, but the full chain through to an
automated growth/operational decision is not evidenced anywhere in this research.

## 7. Advertising economics vs. ROAS

**Rithum's own confirmed language optimizes advertising against sales/revenue outcomes, not contribution
margin — a real, evidenced finding, not an assumption.** The directly-fetched Retail Media Advertising
page states the system "connects spend directly to sales at the ASIN level for profitability measurement"
and describes "closed-loop reporting" tying "every ad dollar to its outcome" — but the stated
*optimization objective* is revenue/sales performance; "inventory, pricing, and margin data insights" are
named as *inputs* available for targeting decisions, not as the confirmed optimization target itself. The
separate Paid Search/Shopping Ads product page uses ROI/ROAS-flavored language ("maximize your ROI on ad
spend") rather than contribution-margin language.

Applying the worked example from the brief directly: nothing found in Rithum's own material confirms its
bidding algorithms would correctly identify a 5x-ROAS campaign as commercially poor once COGS, marketplace
fees, shipping, and expected-return cost are netted out. The industry-level material found in this search
(not Rithum-specific) confirms this is a real, recognized problem in the category — "budget shifts toward
products with stronger margin profiles... giving ad algorithms a fundamentally different instruction" is
described as something that requires a merchant to *explicitly* pass profit/margin data through as a
custom conversion-value signal, which is a real, non-trivial integration step, not a default behavior.

**Verdict: Rithum's advertising decision system, on the evidence gathered, appears to optimize primarily
against revenue/ROAS by default, with margin/profitability data available as a separate reporting layer a
human can consult — not confirmed as a unified contribution-margin optimization target.** This is the
single most economically important finding of this audit: Rithum has both halves of the ROAS-vs-
contribution-margin distinction (real ad automation, real margin data) but no confirmed evidence they are
wired together into one decision.

## 8. Returns/refunds as economic inputs

**Confirmed at the analytics/reporting level, not confirmed at the automated-attribution level.**
Rithum's "2025 Global Returns & Profit Impact Report" (a consumer-survey-based research report, not an
operational product feature) and supporting blog material confirm Rithum "analyzes key metrics such as
country, category, SKU, average order value (AOV), and reviews return reasons when available"
([rithum.com blog](https://www.rithum.com/blog/5-ways-brands-and-retailers-could-reduce-returns/);
[businesswire.com — 2025 Returns Report](https://www.businesswire.com/news/home/20250515391907/en/Rithums-2025-Global-Returns-Profit-Impact-Report-Uncovers-Consumer-Expectations-and-Strategic-Opportunities-for-Retailers-and-Brands-Struggling-with-Returns-Management)).
This confirms return data is attributed to **SKU and category** at minimum. **No evidence found** of
return-cost data feeding back into campaign-level advertising optimization, customer-cohort-level economic
attribution, or supplier-level economic consequence (e.g., "this supplier's SKUs have a higher return rate,
therefore their allocation/scorecard is adjusted") — the returns-to-supplier-performance link exists in
concept (Section 9's scorecard system tracks "fulfillment accuracy") but no source confirms returns
specifically (as opposed to shipping/ASN compliance) are a scored input.

**Classification: SKU/category-level return attribution CONFIRMED (analytics report); campaign/cohort/
supplier-level economic attribution of returns NOT FOUND.**

## 9. Supplier/dropship network

**Real, deep, and a genuinely different capability class from Sanocea's procurement model — the strongest
non-economic finding of this audit.** This is CommerceHub's original core business, and it remains real and
current under Rithum:

- **Onboarding/catalogue/inventory sync**: confirmed — "retailers can onboard suppliers, sync catalog and
  inventory data, and manage fulfillment from one central system"
  ([rithum.com/products/retailers/dropship](https://www.rithum.com/products/retailers/dropship/)).
- **Compliance and chargebacks — a genuinely distinct mechanism from ordinary procurement**: "EDI
  compliance violations (late or inaccurate ASNs, incorrect labeling, shipping errors) trigger chargebacks
  ranging from hundreds to tens of thousands of dollars per violation," with monthly scorecards tracking
  "timeliness, compliance, and fulfillment accuracy," and "$10 fees per non-compliant invoice" (secondary-
  sourced, moderate confidence, but consistent across sources). **This is retailer-enforced financial
  penalty against suppliers for compliance failures — a two-sided, adversarial-incentive mechanism with no
  equivalent anywhere in Sanocea's current supplier/PO model**, which assumes a cooperative
  merchant-initiates-PO relationship, not a retailer-polices-supplier-compliance-with-financial-penalties
  relationship.
- **Scorecards distributed to the supplier network**: "The platform automatically generates and shares
  supplier scorecards with your network to measure and improve performance to your standards"
  — a real, named, running mechanism, not just an internal report.

**This is precisely the "RETAILER-SUPPLIER/DROPSHIP-NETWORK ORCHESTRATION" capability class distinct from
traditional procurement, per the brief's own framing.** Sanocea's current Phase 4/4.1 procurement model
(a merchant buying from suppliers it selected) does not represent this at all — this is a retailer
*policing* a network of suppliers it does not fully control, with automated financial consequences for
non-compliance. **Per the baseline's own do-not-build reasoning** (Section 10 of the baseline: "a dropship
supplier network... is a two-sided marketplace problem, not primarily an engineering one; building the API
surface without the supplier network behind it produces a feature with nothing to connect to"), this
remains correctly out of scope for Sanocea to build — but it is worth naming explicitly as a real
capability class Sanocea's model doesn't represent, for completeness, not as a build recommendation
(Section 18 tags this **D**).

## 10. Canonical data/cross-domain model

**Not confirmed — and Rithum's own material actively avoids the architecture question when asked
directly.** A direct fetch of Rithum's press release introducing Commerce Suite/Delivery Suite (its own
2026 unification announcement) was checked specifically for this question and **explicitly does not
address it**: "the document contains no technical language describing whether these suites share 'one
unified data model' or remain 'separate connected systems'... focuses on business capabilities and
customer benefits rather than technical implementation details." Independently, Rithum's own architecture
description elsewhere states plainly that "the platform now operates three core systems under the Rithum
umbrella" — **OrderStream** (CommerceHub-legacy EDI/SFTP) and **Dsco** (API-first) named as coexisting, not
merged ([cahoot.ai](https://www.cahoot.ai/what-is-rithum/)).

**Per the mandate's explicit instruction not to infer canonical architecture from a unified dashboard:**
Rithum's "modular architecture, with businesses able to tap into one, two, or all four of the core
modules" and its "unified interface" language describe a **connection/UI-layer unification**, not a
confirmed shared data model. Combined with Section 4's finding (settlement data flows *into* an external
ERP rather than being reconciled within one native financial-truth object) and Section 6's finding
(profitability reporting and advertising automation are not confirmed to share a decision loop), the
weight of evidence points toward **multiple coexisting systems (ChannelAdvisor-heritage listings/
advertising, OrderStream, Dsco, RithumIQ as a cross-cutting AI layer, plus a third-party partner ecosystem
for deeper financial closure) connected at the integration/UI layer, not unified at the canonical-data
layer.**

**Verdict: NOT CONFIRMED. This is the same structural pattern found at Unicommerce (Uniware/Shipway/
Convertway) and EasyEcom (four native-but-not-confirmed-shared-model modules) — a multi-product commerce
group, not a single canonical system — now reconfirmed at the platform with the deepest economic-feature
set researched in this program.**

## 11. Automation/AI

Kept scoped to this audit's specific question (does AI close the operations→economics→decision→execution
loop), not a general Pipe17-style AI-mechanism audit. **RithumIQ**, launched September 2025, is confirmed
real and current: "recommends category mappings and content optimizations, resolves errors automatically,
and transforms catalog data when a channel changes its requirements to keep listings live," and separately
"powers... automated bidding and keyword strategies for retail media, and provid[es] insights for
optimizing fulfillment and delivery"
([businesswire.com](https://www.businesswire.com/news/home/20250908237558/en/Rithum-Introduces-RithumIQ-Defining-AIs-Impact-Across-Commerce-Complexity-Marketplace-Growth);
attempted direct fetch of this press release returned HTTP 403, so this relies on the search-snippet
aggregation, moderate confidence). A citable adoption metric exists: "three out of four Rithum clients
accept its recommendations 99% of the time" (carried forward from the combined audit's own earlier
citation, now reconfirmed by fresh search results independently).

**Does AI close the OPERATIONS → ECONOMICS → DECISION → EXECUTION loop specifically?** **No confirmed
evidence.** RithumIQ's confirmed capabilities span operations (category mapping, error resolution, catalog
transformation, fulfilment insights) and advertising execution (bidding/keyword automation) separately —
but nothing found confirms RithumIQ itself reads the profitability/margin data from Section 3 and uses it
to drive the advertising automation from Section 5. The two capability areas appear to be **parallel
applications of the same underlying AI layer**, not a single loop connecting operational data through
economics to an advertising decision. This is consistent with, and reinforces, Section 6's central finding.

## 12. Human-labour test

**"After buying Rithum, what does the merchant still pay a human to do?"**

**Job-market evidence: thin, and revealing in a specific way.** Real Rithum job postings found (via
Greenhouse) are entirely Rithum's own internal hiring — Senior Account Executive, Director of Services
Operations & Planning, Senior Strategic Program Manager, Executive Assistant — **no merchant-side job
listing requiring "Rithum" as a skill was found**, consistent with the Pipe17 audit's finding for the
same reason (Rithum, like Pipe17, is an enterprise/mid-market platform, not a mass-market tool with a
large visible "ecommerce executive" job-market footprint the way Unicommerce/EasyEcom are in India).

**More directly revealing: Rithum's own "Managed Services" offering for Amazon and Walmart advertising
(Section 5) is itself evidence of remaining human labor** — Rithum is selling human-staffed campaign
management as a paid add-on precisely because automated bidding/budget tools alone are not sufficient for
at least some merchants' advertising operations.

Classified per the mandate's scheme:

- **Deterministically automatable**: bid/budget pacing within advertising campaigns (Section 5, confirmed);
  category-mapping/content-error resolution (RithumIQ, confirmed); settlement-data-to-ERP data flow
  (Contorion case study, confirmed).
- **AI-suitable**: category-mapping/content recommendations RithumIQ already handles with human review
  (99% acceptance rate implies a human still reviews, per the mandate's own reading of this exact citation
  in the Linnworks/combined audit context).
- **Human approval / human decision-support today**: profitability-report-driven pricing/investment
  decisions (Section 3 — explicitly framed as human-read); campaign strategy and margin-threshold
  configuration for the third-party MarginDriver tool (Section 6); advertising strategy for merchants using
  the Managed Services tier (Section 5).
- **Physical**: unaddressed by Rithum (an operations/economics/advertising platform, not a WMS-execution
  system) — same universal finding as every prior competitor.
- **Outside Rithum**: native marketplace financial reconciliation with a UniReco/EasyReco-comparable
  discrepancy taxonomy (Section 4 — a human or a different tool, e.g. a dedicated reconciliation product,
  still does this); native contribution-margin-driven advertising decisions (Section 6-7 — a human, or the
  third-party MarginDriver integration, still bridges this); claims/disputes filing for marketplace
  commission/fee disputes specifically (Section 4).
- **Unknown**: exception-handling/escalation workflow depth for advertising campaigns (not researched this
  pass, out of this audit's specific scope).

**Strategic reading:** Rithum removes real, confirmed human labor from advertising bid/budget execution and
from category-mapping/content-error firefighting — genuinely more than any prior competitor in this
program on those two specific axes. But the economic decision-making labor (is this SKU/campaign/channel
actually worth investing in, once true cost is netted out) remains substantially human, or is handed to a
third-party partner (MarginDriver) rather than being native to Rithum itself.

## 13. Customer support (kept short, per instruction)

**No meaningful native customer-conversation, support-automation, or support-triggered-mutation capability
found — Rithum's own support infrastructure (Zendesk-based, per search evidence) is Rithum supporting its
own merchant customers, the identical "operate vs. provide" pattern found at every prior competitor in this
program.** No WhatsApp, live-chat, or conversational-commerce product was found anywhere in Rithum's
current material. This is consistent with Rithum's positioning as an operations/advertising/economics
platform, not a customer-service platform — Gorgias already definitively answered the conversational-
commerce question for this program (per the baseline), and nothing here changes that finding. Not
independently re-researched beyond this confirmation, per the brief's explicit instruction to keep this
section short.

## 14. India relevance

**No evidence found of India-specific capability at all** — no Amazon India, Flipkart, Myntra, or Meesho
connector; no COD/GST/Indian-courier/Indian-marketplace-settlement material found anywhere in Rithum's
current site or press material. Per the brief's explicit instruction: **this absence is not interpreted as
product inferiority** — Rithum's confirmed customer base (large US/global enterprise brands, $50B GMV
across primarily Amazon/Walmart/eBay/Target/TikTok Shop) and its GMV-percentage-plus-high-base-subscription
pricing model (Section 15) both point toward a different market segment entirely, not a gap Rithum failed
to fill.

**Classification: FUTURE GLOBAL COMPETITOR / ARCHITECTURAL REFERENCE.** Not a direct India competitor
today, and — given its pricing floor (Section 15) — unlikely to become one for Sanocea's ₹599/month
initial-SKU-capacity segment. It remains relevant as an architectural reference specifically for the
advertising-economics and dropship-network-orchestration capability classes (Sections 5, 9), which Sanocea
should study as patterns, not as evidence Rithum will ever compete directly for the same India-first
merchant.

## 15. Pricing/packaging

**Real evidence found, though the one primary-source PDF fetch failed** (returned corrupted/unparseable
content — flagged, not silently omitted). Secondary-sourced (moderate confidence, cross-confirmed across
two independent aggregator sources): **base subscription fees of $24,000-$50,000+/year plus a 1.3%-3.0%
GMV-based revenue share**, with additional per-channel integration charges and EDI transaction fees, and
"progressive tiering that resets monthly or annually"
([erpresearch.com](https://www.erpresearch.com/erp-add-ons/marketplace/rithum);
[flxpoint.com](https://flxpoint.com/blog/rithum-alternatives)). Two-year contract commitments are commonly
reported. This unambiguously positions Rithum as a **mid-market-to-enterprise** platform, consistent with
Section 14's finding.

**Module/capability gating:** genuinely `UNKNOWN` at the fine-grained level (which specific capabilities —
RithumIQ, advertising automation, Delivery Suite — are included at the base tier vs. requiring an upsell)
because the one primary pricing document found could not be parsed. What **is** confirmed: the core pricing
mechanism itself (a percentage of GMV, on top of a base subscription) is fundamentally a **capacity-based**
pricing axis (more sales volume = more revenue-share paid), which is directionally consistent with
Sanocea's "price determines capacity, not capability" principle — but the *existence* of a separate,
human-staffed "Managed Services" tier for advertising (Section 5) is itself a form of **capability-tier
gating by service level**, not pure capacity pricing: a merchant who wants Rithum's staff actively running
campaigns pays more than one using only the self-serve automation tools, which is a capability distinction,
not a capacity one. **Do not invent exact percentages for this specific gating** — the evidence confirms
the *existence* of a managed-vs-self-serve tier distinction, not its exact pricing delta.

## 16. Differentiator F destruction test

Sanocea's strongest current differentiator (finance + operations + procurement + support against one
canonical truth), reconfirmed and strengthened through five prior competitors including Gorgias, tested
against Rithum's commerce-operations + supplier/dropship + marketplace-economics + advertising breadth —
the broadest capability surface tested against this claim so far.

| Component | Verdict | Evidence |
|---|---|---|
| A. Catalogue/order/inventory truth | **RITHUM CONFIRMED** | Real, mature, confirmed across 420-600+ channels (Section 2) |
| B. Fulfilment/return truth | **RITHUM CONFIRMED** (fulfilment); **RITHUM PARTIAL** (returns — SKU/category attribution confirmed, deeper economic attribution not found, Section 8) | Sections 2, 8, 9 |
| C. Financial settlement/reconciliation truth | **RITHUM PARTIAL** | Real settlement-data ingestion and profitability calculation (Section 3); no confirmed native discrepancy-taxonomy/dispute-tracking state machine comparable to UniReco/EasyReco (Section 4) |
| D. Supplier/procurement truth | **RITHUM CONFIRMED, and a genuinely different capability class** (dropship-network orchestration with compliance/chargebacks, Section 9) — but this is a different *kind* of truth (retailer-polices-supplier) than Sanocea's differentiator F envisions (a merchant's own procurement/PO truth) | Section 9 |
| E. Customer-support truth | **NOT FOUND** | Section 13 — identical finding to every prior competitor |
| F. Advertising-spend truth | **RITHUM CONFIRMED, real and current** — the deepest advertising capability in this program | Section 5 |
| G. Common canonical linkage across A-F | **NOT FOUND** — multiple coexisting systems (ChannelAdvisor-heritage, OrderStream, Dsco, RithumIQ, third-party MarginDriver) connected at the integration/UI layer, not unified at the data-model layer | Section 10 |
| H. Actions based on that combined truth | **RITHUM PARTIAL** — real actions exist *within* individual domains (advertising bid automation, category-mapping fixes) but no confirmed action spans the combined truth (e.g., a margin-driven ad-spend change) — Section 6's central finding | Sections 6, 7, 11 |

**Overall verdict: SURVIVES.** Rithum has more individual pieces of differentiator F's component list
confirmed than any prior competitor (A, D, F fully confirmed; B, C, H partially) — this is the strongest
opponent this claim has faced. But component G (the actual canonical linkage across all of it) is **not
found**, and component E (customer-support truth) is **not found** at all, identically to every prior
competitor. Differentiator F's core claim — one canonical truth spanning all these domains, with actions
that draw on the combination — remains uncontested after six competitors, even against the single
broadest capability surface tested against it so far.

## 17. New destruction test — economic closed loop

Testing the candidate **future** Sanocea thesis (canonical operational truth + financial truth +
advertising spend → contribution economics → automated decision) — explicitly not promoted to a current
differentiator by this audit, consistent with how the baseline treats plausible-future differentiators
(Section 5.B) as a distinct category from proven current ones.

**Classification: PARTIALLY OCCUPIED.**

- The individual *pieces* of this thesis are more mature at Rithum than anywhere else researched in this
  program: real per-order profit calculation with real cost inputs (Section 3), real advertising-spend
  automation (Section 5), and a real (third-party) rule-based margin-threshold closed loop for order-level
  profitability (MarginDriver, Section 6).
- The *connection* — advertising spend responding to contribution-margin data, specifically, rather than
  revenue/ROAS — is **not confirmed** anywhere in Rithum's own native material (Section 7), and the one
  confirmed closed loop found (MarginDriver's Deficient Orders tool) stops at order-level profitability
  judgment, not an advertising decision.
- Therefore: this is not `ALREADY OCCUPIED` (the specific ad-spend-responds-to-contribution-margin loop is
  not confirmed to exist, natively or via partner), and not `NO EVIDENCE YET` (real, substantial evidence
  exists that the necessary *components* are real and maturing in this exact market segment). **`PARTIALLY
  OCCUPIED` is the honest classification**: the pieces exist and are converging at Rithum specifically, but
  the full loop through to an automated decision has not been demonstrated by any source found.

**This finding should inform, not resolve, Sanocea's future roadmap thinking on this question** — it
suggests that if Sanocea ever pursues this thesis, the individual technical pieces (cost-input aggregation,
margin calculation, ad-platform bid/budget APIs) are each independently precedented and buildable/
integrable, but the specific *wiring* connecting margin to ad decisions is not something any competitor
researched has already solved and shipped — a genuine, if narrow, opening, not yet a proven Sanocea
capability of any kind.

## 18. Capabilities Sanocea should absorb

No implementation authorized — proposals for team review only, consistent with every prior audit in this
program.

| # | Tag | Merchant problem | Rithum evidence | Sanocea state | Generic design lesson | Canonical impact | Human work eliminated | India/global relevance | Priority |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **A** | Know true per-order/per-SKU profit (not just revenue), across marketplace fees, fulfilment fees, and COGS, so unprofitable orders/SKUs can be identified | Rithum's confirmed profitability-reporting product (FBA/WFS fees, settlement-derived fees, product-level margin — Section 3) | `MISSING` — Sanocea has no per-order/per-SKU profitability calculation at all today | A profitability calculation is a read-model over existing canonical order/fee/reconciliation data — it does not require new source-of-truth fields, only a computed view combining what already exists (or will exist once marketplace fee reconciliation, per the Unicommerce/EasyEcom absorb-tables, is built) | Reporting/computed-view layer over existing canonical reconciliation fields — no new canonical entity | Removes the "is this order/SKU actually worth it" manual spreadsheet work every prior audit's human-labor section has implicitly found | Global (universal need); high India relevance once a real Indian-marketplace fee-reconciliation connector exists | **P2** — real and valuable, but depends on marketplace-fee-reconciliation connector work (already P1 from the Unicommerce/EasyEcom audits) landing first |
| 2 | **A** | Advertising bid/budget automation across marketplace ad platforms (Amazon Ads, Walmart Connect, etc.) | Rithum's confirmed real bid/budget/pacing automation (Section 5) — the deepest advertising-automation mechanism found in this program | `MISSING` entirely — explicitly out of scope per the mandate (Section 8: observe growth/marketing, do not build) | If Sanocea ever does build toward advertising (a separately-priced future service per the mandate's own commercial principle, Section 1), the design lesson worth carrying forward now is: **wire the margin-calculation layer (item 1 above) to any future ad-automation layer from day one**, rather than building them as parallel, unconnected capabilities the way Rithum's own evidence suggests happened — this is the single clearest "avoid a competitor's own gap" lesson in this audit | N/A today — explicitly a future-service question, not a Commerce OS core question, per the mandate | N/A today | N/A today | **DO NOT BUILD NOW** — consistent with the mandate's explicit "observe only" instruction for growth/advertising; recorded as a design lesson for *if and when* this ever becomes a Sanocea service, not a current build item |
| 3 | **C** | Optimize advertising against actual contribution economics, not raw revenue/ROAS | The ROAS-vs-contribution-margin gap found in Rithum's own confirmed advertising mechanism (Section 7) — Rithum has both halves (ad automation, margin data) unconnected | N/A — same future-service scoping as item 2 | If/when Sanocea ever pursues advertising as a service, the specific, evidenced design target should be: **margin-aware bidding as the differentiated design point**, since even the deepest advertising-automation platform researched in this program has not confirmed doing this — this is a genuine, specific, evidenced gap in the category, not a Sanocea-invented aspiration | N/A today | N/A today | Global — this is a category-wide gap, not India-specific | **DO NOT BUILD NOW**, same reasoning as item 2 — recorded as a sharp future-service design target, not a current priority |
| 4 | **D** | A retailer-side network of suppliers with compliance scorecards and automated financial penalties for non-compliance | Rithum's dropship/EDI-compliance-chargeback system (Section 9) | N/A — Sanocea's procurement model is deliberately the opposite relationship (cooperative merchant-initiated PO, not adversarial retailer-polices-supplier) | **Do not build this** — it is a two-sided marketplace problem requiring a real supplier network to police, not primarily an engineering problem, consistent with the baseline's existing do-not-build reasoning for a dropship supplier network (baseline Section 10) | N/A | N/A | Low — this capability class is largely irrelevant to Sanocea's target merchant segment (a brand/seller, not a retailer managing a supplier network) | **DO NOT BUILD** — recorded for completeness, per the mandate's instruction to note capabilities found and deliberately excluded, not as a live consideration |
| 5 | **C** | Never trust a single real-time signal for financial truth — always have an independent reconciliation/audit layer, even when the "primary" system is sophisticated | Rithum's own confirmed reconciliation depth (Section 4) is *weaker* than Unicommerce's/EasyEcom's despite Rithum's greater overall economic sophistication — a real, evidenced example that advertising/economics depth does not automatically imply reconciliation depth | Sanocea's dual-status reconciliation model (Section 6 of the combined audit) is already the more architecturally correct pattern | No new design lesson beyond reconfirming Sanocea's existing canonical-field approach is right — this finding is a *validation*, not a gap | N/A — no change needed | N/A | Reinforces (does not add to) the existing P1 marketplace-fee-reconciliation priority from the Unicommerce/EasyEcom audits | **Not a new priority — reconfirms existing P1** |

## 19. Proposed baseline changes after Rithum

**Per instruction: `SANOCEA-PRODUCT-BASELINE-V1.md` is NOT edited by this audit.** The following are
proposals for team review.

### Proposed change 1 — Open Research Question #2 (baseline Section 14, item 2) — resolve, do not carry forward as open

- **Current baseline statement:** *"Is there a mature, closed-loop contribution-margin/ad-spend
  attribution system... Unconfirmed at all four competitors researched. The combined audit's own
  landscape discovery flagged Rithum... as the most plausible remaining candidate — not yet verified."*
- **New evidence:** Rithum, now verified directly, shows a **PARTIALLY OCCUPIED** result (Section 17) —
  the individual components (margin calculation, ad-spend automation, a third-party rule-based
  margin-threshold loop) are real and more mature here than anywhere else in this program, but the specific
  connection (ad spend responding to contribution margin, not revenue/ROAS) is not confirmed anywhere,
  native or partner.
- **Proposed replacement:** *"Resolved, not merely still-open: the most plausible candidate (Rithum) has
  been directly audited. No competitor researched across six audits has a confirmed closed loop from
  advertising spend through to contribution-margin-driven decision-making — Rithum has the individual
  components more mature than any other platform researched, but the specific wiring from margin to ad
  decision is unconfirmed even there. This should be read as a genuine, narrow, unclaimed opening for a
  future Sanocea thesis (per Section 5.B's plausible-future-differentiator framing) — but it remains
  exactly that: a future thesis, not a current capability gap competitors have already closed and Sanocea
  hasn't. Do not re-open this research question by auditing a seventh platform on this specific point
  unless a new, credible candidate (distinct from Rithum) surfaces."*
- **Confidence: High** for "Rithum does not confirm this specific connection" (based on a direct fetch of
  Rithum's own advertising product page finding revenue/ROAS-flavored language, not contribution-margin
  language); **moderate** for "this closes the research question entirely" (one competitor's absence is
  strong but not exhaustive evidence across the whole category).

### Proposed change 2 — Differentiator F (baseline Section 5.A.1) — strengthen further, with a new nuance

- **Current baseline statement:** differentiator F is "the primary anchor differentiator overall,"
  reconfirmed by five competitors including Gorgias.
- **New evidence:** Rithum is confirmed to have *more* of differentiator F's individual components (A, D,
  F fully; B, C, H partially — Section 16) than any prior competitor, making it the strongest test yet —
  and the claim still survives, specifically because component G (canonical linkage) and component E
  (customer-support truth) are both still not found.
- **Proposed replacement:** *"...now tested against six competitors, including the one with the broadest
  individual-component coverage researched (Rithum: real advertising-spend truth, real dropship-network/
  supplier truth, real fulfilment truth, partial financial-reconciliation and cross-truth-action coverage)
  — and still survives specifically on the canonical-linkage and customer-support-truth components, which
  no competitor researched has shown. The claim is now more precisely evidenced as 'no competitor combines
  even most of these pieces under one canonical model,' rather than 'no competitor has most of the
  individual pieces at all' — Rithum shows some competitors do have deep individual pieces; the
  differentiation is specifically in the combination and the linkage, not in any single domain's depth."*
- **Confidence: High** — this is a direct, evidenced sharpening of existing language, not a new claim.

### Proposed change 3 — everything else: no change recommended

Sections 2-4, 6-13 (India connector priorities, reconciliation priorities, procurement, WMS do-not-build,
pricing principle, `OperationalEvidence`, exception-autonomy model, AI Roadmap Stages 0-7, human-labour
thesis, customer-support differentiator E) are unaffected by Rithum-specific evidence. Rithum's dropship/
supplier-network finding (Section 9 here) reinforces, rather than changes, the baseline's existing
do-not-build reasoning for a proprietary supplier network — no change needed there either. No change is
proposed to any of these sections.

## 20. What did Rithum actually teach us?

Filtered strictly to genuinely new information this program did not have after competitors #1-#5:

1. **A mature platform can calculate real, granular per-order profit with real cost inputs (FBA/WFS fees,
   settlement data, COGS) — and still treat it as a report a human reads, not an automated trigger.** This
   is the single most important new fact: economic sophistication and decision-automation are not the same
   thing, and this program had not previously seen a platform with genuinely deep profitability
   *calculation* to test this distinction against.
2. **The deepest advertising-automation mechanism found in this program (real bid/budget/pacing automation
   across Amazon Ads, Walmart Connect, and now Target's Roundel) still runs on revenue/ROAS, not
   contribution margin, by Rithum's own confirmed product language.** This resolves the open research
   question about a closed contribution-margin loop existing anywhere — the answer is "no," with unusual
   specificity now (Sections 6, 7, 17).
3. **A real, working, rule-based margin-threshold closed loop (MarginDriver's Deficient Orders tool) exists
   — but only as a third-party partner integration, not as a native capability of the platform with the
   deepest relevant economic feature set researched.** This is new evidence for a pattern this program had
   suspected but not confirmed this specifically: even where a genuine closed loop exists in the category,
   it may live outside the core platform's own product boundary.
4. **Retailer-side dropship/supplier-network orchestration (compliance scorecards + automated financial
   chargebacks for non-compliance) is a genuinely distinct capability class from Sanocea's own
   procurement model** — not merely "procurement, but bigger." This program had procurement confirmed as
   an existing Sanocea strength (Linnworks/Unicommerce/EasyEcom audits); Rithum is the first competitor to
   expose that "procurement" and "dropship-network orchestration" are two different problems with two
   different (in fact opposed) trust relationships, worth naming even though it's correctly out of scope
   to build.
5. **Corporate/product fragmentation (multiple coexisting systems under one brand, not one canonical data
   model) now holds at the platform with the broadest capability surface tested in this program** — Rithum
   joins Unicommerce and EasyEcom in this specific pattern, but at a materially larger scale (three
   heritage companies plus a third-party partner ecosystem, vs. two acquisitions or zero). This raises,
   rather than lowers, confidence that fragmentation-despite-scale is a structural tendency in this
   category, not a symptom of smaller/less-resourced competitors specifically.

**Per the mandate and the user's explicit instruction: this audit is now complete. No production code was
touched, no recommendation was implemented, `SANOCEA-PRODUCT-BASELINE-V1.md` was not edited (Section 19
above proposes changes only), and no competitor #7 has been started.**
