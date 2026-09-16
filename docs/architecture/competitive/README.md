# Sanocea Competitive Research Mandate

This document governs every competitive-capability audit under `docs/architecture/competitive/`. It
supersedes any prior framing in `docs/architecture/sanocea-competitive-capability-audit.md` (kept as
Pass 1-3 historical record — see "Relationship to the prior combined audit" below). Any future audit
session should read this file first, find its place in the execution log (Section 11), and continue from
there — not restart, not skip ahead.

**Revision history:** v1 established 2026-09-11, replacing an unstated prior framing with an explicit
India-first-commercially / global-in-research mandate after a strategic-direction correction.

---

## 1. Commercial principle

**Price determines capacity, not capability.**

Concept-only pricing shape (not final): SKU-capacity tiers (e.g. up to 50 active SKUs ≈ ₹599/month,
progressively higher capacities at progressively higher prices). A ₹599/month merchant receives the
**same** Commerce OS capability set as a ₹9,999/month merchant — only the SKU/order capacity differs.

Do **not** architect artificial capability tiers: no "Starter reconciliation," "Advanced automation,"
"Pro AI," "Enterprise returns," etc. If Sanocea knows how to automate an ecommerce operation safely, that
capability is normally available to every merchant regardless of plan.

Internally, keep measuring orders, workflows, AI calls, messages, infra cost, storage, etc. for unit
economics and abuse protection — that instrumentation is not customer-facing and does not create tiers.
Pass-through third-party costs (courier, payment gateway, SMS/WhatsApp) may remain separate line items
where genuinely unavoidable.

**Advertising/Growth Operations is explicitly outside this principle.** It may become a separately
priced service later because it involves actively managing merchant ad spend — a different risk/cost
shape from operational automation. Do not fold it into the SKU-capacity price during this research phase.

## 2. Go-to-market vs. product architecture

| Axis | Scope |
|---|---|
| Go-to-market | India first |
| Architecture | Global, merchant-independent |
| Research | Global — never restrict to Indian competitors |

Do not introduce India-specific assumptions into canonical domain logic. India-specific behavior
(COD, GST, Flipkart, Myntra, Meesho, Amazon India, Indian payment gateways, Indian couriers, WhatsApp,
etc.) belongs in connectors, configuration, policy, jurisdiction modules, marketplace adapters, logistics
adapters, and payment adapters — never in the canonical model itself.

Every capability recommendation produced by this research program must be judged for **generic
applicability**, then prioritized for India. A capability that is India-only in its justification is a
connector/policy concern, not a canonical-model concern.

## 3. Global competitor research universe

Research **one competitor at a time**. Do not parallelize across competitors within a single audit pass.

**Global:** Linnworks, Pipe17, Brightpearl, Cin7, Sellercloud, ChannelEngine, Extensiv, Veeqo, Rithum

**India/APAC:** Unicommerce, EasyEcom, Vinculum, Increff, eVanik, Browntape, Anchanto

**Architectural/enterprise reference (when useful, not routine deep-dive targets):** Fluent Commerce,
Kibo, Manhattan Active, Blue Yonder, IBM Sterling, Adobe Commerce/Magento

Do not automatically deep-audit every platform on this list. Within an audit, follow the evidence: if a
platform turns out to have an unusually mature solution to a specific problem (order allocation,
COD/RTO/marketplace exceptions, procurement/replenishment, connector abstraction, reconciliation
evidence, etc.), pursue that thread even if it means citing a platform outside the one currently under
audit. The goal is best-of-category patterns, not a leaderboard of which platform "wins."

## 4. Required question set for every meaningful capability

For each capability worth recording, answer:

- **A.** What merchant problem does this solve?
- **B.** Why does this capability exist — what operational failure/expense/manual-work pattern
  presumably forced mature platforms to build it?
