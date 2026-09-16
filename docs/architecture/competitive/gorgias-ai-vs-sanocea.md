# Gorgias AI Agent vs. Sanocea — Competitive Capability Audit

Governed by [`../competitive/README.md`](./README.md) (the Sanocea Competitive Research Mandate).
Competitor #5, following [`linnworks-vs-sanocea.md`](./linnworks-vs-sanocea.md),
[`unicommerce-vs-sanocea.md`](./unicommerce-vs-sanocea.md), [`easyecom-vs-sanocea.md`](./easyecom-vs-sanocea.md),
and [`pipe17-vs-sanocea.md`](./pipe17-vs-sanocea.md). Authorized specifically to stress-test
[`SANOCEA-PRODUCT-BASELINE-V1.md`](./SANOCEA-PRODUCT-BASELINE-V1.md)'s Section 5 differentiators E and F
and Section 8's AI Roadmap Stage 7 — this file does not edit that document; Section 19 below proposes
changes for separate review.

## 0. Why this audit is different, and how it was run

The first four competitors were commerce-operations systems for which customer support was either
absent or peripheral. Gorgias is the opposite: its entire product thesis is customer-conversation
automation, and its 2026 AI Agent publicly claims to execute real Shopify order mutations
(cancellation, refund, address change, subscription actions) directly from a shopper conversation. This
is the single sharpest test available of Sanocea's differentiator E (support conversation → canonical
truth → policy/approval → operational execution) and a direct challenge to the baseline's Stage-7
conclusion (zero competitor precedent for policy-bounded autonomous AI mutation without per-instance
human confirmation). This audit is deliberately adversarial: every claim below is checked against real
mechanism evidence, not accepted from marketing copy, and where the evidence destroys or qualifies a
Sanocea claim, this file says so plainly.

**Evidence basis:** direct fetches of Gorgias's own primary documentation
(`docs.gorgias.com`/`helpcenter.gorgias.com`) for the central-flow, Actions-catalogue, guardrails, and
security/privacy pages, supplemented by search-snippet synthesis from independent 2026 third-party
guides (eesel AI, getmacha, myaskai, stormy.ai, usefini/Fini Labs) where primary-source fetches did not
cover a specific claim. **Per this program's evidentiary discipline, claims sourced only from
secondary/aggregator content are explicitly flagged as such below and held to lower confidence than
claims fetched directly from Gorgias's own docs.** Ground truth for the Sanocea side of every comparison
comes from reading the actual Sanocea source (`packages/domain_contract/models.py` — `Refund`,
`Approval`, `ExceptionRecord`, `ConnectorCommand`), not from memory of prior audits' claims about
Sanocea.

## 1. Product boundary first

Gorgias in 2026 is not one undifferentiated product. Confirmed, distinct components:

