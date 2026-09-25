<!--
Durable product truth for Sanocea Commerce OS. Structure adapted from the PRODUCT.md convention
documented in pbakaus/impeccable's `init.md` skill reference (Apache-2.0; pattern learned, not
copied — see CLAUDE.md's OSS-first rule, Decision C). This file is not maintained by that tool;
it's a Sanocea-native doc following the same shape because the shape is genuinely useful:
durable product facts that outlive any single feature, kept separate from visual direction
(that lives in DESIGN.md) and separate from any one task's scope.

Update this file when product truth changes (new audience, new positioning, a constraint that
becomes durable). Don't add page-by-page composition or visual decisions here — those belong in
DESIGN.md or in a task's own design-approval-gate preview.
-->

# Product

## Platform

web

## Stack

Backend: Python (see `pyproject.toml`, `packages/*`), Postgres, Temporal-shaped workflow semantics,
S3-compatible object storage. Website/demo frontend: React 19 + Vite + `framer-motion`, plain CSS
(no Tailwind, no component framework).

## Users

Operators at merchants running commerce across multiple connected channels (marketplaces,
storefronts, support inboxes) who need operational exceptions found, investigated, and resolved
without manually watching every channel. The buyer/evaluator audience for the marketing website is
a prospective merchant or operator deciding whether to trial Sanocea.

## Product Purpose

Sanocea is an AI commerce operations layer: it watches connected commerce channels, finds
operational exceptions, investigates them, gathers evidence, prepares decisions, routes work to a
human for approval, executes approved actions, and records the result. Primary story order:
`CONNECT → WATCH → FIND → INVESTIGATE → PREPARE → APPROVE → ACT → AUDIT`.

## Positioning

Sanocea is explicitly **not**: a catalogue management tool, a marketplace dashboard, a generic
inventory dashboard, an AI chatbot, or a generic e-commerce SaaS platform. The mechanism a
neighboring product could not truthfully copy: exceptions are found and investigated automatically,
with evidence assembled before a human is asked to approve an action — not a dashboard a human has
to read, and not a chatbot that acts without evidence or approval.

## Operating Context

Two primary product surfaces:
1. **Command Centre** — where the operation is understood (evidence, records, history).
2. **WhatsApp / chat** — where the operator asks, decides, and acts.

Architecture decision (see `README.md`): Medusa, Akeneo, Pimcore, Activepieces, OPA, flagd,
LangGraph, Amazon, voice, billing, and Kubernetes are excluded as dependencies. Studying their
source for semantics/patterns remains allowed under the OSS-first rule in `CLAUDE.md`; importing
them as dependencies is not.

## Capabilities and Constraints

Phase 0 / 0.5 proves: tenant-scoped canonical commerce entities, connector capability contracts,
guarded connector mutation idempotency, append-only audit events, external ID mapping, merchant
configuration, deterministic policy decisions, Temporal-shaped workflow semantics, a Shopify order
webhook narrow slice, a Chatwoot support conversation narrow slice, supplier ingestion skeleton,
reconciliation divergence handling, Postgres migration/repository implementation, Temporal SDK
workflow/worker implementation, S3-compatible object storage implementation, a Docling extraction
adapter, and a deterministic image processing boundary.

Architectural invariants that constrain all work (see CLAUDE.md): merchant independence, platform
neutrality in canonical/core logic, deterministic-first execution, idempotent guarded mutations,
canonical operating truth, policy/approval boundaries, reconciliation/read-back, tenant isolation,
evidence/auditability, Linux portability.

## Brand Commitments

Existing wordmark and palette (see DESIGN.md) are locked and must be preserved through redesigns —
CLAUDE.md's Design Constitution explicitly forbids discarding the brand to chase a generic "modern
SaaS" look.

## Evidence on Hand

The marketing/demo site uses sandboxed/representative data (seeded prospect-demo sessions, not a
live platform connection) — this must always be stated as such, never presented as a live
integration. See `packages/prospect_demo/` and the honesty constraint in CLAUDE.md's Design
Constitution ("never claim a live platform connection that doesn't exist").

## Product Principles

1. Demonstrate before explaining — show a real operational problem being handled, don't describe one.
2. Evidence beats claims — every number/finding shown must trace to real seeded/live data.
3. One strong, real interaction beats many marketing cards or an animated sequence.
4. Do not look like a generic SaaS dashboard, even when a template's default layout suggests it.
5. Preserve the existing brand identity while rethinking layout/composition around the product story.

## Accessibility & Inclusion

No product-specific accessibility requirement has been established beyond standard WCAG AA
practice (see `design-taste` skill's pre-flight checklist for the working default).