- **C.** Is this relevant to tiny merchants / growing SMEs / high-volume merchants / enterprise only?
- **D.** How frequently would an Indian ecommerce merchant encounter it?
- **E.** Does Sanocea already support it? Classify: `IMPLEMENTED+PROVEN` ·
  `IMPLEMENTED BUT NOT REAL-PLATFORM PROVEN` · `PARTIAL` · `ARCHITECTURAL ONLY` · `MISSING`.
- **F.** If missing, can the current canonical model support it cleanly?
- **G.** Where should it live? canonical domain / deterministic engine / policy / merchant configuration
  / connector / reconciliation / AI interpretation / human exception / other.
- **H.** Would implementing it push merchant-specific or platform-specific logic into the core? If yes,
  challenge the design before accepting it.
- **I.** Does it actually reduce human ecommerce work?
- **J.** Priority: `P0` architectural blocker · `P1` important for initial India product · `P2`
  commercially important as merchants grow · `P3` useful later · `DO NOT BUILD` unnecessary complexity /
  enterprise bloat.

## 5. Absorb, don't clone

Every audit must contain a **"Capabilities Sanocea Should Absorb"** section. For each absorbed pattern,
record: merchant problem, competitor evidence (cited), why their approach is useful, Sanocea's current
state, a **generic** Sanocea design principle (not a copy of the competitor's implementation), canonical-
model impact, implementation location, human workload eliminated, India relevance, global relevance,
priority.

Recommendations are proposals, not commits — nothing in an audit is implemented automatically; the team
reviews before building. Never reproduce a competitor's proprietary code, schemas, or documentation text
verbatim. Cite the existence and shape of a capability, then design Sanocea's own independent solution to
the underlying merchant problem.

## 6. Weight the boring capabilities

Do not bias toward AI or visibly impressive features — mature platforms usually win on boring edge cases.
Explicitly check for: order allocation, split/partial/merged orders, backorders, preorders, bundles/
kits/composites, multi-location inventory, reservations, available-to-sell, oversell prevention,
warehouse routing, pick/pack/dispatch, barcode ops, batch/lot/serial tracking, expiry, 3PL, FBA,
dropshipping, carrier selection, shipping labels, tracking, NDR, RTO, COD, returns, exchanges, partial
refunds, payment lifecycle, settlements, marketplace fees, claims/disputes, reconciliation, supplier
procurement, POs, partial supplier acknowledgement, inbound inventory, goods receipt, replenishment,
forecasting, marketplace listing errors, channel-specific catalogue requirements, bulk operations, rate
limits, eventual consistency, duplicate events, retries, recovery, operational exceptions, high-volume
behavior.

A boring capability that removes two hours/day of human work outranks an impressive AI feature nobody
needs.

## 7. Customer support: audit "operate," not "provide"

Distinguish "the competitor supports its merchants" from "the competitor can operate the merchant's
customer support." For each channel (email, live chat, WhatsApp, Instagram/social, order-status
enquiries, shipment enquiries, address changes, cancellations, returns, exchanges, refund requests,
complaints, NDR interaction, proactive notifications, customer self-service, human handoff), determine
whether the platform reports, suggests, responds, executes, or autonomously resolves.

Sanocea's target flow remains: customer message → intent → canonical operational truth → deterministic
policy → execute/answer when safe → AI if ambiguity exists → human only when genuine uncertainty/risk
remains. Judge every competitor support capability against this flow, not against a generic "has a help
desk" bar.

## 8. Growth/marketing: observe only, do not build

Do NOT build growth/marketing capability during this research phase. Record what's observed for: Amazon
PPC, Flipkart Ads, Myntra advertising, Meta/Instagram/Google Ads, Google Shopping, Performance Max,
marketplace promotions, SEO, listing optimization, A+ content, pricing, promotions, email/SMS/WhatsApp
campaigns, abandoned cart, retention, reviews, CAC, ROAS, attribution.

Classify each as: `NATIVE EXECUTION` · `AUTOMATED EXECUTION` · `INTEGRATION ONLY` · `REPORTING ONLY` ·
`NOT FOUND` · `UNKNOWN`. Pay particular attention to whether any competitor closes the loop from
advertising spend → orders → product margin → payment fees → logistics → COD/RTO → returns →
marketplace fees → actual contribution margin — that end-to-end closure is the interesting signal, not
ad-platform integration breadth by itself.

