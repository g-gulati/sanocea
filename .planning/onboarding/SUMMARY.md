# GSD Brownfield Onboarding Summary: SANOCEA

**Date:** 2026-09-30
**Onboarding Mode:** Brownfield Ingest & Codebase Mapping
**Runtime Environment:** Linux Ubuntu 24.04 (`/opt/sanocea/repo`)

---

## 1. Executive Summary

SANOCEA has successfully onboarded into the Open-GSD Spec-Driven Development (SDD) ecosystem (`@opengsd/gsd-core@1.15.0`). The existing dual-engine codebase — comprising a Python 3.11 FastAPI Commerce OS backend, a Node.js 20 TypeScript Autonomous SEO Sentinel Stack, and a Vite React 19 SPA console — has been fully mapped, audited, and aligned with GSD planning standards.

All 7 canonical codebase intelligence documents have been generated and stamped against git HEAD with drift detection baselines. 4 pre-existing Architectural Decision Records (ADRs) have been formally ingested with zero blockers, and complete project planning artifacts (`PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`) are now actively tracking system health.

---

## 2. Codebase Intelligence Artifacts

The following 7 canonical documents have been authored and stamped in `.planning/codebase/`:

| Document | Focus | Lines | Scope Summary |
|----------|-------|-------|---------------|
| `STACK.md` | Tech Stack | 92 | TypeScript 5.3+, Node.js 20+, Python 3.11+, React 19, SQLite WAL, PostgreSQL 17, Vite 6, systemd. |
| `INTEGRATIONS.md` | External APIs | 107 | Google Search Console API (service account auth), CrUX, WhatsApp Cloud API, Shopify/Woo connectors. |
| `ARCHITECTURE.md` | Architecture | 140 | Dual-engine pattern, data flow, truth provenance layers, tenant isolation, systemd services. |
| `STRUCTURE.md` | Directory Layout | 164 | `apps/`, `packages/`, `website/`, `infra/`, `.planning/` directory map, file naming rules, and placement guide. |
| `CONVENTIONS.md` | Standards | 95 | Epistemological truth rules (`[OBSERVED]`, `[CALCULATED]`, `[MODELED]`), tenant isolation boundaries. |
| `TESTING.md` | Quality & Tests | 129 | Node.js native test runner (`node --test`), 125 passing tests, 18 regression invariants, mock vs live test policy. |
| `CONCERNS.md` | Risks & Debt | 56 | GSC privacy query withholding (<10 imps), crawl budget latency, backlink index gap, multi-channel drift. |

---

## 3. ADR Ingestion & Synthesis

Four Architectural Decision Records from `docs/adr/` were classified and integrated into `.planning/intel/`:
1. **ADR 0001 (Python Package Layout):** Importable packages use underscores (`domain_contract`).
2. **ADR 0002 (Phase 0 Storage Boundary):** Repository abstraction with in-memory harness for deterministic unit tests.
3. **ADR 0003 (Phase 0.5 Infra Validation):** Concrete backends (PostgresStore, Temporal, MinIO) validated behind domain contracts.
4. **ADR 0004 (Postgres RLS Decision):** RLS rejected in favor of explicit `merchant_id` schema constraints and repository filtering.

**Conflict Analysis:** Zero blockers, zero warnings. Full synthesis recorded in `.planning/INGEST-CONFLICTS.md` and `.planning/intel/SYNTHESIS.md`.

---

## 4. Verification & Operational Status

- **Node.js Test Suites:**
  - `@sanocea/seo-stack`: 73/73 tests passing.
  - `website`: 52/52 tests passing.
  - Total: 125 tests passing (0 failures).
- **Background Supervision:**
  - `sanocea-seo-worker.service`: `active` (hourly/daily audit loop + live GSC Search Analytics sync).
  - `sanocea-api.service`: `active`.
- **Live GSC Integration:**
  - Property: `sc-domain:sanocea.com`
  - Service Account: `sanocea-gsc@sanocea-demo.iam.gserviceaccount.com`
  - Verified 28-day Telemetry: 11 clicks, 28 impressions, 39.29% CTR, 2.43 avg position, 0 query rows (privacy withholding).

---

## 5. Next Steps

The project state is set to **Ready to Plan** for **Phase 7: SERP Trajectory Engine & External Provider Adapters**, aiming to bring real-time keyword-level rank velocity and third-party SERP adapter integration into the autonomous dashboard.
