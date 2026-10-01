# Sanocea Commerce OS — Agent Engineering Rules

Persistent instructions for any coding session working in this repository. This file did not exist
before 2026-09-11 — it was created specifically to hold the rule below; add further durable engineering
rules here going forward rather than creating parallel rules documents.

## OSS-first / do-not-reinvent rule

Before implementing any materially new capability, subsystem, algorithm, connector pattern, workflow
primitive, or infrastructure mechanism from scratch, perform **one** focused GitHub/open-source
landscape check first.

**Purpose:** Sanocea should not spend engineering effort rediscovering solved, battle-tested commodity
problems.

Sequence:

```
REQUIREMENT
→ CHECK EXISTING OSS
→ INSPECT RELEVANT SOURCE CODE
→ CHECK LICENSE
→ DECIDE REUSE / ADAPT / LEARN / BUILD
→ IMPLEMENT
→ TEST AGAINST SANOCEA INVARIANTS
```

**The search is mandatory once per genuinely new capability. It is not a recurring research loop.** Do
not repeatedly search GitHub after implementation has begun unless a specific blocker or correctness
question justifies reopening research.

### What to look for

Search serious, maintained open-source projects for implementations of the same or closely related
problem. Prefer, in rough order:

1. Mature, production-used projects
2. Active repositories
3. Implementations with tests
4. Implementations with documented edge cases
5. Projects operating at meaningful scale
6. Source code over marketing descriptions

Inspect the actual implementation where practical. Look specifically for: domain semantics, state
machines, invariants, database constraints, concurrency handling, idempotency, retry/recovery, failure
modes, edge cases, test cases, API/connector abstractions. Also inspect open issues when useful — mature
OSS projects' bug trackers often reveal failure modes to avoid, not just patterns to copy (e.g. a real,
shipped oversell race in a mature commerce platform's checkout-time reservation logic is more valuable
evidence than its documentation alone).

### Decision

For relevant OSS found, make a lightweight internal decision:

- **A. Reuse directly**
- **B. Adapt** (implementation pattern, not the code itself)
- **C. Learn semantics/pattern only**
- **D. Not applicable**
- **E. Build our own**

Do not automatically add a dependency merely because code already exists. Sanocea remains
architecturally independent. Prefer borrowing proven semantics and implementation patterns when pulling
in the entire dependency would create unnecessary coupling.

### License / provenance

Never copy source blindly. Before directly incorporating code, verify its license permits the intended
use and preserve any attribution/license obligations. If licensing is incompatible or unclear: **do not
copy the code** — learn the public design/behavioral pattern and implement an independent Sanocea-native
version instead. Record provenance when actual third-party code is incorporated.

### Architectural boundary

OSS must conform to Sanocea's architecture — Sanocea must not be distorted to conform to an OSS
project. Reusable code/patterns must preserve:

- Merchant independence
- Platform neutrality in canonical/core logic
- Deterministic-first execution
- Idempotent guarded mutations
- Canonical operating truth
- Policy/approval boundaries
- Reconciliation/read-back
- Tenant isolation
- Evidence/auditability
- Linux portability

Platform-specific behavior remains inside connectors/adapters. Do not import an entire e-commerce
framework merely to obtain one useful primitive.

**Cross-reference — this rule does not reopen or contradict the existing dependency-exclusion
decision.** `README.md` already states, as an architecture decision, that Medusa, Akeneo, Pimcore,
Activepieces, OPA, flagd, LangGraph, Amazon, voice, billing, and Kubernetes are excluded from Sanocea
*as dependencies*. This rule is fully consistent with that: studying Medusa's (or any excluded
project's) source for semantics/patterns is exactly what Decision option C above covers, and remains
allowed and encouraged; importing it as a dependency remains excluded per that prior decision. If this
rule's research ever surfaces a case for reconsidering that exclusion, record that as its own explicit
decision (an ADR under `docs/adr/`) rather than silently overriding it here.

### Examples (illustrative, not exhaustive — the rule applies equally to future capabilities not listed)

| Before building | Inspect |
|---|---|
| Inventory reservations / allocation | Medusa, Saleor, ERPNext, or stronger relevant OSS |
| Returns/refunds state machines | Mature commerce implementations |
| Bundles/kits | Established inventory/commerce implementations |
| Webhook reliability | Battle-tested event-processing patterns |
| Rate limiting/retries | Established libraries before writing custom infrastructure |
| Marketplace connector | Maintained SDKs/connectors before implementing raw HTTP |
| Support automation | Chatwoot ecosystem/integrations before recreating capabilities |

### Important

This rule exists to **reduce** research and coding time, not increase it. A focused OSS check should
answer: *"Has this already been solved well enough that we can reuse it or learn from it?"* Then make
the decision and move on. Do not turn every implementation task into another competitive audit.

## Canonical UI rule

**CANONICAL UI RULE: /demo.html is the single SANOCEA Command Centre. Do not create parallel Command Centre UIs,
internal copies, admin copies, SEO copies, or alternative presentation surfaces. All product UI capabilities must be
implemented in the existing /demo.html application. Backend services may remain separated architecturally, but there
must be one canonical frontend.**

Before implementing any future UI capability, an agent must search the existing /demo.html application first
(`website/demo.html` → `website/src/whatsapp-demo/`) and extend the existing component rather than creating another
surface.

Consequences already enacted (2026-10-01):

- The API-served `/ui` Command Centre (`apps/command_center/`) and the `/console.html` Operations Console were retired.
  The API serves no UI; its root redirects to /demo.html. Their backend endpoints remain; capabilities that existed
  only in those UIs are API-only and tracked in `docs/architecture/retired-ui/FUTURE_UI_MIGRATION_BACKLOG.md`.
- SEO intelligence has ONE data path: SEO worker (persisted state) → `GET /demo/seo/overview` (packages/seo_bridge,
  authorized by the existing demo-session key) → the shared loader `website/src/whatsapp-demo/useSeoOverview.js` → the
  SEO & Commerce Audit tab and the Dashboard's SEO sections. Do not add a second loader, a snapshot file, a
  second login, or hard-coded copies of live telemetry. A value the worker does not supply renders NOT AVAILABLE with the
  worker's reason, never a zero or a fixture. Worker provenance labels and timestamps are shown exactly as supplied.
- Static case-study material (for example the September 2026 intervention record) must be labelled
  `[HISTORICAL · STATIC]`, or live in documentation (`docs/case-studies/`), never presented as live telemetry.
