# EasyEcom vs. Sanocea — Competitive Capability Audit

Governed by [`../competitive/README.md`](./README.md) (the Sanocea Competitive Research Mandate, v1,
2026-09-11). Third per-competitor audit under that mandate, following
[`linnworks-vs-sanocea.md`](./linnworks-vs-sanocea.md) (global OMS/WMS perspective) and
[`unicommerce-vs-sanocea.md`](./unicommerce-vs-sanocea.md) (India-specific OMS/WMS/reconciliation
perspective). Linnworks/Unicommerce findings are referenced only in Sections 9-10 (convergence and
priority reconciliation), not re-researched here.

**Explicit reminder carried over from the user's instruction, for all three audits so far:** this is
evidence and analysis only. Nothing in this file authorizes any Sanocea implementation work. No
production code, connector, test, or script was touched to produce it.

## 0. Scope, evidentiary basis, and two corrections to the brief

Twenty targeted WebSearch queries were run this pass, covering: the EasyOMS/EasyWMS/EasyReco/EasyVMS
product-boundary question; EasyReco mechanics compared against UniReco; COD/courier reconciliation;
NDR/RTO and video/image evidence capture; multi-location allocation and order routing; bundles/kits/BOM;
procurement/vendor operations; accounting/GST/Tally; pricing; WhatsApp/customer support; growth/
advertising; RBAC; barcode/pick/pack/QC; split/cancellation/backorder; demand forecasting; named
operational-AI features; and EasyEcom's own corporate/acquisition history and job-market footprint.