Advertising/Growth may later become a separately priced Sanocea service (Section 1). Never mix its
implementation into Commerce OS core-scope decisions during these audits.

## 9. The real competitor is also human labour

Do not evaluate Sanocea only against SaaS platforms. Sanocea's core commercial hypothesis is that
merchants keep paying human ecommerce executives even after buying an OMS/WMS/marketplace tool. Every
audit must answer: **after buying this competitor, what work does the merchant still pay a human to do?**
(listing corrections, marketplace exceptions, pricing updates, inventory investigation, order exceptions,
shipment issues, NDR/RTO, returns, refunds, reconciliation, support tickets, customer messages, reports,
Excel work, supplier coordination, advertising operations.)

The strategic implication: Sanocea's win condition is not necessarily "replace Unicommerce." It may be
"operate Unicommerce + Shopify + Amazon + Flipkart + logistics + payments + support on the merchant's
behalf." Existing OMS/ERP platforms may eventually become Sanocea connectors rather than pure
competitors.

## 10. Sanocea's automation hierarchy is non-negotiable

```
DETERMINISTIC CODE
      ↓
AI IF AMBIGUITY REMAINS
      ↓
HUMAN IF GENUINE UNCERTAINTY/RISK REMAINS
```

Do not compromise this hierarchy merely because a competitor markets "agentic" everything. AI must not
become the default execution engine because agentic commerce is fashionable. Repeated AI/human patterns
are candidates for promotion to deterministic automation, not permanent AI dependence. Every audit should
explicitly re-test whether this hierarchy remains genuinely differentiated after that competitor's
research — and say plainly if the competitor already does the equivalent thing under different
terminology.

## 11. Execution log — one competitor at a time

Status as of 2026-09-11:

| Competitor | Status | Audit file |
|---|---|---|
| Linnworks | **Complete** — reviewed and accepted as evidence; recommendations not yet implemented | [`linnworks-vs-sanocea.md`](./linnworks-vs-sanocea.md) |
| Unicommerce | **Complete** — reviewed and accepted as evidence; recommendations not yet implemented | [`unicommerce-vs-sanocea.md`](./unicommerce-vs-sanocea.md) |
| EasyEcom | **Complete** — reviewed and accepted as part of the first three-competitor synthesis (Linnworks + Unicommerce + EasyEcom); recommendations not yet implemented | [`easyecom-vs-sanocea.md`](./easyecom-vs-sanocea.md) |
| Pipe17 | **Complete** — reviewed and accepted as part of the four-competitor synthesis baseline; recommendations not yet implemented | [`pipe17-vs-sanocea.md`](./pipe17-vs-sanocea.md) |
| Gorgias AI Agent | **Complete** — reviewed and accepted; competitor #5, authorized specifically to stress-test differentiators E/F and AI Roadmap Stage 7; its Section 19 proposed changes were reviewed and selectively applied to the baseline (see amendment note below); recommendations beyond that not implemented | [`gorgias-ai-vs-sanocea.md`](./gorgias-ai-vs-sanocea.md) |
| Brightpearl | Not started under this mandate (prior findings exist in the combined audit — see below) | — |
| Cin7 | Not started under this mandate (prior findings exist in the combined audit — see below) | — |
| Rithum | **Complete** — reviewed and accepted; competitor #6, authorized specifically to resolve Open Research Question #2 (the economic closed-loop question) and to run differentiator F through its broadest-capability-surface test yet; its Section 19 proposed changes were reviewed and selectively applied to the baseline (see amendment note below); recommendations beyond that not implemented | [`rithum-vs-sanocea.md`](./rithum-vs-sanocea.md) |
| Sellercloud, ChannelEngine, Extensiv, Veeqo, Vinculum, Increff, eVanik, Browntape, Anchanto, Siena, Yuma, Decagon, Intercom, Zendesk, Ada | Not started — competitor #7 not yet named; per research discipline, the next target must answer a remaining OPEN question from the amended baseline (Section 14 there), not be chosen merely because it exists | — |

