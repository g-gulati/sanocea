# SANOCEA Autonomous Commerce OS & SEO Sentinel Stack

## What This Is

SANOCEA is an Autonomous Commerce Operating System and Enterprise Search Intelligence Stack for modern multi-channel retail. It orchestrates inventory, pricing, and exception reconciliation across marketplaces and ecommerce stores while autonomously monitoring, auditing, and remediating technical SEO, ecommerce schema, and Generative Engine Optimization (GEO/AEO) visibility with live Google Search Console telemetry.

## Core Value

Verifiable, evidence-backed autonomous commerce operations and search visibility with absolute truth integrity — zero fabricated or conflated metrics.

## Business Context

- **Customer**: Mid-market and enterprise multi-channel ecommerce merchants, brand manufacturers, and digital retail operations teams.
- **Revenue model**: Tiered SaaS subscription based on managed GMV, channel SKU volume, and automated search crawl footprint.
- **Success metric**: 100% verified technical audit compliance, 0 undetected inventory drift exceptions, and measurable organic search visibility.
- **Strategy notes**: Flagship controlled case study on `sanocea.com` demonstrates autonomous closed-loop capability before rollout to enterprise tenants.

## Requirements

### Validated

- [x] **M1: Domain Contract Foundation** — Canonical Pydantic schemas, tenant repository interface, and in-memory test harness (ADR 0001, ADR 0002).
- [x] **M2: Infrastructure Validation** — PostgreSQL persistence, MinIO S3 object storage, Temporal distributed workflow engine, and Docling document extraction (ADR 0003, ADR 0004).
- [x] **M3: Multi-Channel Connectors** — Shopify and WooCommerce connector SDK adapters, marketplace inventory sync, and channel degradation recovery.
- [x] **M4: WhatsApp Operations Transport** — Meta Cloud API integration, executive alert dispatch, interactive approval console, and multi-tenant simulator.
- [x] **M5: Autonomous SEO Sentinel Stack** — Multi-tier crawler (Cheerio + Playwright), JSON-LD validator, faceted parameter classifier, and closed-loop technical remediator.
- [x] **M6: Live GSC Integration & Truth Provenance** — Production service account auth (`sanocea-gsc@sanocea-demo.iam.gserviceaccount.com`), Sites API validation, Search Analytics pipeline for `sc-domain:sanocea.com`, SQLite WAL ledger, and strict epistemological segregation (`[OBSERVED]`, `[CALCULATED]`, `[MODELED]`).

### Active

- [ ] **M7: SERP Trajectory & External Provider Adapters** — Real-time keyword ranking tracking via third-party SERP provider adapters (DataForSEO / SerpAPI) to bridge the GSC privacy withholding threshold.
- [ ] **M8: AEO & GEO Answer Engine Visibility** — Generative AI citation tracking across Perplexity, ChatGPT Search, and Google AI Overviews, with automated `llms.txt` and AI crawler directive enforcement.
- [ ] **M9: Autonomous Multi-Channel Expansion** — Self-healing channel inventory drift and automated catalog onboarding at enterprise scale.

### Out of Scope

- **Synthesizing Query Rows**: Fabricating or backfilling query-level telemetry when Google Search Console withholds rows under the privacy threshold (<10 impressions).
- **Prospect Background Mutation**: Autonomous background remediation on prospect/quarantined tenants (Waaree Energies, Carzex, etc.) without explicit tenant credentials.
- **Metric Conflation**: Blending modeled industry keyword volumes or third-party opportunity estimates into observed GSC search console telemetry.

## Context

- **Brownfield Codebase**: High-performance dual-engine architecture combining Python 3.11 FastAPI backend (`apps/api/`, `packages/*`) with Node.js 20 TypeScript autonomous SEO stack (`packages/seo-stack/`) and Vite React 19 SPA (`website/`).
- **Production Environment**: Ubuntu 24.04 LTS host at `/opt/sanocea/repo`, production web release at `/var/www/sanocea/current`, active systemd services (`sanocea-seo-worker.service`, `sanocea-api.service`).
- **Verified Telemetry Baseline**: 28-day live GSC baseline for `sc-domain:sanocea.com` establishing 11 clicks, 28 impressions, 39.29% CTR, 2.43 average position, and 0 query rows (privacy withholding).
- **Test Baseline**: 125 total passing native Node.js tests (73 in `@sanocea/seo-stack`, 52 in `website`), plus pytest backend unit suites.

## Constraints

- **Epistemological Discipline**: All analytical data must carry explicit provenance tags (`[OBSERVED]`, `[CALCULATED]`, `[MODELED]`, `[REQUIRES_ACCESS]`).
- **Tenant Isolation**: Only the `sanocea` tenant has autonomous execution privileges. All demo/prospect tenants operate in quarantined read-only mode.
- **Search Engine Latency**: Respect the 5-phase progression (Remediated -> Declared -> Discovered -> Evaluated -> Surfaced); never claim instantaneous SERP rank changes from code edits.
- **Storage Boundaries**: PostgreSQL for transactional commerce state; SQLite WAL for local high-throughput SEO monitoring.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| **ADR 0001**: Python Package Layout | Use underscores (`domain_contract`) for importable Python modules | ✓ Good |
| **ADR 0002**: Storage Boundary | Repository interface with in-memory harness for deterministic testing | ✓ Good |
| **ADR 0003**: Infra Validation | Real backends (Postgres, Temporal, MinIO) validated behind domain contracts | ✓ Good |
| **ADR 0004**: Reject PostgreSQL RLS | Single application DB role; tenant isolation enforced via schema constraints & repository filtering | ✓ Good |
| **Truth Provenance Architecture** | Strict visual and logical segregation between GSC observed telemetry and modeled opportunities | ✓ Good |
| **Single Autonomous Flagship** | Restrict autonomous background mutations to `sanocea` tenant to prevent unauthorized external changes | ✓ Good |

---
*Last updated: 2026-09-30 after GSD Core Brownfield Onboarding*
