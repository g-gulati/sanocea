# Roadmap: SANOCEA Commerce OS

Rewritten 2026-10-02 from `git log` (92 commits, HEAD `f80ea8a`). Anything not in a commit is marked
UNCOMMITTED; deployment state is not recorded here (check the VPS, not this file). Standing rules live in
`CLAUDE.md`, not here.

## Phases

- [x] **Phase 1: Domain contracts & in-memory harness** — Pydantic domain models, tenant-scoped repository, offline deterministic tests (ADR 0001, 0002).
- [x] **Phase 2: Infrastructure validation** — PostgreSQL, MinIO, Temporal worker, Docling; RLS rejected in favour of repository-level isolation (ADR 0003, 0004).
- [x] **Phase 3: Multi-channel connectors** — Shopify/WooCommerce/marketplace connectors, live marketplace connectors, reference-merchant certification (2026-09-16).
- [x] **Phase 4: WhatsApp operations** — approval workflows, Cloud API dispatch, interactive simulator.
- [x] **Phase 5: SEO Sentinel & crawler** — Cheerio + Playwright audits, schema validation, closed-loop remediation.
- [x] **Phase 6: Live GSC telemetry & truth provenance** — service-account GSC sync, SQLite WAL, `[OBSERVED]/[CALCULATED]/[MODELED]` segregation.
- [x] **Phase 6.5: Zero-cost SEO intelligence & single UI** (2026-09-30 → 10-01)
  - Zero-cost SEO backend with persisted scheduler (`8f23587`); SEO bridge authorizes the internal tenant by key class (`d61ece6`).
  - `/demo.html` is the sole UI; `/ui` and `/console.html` retired; live SEO via `GET /demo/seo/overview` (`d9dae78`).
  - Evidence sources added: GA4 read-only (`cdd7e13`), Bing Webmaster incl. URL-index/crawl/issue evidence (`328b70f`).
  - Plain-English audit layer and opportunity stack with brief → draft backend (`cd1c435`, `ee234e9`).
- [x] **Phase 6.6: Autonomous SEO execution loop** (2026-10-01)
  - Autonomy policy: tenant modes, Class A/B/C/D action classes, autonomous approval records, publish eligibility (`28acdbd`, `a7fac2c`, `146aff3`).
  - Actions: `FIX_SITEMAP_ENTRY`, redirect/canonical family, `CHANGE_CANONICAL` through the same policy-gated path (`8585d0d`, `29f0439`, `1cac0b5`).
  - Node→Python executor bridge, policy-gated execution, post-publication verification with learn/rollback/investigate (`cb4d43c`, `a2259be`).
  - Diagnosis raises one precise owner question when the gap is a business fact (`2b6e0df`).
  - Customer-facing lifecycle Found → Concluded → Selected → Policy → Executed → Verified, and Section 5 UI per approved design (`622fa48`, `0caf16c`).
  - First autonomous change recorded: `chg_50549083be05`, canonical trailing slash on `/solutions/marketplace-reconciliation` (`6449acf`).
- [ ] **Self-service prospect demo** — see "In progress" below.
- [ ] **Phase 7: SERP trajectory** — DEFERRED, needs a decision (see below).
- [ ] **Phase 8: GEO / AEO citations** — not started.
- [ ] **Phase 9: Competitive intelligence & backlink index** — not started.

## In progress (UNCOMMITTED in the working tree at time of writing)

- Demo session leasing / prospect tenant work: `packages/prospect_demo/{reset,scenarios,sessions,tenants}.py`, `tests/integration/test_demo_sessions.py`. Per project memory, Slice 1 was done and deployed, Slice 2 is next, and there is a known channel-id collision bug (unfixed).
- Domain/approvals/notifications/product-onboarding edits (`packages/domain_contract/*`, `packages/approvals/service.py`, `packages/notifications/*`, `packages/product_onboarding/*`, `packages/ai/provider.py`).
- Website: `website/src/main.jsx`, `Walkthrough.jsx`, `chat.css`, `index.html`, wordmark; `CLAUDE.md` and `design-taste` skill edits.
- Untracked design previews under `.frontend-design/` and various marketing assets (`Reels/`, `Carousel 01/`, audit sheets).

Review and commit or discard these before treating the roadmap as current.

## Needs a decision

**Phase 7 (SERP trajectory).** As originally written it relies on DataForSEO or SerpAPI. The SEO stack
has since been built under a zero-cost-only rule (`8f23587`; a fabricated SERP seed was quarantined; GSC
returns no query-level rows for sanocea). Options: (a) drop Phase 7, (b) redefine it on free sources only,
(c) record an ADR in `docs/adr/` explicitly allowing a paid provider. Until decided, do not plan it.

## Deferred / backlog

- Free Audit website feature — skipped 2026-09-24; spec in project memory.
- Capabilities that existed only in the retired UIs are API-only: `docs/architecture/retired-ui/FUTURE_UI_MIGRATION_BACKLOG.md`.
- SEO drift detection — deferred (SEO OSS review, 2026-10-01).
- ADR 0004 revisit: re-evaluate RLS once a trusted request context exists (demo-session auth may qualify; unverified).