**Two corrections to the brief's assumptions, surfaced by this research and disclosed per this program's
evidentiary discipline (the same discipline the Unicommerce audit applied to "Smart Facility
Allocation"):**

1. **"EasyVMS" is not a vendor-management system.** EasyEcom's own product suite names it the **Video
   Management System** — it links packing and return-unpacking video/image capture to every order ID for
   marketplace-dispute evidence. This is confirmed directly from EasyEcom's own product pages
   ([easyecom.io/warehouse-management-system](https://www.easyecom.io/warehouse-management-system);
   [easyecom.io/video-management-system](https://www.easyecom.io/video-management-system);
   [vms.easyecom.io](https://vms.easyecom.io/)). Procurement/vendor operations (purchase orders, a Vendor
   Master, GRN) exist as real EasyEcom capability (Section 2.6) but are **not** branded as a distinct
   "EasyVMS" product the way the brief assumed — they appear to be a module of the core OMS/WMS suite,
   not a fourth named product. This is corrected throughout the file rather than silently followed.
2. **A candidate "EasyBooks" accounting product could not be confirmed as real, separately-branded
   product.** One blog snippet surfaced the term in a reconciliation context, but no dedicated product
   page, pricing entry, or independent confirmation was found anywhere else this pass. Treated as
   `UNKNOWN — not confirmed as a distinct branded product`, not asserted as real (Section 2.8).

**Corporate structure — a materially different shape from Unicommerce, which changes the
classification exercise:** EasyEcom was founded in 2015 (Bengaluru; founders Punit Gupta and Swati
Jindal), is privately held (not listed, unlike Unicommerce's NSE listing), has raised a comparatively
small ~$2.08M across rounds (latest a Series B in January 2022; investors include IndiaMART InterMESH,
Tradezeal Online, Amistad Ventures), and — confirmed via PitchBook/Tracxn/Crunchbase/CB Insights —
**has made no acquisitions** ([tracxn.com/d/companies/easyecom](https://tracxn.com/d/companies/easyecom/__aGiKBbqaL_tU-yqoXs4lgU5MwMTGORx2jmzmSAMiBJ8);
[cbinsights.com/company/easyecom](https://www.cbinsights.com/company/easyecom/financials)). This means
**EasyOMS, EasyWMS, EasyReco, and EasyVMS are all native, in-house-built modules of one company** — the
opposite classification finding from Unicommerce, where Shipway and Convertway are acquired subsidiaries.
EasyEcom's courier/logistics layer is delivered through **third-party** courier aggregators (Shiprocket,
NimbusPost, and others are named as comparable/competing players in the same market segment EasyEcom
occupies — see Section 2.2) rather than an owned logistics subsidiary the way Unicommerce owns Shipway.

**Genuinely thin or unconfirmed after this pass** (real gaps, not resolved findings — flagged honestly
rather than filled with confident-sounding prose): RBAC/permission granularity (no evidence found at
all, not even a generic mention); a dedicated NDR panel/named workflow equivalent to Shipway's (return-to-
origin *tracking* is confirmed, but a re-attempt/RTO decision workflow with the same evidentiary depth as
Unicommerce's finding was not found); WhatsApp-specific customer automation (nothing EasyEcom-branded
surfaced, unlike Unicommerce's Convertway); a named, shipped operational-AI feature (only generic
"AI-enabled carrier allotment" marketing language, with no mechanism detail); merchant-side job listings
that name EasyEcom as a required skill (only EasyEcom's own internal hiring postings surfaced — see
Section 6 for why this materially weakens the human-labor evidence versus the Unicommerce pass);
idempotency/webhook/rate-limit architecture; exact pricing figures (see Section 2.9).

---

## 1. Executive summary — EasyEcom vs. Sanocea

EasyEcom is the narrowest but most internally coherent of the three platforms audited so far: unlike
Unicommerce's three-product holding structure (Uniware/Shipway/Convertway, two of them acquisitions),
EasyEcom's four capability areas (order management, warehouse management, reconciliation, video-evidence)
are genuinely one company's in-house build, which is the strongest real-world precedent in this research
program for Sanocea's own "one canonical system" ambition — though EasyEcom's own public material gives
no evidence its four areas share one canonical *data model* either, only that they share one vendor and
one sales relationship.

The single most novel finding of this pass, not anticipated by either prior audit, is **EasyVMS**: a
dedicated video/image evidence-capture product tying packing and return-unpacking footage to every order
ID specifically to win marketplace disputes (a claimed 90% win rate) and preserve Seller Protection Fund
(SPF) eligibility on Flipkart/Amazon/Myntra. Neither Linnworks nor Unicommerce's research surfaced
anything like this — it is a genuinely new capability class for this program, addressing the same
underlying problem (marketplace dispute/claim resolution) that UniReco addresses financially, but through
physical evidence rather than fee-ledger reconciliation. Sanocea has nothing analogous.

Conversely, EasyEcom is weaker than Unicommerce on customer-facing automation (no confirmed WhatsApp
product, no confirmed proactive-notification widget at Linnworks' level of detail) and weaker on named,
India-specific logistics-exception depth (no confirmed dedicated NDR panel, no owned courier-aggregation
subsidiary) — its courier layer is third-party, not an owned or even acquired capability. EasyReco's
reconciliation mechanics are directionally similar to UniReco's but evidenced at lower granularity in
public material (Section 2.4). The human-labor evidence for this pass is also the thinnest of the three
audits: no merchant-side job listing citing EasyEcom as a required skill was found, only EasyEcom's own
internal hiring — a real evidentiary gap, disclosed rather than papered over (Section 6).

## 2. Capability-by-capability audit (A-J framework)

### 2.1 Order routing and multi-location allocation (EasyOMS)

- **A. Merchant problem:** route each incoming order automatically to the warehouse holding the stock
  closest to the customer, across a multi-warehouse or multi-brand footprint, without a human manually
  assigning fulfilment location per order.
- **B. Why it exists:** same root failure mode identified against both prior competitors — manual
  multi-location assignment doesn't scale, and naive single-location defaults strand fulfilable orders.
- **C. Relevance:** growing SMEs onward, once a merchant has more than one facility.
- **D. India frequency:** high — EasyEcom explicitly supports the 1-to-50-warehouse range and B2B-specific
  routing rules, both directly relevant to Indian D2C/B2B-hybrid sellers.
- **E. Sanocea status:** `ARCHITECTURAL ONLY` — unchanged finding from both prior audits.
- **F/G/H/I.** Same reasoning as Linnworks Section 2.1-2.2 and Unicommerce Section 2.5 — this is not a
  new design question, it is a third independent confirmation of the same one (Section 9).
- **J. Priority: P0** — **now independently validated a third time**, by a platform using yet another
  allocation philosophy (ZIP-code/distance-based proximity routing plus explicit priority-rule
  configuration for multiple warehouses serving the same pincode) alongside Linnworks' criteria-based
  routing and Unicommerce's network-wide fill-maximization. Three different mechanisms, same underlying
  problem, across three independently-built platforms — the strongest possible signal in this program
  that this is a universal architectural requirement, not a platform quirk.

*Evidence:* EasyEcom "can run 1-50 warehouses and routes each order to the warehouse with stock closest
to the customer using ZIP code and distance logic"; supports B2B Order Routing (intelligent warehouse
allocation during order creation based on configured routing rules and inventory availability) and
priority-based order routing for multiple warehouses assigned to the same pincode
([easyecom.io/products/multi-warehouse-management](https://easyecom.io/products/multi-warehouse-management);
[easyecom.io/whats-new](https://www.easyecom.io/whats-new)). The homepage additionally claims order
routing at "47ms to route" — a specific latency claim with no independent verification found; treat as an
unverified marketing figure, not confirmed performance evidence.

### 2.2 Warehouse execution: scan-based pick/pack/QC (EasyWMS)

- **A.** Get a warehouse worker to the right stock, correctly, using ordinary Android devices rather than
  proprietary scanning hardware.
- **B.** Same root failure mode as Linnworks' pick/pack/dispatch finding (mis-picks, no batching, wasted
  time) — EasyEcom's specific differentiator claim is removing the *hardware* barrier (no rugged-scanner
  requirement) that raises the cost of adopting warehouse execution tooling at all.
- **C.** Relevant only to merchants running their own warehouse floor, same segment-scoping caveat as the
  Linnworks finding.
- **D. India frequency:** moderate, same reasoning as against Linnworks — many Indian D2C sellers below a
  certain scale use a 3PL rather than their own warehouse.
- **E. Sanocea status:** `MISSING` — unchanged from the Linnworks-audit finding; this pass does not add a
  new gap, it reconfirms an existing one with a lower-barrier-to-adopt variant.
- **F/G/H.** Same reasoning as Linnworks Section 2.6 — a large canonical addition, not an extension, and
  explicitly named there as a feature-bloat trap absent a real multi-bin-warehouse merchant on the roadmap.
- **I.** Yes, for the subset of merchants running their own warehouse.
- **J. Priority: DO NOT BUILD now / P3 later** — unchanged from the Linnworks finding. EasyEcom's
  "runs on any Android phone, no proprietary hardware" framing is worth noting as a *design* input if this
  is ever built (a lower-cost-of-adoption bar than dedicated scanning hardware), but does not change the
  underlying priority call.

*Evidence:* "EasyEcom is scan-based and paperless out of the box, with teams going live on rugged
handhelds or phones in their pockets, with no proprietary hardware and no rip-and-replace"; "scan-based
inward, QC, putaway and picking on rugged handhelds or any Android phone, with SKU, EAN, UoM, batch and
serial codes validated at every touch, including shelf and bin barcoding"; claims 99.7% accuracy across
1-50 warehouses ([easyecom.io/warehouse-management-system](https://www.easyecom.io/warehouse-management-system)).
The 99.7% figure has no independent verification found — treat as an unverified marketing claim.

### 2.3 Reconciliation (EasyReco) — mechanics compared directly against UniReco

- **A. Merchant problem:** confirm a marketplace/payment gateway/courier actually paid and returned what
  it owed, and recover money lost to fee errors, wrong deductions, or short settlements before dispute
  windows close.
- **B. Why it exists:** identical root cause to UniReco (Unicommerce Section 2.2/2.9) — dense,
  marketplace-favorable settlement statements create silent, hard-to-notice margin leakage.
- **C. Relevance:** any merchant selling through marketplaces/payment gateways — SME onward.
- **D. India frequency:** very high — EasyEcom's own material specifically quantifies this at "1-3% of
  GMV" globally and "2-4% in India, where deduction rules and return-to-origin (RTO) are heaviest."
- **E. Sanocea status:** same as the Unicommerce-audit finding — `IMPLEMENTED+PROVEN` in *shape*
  (dual-dimension reconciliation), never proven against a real Indian marketplace settlement feed.
- **F/G/H.** Same reasoning as Unicommerce Section 2.9 — extends the existing canonical dual-status
  pattern; fee-category vocabulary belongs in connector configuration, not canonical logic.
- **I.** Yes, directly.
- **J. Priority: P1**, reconfirmed rather than newly established.

**Direct mechanics comparison against UniReco, per the user's explicit instruction not to just say "both
have reconciliation":**

| Dimension | UniReco (Unicommerce) | EasyReco (EasyEcom) | Assessment |
|---|---|---|---|
| Public documentation depth | Support-portal-level detail: a named 5-state status vocabulary (`RECONCILED`, `RECONCILED BY DELTA`, `RECONCILED MANUALLY`, `PARTIAL PAYMENT`, `PAYMENT DISPUTED`) and a named fee-category list (Commission Fee, Commission Override Fee, Fixed Fee, Payment Gateway Collection Fee, Pick and Pack Fee, Refund Commission Fee, Shipping Fee) | Marketing/blog-level detail: "three numbers per channel — expected, landed, recovered" and a generic "commission, logistics, payment gateway fee" deduction list, without a comparably granular named-category breakdown found in public material this pass | UniReco's public evidence is genuinely more granular; this may reflect EasyEcom's public documentation being thinner rather than the underlying product being shallower — flagged as an evidence-depth difference, not a confirmed capability gap. |
| Named marketplace targeting | Explicitly names Flipkart, Amazon, Myntra, Meesho | Implied (Amazon/Flipkart/Shopify/Quick Commerce integration breadth generally) but not named as reconciliation-specific targets with the same specificity | UniReco's evidence is more explicit here. |
| Tolerance/delta matching | Explicit named state (`RECONCILED BY DELTA`) | Not explicitly named as a distinct state in public material; framed generally as "identify payment mismatches ... across channels" | UniReco's evidence shows a more explicit tolerance mechanism; EasyReco's may exist but isn't publicly documented at the same granularity — `UNKNOWN`, not `ABSENT`. |
| Dispute/claim automation | `PAYMENT DISPUTED` is confirmed as a status/queue a human then acts on (per the Unicommerce audit's human-labor findings) — flag, not auto-file | EasyReco's own framing goes one step further in its marketing language: "it finds the money you lost, **then files the claim**," and separately, for returns specifically, "surfaces every disputed return, short payment and overdue settlement with the evidence attached, then **auto-tickets the claim** and tracks it through to Reconciled" | This is EasyReco's most interesting claim relative to UniReco — *if accurate*, EasyEcom's claim-filing step is more automated than what was confirmed for UniReco. This is marketing-page language, not support-documentation-level confirmation, so it should be treated as `PLAUSIBLE, not independently verified` rather than accepted at face value — but it is a real, specific, checkable claim worth flagging as a possible genuine mechanics difference, not just phrasing. |
| Inventory/return reconciliation scope | Reconciliation product is COD-remittance- and commission-fee-focused | EasyReco explicitly covers "payment, inventory, returns and margin" as one combined product, plus a separate "Return Reconciliation Dashboard" feature release | EasyReco's scope framing is broader (folds inventory reconciliation into the same product) — but broader framing is not the same as deeper mechanism evidence; both should be weighed, not one assumed superior. |

**Net assessment:** EasyReco and UniReco pursue the identical underlying merchant problem with broadly
similar mechanics (settlement matching, UTR-based transaction matching, discrepancy flagging, claim
generation). UniReco's public evidence is more granular and specific; EasyReco's public evidence makes a
more automated-sounding claim about claim-filing specifically, but at lower documentation depth. Neither
should be treated as definitively "ahead" of the other on the evidence gathered — this is a case where
the honest answer is that both independently validate the same reconciliation-pattern *and* the same
automate-the-claim-not-just-the-flag ambition, with EasyEcom's marketing claiming to have gone slightly
further on the latter, unverified.

*Evidence:* [easyecom.io/products/easy-reco-reconciliation](https://easyecom.io/products/easy-reco-reconciliation);
[easyecom.io/payment-reconciliation](https://www.easyecom.io/payment-reconciliation);
[easyecom.io/blog/everything-you-need-to-understand-and-fix-reconciliation-gaps](https://easyecom.io/blog/everything-you-need-to-understand-and-fix-reconciliation-gaps);
[easyecom.io — Return Reconciliation Dashboard](https://easyecom.io/whatsnew-articles/new-feature-avoid-losses-and-simplify-claim-process-with-return-reconciliation-dashboard).

### 2.4 Video/image evidence capture for disputes (EasyVMS) — genuinely new to this program

- **A. Merchant problem:** win a marketplace dispute (item-not-received, wrong/damaged/tampered item,
  return-fraud claim) with physical proof, rather than a merchant's word against a buyer's, and preserve
  eligibility for marketplace seller-protection programs that now *require* such proof.
- **B. Why it exists:** marketplaces increasingly require video/photo proof for seller-protection claims
  (explicitly named for Flipkart, Amazon, Myntra) — without it, sellers face automatic claim rejection and
  loss of protection-program eligibility, a direct, quantifiable revenue exposure distinct from (though
  related to) the fee-reconciliation problem UniReco/EasyReco address.
- **C. Relevance:** any merchant shipping physical goods through marketplaces with dispute/return-fraud
  exposure — SME onward, more consequential at higher return-fraud volume.
- **D. India frequency:** high — return fraud and product-swap disputes are a well-known Indian D2C/
  marketplace pain point, compounded by high COD-driven return volume.
- **E. Sanocea status:** `MISSING` — no evidence of any video/image-evidence-capture concept anywhere in
  Sanocea's canonical model or connectors.
- **F.** Not supportable today without new capability — this would require a genuinely new concept (an
  evidence-attachment relationship between a physical fulfilment/return event and an order/exception
  record), not an extension of anything that currently exists.
- **G.** Canonical domain (an evidence-attachment concept on the order/return/exception record) + a new
  connector/integration surface (actual video/image capture requires camera hardware or a
  warehouse-worker-facing capture flow, which is a physical-execution concern, not a pure backend one) +
  human exception (dispute filing, at minimum evidence-gathering, cannot be fully automated without a
  real capture integration).
- **H.** Low risk to the canonical model itself if scoped narrowly as "an exception record can carry
  evidence attachments" (generic, not marketplace-specific) — risk rises if the *capture mechanism itself*
  (which camera, which warehouse workflow) is built prematurely without a real merchant's warehouse
  process to design against.
- **I.** Yes, potentially significant — this is real, evidenced human/financial-risk work today (filing a
  dispute with adequate evidence, or losing SPF eligibility without it).
- **J. Priority: P2** — a real, novel, evidenced merchant need with no Sanocea equivalent, but it depends
  on a physical-capture integration Sanocea does not have any foundation for yet (unlike, e.g., the
  reconciliation extension in Section 2.3, which extends an existing canonical pattern). Sequenced behind
  P0/P1 items that extend existing Sanocea capability more directly.

*Evidence:* "EasyVMS is a video management system that links packing and return video to every order to
beat return fraud and win marketplace disputes... 90% win rate"; "EasyVMS tags every order's packing and
return video with its order ID, so any clip is searchable in seconds and ready to use as dispute
evidence"; "EasyVMS records videos along with images of the products both for forward shipments (packing)
and reverse shipments (unpacking returns) to protect you from return fraud, product swaps, and tampered
packages"; "Flipkart, Amazon, Myntra, and other marketplaces require video proof for seller protection
claims. Without a proper video management system, you risk losing SPF eligibility and automatic claim
rejections" ([easyecom.io/video-management-system](https://www.easyecom.io/video-management-system);
[vms.easyecom.io](https://vms.easyecom.io/);
[easyecom.io/blog/how-video-management-software-helps-ecommerce-sellers-win-disputes-and-save-money](https://easyecom.io/blog/how-video-management-software-helps-ecommerce-sellers-win-disputes-and-save-money)).
The 90% win-rate figure is EasyEcom's own marketing claim with no independent verification found — cite
as a claim, not a confirmed statistic. **Category 1 (native)** — EasyVMS is EasyEcom's own in-house
product per Section 0's corporate-history finding, not an acquisition, though it is marketed on its own
dedicated subdomain (`vms.easyecom.io`), suggesting a distinct sales motion even if not a distinct legal
entity — worth flagging as a structural observation, not a confirmed fact about pricing/gating (Section
2.9 addresses pricing directly).

### 2.5 Procurement and vendor operations — real, but not a distinct "EasyVMS" product

- **A.** Get the right stock from the right vendor with a real audit trail, same problem as the
  Unicommerce-audit procurement finding.
- **B.** Same root cause as Unicommerce Section 2.8 — ad hoc vendor ordering without a lifecycle loses
  visibility into what's pending/approved/received.
- **C.** SME onward.
- **D. India frequency:** high, same reasoning as against Unicommerce.
- **E. Sanocea status:** `IMPLEMENTED+PROVEN` per the combined audit — not a gap.
- **F/G/H.** N/A — not a gap.
- **I.** Already yes.
- **J.** Not a gap, but worth noting the specific mechanics found: a Vendor Master holding per-vendor
  payment terms (pulled automatically into new POs rather than re-entered manually), an "approved PO and
  inward operations" control layer, and a unified warehouse view spanning pending GRNs/Returns/
  Cancellations in one place. This is a real, if less independently-verified-at-lifecycle-stage-naming-
  depth, echo of the Unicommerce finding (`PO created → PO Approved → PO sent → GRN`) — useful as a
  second data point that this general PO-lifecycle shape (cart/select → approve → send → receive with a
  vendor-configuration layer underneath) is a recurring, not idiosyncratic, pattern.

*Evidence:* "EasyEcom has enhanced its purchase order management to give procurement teams greater control
over approved POs and inward operations, including a unified warehouse view to monitor all pending
inventory across GRNs, Returns, and Cancellations"; "EasyEcom overhauled its Purchase Order Template to
put vendor-level configuration at the center. Payment terms now pull directly from the Vendor Master,
eliminating manual entry for every order" ([easyecom.io/whats-new](https://www.easyecom.io/whats-new)).
**Category 1 (native)** — a module within the core OMS/WMS suite, not a separately branded fourth product
(correcting the brief's "EasyVMS = vendor management" assumption per Section 0).

### 2.6 Bundles/kits/BOM

- **E. Sanocea status:** `MISSING` — unchanged from both prior audits.
- **Evidentiary note, disclosed honestly rather than papered over:** unlike Sections 2.1-2.5, this search
  pass did **not** surface EasyEcom-specific bundle/kit/BOM mechanism detail — every result returned was
  generic industry content (Zenventory, Zoho Inventory, Finale Inventory, Ecomdash) or general
  bundle-vs.-BOM explainer material, not an EasyEcom product page or support article. This should be
  marked `UNKNOWN — not reached this pass` for EasyEcom specifically, not assumed absent. A follow-up
  search specifically against `easyecom.io` and `support.easyecom.io` domains would be needed to close
  this gap; it was not closed this pass.
- **J. Priority:** unchanged (`P2`, per the Linnworks/Unicommerce convergence in Section 9) — this
  capability's priority rests on two independent confirmations already, not on EasyEcom adding a third;
  EasyEcom's specific mechanics remain a genuine open question, not a new finding either way.

### 2.7 Order cancellation, splitting, and partial fulfilment

- **A.** Cancel, split, or partially fulfil an order cleanly at any point in its lifecycle, including
  item-level (not just whole-order) granularity.
- **B.** Same root cause as the Linnworks/Unicommerce findings — partial availability and mid-flight order
  changes are routine, high-frequency events that become manual order-desk work without real tooling.
- **C.** Every segment, same as the Unicommerce-audit finding (Section 2.11 there).
- **D. India frequency:** high — item-level cancellation on a marketplace order is common when a customer
  partially modifies an order after placing it.
- **E. Sanocea status:** `IMPLEMENTED+PROVEN` (3 real platforms) for basic cancellation per the combined
  audit; split-order handling is `MISSING` per both prior audits — this pass does not change either
  verdict, but adds a concrete design cue (below).
- **F.** The "Force Split" mechanism found here — allowing partial packing of a B2C order without waiting
  for every item to be available — is a specific, real, named mechanic worth carrying forward as a design
  input for Sanocea's own eventual split-order model (Linnworks Section 2.5, Unicommerce priority
  reconciliation Section 9): the pattern is "split becomes available as a packing-station-level override,"
  not only an order-creation-time decision.
- **G/H.** Same reasoning as Linnworks Section 2.5 — deterministic engine + canonical domain (order-
  lineage relationship), generic eligibility rules, not hardcoded to one payment/shipping model.
- **I.** Yes, same reasoning as both prior audits.
- **J. Priority: P2/P3** — unchanged from the Linnworks-audit sequencing; this pass adds design-input
  detail, not a priority change.

*Evidence:* "EasyEcom has enhanced the B2C Packing Station to support Force Split, bringing order
splitting into order packing so teams can partially process eligible orders. Previously, B2C orders had
to wait for all items before packing could be completed"; "the upgraded Flipkart smart integration
enables cancellation of orders at item-level, whereas earlier the entire order was canceled in case of
order changes" ([easyecom.io/whats-new](https://www.easyecom.io/whats-new);
[easyecom.io — Flipkart Smart Integration item-level cancellation](https://easyecom.io/whatsnew-articles/upgraded-flipkart-smart-integration-partial-order-cancellation-at-item-level-now-available)).

### 2.8 Accounting/finance — distinguishing marketing language from actual capability

Per the mandate's explicit instruction not to let marketing language collapse distinct financial concepts
into one category, here is what this pass found, separated cleanly:

| Claimed concept | What's actually confirmed | Classification |
|---|---|---|
| "Accounting" (general marketing claim on company-profile pages) | No dedicated general-ledger/accounting-system product confirmed. One secondary source mentioned "EasyBooks" tracking commission/logistics/payment-gateway-fee deductions, but this could not be independently confirmed as a real, distinct branded product anywhere else this pass. | `UNKNOWN — not confirmed as a distinct product`; the underlying deduction-tracking described sounds like a EasyReco feature described under a possibly-informal or mis-cited name, not evidence of a separate accounting system. |
| Tally/SAP/QuickBooks integration | Confirmed — "ready integrations with... ERPs like SAP, Tally etc."; a separate pricing-tier description explicitly lists "QuickBooks" as an included integration | **Third-party integration/export (category 3)** — EasyEcom exports/connects to a real external accounting system; it is not itself a general ledger. |
| GST/tax handling | No EasyEcom-specific evidence found this pass (searches returned generic third-party GST-software content, not EasyEcom's own material) | `UNKNOWN — not reached this pass`. |
| Invoicing | Not independently confirmed as a distinct capability this pass, beyond what's implied by order/PO management generally | `UNKNOWN`. |
| COGS / margin / profitability reporting | Confirmed — "advanced data analytics based margin report provides in-depth analysis of the profitability of businesses" | **Native reporting capability (category 1)** — a real analytics/reporting feature, not a general ledger. |
| Marketplace P&L / contribution-margin attribution | Margin reporting exists (above); no evidence found of a closed-loop ad-spend-to-contribution-margin attribution model specifically | `UNKNOWN`/`NOT FOUND` for the closed-loop version specifically — consistent with the mandate's Section 8 interest in this exact question, and consistent with both prior audits' inability to confirm this pattern anywhere in the program so far. |
| Actual general-ledger/accounting system | Not found | `NOT FOUND` — EasyEcom's "accounting" positioning resolves, on the evidence gathered, to (a) reporting/margin-analytics and (b) integration/export to a real external accounting product (Tally/SAP/QuickBooks), not a native ledger. |

**Conclusion for this section, stated plainly per the mandate's instruction:** EasyEcom's "accounting"
claim is real but narrower than the word implies — it is operational-reconciliation-plus-margin-reporting
plus third-party-accounting-software integration, not an actual general ledger. This is directionally
consistent with the combined audit's own finding that Sanocea's dual-status reconciliation model is a
canonical *field*, not a bolt-on accounting *product* — the same distinction, applied to a different
competitor.

### 2.9 Pricing/packaging

- **Official source:** `easyecom.io/pricing` publishes no self-serve tiers or numeric plans — every
  advertised option routes to a sales-contact form. This is confirmed directly, not inferred.
- **Third-party-aggregator claims (explicitly lower-reliability, per the mandate's instruction not to
  rely on unverified competitor-comparison sites for pricing):** a review-aggregator states pricing
  "starts at $0.49 per order" and separately "$89/Per Month," with a "$39.0 one-time Simple Pricing plan"
  covering 3PL integrations, API integration, centralised inventory, omnichannel orders, reconciliation,
  shipping, QuickBooks, and unlimited marketplaces. **These figures come from SaaSworthy/similar
  comparison-aggregator content, not EasyEcom's own pricing page, and should be treated as
  `UNKNOWN — not independently verified against EasyEcom's own material`, not reported as fact.**
- **What can be stated with confidence:** EasyEcom's pricing model is **sales-led/quote-based**, not
  publicly tiered — the same "custom, quotation-based final pricing" shape the Unicommerce audit found for
  Unicommerce's own overall billing (Section 2.12 there), even though Unicommerce additionally publishes
  named tier *feature* boundaries (Standard/Professional/Enterprise) that EasyEcom does not publicly
  disclose at all.
- **Module-gating question:** cannot be confirmed either way from public material. The observation that
  EasyVMS is marketed on its own dedicated subdomain (`vms.easyecom.io`), separate from the main
  `easyecom.io` domain where EasyOMS/EasyWMS/EasyReco live, is suggestive of a distinct sales motion for
  that specific product — but this is an inference from marketing-site structure, not a confirmed pricing
  fact, and is disclosed as such rather than asserted.
- **Comparison against Sanocea's mandate principle ("PRICE DETERMINES CAPACITY, NOT CAPABILITY"):**
  unlike Unicommerce, which provided clear, confirmable evidence of capability-gating (payment
  reconciliation locked behind the Professional tier), **EasyEcom provides no public evidence either
  confirming or refuting capability-gating** — the sales-led model simply doesn't disclose enough to make
  the comparison. This should be stated as an open question, not assumed to violate or comply with the
  mandate's principle either way.

## 3. Thinner-evidence capability summary

| Capability | EasyEcom status | Classification | Note |
|---|---|---|---|
| Catalogue/PIM, inventory sync, 80+ channel integration (incl. Amazon, Flipkart, Shopify, Blinkit, Zepto) | Confirmed real | Native (1) | Table-stakes; matches the marketplace/quick-commerce breadth already established for Unicommerce. |
| Courier/carrier layer | Confirmed real, but delivered through third-party aggregators (Shiprocket, NimbusPost, and comparable named competitors), with EasyEcom's own claimed value-add being "AI-enabled carrier allotment" for cheapest-carrier selection | **Third-party integration (3)** for the couriers themselves; the *selection logic* may be native (1), mechanism depth `UNKNOWN` | A materially different structure from Unicommerce, which owns its courier-aggregation layer (Shipway) outright. |
| NDR/RTO | Return-to-origin **tracking** confirmed (an RTO-delivered-date field in the Returns Report); a dedicated NDR re-attempt/RTO-decision panel with Shipway-level evidentiary depth was **not found** this pass | `UNKNOWN`/thinner than Unicommerce's confirmed finding | A real gap relative to the Unicommerce pass, disclosed rather than assumed away. |
| Demand forecasting/replenishment | Confirmed real — "replenishment engine suggests precise reorder quantities based on 7-60-day movement" | Native (1) | Comparable in shape to Linnworks' and Sanocea's own existing velocity-based logic; no seasonal-trend claim found specifically for EasyEcom (unlike Linnworks' explicit seasonal-trend claim). |
| RBAC/permissions | No evidence found at all — not even a generic marketing mention | `UNKNOWN` | The weakest evidence of the three audits on this specific point; genuinely not reached, not confirmed absent. |
| AI-assisted *operations* | Only generic "AI-enabled carrier allotment" and industry-generic "AI-powered forecasting" marketing language; no named, shipped feature with mechanism detail found | `UNKNOWN`/`NF` for a genuinely named feature | Consistent with the pattern of "marketing uses the word AI, no confirmed mechanism" seen elsewhere in this program (contrast with Linnworks' Spotlight AI and Unicommerce's Catalyst, both of which have real mechanism detail). |
| Customer support/WhatsApp | No EasyEcom-branded conversational-support or WhatsApp product found | `NOT FOUND` | The weakest of the three platforms on this specific axis — see Section 4. |
| Growth/advertising (Amazon PPC, Flipkart Ads, etc.) | No evidence found | `NOT FOUND` | Consistent with EasyEcom's OMS/WMS/reconciliation/evidence-capture positioning — advertising is simply outside scope, same conclusion reached for Linnworks. |

## 4. Customer support — operate vs. provide (Mandate Section 7)

This is the thinnest support finding of the three audits. No native or group-owned conversational-support
capability was found for EasyEcom at all — no WhatsApp chatbot (contrast Unicommerce's Convertway), no
order-tracking self-service widget with the documented depth of Linnworks' "Track My Order" feature.

**What was found, and how it's classified:**

- **EasyEcom's own support center** (`support.easyecom.io`) is, exactly as with Linnworks' and
  Unicommerce's own support portals, EasyEcom supporting *its own merchant customers* (using EasyEcom),
  not a feature for merchants to support *their* end customers. This distinction, established in both
  prior audits, holds a third time.
- **EasyReco's claim-auto-ticketing** (Section 2.3) is a B2B/marketplace-facing dispute-filing mechanism,
  not an end-customer conversation channel — it resolves a merchant-vs-marketplace dispute, not a
  merchant-to-shopper conversation. Worth naming explicitly so it is not miscounted as customer support.
- **No evidence surfaced** of native email, live chat, Instagram/social handling, or a WhatsApp product
  anywhere in EasyEcom's public material.

**Classification table:**

| Channel | EasyEcom capability | Classification |
|---|---|---|
| Order-status/shipment enquiries | Not confirmed as a native self-service feature with the depth found for Linnworks | `UNKNOWN`/`NOT FOUND` |
| WhatsApp | No product found | `NOT FOUND` |
| Email/live chat/Instagram-social conversations | No product found | `NOT FOUND` |
| Returns/complaints — customer-facing | Return *processing* (Section 2.6/2.3's return-reconciliation scope) is real, but as an operational/financial workflow, not a customer-conversation channel | `NOT FOUND` for the conversational dimension specifically |
| Marketplace dispute/claims resolution | EasyReco auto-tickets claims (Section 2.3) | `AUTOMATED EXECUTION` — but this is merchant-vs-marketplace, not merchant-vs-shopper |
| Human handoff | Not applicable — no conversational channel exists to hand off from | `N/A` |

**Implication for Sanocea:** this is the sharpest customer-support contrast of the three audits so far —
EasyEcom's group has *no* confirmed conversational-support capability at all, weaker even than Linnworks'
zero-native-but-third-party-integrated position. Sanocea's Chatwoot-based, canonically-connected support
integration (proven per the combined audit) is a genuine, currently-true differentiator against EasyEcom
specifically, with no caveats needed about a group-owned bolt-on the way the Unicommerce finding required.

## 5. Growth/marketing — observed only (Mandate Section 8)

No native or integrated advertising-execution capability surfaced for EasyEcom, matching the Linnworks
finding rather than the Unicommerce one (which found real, if ad-spend-scope-limited, growth automation
via Convertway).

**Classification against the mandate's checklist:**

| Growth/marketing capability | Finding | Classification |
|---|---|---|
| Amazon PPC, Flipkart Ads, Myntra advertising, Meta/Google Ads, SEO, listing optimization, A+ content | No evidence found | `NOT FOUND` |
| Pricing/repricing engine | No evidence found | `NOT FOUND` |
| Marketplace promotions/campaign automation | No evidence found | `NOT FOUND` |
| Cart-recovery / retention automation (the one area where Unicommerce's Convertway showed real capability) | No evidence found for EasyEcom | `NOT FOUND` |
| Closed-loop ad-spend → order → margin → fees → logistics → returns → contribution-margin attribution | No evidence found | `NOT FOUND` |

**Assessment:** EasyEcom's scope is entirely operations/reconciliation/evidence-capture — no growth or
retention automation of any kind was found, unlike Unicommerce's group. This reinforces rather than
weakens the combined audit's standing flag that Rithum remains the more plausible candidate for the
closed-loop contribution-margin pattern the mandate specifically asks about — three competitors deep into
this program, that pattern has not been confirmed anywhere yet.

## 6. After buying EasyEcom, what does the merchant still pay a human to do? (Mandate Section 9)

**Evidentiary honesty first:** this section's evidence base is genuinely weaker than the Unicommerce
pass's. Searches for merchant-side job listings explicitly requiring "EasyEcom," "EasyEcom OMS," or
"EasyEcom WMS" as a skill returned **only EasyEcom's own internal hiring postings** (e.g. "eCommerce
Operations Executive at EasyEcom" on Wellfound — this is EasyEcom hiring for itself, not a merchant hiring
someone with EasyEcom experience) and generic e-commerce-executive job-description templates with no
EasyEcom-specific mention. **No merchant-side listing naming EasyEcom as a required skill was found this
pass**, in contrast to the Unicommerce audit, which found real listings requiring "strong working
knowledge of Unicommerce OMS." This is disclosed as a genuine research gap, not filled with invented
specifics.

**What can still be inferred from the confirmed capability gaps above (Sections 2-5), separated per the
mandate's required breakdown — inference, not job-listing evidence, and labeled as such:**

- **Physically unavoidable human work:** same finding as against both prior competitors — physical
  picking/packing/QC still needs a human hand; EasyWMS lowers the hardware barrier to structuring that
  work but does not remove the human from it.
- **Repetitive deterministic work (candidate for automation):** channel/marketplace connector setup and
  ongoing sync troubleshooting (inferred by analogy to the Unicommerce finding and to EasyEcom's own
  documented "occasional inventory sync and integration delays" user-review criticism found in this pass's
  search results — a real, if secondhand, signal); manually acting on EasyReco's flagged discrepancies
  where the claim-auto-ticketing claim (Section 2.3) turns out not to fully close the loop; manual
  vendor/PO administration beyond what the Vendor Master automates.
- **Ambiguous work suitable for AI:** deciding whether a flagged reconciliation discrepancy is worth
  disputing (same pattern as the Unicommerce finding); reviewing EasyVMS-flagged evidence before
  submitting a dispute (a judgment call about whether the captured evidence actually supports the
  merchant's case).
- **Approval/risk work:** dispute-filing decisions, same as the Unicommerce finding; no evidence of any
  blocking human-approval-gate mechanism (like Cin7's credit-hold gate) confirmed for EasyEcom
  specifically — `UNKNOWN`, not confirmed absent.
- **Cross-system integration work:** connecting EasyEcom's four native modules to third-party couriers
  (Shiprocket/NimbusPost/etc.) and to a real external accounting system (Tally/SAP/QuickBooks, Section
  2.8) — since these are genuine third-party integrations rather than owned subsidiaries, a human is
  plausibly involved in initial setup and ongoing troubleshooting of those specific seams, inferred from
  the integration-breadth evidence rather than directly observed.
- **Reporting/Excel work:** margin/profitability reporting exists natively (Section 2.8), which plausibly
  *reduces* rather than causes Excel work relative to a merchant with no reconciliation tooling at all —
  worth noting as a point where EasyEcom looks stronger than the "still need Excel" pattern found for
  Unicommerce, though this is an inference from feature existence, not job-listing evidence either way.
- **Customer support:** entirely human or a separate tool, given the confirmed absence of any native
  conversational-support product (Section 4) — the clearest, most confidently-stated item in this list.
- **Advertising/growth work:** entirely human or a separate tool, given the confirmed absence of any
  growth/advertising capability (Section 5) — equally confidently stated.

**Strategic reading:** the human-labor evidence for EasyEcom specifically is inconclusive on the
job-listing dimension (a real research gap, not a finding of "less human labor required") but the
capability-gap evidence above still points the same direction as both prior audits: a human is doing the
customer-conversation work and the growth/advertising work entirely, and is very plausibly still the
integration layer between EasyEcom's native modules and the third-party couriers/accounting systems they
connect to — a narrower version of the "human bridges the gaps between systems" pattern found for both
Linnworks (Replyco/Gorgias) and Unicommerce (Uniware/Shipway/Convertway), here applied to third-party
courier/accounting integrations specifically rather than group-owned-but-separate products.

## 7. Automation hierarchy — does EasyEcom change the differentiation? (Mandate Section 10)

- **Deterministic-first** — EasyEcom's order-routing rules, Force Split packing-station logic, and
  procurement PO-lifecycle controls are all the same deterministic-first pattern under different names,
  reconfirming (a third time) that this is industry-standard, not Sanocea-unique.
- **AI only for ambiguity** — EasyEcom shows the weakest AI-operations evidence of the three competitors:
  only generic "AI-enabled" marketing phrasing with no named, mechanism-level feature (contrast Linnworks'
  Spotlight AI and Unicommerce's Catalyst, both real and named). Against EasyEcom specifically, "AI for
  operational ambiguity" is an open field exactly as it was against Unicommerce — Sanocea is not
  pre-empted here, but still has zero real inference of its own (`DeterministicAIProvider` remains a
  non-inferencing stub).
- **Human only for genuine uncertainty/risk** — the dispute-filing decision (Section 6) and the
  evidence-review-before-submitting-a-claim judgment (Section 2.4/6) are both real human-decision points
  EasyEcom's tools surface (flag a discrepancy, capture evidence) but do not appear to fully resolve —
  consistent with the pattern already established against both prior competitors and with Cin7's
  credit-hold gate in the combined audit.
- **Net assessment:** against EasyEcom specifically, Sanocea's differentiated bet is sharper on customer
  support (EasyEcom has literally nothing, Section 4) and on the AI-operations axis (no precedent to catch
  up to, same as Unicommerce) than against Linnworks, and roughly as sharp on the canonical-cross-domain-
  system axis as against both prior competitors — but weaker on the single most novel finding of this
  pass, video/image evidence capture for disputes (Section 2.4), which Sanocea has no equivalent for and
  which neither prior audit anticipated as a capability class at all.

## 8. Capabilities Sanocea should absorb

Absorb the underlying pattern; do not copy EasyEcom's implementation, API shape, UI, or documentation
text. **This table is a proposal for review — nothing here is authorized for implementation** (per the
user's explicit instruction, consistent across all three audits so far). Each row is tagged per the
user's classification scheme: **A.** genuinely new capability, **B.** independently reconfirmed capability
(validated by ≥2 of the three competitors), **C.** better implementation/design insight for an
already-known capability, **D.** competitor complexity Sanocea should deliberately avoid. The goal is the
best generalizable pattern, not the largest possible feature list.

| # | Tag | Merchant problem | Competitor evidence | Why useful | Sanocea current state | Generic design principle | Canonical-model impact | Implementation location | Human workload eliminated | India relevance | Global relevance | Priority |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **B** | Multi-warehouse order allocation | EasyEcom's ZIP/distance-based routing + priority rules, alongside Linnworks' criteria-based routing and Unicommerce's fill-maximization | Third independent validation of the same universal problem, now with a third distinct mechanism | `ARCHITECTURAL ONLY` | Allocation logic stays generic and merchant-configurable; the *specific* algorithm (proximity vs. criteria vs. network-fill) is a policy choice, not a hardcoded assumption | Canonical domain + deterministic engine (unchanged design target from prior audits) | Canonical domain + connector | Manual "which warehouse ships this" decision | High | High | **P0** (reconfirmed a third time) |
| 2 | **A** | Win marketplace disputes/return-fraud claims with physical evidence, and preserve seller-protection-program eligibility | EasyVMS — order-ID-tagged packing/return video and image capture | A genuinely new capability class for this program; addresses the same underlying "protect margin from marketplace disputes" problem as reconciliation, via a different mechanism (visual evidence vs. financial matching) | `MISSING` — no equivalent concept anywhere in Sanocea | An exception/order record can carry evidence attachments (video/image references) with an explicit link back to a fulfilment or return event; the capture mechanism itself is a connector/physical-integration concern, kept separate from the canonical evidence-attachment concept | Canonical domain (new evidence-attachment relationship) — a genuine addition, not an extension | Canonical domain + connector (capture integration) + human exception (dispute filing) | Manual/no evidence gathering today; reduces claim-rejection risk | High (COD/RTO-heavy return-fraud exposure) | High (any marketplace with seller-protection video requirements) | **P2** — real and novel, but depends on a physical-capture integration Sanocea has no foundation for yet |
| 3 | **C** | Marketplace/payment reconciliation with automated claim-filing, not just discrepancy-flagging | EasyReco's "finds the money you lost, then files the claim" / auto-ticketing framing, compared against UniReco's more granular but flag-only-confirmed state machine | Sharpens the ambition for Sanocea's own eventual marketplace-reconciliation work: aim for auto-filing the dispute, not just flagging the discrepancy for a human to act on — a specific automation-depth target, if EasyEcom's claim holds up under real evaluation | `IMPLEMENTED+PROVEN` in shape, `MISSING` against any real marketplace feed | The reconciliation engine should distinguish "flag for human review" from "auto-file a structured claim" as two distinct, separately-buildable capability levels, with the second only attempted once the first is proven reliable | Reconciliation (canonical field, exists) + deterministic engine (claim-filing logic, new) | Reconciliation + deterministic engine + connector (marketplace claim-submission API, where one exists) | Manual dispute-filing paperwork, if the claim-filing step proves real | Very high | Moderate-high | **P1** — same priority as the underlying reconciliation item (Unicommerce Section 8, item 5), sharpened with this specific design target |
| 4 | **C** | Partial order fulfilment triggered at the packing-station level, not only at order-creation time | EasyEcom's "Force Split" — a packing-station override allowing partial processing of eligible orders | Sharper design input than the Linnworks/Unicommerce split-order findings alone — suggests split eligibility should be evaluable at multiple points in the fulfilment lifecycle, not only decided once upfront | `MISSING` | Split-order eligibility is a deterministic-policy check re-evaluable at each fulfilment-lifecycle stage (order creation, packing, dispatch), not a single upfront decision | Canonical domain (order-lineage concept, unchanged from prior audits) + deterministic engine (now re-evaluable at multiple lifecycle points) | Canonical domain + deterministic engine | Manual order-desk triage for partial-stock scenarios discovered late (at packing time, not just order time) | High | High | **P2/P3** (unchanged priority, sharpened design) |
| 5 | **D** | — | EasyEcom's sales-led, fully non-public pricing model (Section 2.9) | A **negative** reference: opaque, quotation-only pricing with no public tier/feature disclosure is easier for a competitor to hide behind, but it is also a real source of merchant friction (a merchant cannot self-evaluate fit without a sales call) | N/A | Sanocea should keep pricing transparent and self-serve wherever possible, per the mandate's broader simplicity principle ("sell simply") — opacity is not a pattern to imitate even where a competitor uses it | N/A | N/A | N/A | High (India-first buyers value transparent, low-friction pricing) | High | **DO NOT ABSORB** — explicitly flagged as complexity/opacity to avoid, not a capability to build |
| 6 | **D** | — | EasyEcom's reliance on third-party courier aggregators without an owned logistics layer (contrast Unicommerce's owned Shipway) | A cautionary structural reference: this is the *weaker* of the two group-structure patterns found in this program for logistics specifically — Unicommerce's owned NDR/RTO depth (via Shipway) is confirmed deeper than anything found for EasyEcom's third-party-courier-only approach | N/A | Sanocea's canonical model should treat courier-specific NDR/RTO event shapes as a connector concern regardless of whether the courier relationship is owned or third-party — the *lesson* is to resolve courier-specific detail to a generic canonical NDR state either way, not to prefer owning vs. integrating couriers as a strategic choice this research program can settle | N/A | Connector | N/A | High | Moderate | Not a build item — a structural observation feeding the NDR/RTO item already prioritized P1 against Unicommerce |

## 9. Three-competitor convergence signals

Comparing only Linnworks, Unicommerce, and EasyEcom — not re-researching any of the three, only
synthesizing what their three completed audits already found.

| Capability | Convergence | Evidence |
|---|---|---|
| Multi-location/warehouse order allocation | **3/3 VALIDATED** | Linnworks (MLI + criteria-based Rules Engine), Unicommerce (Smart Fill network-wide fill-maximization + proximity allocation), EasyEcom (ZIP/distance routing + priority rules) — three independently-built platforms, three different mechanisms, same universal problem. The single strongest convergence signal in this program. |
| ATS/oversell prevention | **2/3 VALIDATED** | Confirmed real, distinct mechanisms at Linnworks (bin-type exclusion rules) and Unicommerce (Kafka-delta + snapshot reconciliation); not independently researched for EasyEcom this pass — `UNKNOWN` for EasyEcom specifically, not a non-finding. |
| Bundles/kits/BOM as more-than-one-construct | **2/3 VALIDATED, EasyEcom UNKNOWN** | Linnworks' composite-item constraint and Unicommerce's explicit three-way Bundle/Kit/BOM distinction both independently point at the same underlying complexity; EasyEcom's specific mechanics were not reached this pass (Section 2.6) — genuinely unresolved, not absent. |
| Split/merge orders | **2/3 VALIDATED (split); merge 1/3 ONLY** | Split confirmed with real, distinct mechanics at Linnworks, Unicommerce (item-level cancellation, Force Split), and EasyEcom (Force Split specifically) — arguably now closer to 3/3 for *split* specifically, though EasyEcom's evidence is packing-station-scoped rather than full order-splitting depth. Merge was only confirmed with real mechanics at Linnworks (narrow eligibility-rule list) — Unicommerce and EasyEcom show no equivalent evidence. Recorded conservatively as split near-3/3, merge 1/3 ONLY. |
| Marketplace connector breadth (Amazon/Flipkart/Myntra/Meesho, quick-commerce) | **2/3 VALIDATED, INDIA-SPECIFIC** | Deep, named evidence at Unicommerce and EasyEcom (both confirm Blinkit/Zepto quick-commerce integration specifically); Linnworks' marketplace breadth is real but not researched at this India-specific granularity (its market is UK/global-first) — tagged `INDIA-SPECIFIC` because the granularity itself, not just the existence of connectors, is what's validated. |
| COD reconciliation | **1/3 ONLY, INDIA-SPECIFIC** | Deep, named evidence only at Unicommerce (UniReco's COD-remittance state machine); EasyEcom's reconciliation evidence (Section 2.3) does not confirm a COD-specific mechanism with comparable granularity, and Linnworks' market makes this largely inapplicable. |
| Marketplace commission/fee reconciliation | **2/3 VALIDATED, INDIA-SPECIFIC (with a real mechanics difference)** | Confirmed at both Unicommerce (UniReco, more granular public evidence) and EasyEcom (EasyReco, broader-scoped framing, less granular public evidence, a possibly-more-automated claim-filing step) — Section 2.3's direct comparison is the relevant detail; Linnworks shows no equivalent. |
| NDR/RTO | **1/3 ONLY (deep), 1/3 THIN, INDIA-SPECIFIC** | Deep, named, dedicated-workflow evidence only at Unicommerce (via Shipway); EasyEcom confirms RTO *tracking* but not a dedicated NDR decision workflow with comparable depth (Section 3); Linnworks shows no equivalent at all (`UNK`). |
| Courier selection | **2/3 VALIDATED, mechanism differs** | Confirmed real at Unicommerce (owned Shipway subsidiary) and EasyEcom (third-party aggregator integration + native selection-rule claim); Linnworks confirmed real but with less mechanism detail (`C` in the combined audit's matrix, not independently deep-dived at this level). The *ownership* structure differs materially (Section 8, item 6) even though the capability itself converges. |
| Procurement/vendor operations | **3/3 VALIDATED** | Real, evidenced PO-lifecycle/vendor-management capability at Linnworks, Unicommerce, and EasyEcom, with genuinely convergent lifecycle-stage shapes (create → approve → send → receive/GRN) across all three — and already a confirmed Sanocea strength (`IMPLEMENTED+PROVEN`), so this convergence validates Sanocea's existing design rather than exposing a gap. |
| Customer support/conversational operations | **0/3 fully native — but divergent depth**: Linnworks 100% third-party (Replyco/Gorgias); Unicommerce has a real group-owned WhatsApp chatbot (Convertway) but unconfirmed canonical connection; EasyEcom has nothing confirmed at all | This is a genuine *divergence* signal, not a convergence one — worth stating plainly rather than forcing into the convergence framing: no platform in this program has a confirmed, canonically-connected, native conversational-support capability. Sanocea's own Chatwoot-based, Phase-4.6-proven capability is the strongest evidenced position on this specific axis across all four systems compared (three competitors + Sanocea). |
| WhatsApp specifically | **1/3 ONLY, INDIA-SPECIFIC** | Confirmed only at Unicommerce (Convertway); not found for Linnworks (expected — different market) or EasyEcom (a genuine gap, not a market-mismatch explanation, since EasyEcom is also India-first). |
| RBAC | **0/3 confirmed granular-and-ungated** — Linnworks gates behind a paid plan tier, Unicommerce gates role-count by facility/SKU tier, EasyEcom shows no evidence at all | Best read as **2/3 VALIDATED (as a gated pattern)**, with EasyEcom `UNKNOWN`. The convergence signal here is about competitors' *pricing behavior* around RBAC, not the capability itself — both confirmed instances gate it, reinforcing Sanocea's differentiation opportunity (Linnworks-audit Section 2.10, Unicommerce-audit Section 2.12) regardless of EasyEcom's unconfirmed status. |
| Demand forecasting | **3/3 VALIDATED** | Confirmed real at all three, though with different sophistication levels (Linnworks: sales history + seasonal trends; Unicommerce: not independently deep-dived at forecasting-mechanism level this program; EasyEcom: velocity-based 7-60-day movement window, no seasonal claim found) — Sanocea's existing partial velocity-lookback implementation is validated as the right *shape*, with seasonality (Linnworks' specific contribution) as the clearest remaining enhancement. |
| Warehouse-floor execution (pick/pack/QC) | **3/3 VALIDATED, ENTERPRISE/WMS-SPECIFIC** | Real, deep evidence at all three (Linnworks' wave/zone/batch/TOTE; Unicommerce's pigeonhole/FIFO/FEFO; EasyEcom's scan-based no-proprietary-hardware approach) — but tagged `ENTERPRISE/WMS-SPECIFIC` per the mandate's own segment-relevance question (Section 2.6 of the Linnworks audit, reconfirmed at 2.2 here): relevant only to merchants running their own warehouse floor, and explicitly a feature-bloat trap for Sanocea's likely SMB/DTC-with-3PL target segment. Convergence confirms the capability is real and universal *among mature platforms*, not that it's a near-term Sanocea priority. |
| AI operational decision-making | **1/3 ONLY (real+named), 1/3 REAL BUT MARKETING-SUBSIDIARY-SCOPED, 1/3 NOT FOUND** | Linnworks' Spotlight AI is real, named, operations-scoped, with a quantified outcome; Unicommerce's Catalyst is real and named but scoped to the marketing subsidiary (Convertway), not operations; EasyEcom shows no named feature at all, only generic "AI-enabled" marketing language. No platform in this program has a confirmed, named, *operational*-decision-making AI feature outside Linnworks specifically. |

## 10. Priority changes after three competitors

Explicitly for review, not for implementation — this section compares all three completed audits per the
user's instruction and changes nothing in any of the three files.

- **Multi-location allocation (P0): INCREASE confidence, priority itself STAYS at P0.** Already the
  correct top priority after two competitors; a third, differently-mechanized confirmation (Section 9)
  makes this the single most over-determined finding in the program. There is no higher priority to move
  it to — P0 already means "architectural blocker" — but the *confidence* behind the call is now
  substantially stronger than after either single prior audit.
- **Indian-marketplace connector work (P1): STAYS at P1**, with EasyEcom's independent confirmation of
  quick-commerce (Blinkit/Zepto) integration depth (Section 9) reinforcing rather than changing the
  Unicommerce-audit finding that this is a firm, evidence-backed P1, not merely plausible.
- **Marketplace/COD/commission reconciliation (P1): STAYS at P1**, with a sharpened design target added
  by EasyEcom's claim-auto-filing framing (Section 8, item 3) — worth building toward "auto-file, not just
  flag" as the ambition, once the underlying reconciliation connector work is real.
- **NDR/RTO as an explicit workflow (P1 against Unicommerce): STAYS at P1 overall, but EasyEcom's thinner
  evidence here (Section 3, Section 9) means the priority rests specifically on Unicommerce's finding, not
  on independent triple-confirmation.** This is a case for honest confidence-labeling, not a priority
  change — the underlying merchant problem (RTO cost in a high-COD market) doesn't depend on how many
  competitors happen to have public documentation about their solution to it.
- **Bundles/kits/BOM (P2): STAYS at P2.** EasyEcom neither confirms nor weakens this — the priority
  already rested on two independent confirmations (Section 9); a third platform's unresolved status
  doesn't change that.
- **WhatsApp as a support/notification channel (new P1 after Unicommerce): DECREASE in cross-competitor
  confidence, but priority itself STAYS at P1 for India-first reasons independent of competitor
  validation.** EasyEcom's failure to confirm any WhatsApp product (Section 9) means this is now a 1/3
  finding, not a pattern two competitors independently reached — but WhatsApp's dominance in Indian
  ecommerce communication is a market fact Sanocea should act on regardless of how many competitors have
  built it, so the priority itself should not drop; only the "competitors validate this" framing should be
  used more carefully going forward (cite Unicommerce specifically, not "competitors generally").
- **A real `AIProvider` implementation (P1 against Linnworks): STAYS at P1 overall, urgency argument now
  weaker on competitive-parity grounds for a third consecutive competitor.** Neither Unicommerce nor
  EasyEcom shows a named, operational (not marketing-subsidiary-scoped) AI feature to catch up to — only
  Linnworks does. The underlying architectural gap (zero real AI inference anywhere in Sanocea) is
  unchanged and the priority should not be lowered on that basis, but the "we're falling behind
  competitors" argument for it should now be scoped explicitly to Linnworks, not stated as an
  industry-wide pressure.
- **RBAC granularity (P1 against both prior competitors): STAYS at P1**, and the "Sanocea doesn't gate
  this behind price tier" positioning claim (Linnworks Section 2.10, Unicommerce Section 2.12) is now
  supported by two confirmed instances of competitor gating, with EasyEcom's unconfirmed status neither
  strengthening nor weakening it.
- **NEW this pass, not previously identified: video/image evidence-capture for marketplace disputes
  (Section 8, item 2).** This is a genuinely new capability class no prior audit anticipated. It enters
  the priority list at **P2** — real, novel, evidenced, but dependent on a physical-capture integration
  Sanocea has no foundation for, unlike most other P1/P0 items which extend existing canonical patterns.
- **Full warehouse-floor execution (DO NOT BUILD now / P3 later): STAYS unchanged, confidence
  INCREASES.** A third mature platform (EasyEcom) treating this as real, deep, production capability
  (Section 9) — combined with EasyEcom's own lower-hardware-barrier framing, which if anything makes WMS
  *easier* to adopt without changing whether Sanocea's SMB/DTC-with-3PL target segment actually needs it —
  reinforces rather than weakens the existing feature-bloat-trap judgment.

## 11. Summary and stop condition

This pass's most significant new finding is **EasyVMS** (Section 2.4) — a genuinely novel capability class
(video/image evidence capture for marketplace disputes) that neither the Linnworks nor Unicommerce audits
anticipated, addressing the same underlying "protect margin from marketplace disputes" problem
reconciliation tools address, through a different mechanism. The second most significant finding is the
**corporate-structure contrast**: EasyEcom is the first platform in this program confirmed to have made
no acquisitions, meaning its four capability areas are a single company's native build — a real-world
existence proof that "multiple deep capability areas, one company, one product suite" is achievable,
though EasyEcom's own public evidence does not show these four areas share one *canonical data model* any
more than Unicommerce's three products do.

Multi-location order allocation remains the correctly-identified P0, now independently validated a third
time by a third distinct mechanism — the strongest convergence signal across all three completed audits.

**Per the mandate and the user's explicit instruction: none of Section 8's proposals is implemented by
this audit. This report is now complete. Do not automatically begin Vinculum, Pipe17, Brightpearl, Cin7,
Sellercloud, or any other competitor — per the user's stated plan, a deliberate three-competitor synthesis
happens next, before competitor #4 is authorized.**