**Rule:** do not begin the next competitor until the team has reviewed the current one's "Capabilities
Sanocea Should Absorb" section and named the next target explicitly. Finishing Linnworks does not
authorize starting Brightpearl automatically.

**Synthesis checkpoint (2026-09-11):** after Linnworks + Unicommerce + EasyEcom + Pipe17, a deliberate
consolidation was produced at
[`SANOCEA-PRODUCT-BASELINE-V1.md`](./SANOCEA-PRODUCT-BASELINE-V1.md) — the authoritative roadmap-priority
reference until later research changes it. It named Gorgias AI Agent as the recommended competitor #5,
specifically to stress-test Sanocea's support→operational-mutation differentiator.

**Baseline V1 — amended after Gorgias (2026-09-11):** the Gorgias audit's Section 19 proposed changes
were reviewed and selectively applied to the baseline's Section 5 (differentiators E and F), Section 6
(the human-labour thesis), and Section 8 (AI Roadmap Stage 7 — a narrow, moderate-confidence precedent
now recorded; general DO-NOT-BUILD retained). The document remains `SANOCEA-PRODUCT-BASELINE-V1.md` — an
amendment, not a version bump.

**Baseline V1 — amended after Rithum (2026-09-11):** Rithum's Section 19 proposed changes were reviewed
and selectively applied to the baseline's Section 5 (differentiator F strengthened and re-termed
"cross-domain canonical operating truth"; a new plausible-future-differentiator item added to Section
5.B for the economic closed loop; a new product-doctrine subsection 5.D — "CALCULATION ≠ DECISION ≠
EXECUTION"), Section 10 (do-not-build design guidance sharpened for advertising and for the
dropship/supplier-network distinction), Section 13 (a new P2 item: per-order/per-SKU profitability
read model), and Section 14 (**Open Research Question #2 — the economic closed-loop question — is now
CLOSED FOR THE CURRENT RESEARCH PROGRAM, reopen only on new positive evidence**). The document remains
`SANOCEA-PRODUCT-BASELINE-V1.md` — an amendment, not a version bump. Competitor #7 has not been named;
per research discipline (Section 14 of the baseline), the next target must be chosen to answer a
remaining open question, not merely because it is next on a list. Do not begin one until the team
reviews this amendment and names the next target explicitly.

## 12. BigCommerce (unrelated to competitor research)

BigCommerce Partner application has been submitted; certification is externally blocked pending approval.
Do not poll. Do not make speculative BigCommerce/core changes. When sandbox access arrives, resume the
prepared real-platform certification (`docs/architecture/bigcommerce-sandbox-certification-preparation.md`)
separately from this research track.

## 13. Relationship to the prior combined audit

`docs/architecture/sanocea-competitive-capability-audit.md` (Pass 1-3) researched 9 platforms
simultaneously in one document and is kept as-is — a real, cited, three-pass-corrected artifact with its
own disclosed evidentiary limits. It predates this mandate's per-competitor, absorb-don't-clone,
human-labor-lens, and support/growth-audit structure.

Going forward:

- New research follows this mandate, one file per competitor under `docs/architecture/competitive/`.
- Existing Pass-3 citations for a given platform (e.g. Linnworks' Composite Items, Rules Engine,
  Spotlight AI, MLI API) are treated as already-verified evidence and may be reused/re-cited rather than
  re-researched from zero — re-verify only if a claim looks stale or a fresh search surfaces something
  that contradicts it.
- Do not delete or rewrite the combined audit; it remains the historical record of Passes 1-3.

## 14. Final principle

India first does not mean India-only thinking.

**Learn globally. Build generically. Prioritize for India. Sell simply.**

Commercially: **one Sanocea, every commerce-operations capability, priced by active-SKU capacity.**
Advertising/Growth may later be a separate paid service.