| Component | What it is | Classification |
|---|---|---|
| **Helpdesk** | The base ticketing/CRM layer — inbox, customer sidebar, multi-channel inbox (email, chat, SMS, Instagram, Facebook Messenger, WhatsApp, Telegram, TikTok) | NATIVE GORGIAS |
| **Automate (legacy rules)** | A separate, older deterministic "Rules" engine: `WHEN/IF/THEN` logic, matches exact keywords not intent, used for tagging/routing/canned replies/spam-closing. Confirmed being phased out: accounts created before September 2024 can keep dedicated Autoresponder Rules only until **January 30, 2026**, after which the feature stops working ([eesel AI — Gorgias rules](https://www.eesel.ai/blog/gorgias-rules)). Runs *before* AI Agent in execution order — rules tag/assign/auto-reply first, then AI Agent picks up. | NATIVE GORGIAS (legacy, being sunset) |
| **AI Agent** | The current top-tier automation product. Composed of **Skills** (WHEN/IF/THEN-style instructions tied to an intent, e.g. "Return/Request"), **Actions** (steps that mutate a connected app — Shopify/Loop/Recharge/etc. — sequential, top-to-bottom, only fire when a Skill calls them), **Guidance** (up to 100 plain-language policy instructions, the highest-priority layer, overrides other sources on conflict), and **Knowledge** (Help Center articles, website content, uploaded docs, Shopify data) ([docs.gorgias.com — AI Agent explained](https://docs.gorgias.com/en-US/ai-agent-explained-497772); [docs.gorgias.com — How Gorgias's AI Agent works](https://docs.gorgias.com/en-US/how-gorgiass-ai-agent-works-1997817); [gorgias.com/blog/ai-agent-guardrails](https://www.gorgias.com/blog/ai-agent-guardrails)). | GORGIAS AI AGENT |
| **Support Agent** | AI Agent's post-purchase mode — order tracking, cancellations, returns, missing items. | GORGIAS AI AGENT (a mode, not a separate product) |
| **Shopping Assistant** | AI Agent's pre-purchase mode — product Q&A, sizing help, recommendations, discount-code issuance at high-intent moments, spanning chat/email/SMS ([gorgias.com/ai-agent/shopping-assistant](https://www.gorgias.com/ai-agent/shopping-assistant)). | GORGIAS AI AGENT (a mode, not a separate product) |
| **Gaia** | A confirmed, separate "coaching agent" that audits AI Agent's own setup, flags duplicated/missing knowledge, and drafts corrections for a human to approve — a meta-agent auditing the agent, not the customer-facing agent itself. | NATIVE GORGIAS (distinct sub-product) |
| **Actions on third-party apps** | Loop Returns (return-portal deep links, return-shipping-status lookups; requires an active Loop account + API key + Order/Return scopes — [docs.gorgias.com — Send Loop Returns portal deep link](https://docs.gorgias.com/en-US/ai-agent-action-send-loop-returns-portal-deep-link-757795)), Recharge (pause/cancel/update subscriptions, create discount codes), Skio, Loop Subscriptions, ShipStation/ShipBob/ShipHero/ShipMonk (3PL/shipping management), Stay AI, Wonderment. | THIRD-PARTY INTEGRATION (each requires its own separate account/API key with Gorgias) |
| **Shopify order mutations** | Cancel Order, Edit Shipping Address, Remove Item, Replace Item, Reship for Free, Add Order Note. | SHOPIFY-NATIVE ACTION VIA GORGIAS (Gorgias calls Shopify's own admin API; the mutation itself executes inside Shopify) |
| **Gorgias MCP server** | Referenced in search results as connecting external AI assistants to tickets/customers/conversations. Mechanism depth (read vs. mutate, confirmation gating) **not independently verified this pass** — flagged `UNKNOWN`, not assumed equivalent to Pipe17's MCP surface. | UNKNOWN |
| **Reconciliation/financial-ledger capability** | A search result described Gorgias "shortening its close by seven days by automating cash and flux workflows" — **this is Gorgias-the-company's own internal accounting process** (likely using a third-party finance-automation tool for its own books), **not a merchant-facing product capability**. Explicitly called out here to avoid the exact misattribution the mandate warns against — this is not evidence Gorgias AI Agent reconciles merchant payments. | NOT A GORGIAS PRODUCT CAPABILITY — do not cite this as merchant-facing evidence |
| **Procurement/supplier/replenishment** | Searched specifically; no Gorgias-specific evidence found at all — only generic industry content returned. | NOT FOUND |

**Key correction to any assumption that "Gorgias automation" is one thing:** the legacy Rules engine and
AI Agent are confirmed as two separate systems that both currently exist, run in a defined order (rules
first, AI Agent second), and are on different lifecycles (rules being sunset for older accounts; AI Agent
being actively expanded). Do not describe "Gorgias's automation" as a single system in any future
Sanocea-facing material.

## 2. The central flow

Mapped mechanistically from Gorgias's own documentation, per action, with every unconfirmed step marked
`UNKNOWN` rather than inferred.

### 2.1 General mechanism (applies to all actions)

1. **Intent identification:** "agentic logic" — the AI Agent "interprets your knowledge and instructions
   to make ongoing decisions about how to fully satisfy the intent behind the customer's request"
   ([docs.gorgias.com — How Gorgias's AI Agent works](https://docs.gorgias.com/en-US/how-gorgiass-ai-agent-works-1997817)).
   This is LLM-based intent classification, matched against a **Skill** — confirmed **LLM-decided**, not
   a deterministic keyword match (that's what the legacy Rules engine does instead, per Section 1).
2. **Merchant instructions/policy consulted:** Guidance (plain-language rules, up to 100 instructions,
   highest priority), Skills (the specific WHEN/IF/THEN instruction set for the matched intent), Knowledge
   (Help Center, website, docs, Shopify data).
3. **Live order state read:** confirmed via Shopify's own live data (order status, fulfillment status,
   customer profile, product catalog) — "AI Agent draws on... Shopify data" — read live, not from a
   separate stored copy (Section 5 below).
4. **Eligibility checks:** a mix of LLM-based screening (malicious-intent/spam/excluded-topic checks,
   confirmed LLM-evaluated: "AI Agent performs a check") **and** deterministic Shopify-state checks
   specific to each Action (e.g., "order must be unfulfilled" for Cancel Order — a hard boolean, not an
   LLM judgment call).
5. **LLM vs. deterministic decision for eligibility:** **both**, at different layers — intent
   classification and topic/malicious-content screening are LLM-decided; the specific Action's
   go/no-go precondition (e.g., fulfilment status) is a deterministic Shopify-state check.
6. **Action selected:** the Skill calls a specific Action; Actions run sequentially, top to bottom, and
   only fire when explicitly called from inside a Skill (they never fire independently).
7. **Human approval before execution:** **not universal — see the per-action breakdown below.** Some
   Actions (Edit Shipping Address, Remove Item, Replace Item) explicitly require the **shopper** (not an
   internal human agent) to confirm details before running. Cancel Order's documentation does **not**
   explicitly state a confirmation step either way (`UNKNOWN`, not confirmed absent — see Section 2.2's
   caveat on this).
8. **Does Gorgias call Shopify directly?** Yes, confirmed — Actions call Shopify's admin API directly.
9. **What mutation occurs:** varies by Action (Section 2.2).
10. **Is success read back?** Confirmed implicitly for Cancel Order (restocking + refund are described as
    resulting effects, implying Gorgias reads Shopify's mutation response) — explicit read-back mechanism
    detail (e.g., a retry-on-uncertain-response pattern) **not found**, `UNKNOWN`.
11. **What happens on a Shopify error:** **not documented anywhere found this pass** — `UNKNOWN` for
    every Action. This is a genuine, disclosed evidentiary gap, not a confirmed absence of error handling.
12. **What the customer receives:** a confirmation email (confirmed for Cancel Order specifically);
    general pattern otherwise `UNKNOWN`.
13. **What is audit-logged:** every AI-generated message is labeled "Automated" in the ticket, reviewable
    with its sources; a response only sends after passing an internal QA step (a second AI model checking
    a confidence threshold). No structured, queryable audit-log mechanism (comparable to Sanocea's
    `AuditLedger` or Pipe17's "audit-logged" claim) was found with the same mechanism specificity — `Gaia`
    (Section 1) audits the *agent's configuration*, not a transaction-level audit trail of executed
    mutations. **This is thinner evidence than Pipe17's audit-logging claim.**
14. **Can the action be retried safely?** **No idempotency/duplicate-protection mechanism was found for
    AI Agent Actions specifically** — searched directly, no result surfaced (Section 7). This is a real,
    disclosed gap, not a confirmed absence (Gorgias may have this and simply not document it publicly).

### 2.2 Per-action mechanics

| Action | Eligibility (deterministic check) | Confirmation step found | Mutation | Confidence-gating (LLM) |
|---|---|---|---|---|
| **Cancel Order** | Order must be `unfulfilled` (Shopify order status) | **Not explicitly stated in primary docs** ([docs.gorgias.com — AI Agent Actions: make changes to Shopify orders](https://docs.gorgias.com/en-US/ai-agent-actions-make-changes-to-shopify-orders-757792)) | Order cancelled, product(s) restocked in Shopify, full refund issued, confirmation email sent | A secondary source (not Gorgias's own primary docs — lower confidence) recommends configuring a **90% confidence threshold**, below which the AI hands off to a human rather than cancelling ([usefini/Fini Labs — AI chatbots that cancel & refund](https://www.usefini.com/guides/ai-chatbots-cancel-subscriptions-refunds-shopify-plus-gorgias)) |
| **Edit Shipping Address** | Order must be `unfulfilled` | **Yes** — "AI Agent asks the shopper to confirm their updated shipping address" | Address updated in Shopify; cannot determine adjusted tax/shipping charges | Not separately specified |
| **Remove Item** | Order must be `unfulfilled` | **Yes** — shopper confirms the order and item(s) to remove | Item removed, restocked, partial refund issued | Not separately specified |
| **Replace Item** | Replacement item must be in stock | **Yes** — AI Agent requests clarification on items to remove/add; hands off to a human if additional payment is needed | Item swapped; **currently limited to a single item** | Hands off to human for payment-adjustment cases specifically |
| **Reship Order for Free** | Order lost in transit or damaged | Not stated | Order duplicated at no charge | Not stated |
| **Add Order Note** | None | N/A | Logs a note to the Shopify order record (non-mutating in commerce terms) | N/A |
| **"Autonomous Refunds" (2026 feature)** | **Order value under a merchant-configured dollar threshold (example cited: <$50) AND tracking status shows "Returned to Sender"** — both deterministic conditions | **None found** — described as a toggle that, once both deterministic conditions are met, executes without a further confirmation step | Refund issued | Sourced from secondary 2026-guide content, not confirmed via Gorgias's own primary docs this pass — **held to lower confidence** than the Cancel Order/Edit Address findings above |

**The single most important mechanical finding of this section, carried into Sections 3 and 13:** for
**Edit Shipping Address, Remove Item, and Replace Item**, the confirmation step is the **shopper
confirming their own request's details** — not an internal human agent approving a risk decision, and
not comparable in kind to Pipe17's "the system summarizes what it's about to do and confirms with the
user" (where "the user" in Pipe17's context is far more plausibly an internal operator using an MCP
client, not the end shopper — Pipe17's own material never describes an end-customer-facing confirmation
step, since it has no customer-conversation ingestion at all, per the Pipe17 audit's Section 8). **Cancel
Order and the "Autonomous Refunds" toggle show no confirmation step of *either* kind** — the only gate
found is either an LLM confidence score (Cancel Order, per lower-confidence secondary sourcing) or a pair
of deterministic conditions (Autonomous Refunds). This distinction — customer confirming their own
request vs. a risk-review confirmation step vs. no confirmation at all — is treated carefully and
separately throughout the rest of this audit, per the user's explicit instruction not to blur it.

## 3. Autonomy classification

| Action | Classification | Constraint on autonomy |
|---|---|---|
| General Q&A / order-status lookups | RESPOND | Confidence-threshold QA gate (second AI model) before any response sends |
| Cancel Order | **Best-evidenced classification: AUTONOMOUS EXECUTION, gated by an LLM confidence score, not a human or deterministic risk cap.** Primary docs do not state a confirmation step; the only cited gate (secondary source) is a merchant-configured confidence threshold, itself an LLM judgment, not a hard rule. | Deterministic precondition (unfulfilled) + LLM confidence threshold (merchant-set, e.g. 90%, per lower-confidence secondary sourcing) |
| Edit Shipping Address / Remove Item / Replace Item | EXECUTE WITH (SHOPPER) CONFIRMATION | Deterministic precondition (unfulfilled/in-stock) + the shopper's own confirmation of their request's specifics |
| "Autonomous Refunds" (2026, <$50, Returned-to-Sender) | **AUTONOMOUS EXECUTION, gated by two deterministic conditions (dollar cap + tracking-status match), not LLM risk-judgment.** | Deterministic dollar threshold + deterministic tracking-status match — this is closer to "policy-bounded autonomous mutation" than "AI judgment authorizes the mutation" |
| Reship for Free | EXECUTE WITH CONFIRMATION or AUTONOMOUS EXECUTION — **not stated either way**, `UNKNOWN` | Eligibility condition (lost/damaged) confirmed; confirmation-step presence not documented |
| Shopping Assistant discount-code issuance | AUTONOMOUS EXECUTION (a discount code is issued at a "high-intent moment" with no confirmation step described) | Not separately specified; lower-stakes than a refund/cancellation |

**Direct answer to the crux question the user posed:** for Cancel Order, the evidence (moderate
confidence — the exact mechanism for the confirmation/non-confirmation question is not stated in
Gorgias's own primary docs) suggests **LLM judgment is doing real risk-authorization work**, not merely
parameter extraction — the deterministic precondition only checks that the order *can* be cancelled
(hasn't shipped), not whether it *should* be, and the decision to proceed despite that being a real,
consequential mutation (money leaves the store, stock returns) rests on an AI confidence score, which is
a materially different — and less conservative — design than every prior competitor in this program
(Pipe17's universal human-confirmation gate; Sanocea's own `Approval` default). For the "Autonomous
Refunds" toggle specifically, the evidence points the other way: **the LLM is very plausibly only doing
intent-matching and parameter-extraction (which order, does the tracking status say RTO), while the
actual class-of-action-is-allowed-at-all decision is fully deterministic and merchant-configured** (the
dollar cap and the tracking-status condition) — this is a real, working instance of exactly the
narrow, policy-bounded shape the baseline's Stage 7 description said would be required before any such
capability could be justified (Section 13 below).

## 4. Policy model

Comparing Gorgias's Skills/Guidance/Actions against Sanocea's `Approval`/`ExceptionRecord`/
`ConnectorCommand` (ground truth read directly from `packages/domain_contract/models.py`).

**Are Skills/Guidance effectively a policy engine?** Partially, yes — Guidance is explicitly described
as the *highest-priority* layer, overriding other sources on conflict, and can encode conditional logic
("different steps based on whether the customer is a VIP, whether they have loyalty points, and based on
the customer's location," and "when the AI agent should escalate to a human, such as for negative
sentiment, VIP customers, or legal issues" — [eesel AI search synthesis](https://www.eesel.ai/blog/gorgias-customer-service);
[gorgias.com/blog/ai-agent-guardrails](https://www.gorgias.com/blog/ai-agent-guardrails)). This is a real,
working policy layer for the *support-conversation* domain specifically.

**Are eligibility rules deterministic before AI execution?** Yes, for the Shopify-state preconditions
(unfulfilled/in-stock, Section 2.2) — confirmed deterministic. The *decision to execute despite passing
the precondition* is where the mechanism diverges by action (Section 3).

**Can merchants specify refund limits, cancellation conditions, fulfilment-state constraints, order-age
constraints, VIP/customer rules, product exclusions, fraud/risk constraints?** Confirmed for: refund
limits (the $50 example), fulfilment-state constraints (unfulfilled precondition), VIP/customer rules
(Guidance example above), fraud/risk language handoff (Guidance's "fraud-related language or chargeback
mentions" trigger). **Order-age constraints and product-exclusion rules are suggested but not confirmed
with specific mechanism detail** — one secondary source recommends "using `Order Date` conditions to
prevent cancellations post-fulfillment," but whether this is a first-class, named configuration option or
informal advice is `UNKNOWN`.

**Does Sanocea's policy-controlled support pathway remain meaningfully different?** **Partially.**
Gorgias's Guidance/Skills/eligibility-precondition stack is a real, working analog to a policy engine
*scoped to the support-conversation domain specifically*. What it does **not** have, per every section
below, is: (a) Sanocea's generalized `Approval` object usable across *any* domain (finance, procurement,
support alike — Gorgias's policy layer is purpose-built for support only, not a reusable cross-domain
primitive); (b) a canonical, dual-status financial-truth field distinct from operational status (Section
8); (c) any confirmed connection to procurement/inventory-planning/reconciliation (Section 6). The
narrower, domain-specific nature of Gorgias's policy layer is a real distinction from Sanocea's
general-purpose model — but the *support-specific* slice of that comparison is now genuinely closer than
it was against any of the first four competitors.

## 5. Canonical truth vs. connected-app truth

**Confirmed: Gorgias does not own a canonical commerce data model. It reads Shopify's own live state
directly, action by action, with no confirmed shared normalized operational-truth layer of its own.**

- Gorgias's own security/privacy documentation does not state whether it stores a persistent copy of
  order/customer data — it only says AI Agent draws on "Your Shopify order and fulfillment data" as a
  connected knowledge source ([docs.gorgias.com — Security and privacy FAQ](https://docs.gorgias.com/en-US/security-and-privacy-faq-for-gorgias-ai-agent-1997987)).
- Independent sources are more explicit: "Gorgias's AI Agent accesses real-time data from platforms like
  Shopify... The system does not maintain its own separate database of orders and customers," and "that
  sidebar is the data source for everything else" (secondary sourcing, moderate confidence).
- **Explicit statement, per the user's specific instruction not to make this mistake:** the fact that a
  Gorgias ticket sidebar displays a shopper's full order history, customer profile, and product catalog
  data is **UI-level data surfacing from a live connected app, not evidence of a canonical operational
  model**. Gorgias's own canonical database is confirmed to exist for exactly one domain: **the
  conversation/ticket itself** (the Helpdesk's native CRM layer) — not orders, not inventory, not
  fulfilment, not payments.
- **Payments/refunds:** executed via Shopify's own refund mechanism (and Stripe, per one secondary
  source) — no canonical Gorgias-owned payment-truth object found.
- **Inventory:** read live from Shopify at mutation time (e.g., stock check for Replace Item); no
  canonical Gorgias-owned inventory state found.
- **Subscriptions:** read/mutated via Recharge/Skio/Loop Subscriptions — third-party systems, not a
  Gorgias-owned canonical subscription model.
- **Customer:** the one entity with genuine Gorgias-native persistence (a customer profile within the
  Helpdesk), but this is a support-CRM record, not a commerce-operational-truth record.

**Verdict: Gorgias has zero confirmed canonical commerce operational model.** It is architecturally an
orchestration/action layer over connected apps' own truth (Shopify, Loop, Recharge, various shipping
apps), with a native canonical model only for the conversation/ticket domain. This is a genuinely
different architecture from Sanocea's (and Pipe17's) canonical-normalization-layer approach — not
better or worse per se, but structurally distinct, and it directly shapes the cross-domain test below.

## 6. Cross-domain test

**No evidence found, in any direction, of Gorgias connecting a support-triggered action's result into
financial reconciliation, settlement state, marketplace fees, procurement, inventory planning, NDR/RTO
management, or supplier state.**

- **Refund → financial settlement:** no evidence Gorgias later verifies whether a Shopify-issued refund
  actually settled on the payment processor's side, or reconciles it against any external truth. The one
  "reconciliation" reference found (Gorgias-the-company "shortened its close by seven days") is Gorgias's
  own internal accounting process (Section 1) — **explicitly not evidence of a merchant-facing
  capability**, and this audit takes care not to conflate the two.
- **Refund → procurement/replenishment:** searched specifically (Section "procurement" queries); no
  Gorgias-specific evidence found. A cancelled/refunded order does result in Shopify-side restocking
  (confirmed, Section 2.2), which *could* in principle feed a merchant's own replenishment logic — but
  that logic lives in Shopify or a separate inventory-planning tool, not in Gorgias.
- **NDR/RTO:** Gorgias reads a Shopify/shipping-app tracking status (e.g., "Returned to Sender") as an
  *input condition* to the Autonomous Refunds feature (Section 2.2/3) — this is real, but it is
  consuming an existing NDR/RTO signal from elsewhere (the shipping carrier/3PL integration), not running
  an NDR/RTO management workflow itself the way Unicommerce's Shipway does.
- **Marketplace fees/commission:** no evidence found — Gorgias's commerce surface is Shopify-order-centric,
  not marketplace-settlement-centric; this capability class appears to be genuinely outside its product
  scope, consistent with it never having been built for the OMS/marketplace-operations problem at all.
- **Supplier state:** no evidence found — consistent with Section 1's "not found" on procurement.

**This is the narrowest cross-domain footprint of any of the five competitors researched in this
program.** Gorgias is not attempting differentiator F's territory at all — it is a customer-conversation
and connected-commerce-action layer, full stop, with no aspiration toward finance/procurement/settlement
truth found anywhere in its public material.

## 7. Safety/failure/recovery

| Dimension | Finding | Confidence |
|---|---|---|
| Permission checks | AI Agent inherits Shopify API permissions once connected ("Gorgias connected to Shopify, AI Agent already has permission to access customer data and can use Actions to make changes to orders") — no separate, finer-grained per-Action permission model found | Moderate |
| Authentication | OAuth-style app connection to Shopify/Loop/Recharge (standard app-install pattern); no AI-Agent-specific auth mechanism beyond the underlying app connections documented | Moderate |
| Action authorization | The confidence-threshold QA step (a second AI model) gates whether a *response* sends, but this is documented as a response-quality gate, not explicitly an action-authorization gate distinct from it — `UNKNOWN` whether mutation-triggering and message-sending share exactly one gate or two separate ones | Low-moderate |
| Audit trail | "Automated" labeling on messages + reviewable sources (Section 2.1, item 13) — real but thinner than Pipe17's "audit-logged" claim or Sanocea's `AuditLedger` | Moderate |
| Idempotency | **No mechanism found, searched specifically.** This is a genuine, disclosed gap — not confirmed absent, but no evidence surfaced either way | Low (absence of evidence, not evidence of absence) |
| Duplicate customer messages | Not addressed in any source found | `UNKNOWN` |
| Duplicate action protection | Not addressed in any source found | `UNKNOWN` |
| Retry behavior on Shopify error | Not addressed in any source found | `UNKNOWN` |
| Connector timeout handling | Not addressed | `UNKNOWN` |
| Mutation-succeeds-but-response-lost | Not addressed | `UNKNOWN` |
| Stale Shopify state / concurrent order mutation | Not addressed | `UNKNOWN` |
| Partial action failure | Not addressed | `UNKNOWN` |
| Read-after-write verification | Implied for Cancel Order (restocking + refund described as resulting effects) but not documented as an explicit verification step | Low |
| Rollback | Not addressed | `UNKNOWN` |
| Escalation | Well-documented (Section 12) | High |

**Verdict on the user's explicit question — is Gorgias actually safer than Sanocea, less safe, or
differently designed?** **The honest answer is: insufficient public documentation exists to make this
comparison rigorously for the transaction-safety mechanics (idempotency, retry, rollback, concurrent
mutation) — this is a genuine evidentiary gap, not a finding that Gorgias lacks these mechanisms.**
What *can* be said with confidence: Gorgias's **escalation/handoff design is well-documented and mature**
(Section 12); its **transaction-safety mechanics (idempotency, retry-on-failure, rollback) are
undocumented publicly**, in contrast to Sanocea's own source-code-verifiable `IdempotencyService`
(explicit release-on-failure behavior, confirmed by reading the code in the Pipe17 audit) and
`ConnectorCommand` state machine (`pending → approved → executing → succeeded/failed/uncertain/blocked`
— an explicit `uncertain` state Gorgias shows no public equivalent for). **This is a real, evidenced point
where Sanocea's architecture is more transparently safety-engineered than Gorgias's public material
demonstrates** — though this reflects what's publicly documented, not necessarily what's actually built
internally at Gorgias (the same caveat the Pipe17 audit applied to its own idempotency comparison).

## 8. Refund test

- **Can AI Agent refund autonomously?** Yes, confirmed for two distinct paths: (1) as part of Cancel
  Order (full refund, no confirmation step documented, gated at most by an LLM confidence threshold per
  lower-confidence secondary sourcing); (2) via the "Autonomous Refunds" toggle (deterministic dollar cap
  + RTO tracking-status match, no confirmation step found).
- **Full vs. partial refund:** full refund confirmed for Cancel Order and Remove Item (partial, for the
  removed item specifically); the Autonomous Refunds toggle's scope (full vs. partial) is `UNKNOWN`.
- **Refund amount limit:** confirmed only for the Autonomous Refunds toggle (<$50 example) — Cancel
  Order's refund has **no documented monetary cap**, meaning a high-value order's cancellation-triggered
  refund is gated the same way as a low-value one (by the same confidence threshold, if any), a real
  and material difference from the deliberately narrow, dollar-capped Autonomous Refunds design.
- **Eligibility rules:** unfulfilled-order precondition (deterministic) for Cancel Order; RTO-tracking +
  dollar-cap (deterministic) for Autonomous Refunds.
- **Shopify payment-state validation:** not separately documented — `UNKNOWN` whether Gorgias checks the
  original payment's state (captured, already refunded, disputed) before issuing a new refund.
- **Fulfilled/unfulfilled distinction:** confirmed as the core eligibility gate for Cancel Order/Address
  Edit/Remove Item.
- **Return-before-refund requirement:** not required for Cancel Order (refund is immediate, tied to
  cancellation, not to a physical return); for Loop-mediated returns, the *return* process is a separate
  integration (Section 10) and its own refund-timing mechanics are `UNKNOWN`.
- **Approval threshold:** the 90% confidence figure (Cancel Order, lower-confidence secondary sourcing)
  is the only explicit numeric threshold found for a refund-adjacent action.
- **Store credit vs. original payment:** not documented — `UNKNOWN`.
- **Duplicate-refund protection:** **not found**, searched specifically (Section 7).
- **Failed-refund handling:** **not found** — `UNKNOWN` what happens if Shopify's refund API call itself
  fails after the AI Agent has already told the customer it's processed.
- **Financial-settlement verification:** **not found anywhere** — confirmed absent as a Gorgias-native
  concept (Section 6).

**Direct comparison to Sanocea's `Refund.status` vs. `Refund.financial_reconciliation_status`:** Gorgias
has **no confirmed equivalent to the second dimension at all.** Sanocea's model explicitly tracks whether
a refund's settlement/statement evidence confirms correct debiting, separately and durably, from whether
the refund was operationally executed (per the code comment: "A refund can be operationally 'completed'
while this stays 'pending'... or flips to 'discrepancy' — that is a REAL, surfaced state, never silently
collapsed into `status`"). **Nothing in Gorgias's public material shows an equivalent concept — a refund,
once issued via Shopify, appears to have no further Gorgias-tracked financial-truth state at all.** This
is the sharpest, most direct confirmation in this section that differentiator F's specific mechanism
(dual-dimension reconciliation) is unthreatened by Gorgias, even though Gorgias's *operational* refund
execution (the mutation itself) is real, live, and — for at least the Cancel Order path — arguably less
conservatively gated than Sanocea's own `Approval`-defaulting design.

## 9. Cancellation test

**Confirmed, with the caveat on the confirmation-step gap already established in Sections 2-3:** the
public-material description of AI Agent verifying a Shopify order is unfulfilled, cancelling it,
restocking products, and triggering a refund to the shopper is accurate per Gorgias's own primary
documentation ([docs.gorgias.com — AI Agent Actions: make changes to Shopify orders](https://docs.gorgias.com/en-US/ai-agent-actions-make-changes-to-shopify-orders-757792)).

**Gorgias handles only Shopify's own cancellation semantics — confirmed, not a broader lifecycle.** No
evidence found of Gorgias's Cancel Order action interacting with a fulfilment/logistics system beyond
Shopify itself (e.g., no confirmed interaction with a 3PL's own cancellation/hold API, no confirmed
handling of a *post-dispatch* cancellation — the eligibility check is specifically "unfulfilled," meaning
a shipped order cannot be cancelled via this Action at all, full stop). **This is meaningfully narrower
than Sanocea's timing-dependent cancellation model** (pre-invoice / post-invoice-pre-dispatch /
post-dispatch, each with different handling — per the Unicommerce audit's finding on this pattern, and
confirmed as a real, evidenced Sanocea capability per the combined audit). Gorgias's design essentially
punts on the hardest case (a shipped order) by making it ineligible for autonomous cancellation entirely,
which is a real, deliberate, and arguably sensible scope boundary — not a weakness so much as a different
risk appetite: Gorgias automates the *easy* cancellation case fully, and leaves the *hard* case (courier-
return handling for an already-shipped order) to a human, with no confirmed Gorgias-native workflow for
it at all.

## 10. Returns/exchanges

**Precise, stage-by-stage confirmation — do not describe this as "processes returns end-to-end":**

| Stage | Confirmed? | Evidence |
|---|---|---|
| Starts the return / points the customer to a return portal | **Confirmed** | "AI Agent can be set up to spot a return request and automatically reply with a personalized link to the Loop portal" |
| Creates an RMA | **Not confirmed as a Gorgias-native action** — the RMA is created *inside Loop*, reached via the deep link | Gorgias sends a link; Loop's own portal (a third-party product) handles RMA creation |
| Generates a label | **Not confirmed as Gorgias-native** | "The app [Loop] then creates the return label and sends it off to the customer" — this is Loop's action, described in the context of a *human agent* manually clicking through Loop's own UI inside the Gorgias sidebar for the general (non-AI-Agent) case; whether the **AI Agent** path also requires this manual click-through, or whether it's more automated for AI Agent specifically, is `UNKNOWN` |
| Tracks return transit | **Confirmed** | A dedicated Action exists: "Send return shipping status from Loop Returns" |
| Confirms warehouse receipt | **Not confirmed** | No evidence found of Gorgias/AI Agent surfacing or acting on a warehouse-receipt event |
| Inspects return state (e.g., condition of returned item) | **Not confirmed** | No evidence found |
| Triggers refund following a return | **Not confirmed as automatic** | No evidence found connecting a Loop return's completion to an automatic Gorgias-triggered refund — the refund mechanism confirmed in Section 8 (Cancel Order, Autonomous Refunds) is not described as return-completion-triggered |
| Reconciles the refund | **Not found** — consistent with Section 6/8 | — |
| Exchange reservation/replacement | **Confirmed, narrowly** | "Replace Order Item" Action, limited to a single item, requires in-stock availability, hands off to a human for payment-adjustment cases |

**Verdict, stated precisely per the user's instruction:** Gorgias's return handling is confirmed for
**initiation (via a Loop deep link) and status-tracking (via a dedicated Action)** — the genuinely
operational middle of the return lifecycle (RMA creation, label generation, warehouse receipt,
inspection, and refund-triggering) is either confirmed to belong to Loop (a third-party product), or is
simply `UNKNOWN`/not found. **Gorgias does not process returns end-to-end; it initiates and reports on a
return that a separate, third-party product (Loop) actually operates.**

## 11. Customer channel depth

| Channel | AI response | Operational Action capability | Handoff | Notes |
|---|---|---|---|---|
| Email | Confirmed | Confirmed (all documented Actions) | Confirmed | Primary channel |
| Chat | Confirmed | Confirmed | Confirmed | Primary channel |
| SMS | Confirmed | Confirmed | Confirmed | Listed alongside email/chat as an AI-Agent-enabled channel |
| Instagram DM / Facebook Messenger | **Channel exists in Gorgias's Helpdesk, but AI Agent's own automation is confirmed limited to email/chat/SMS only** — "as of mid-2026 the AI Agent works on email, chat, and SMS, but not yet on voice or social channels" | **Not confirmed for AI Agent specifically** | `UNKNOWN` | A real, material distinction between "Gorgias supports this channel" and "AI Agent automates this channel" — exactly the mandate's own "operate vs. provide" distinction, applied here to channel breadth rather than support-vs-operations |
| WhatsApp | Same caveat as Instagram/Facebook — Gorgias-the-Helpdesk supports it as a channel; **AI Agent automation on WhatsApp specifically was not confirmed** in the primary-doc fetches this pass (one blog post discusses "why and how to use WhatsApp for customer service" generally, not AI-Agent-specific mechanics) | `UNKNOWN` | `UNKNOWN` | Genuinely important: this means Gorgias may **not** currently have the WhatsApp-native AI-Agent depth the audit brief's framing implied — flagged as a real finding, not assumed |
| Telegram / TikTok | Confirmed as Helpdesk channels; AI Agent automation **not confirmed** | `UNKNOWN` | `UNKNOWN` | Same pattern |
| Voice | **Explicitly confirmed absent** — "Gorgias lacks voice support and AI-powered phone capabilities" | Not applicable | Not applicable | A clean, confirmed `NOT FOUND` |

**Does the same operational action (e.g., a refund) originate from all channels or only selected ones?**
Per the confirmed evidence: **only email, chat, and SMS are confirmed to carry AI Agent's automated
Action capability.** WhatsApp/Instagram/Facebook/Telegram/TikTok are real Gorgias Helpdesk channels but
their AI-Agent-automation depth (as opposed to human-agent-assisted handling within the same inbox) was
not confirmed this pass — this should be treated as a genuine, disclosed research gap for a future pass,
not asserted as confirmed automation breadth.

## 12. Human handoff

Confirmed triggers, directly from Gorgias's own documentation:

- **Confidence:** "lacking confidence in an answer"; the internal QA step (second AI model) blocking a
  low-confidence response from sending at all.
- **Unable to find relevant content:** "unable to find relevant content in knowledge sources."
- **Emotional/sentiment:** "detecting customer anger or frustration"; Guidance-configurable "negative
  sentiment" escalation.
- **Explicit customer request:** "customer explicitly requests human agent."
- **Policy boundary / configured Handover Topics:** legal disputes or lawyer mentions, medical
  questions/health conditions, fraud-related language or chargeback mentions, "judgment-call situations
  outside written policy."
- **VIP:** confirmed as a Guidance-configurable escalation trigger.
- **Monetary amount:** **not confirmed as a general handoff trigger** — the only monetary-threshold
  mechanism found (Autonomous Refunds' <$50 cap) is a *scope-limiter for autonomous execution*, not a
  documented "escalate to human above $X" rule for the other Actions (Cancel Order's refund, notably, has
  no documented monetary escalation trigger at all — Section 8).
- **Failed action:** `UNKNOWN` — no source found describing what happens when an Action itself fails
  (as opposed to the AI failing to find an answer), consistent with Section 7's broader failure-handling
  gap.

**Comparison to Sanocea's deterministic→AI→human hierarchy:** Gorgias's handoff triggers are a real,
working instance of "human only for genuine uncertainty/risk" *for the response-generation and
sentiment/topic dimensions* — this is a genuine, evidenced convergence with Sanocea's own hierarchy,
similar in spirit to what the Pipe17 audit found for Pippen. **The gap, and it is a real one:** Sanocea's
hierarchy (and Pipe17's) routes *every* AI-mediated *mutation* through a human/confirmation gate; Gorgias's
evidenced handoff triggers are primarily about *response quality and topic sensitivity*, and — per
Sections 2-3 — at least one mutation-capable Action (Cancel Order) shows no confirmed monetary or human
gate at all, only a confidence-score gate on the AI's own certainty about intent. **This is a materially
different, and less conservative, application of "human only for risk" than either Sanocea's stated
design or Pipe17's confirmed universal gate** — Gorgias's evidenced position is closer to "human only for
low AI-confidence or sensitive topics," which is not the same claim as "human only for high-stakes
mutations regardless of AI confidence."

## 13. AI Roadmap Stage-7 destruction test

**The baseline states:** *"Zero competitor precedent found anywhere in the program, including at Pipe17
— the most AI-forward competitor researched confirms the opposite pattern (universal
confirm-before-execute)."*

**Gorgias evidence, weighed carefully:**

1. **The "Autonomous Refunds" toggle (<$50, Returned-to-Sender tracking status) is a real, if
   secondary-sourced (lower-confidence), example of exactly the narrow, deterministically-bounded shape
   the baseline's own Stage 7 description said would be required before such a capability could ever be
   justified**: "a hard, narrow policy envelope (e.g., 'only for orders under ₹X, only for a pre-approved
   action type')." Gorgias's toggle matches this description closely — a dollar cap plus a single,
   specific triggering condition, with (per available evidence) no per-instance human or customer
   confirmation step. **If this feature is confirmed accurately by future, higher-confidence research, it
   is genuine competitor precedent for policy-bounded autonomous mutation.**
2. **Cancel Order is a second, more concerning data point** — no monetary cap, gated (per lower-confidence
   secondary sourcing) only by an LLM confidence *score*, which is itself a form of AI judgment
   authorizing the mutation's execution, not merely parameter extraction. This is a **less narrow, less
   deterministically-bounded** case than the baseline's Stage 7 description envisioned — closer to "AI
   decides this is probably fine and does it" than "a deterministic policy decided this class of action is
   always safe."
3. **Is LLM judgment actually authorizing the mutation, or merely selecting a deterministic pre-approved
   Action?** The honest, precise answer, per the evidence: **it depends on the specific Action, and this
   audit finds real examples of both patterns simultaneously at the same competitor** — Autonomous
   Refunds is closer to "deterministic policy pre-approved this narrow class of action, the LLM just
   matches parameters"; Cancel Order (on the balance of available, lower-confidence evidence) is closer
   to "the LLM's own confidence judgment is doing real risk-authorization work." **This is the single most
   important nuance of the entire audit — do not collapse it into one answer for "Gorgias" as a whole.**

**Verdict: NEEDS QUALIFICATION.** The baseline's "zero competitor precedent" statement is **no longer
accurate as an absolute claim** — real, if not fully primary-source-confirmed, evidence exists of at
least one Gorgias feature (Autonomous Refunds) matching the narrow, deterministically-bounded profile the
baseline itself said would be the only acceptable shape for Stage 7, and at least one other feature
(Cancel Order) that goes further than the baseline anticipated, gating a real mutation by AI confidence
rather than a deterministic cap. **This does not mean Sanocea should build Stage 7 broadly** — if
anything, Cancel Order's design is a cautionary example of exactly the risk the baseline warned about
(AI risk-judgment with no hard boundary), while Autonomous Refunds is a genuine, worth-considering
precedent for a *narrow, deterministically-bounded* future exception (Section 19 proposes exact
baseline-change language).

## 14. Differentiator E destruction test

Breaking "support conversation → canonical commerce truth → policy/approval → operational execution"
into its components, per the user's explicit instruction not to collapse this into one sentence.

| Component | Verdict | Evidence |
|---|---|---|
| **A. Conversation ingestion** | **Gorgias meets or exceeds Sanocea on breadth and production maturity.** Sanocea's ingestion (Chatwoot-integrated) is real and proven (Phase 4.6), but Gorgias natively ingests email/chat/SMS at AI-Agent depth across, per its own positioning, a very large number of live Shopify merchants — a materially larger real-world proof point. Not a "differentiator" for Sanocea against this specific competitor. | Section 1, Section 11 |
| **B. Intent understanding** | **Not differentiated for Sanocea — arguably the reverse.** Gorgias's intent classification is a real, shipped, production LLM system; Sanocea's own AI path has never made a real inference call (consistent with every prior audit's finding on `AIProvider`). | Section 2.1 |
| **C. Live commerce truth** | **PARTIALLY SURVIVES for Sanocea.** Gorgias reads live Shopify state per-action (real, proven at scale) but has no canonical, cross-platform, normalized truth layer (Section 5) — Sanocea's canonical model is broader in intended scope (spans orders/finance/procurement/support across multiple certified platforms) but proven at smaller real-world scale (one org's certifications, not thousands of live merchant deployments). | Section 5 |
| **D. Deterministic/policy eligibility** | **PARTIALLY SURVIVES for Sanocea.** Gorgias has a real, working eligibility-precondition + Guidance-policy layer, but scoped only to support-conversation actions, not a general-purpose, cross-domain `Approval`/policy primitive the way Sanocea's is. | Section 4 |
| **E. Operational mutation** | **DESTROYED as an exclusive Sanocea claim, on production-scale evidence.** Gorgias executes real Shopify mutations (cancel/refund/address-change/subscription) from live customer conversations across (per its own positioning) a very large number of real merchants — this is a materially more production-proven instance of "support conversation causes real operational mutation" than Sanocea's own Phase-4.6 proof, even though Gorgias's mutation scope (Shopify-order-only) is narrower than Sanocea's cross-domain ambition. | Sections 2, 8, 9 |
| **F. Approval/risk control** | **NEEDS QUALIFICATION — the most genuinely contested component.** Sanocea's `Approval` model defaults every mutation to `REQUIRE_APPROVAL`; Gorgias shows a mix — real shopper-confirmation steps for some Actions, but no confirmed human or deterministic-cap gate at all for Cancel Order (LLM-confidence-gated only) and a genuinely narrow deterministic gate for Autonomous Refunds. Sanocea's *principle* (never let AI mutate unattended) is not disproven as correct — but "no competitor lets AI-judgment authorize a real mutation without a human or hard deterministic gate" is no longer fully true after this audit. | Sections 3, 13 |
| **G. Reconciliation/read-back** | **SURVIVES strongly for Sanocea.** No evidence of Gorgias's dual-dimension (operational vs. financial-truth) reconciliation model anywhere — a refund, once issued, has no further Gorgias-tracked financial-truth state found. | Section 8 |
| **H. Cross-domain canonical consequence** | **SURVIVES strongly for Sanocea.** Confirmed zero connection to procurement, financial reconciliation, marketplace fees, or supplier state (Section 6) — the narrowest cross-domain footprint of any competitor in this program. | Section 6 |

**Overall verdict: PARTIALLY SURVIVES, and unevenly across the chain — exactly the pattern the audit
brief anticipated, with one important refinement.** Components A, B, and E are genuinely won or matched by
Gorgias on production-scale evidence; components G and H remain strongly, cleanly won by Sanocea; C, D,
and F are the genuinely mixed middle, with F being the sharpest and most important nuance this audit adds
(Section 13's Cancel Order finding specifically). **The differentiator survives as a whole because its
strongest components (F-H, the risk-control and cross-domain-truth pieces) are the ones Gorgias's narrow,
Shopify-order-scoped, no-canonical-model architecture cannot reach — but Sanocea should stop claiming
components A, B, and E as differentiated against a competitor whose production-scale proof on exactly
those components now exceeds its own.**

## 15. Differentiator F destruction test

**"Finance + commerce operations + procurement + customer operations against one canonical truth" —
tested directly against Gorgias.**

Per Sections 5-6: Gorgias handles customer conversation and a narrow, Shopify-order-scoped set of
connected commerce actions. It has **zero** confirmed procurement capability, **zero** confirmed native
financial-reconciliation capability (the one "reconciliation" reference found was Gorgias's own internal
books, explicitly not a merchant-facing feature — Section 1), and **zero** confirmed canonical
cross-domain data model of any kind (Section 5). Gorgias is not attempting this territory at all — it is,
by a clear margin, the narrowest-scoped competitor of the five audited in this program on this specific
dimension.

**Verdict: SURVIVES, and more decisively than against any of the first four competitors.** Even Pipe17
(the most architecturally sophisticated prior competitor) had a real canonical model spanning
orders/inventory/fulfillment and touched finance via integration; Gorgias has no canonical model at all
beyond its own conversation/ticket layer, and no finance/procurement footprint whatsoever. This is the
single cleanest reconfirmation of differentiator F in the program.

## 16. Human-labour test

**"After buying Gorgias AI Agent, what does the merchant still pay a human to do?"**

- **Complex support:** confirmed real and ongoing — every documented handoff trigger (low confidence,
  sensitive topics, VIP, explicit request, negative sentiment, unsupported channels like voice/social
  automation) routes to a human. Marketing itself caps automation at "60% of email and chat
  conversations" (one secondary source) — by definition, a human still handles the other ~40%.
- **Policy design:** a human (a merchant's ops/CX lead) still writes and maintains Guidance (up to 100
  instructions) and configures Skills/Actions/thresholds — Gorgias automates *execution* of policy, not
  its *authorship*, the identical pattern found for Pipe17's Pippen rule-authorship (Section 6 of the
  Pipe17 audit) and Linnworks' Spotlight AI.
- **Refunds/risk approvals:** for Actions with no confirmed human/deterministic gate (Cancel Order, per
  Section 13), the *design decision itself* (how conservative to set the confidence threshold, whether to
  even enable the Action) is real, ongoing human risk-management work, even though per-instance execution
  is automated.
- **Failed actions:** entirely human-bridged, by evidentiary default — no failure-handling mechanism was
  found (Section 7), meaning any failure discovered is very plausibly currently surfaced to a human via
  the general handoff/QA mechanism rather than any Action-specific recovery logic.
- **Operations (multi-location allocation, warehouse execution, courier selection):** **entirely outside
  Gorgias's scope** — it has zero operational-fulfilment capability of any kind; Shopify/a separate
  OMS/WMS does this work, Gorgias only reads the result.
- **Reconciliation:** entirely human or a separate tool — confirmed zero native capability (Section 6, 8).
- **Procurement:** entirely human or a separate tool — confirmed zero native capability (Section 6).
- **NDR/RTO:** Gorgias consumes an existing RTO signal (Section 6) but does not manage the NDR/RTO
  *decision* (re-attempt vs. accept) itself — that remains with whatever system (Shipway-equivalent, or a
  human) generates the tracking-status signal in the first place.
- **Reporting:** not evidenced either way this pass — genuinely `UNKNOWN`.
- **Marketplace work:** not applicable — Gorgias is confirmed Shopify-order-scoped, with no marketplace
  (Amazon/Flipkart-equivalent) presence found in any source this pass.
- **Physical work:** unconditionally human, same as every prior competitor.

**Say plainly, per the brief's explicit instruction:** **yes, the evidence supports that Gorgias removes
substantially more customer-*support-conversation* labor than any of the first four competitors** — its
"resolves requests end to end... even when human agents are offline" positioning, if the ~60%
auto-resolution figure is directionally accurate, is a real, meaningful reduction in the *volume* of
support tickets a human touches. **But this is narrowly scoped to support-conversation labor
specifically** — every other human-labor category in the mandate's checklist (operations, procurement,
reconciliation, NDR/RTO decision-making, marketplace work, physical work) is either entirely untouched by
Gorgias or only marginally affected by it, since Gorgias was never built to touch those domains at all.

## 17. Pricing/capability gating

Confirmed via multiple 2026 third-party pricing breakdowns (no single, first-party Gorgias pricing page
was fetched directly this pass — held to moderate confidence, consistent with the mandate's instruction
not to rely on stale/unverified pricing, and cross-checked across several independent secondary sources
that broadly agree with each other):

- **Helpdesk base plans:** ticket-volume-based, roughly **$10/month (Starter) to $750/month (Advanced)**
  — billed on conversation volume, not per-seat.
- **AI Agent:** **per-resolution pricing, roughly $0.90 (annual)–$1.00 (monthly) per resolution**, with
  plans bundling 90 to 2,500+ automated interactions per month.
- **A specific, material capability-gating mechanic confirmed by multiple independent sources: each AI
  resolution also counts as a helpdesk ticket** — a "double-billing" structure where an automated
  resolution consumes both an AI-resolution credit *and* a helpdesk-ticket-volume credit, pushing the
  effective per-resolution cost higher than the headline $0.90-$1.00 figure once overage is factored in
  (one source's estimate: "~$1.26" effective cost on a mid-tier plan).
- **Overage charges:** AI-resolution overage cited at $1.50/interaction; ticket-overage cited at
  $0.32-$0.40/ticket depending on plan tier.
- **Feature/Action availability by tier:** **not confirmed with specific detail this pass** — whether
  specific Actions (e.g., Autonomous Refunds, or the full Actions catalogue) are gated behind a
  specific pricing tier, or available uniformly once AI Agent is purchased at any tier, is `UNKNOWN`.

**Compare against Sanocea's "price determines capacity, not capability":** Gorgias's confirmed pricing
mechanics are **capacity-based in shape** (order/resolution/ticket-volume-driven), which is broadly
consistent with Sanocea's own principle's allowance for capacity-based pricing — but the **double-billing
structure (one resolution consuming two separate metered credits simultaneously)** is a real, evidenced,
and somewhat opaque cost-stacking mechanic that a merchant would need to understand carefully to predict
their actual spend. This is not "capability gating" in the sense Linnworks (RBAC) or Unicommerce
(reconciliation) were confirmed to practice — it is closer to a **compounding-capacity-metric** pattern,
worth naming as its own, distinct category from the tiered-feature-gating pattern found at the first four
competitors, rather than conflating the two.

## 18. Capabilities Sanocea should absorb

Nothing here is authorized for implementation — proposals only, per the user's explicit instruction
(consistent across all five audits so far).

| # | Merchant problem | Gorgias evidence | Sanocea state | Generic design lesson | Canonical impact | Human labor eliminated | Priority | Tag |
|---|---|---|---|---|---|---|---|---|
| 1 | Support conversations need real-time visibility into live commerce state without a human hunting across systems | AI Agent reads live Shopify order/fulfilment/customer data directly into the conversation context | `IMPLEMENTED+PROVEN` for triggering mutations, but not independently confirmed at Gorgias's specific "sidebar shows everything live" UX pattern | A support-conversation interface should surface live canonical-model state (order/shipment/refund status) directly alongside the conversation, not require a separate lookup — a UX lesson, not an architecture change, since Sanocea's canonical model already has this data | None — this is presentation-layer, not canonical-model work | Removes manual cross-system lookup during a support conversation | **P2** | **C** — superior design/UX insight for an already-proven Sanocea capability |
| 2 | A narrow, deterministically-bounded, low-dollar, single-condition-triggered autonomous mutation (e.g., a small refund when a specific deterministic condition — like RTO tracking status — is independently confirmed) may be a legitimate, safe exception to a universal per-instance human-confirmation default | Gorgias's "Autonomous Refunds" toggle (<$50, Returned-to-Sender tracking status) — real precedent, moderate confidence (secondary-sourced) | `ARCHITECTURAL ONLY` — Stage 7 currently rated DO NOT BUILD outright | If Sanocea ever revisits Stage 7, the correct shape is exactly this narrow: a hard dollar cap AND a single, independently-verified deterministic triggering condition (not an LLM confidence score) — the LLM's role limited to parameter-matching, never risk-authorization | Would require a new, explicitly narrow policy-envelope concept distinct from the general `Approval` default — not a wholesale Stage-7 build | Removes a specific, low-risk, high-volume manual refund-approval pattern | **P3 — narrow, exploratory only, not a general Stage-7 build** | **A** — genuinely new pattern (a specific, narrow, real-world-precedented exception shape, not a general capability) |
| 3 | Support-conversation policy (Guidance) needs a single, explicit, highest-priority instruction layer that overrides other knowledge sources on conflict | Gorgias's Guidance (up to 100 plain-language instructions, explicit override priority) | `PARTIAL` — Sanocea's policy engine exists but is not confirmed to have this exact "highest-priority override layer, explicitly documented as such" framing for the support domain specifically | A support-conversation policy layer should have one clearly-documented, highest-priority instruction set merchants configure directly, distinct from general knowledge sources | Extends existing policy/merchant-configuration pattern; no canonical-model change | Reduces ambiguity/conflict in how a support AI is configured to behave | **P2** | **C** — superior design insight for the support-specific slice of Sanocea's existing policy model |
| 4 | Customers confirming their own request's specifics before a moderate-risk mutation executes (address change, item removal) is a real, working middle ground between full autonomy and full human-approval | Gorgias's shopper-confirmation step for Edit Shipping Address / Remove Item / Replace Item | `MISSING` — Sanocea's `Approval` model routes to a human/operator, not a customer-facing "please confirm your own request" step | For moderate-risk, customer-initiated mutations, a customer-confirmation step (distinct from an operator-approval step) may reduce operator load without weakening safety, since the customer is confirming *their own* stated intent, not a third party approving someone else's risk | Could be modeled as a new `Approval`-adjacent confirmation type, distinct from operator approval — a design nuance, not a schema requirement here | Reduces operator-approval load for genuinely low-ambiguity, customer-confirmable mutations | **P2** | **A** — a genuinely new pattern (customer-self-confirmation as a distinct safety tier) not previously identified in this program |
| 5 | A confidence-threshold-based response-quality gate (a second AI model checking the first's output before it reaches the customer) | Gorgias's internal QA step | `MISSING` — no equivalent exists once a real `AIProvider` is wired in | Any real Sanocea AI feature (Stage 1 onward, per the baseline's AI Roadmap) should ship with a similar two-model quality gate before any AI-generated content reaches a customer or triggers a mutation-proposal | AI interpretation layer design detail, not a canonical-model change | Reduces the risk of a single-model hallucination reaching a real customer/mutation | **P1** | **C** — superior design insight directly applicable to the baseline's own Stage 1-2 recommendation |
| 6 | Double-billing/compounding-metric pricing structures are real merchant friction even when nominally "capacity-based" | Gorgias's confirmed AI-resolution-also-counts-as-a-ticket mechanic | N/A | Sanocea's capacity-based pricing metrics should be singular and transparent per unit of work — avoid a design where one customer interaction consumes two separately-billed capacity pools, since this is a real, evidenced source of merchant cost-unpredictability even without being "capability gating" in the stricter sense | N/A | N/A | N/A | **DO NOT ABSORB** — explicitly flagged as a pricing-mechanic complexity to avoid, consistent with the mandate's "sell simply" principle |

## 19. Proposed baseline changes after Gorgias

**Per the user's explicit instruction: `SANOCEA-PRODUCT-BASELINE-V1.md` is NOT edited by this audit.**
The following are proposals for the team to review before any change is made to that document.

### Proposed change 1 — AI Roadmap Stage 7 (baseline Section 8)

- **Current baseline statement:** *"None — this is the one stage with zero competitor precedent found
  anywhere in the program, including at Pipe17, the most AI-forward competitor researched."*
- **New evidence:** Gorgias's "Autonomous Refunds" toggle (<$50 order value AND "Returned to Sender"
  tracking status, both deterministic conditions, no confirmed human or customer confirmation step) —
  sourced from secondary 2026-guide content, not confirmed via Gorgias's own primary documentation this
  pass.
- **Proposed replacement:** *"One narrow, secondary-sourced (moderate-confidence) competitor precedent
  now exists: Gorgias's 'Autonomous Refunds' feature, gated by a hard dollar cap and a single
  independently-verified deterministic condition, with no confirmed human or customer confirmation step.
  This matches the narrow policy-envelope shape this section itself specified as the only acceptable
  form of Stage 7 — but it remains a single, narrowly-scoped, moderate-confidence data point, not general
  precedent for autonomous AI-judgment-authorized mutation. The DO-NOT-BUILD recommendation for Stage 7
  in general stands; a narrow, deterministically-bounded exception in this specific shape (hard cap +
  single independently-verified condition, LLM restricted to parameter-matching only) may be worth a
  dedicated, separate future proposal if evidence continues to accumulate — it should not be built as
  part of a general Stage 7 rollout."*
- **Confidence: Moderate.** The core finding (a real competitor ships *something* in this shape) is
  reasonably well-supported across multiple independent secondary sources describing the same 2026
  feature; the exact mechanism detail (is there truly zero confirmation step, or was one simply not
  mentioned) was not independently verified via Gorgias's own primary documentation this pass.

### Proposed change 2 — Differentiator E (baseline Section 5.A.2)

- **Current baseline statement:** *"Support conversation → operational execution through the same
  policy/approval path (old differentiator E). Zero of four competitors showed any equivalent... Sanocea's
  Phase-4.6-proven support-to-refund path via the same policy engine an operator uses remains
  uncontested."*
- **New evidence:** Gorgias executes real Shopify mutations (cancellation, refund, address change,
  subscription actions) from live customer conversations, at production scale across many real
  merchants — a materially larger real-world proof point for "support conversation causes real
  operational mutation" than Sanocea's own single-organization Phase-4.6 proof. However, Gorgias has zero
  canonical cross-domain model, zero financial-reconciliation dual-status equivalent, and zero
  procurement/finance footprint (Sections 5, 6, 8, 15) — the specific *combination* of differentiator E
  with differentiator F remains uncontested.
- **Proposed replacement:** *"Support conversation → operational execution through the same policy/
  approval path (old differentiator E) remains genuinely differentiated ONLY in combination with
  differentiator F (cross-domain canonical truth including finance/procurement) — Gorgias AI Agent (2026)
  is now confirmed to execute real, production-scale commerce mutations from customer conversations,
  meeting or exceeding Sanocea's own proof on conversation-ingestion breadth and mutation-execution
  volume. Sanocea should no longer claim 'support-triggered mutation' as differentiated in isolation;
  the differentiated claim is specifically 'support-triggered mutation that is also canonically connected
  to financial-truth reconciliation, procurement, and every other operational domain in one system' —
  which no competitor researched, including Gorgias, has been shown to do."*
- **Confidence: High** for the "Gorgias executes real mutations at scale" finding (multiple independent
  primary-doc and secondary sources agree); **high** for "Gorgias has no cross-domain canonical model"
  (Section 5-6, well-evidenced); the overall reframing recommendation is a synthesis judgment, not a new
  fact, so treat the *recommendation* itself as a proposal for team discussion, not a settled fact.

### Proposed change 3 — Human-only-for-risk framing (baseline Section 5.A, differentiator D area / Section 10)

- **Current baseline statement (from the Pipe17 audit, carried into the baseline's framing):**
  effectively, "no competitor lets AI-judgment authorize a real mutation without a human or hard
  deterministic gate."
- **New evidence:** Gorgias's Cancel Order action (Section 13) shows, on the balance of available
  (lower-confidence, secondary-sourced) evidence, an LLM confidence *score* — not a human, not a hard
  deterministic cap — as the only gate on a real, potentially high-value refund-and-cancellation
  mutation.
- **Proposed replacement:** *"Human-only-for-genuine-risk remains Sanocea's correct design principle, and
  is independently reconfirmed by Pipe17's universal confirm-before-execute gate — but it is not
  universal industry practice even among AI-forward competitors: Gorgias's Cancel Order action (2026,
  moderate confidence) appears to gate a real, uncapped-value refund mutation by AI confidence score
  alone, with no confirmed human or deterministic monetary safeguard. This should be read as a
  cautionary competitor example reinforcing why Sanocea's stricter default is the right choice, not as
  evidence the stricter default is unnecessary or old-fashioned."*
- **Confidence: Moderate** — this rests on the same lower-confidence secondary sourcing as Proposed
  change 1's core evidence; worth a dedicated primary-source verification pass before treating this as
  settled.

### Proposed change 4 — no change recommended

Everything else in the baseline (Sections 2-4, 6-7, 9-12, 14) is either unaffected by Gorgias evidence
(multi-location allocation, India-specific reconciliation, procurement, WMS-floor-execution do-not-build
reasoning) or **reinforced rather than challenged** by it (differentiator F, Section 15 above). No
change is proposed to these sections.

## 20. Stop condition

This audit is complete. Per the user's explicit instruction: **`SANOCEA-PRODUCT-BASELINE-V1.md` was not
modified.** No recommendation in this file, or in any of the prior four audit files, is authorized for
implementation. No competitor #6 (Siena, Yuma, Decagon, Intercom, Zendesk, Ada, or any other
conversational-AI competitor) has been started. No Sanocea production code, connectors, tests, or scripts
were modified — reading `packages/domain_contract/models.py` for ground truth was the only interaction
with the Sanocea codebase. The mandate's execution log (`README.md`, Section 11) should be updated to
mark Gorgias complete, once this file is reviewed.
