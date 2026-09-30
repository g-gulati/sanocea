---
last_mapped_commit: ee202cf2d03a25f8a2a597e5a2348729f29a2eca
last_mapped_at: 2026-09-30
---
<!-- refreshed: 2026-09-30 -->

# Architecture

**Analysis Date:** 2026-09-30

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Client / Operator Interfaces                           │
├───────────────────────────────┬───────────────────────────────┬─────────────┤
│   Executive Web Console       │   WhatsApp Ops Simulator      │   GSC API   │
│   `website/src/App.jsx`       │   `website/src/components/`   │  Telemetry  │
└───────────────┬───────────────┴───────────────┬───────────────┴───────┬─────┘
                │                               │                       │
                ▼                               ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Autonomous Operations Layer                            │
├───────────────────────────────────────────────┬─────────────────────────────┤
│   Python Commerce OS Engine                   │   Autonomous SEO Sentinel   │
│   `apps/api/`, `packages/policy_engine/`      │   `packages/seo-stack/`     │
│   - Domain Contracts & Invariants             │   - 3-Tier Sentinel Worker  │
│   - Human-in-the-Loop Approvals               │   - SearchSignalsEngine     │
│   - Multi-channel Inventory Reconciliation    │   - Autonomous Remediator   │
└───────────────────────┬───────────────────────┴───────────────┬─────────────┘
                        │                                       │
                        ▼                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Persistence & External Storage                         │
├───────────────────────────────────────────────┬─────────────────────────────┤
│   PostgreSQL 17 (Commerce State)              │   SQLite WAL Mode           │
│   `packages/domain_contract/persistence/`     │   `packages/seo-stack/`     │
│   - Tenant-isolated relational tables         │   - Audit Snapshots Ledger  │
│   - Audit logs & idempotency keys             │   - SERP Trajectory Ledger  │
└───────────────────────────────────────────────┴─────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **SEO Sentinel Daemon** | Periodic multi-tier audit cycle (hourly/daily), GSC sync, and SERP trajectory logging | `packages/seo-stack/src/worker/workerDaemon.ts` |
| **Search Signals Engine** | Truth-provenance signal derivation separating Observed GSC data from Calculated and Modeled insights | `packages/seo-stack/src/signals/searchSignalsEngine.ts` |
| **Autonomous Remediator** | Applies deterministic technical fixes (JSON-LD schemas, canonicals, meta tags) and records verifiable receipts | `packages/seo-stack/src/remediation/autonomousRemediator.ts` |
| **SERP Trajectory Engine** | Tracks keyword ranking movement across historical snapshots without synthetic backfill | `packages/seo-stack/src/serp/serpTracker.ts` |
| **FastAPI Gateway** | REST API endpoints for commerce workflows, tenant configurations, and health checks | `apps/api/main.py` |
| **Domain Contracts** | Pydantic v2 domain models and business invariants across orders, inventory, catalog, and channels | `packages/domain_contract/` |
| **Policy Engine** | Rule evaluation for inventory drift, pricing discrepancies, and approval escalation | `packages/policy_engine/` |
| **Operational Store** | Frontend reactive state manager with deep-freeze tenant isolation and simulation workflows | `website/src/data/store.js` |
| **SEO View & Dashboard** | High-fidelity executive visualization of live GSC telemetry, SEO opportunities, and audit findings | `website/src/components/` |

## Pattern Overview

**Overall:** Dual-Engine Asynchronous Event-Driven Architecture with Strict Truth Provenance.

**Key Characteristics:**
- **Engine Segregation:** The Python backend handles commerce domain logic and multi-channel workflows; the Node/TypeScript engine handles high-throughput crawling, DOM analysis, and GSC search intelligence.
- **Truth Integrity Discipline:** Every metric and signal is classified into one of four immutable epistemological buckets: `[OBSERVED]`, `[CALCULATED]`, `[MODELED]`, or `[REQUIRES_ACCESS]`. Modeled or inferred figures are never conflated with observed API telemetry.
- **Tenant Isolation Invariance:** The flagship tenant `sanocea` operates autonomously with background workers and real credentials. All prospect tenants (Waaree, Carzex, Premium Basket, etc.) operate in quarantine — detection and simulation only, with zero state cross-contamination.

## Layers

**1. Presentation Layer (`website/`):**
- Purpose: Responsive dashboard, interactive WhatsApp simulator, and live executive scorecard.
- Contains: React 19 components, Tailwind/custom styles, operational store.
- Depends on: Local mock state / operational store, and HTTP endpoints.

**2. Autonomous SEO Stack (`packages/seo-stack/`):**
- Purpose: Technical crawling, performance audits, GSC synchronization, and closed-loop remediation.
- Contains: Cheerio crawler, Playwright browser engine, SQLite WAL persistence, signal analyzer.
- Depends on: Google Search Console API, SQLite, local DOM files.

**3. Commerce Engine Layer (`packages/`, `apps/api/`):**
- Purpose: Multi-channel operations, inventory drift resolution, order tracking, and approval rules.
- Contains: Domain entities, repository interfaces, policy rules, and workflow activities.
- Depends on: PostgreSQL (or in-memory repository harness in test mode).

**4. Persistence Layer:**
- Purpose: Durable transactional storage.
- Contains: `seo_monitoring.sqlite` (SQLite with WAL journaling) and PostgreSQL 17.

## Data Flow

### Primary SEO Intelligence Flow

1. **GSC & SERP Harvest:** Sentinel worker invokes `gscClient.ts` to query Search Analytics API for `sc-domain:sanocea.com` (`packages/seo-stack/src/worker/workerDaemon.ts`).
2. **Persistence:** Raw snapshot is written to `seo_monitoring.sqlite` in an atomic WAL transaction (`packages/seo-stack/src/persistence/sqlitePersistence.ts`).
3. **Signal Derivation:** `searchSignalsEngine.ts` processes observed data against configured benchmarks (e.g., Advanced Web Ranking CTR models) to produce structured signals with confidence ratings.
4. **Dashboard Ingestion:** `website/src/components/DashboardView.jsx` and `SeoView.jsx` render the segregated panels:
   - Panel A: Observed GSC Telemetry (11 clicks, 28 impressions, 39.29% CTR, 2.43 avg position).
   - Panel B: Derived Intelligence Signals (conservative interpretation with documented provenance).
   - Panel C: SEO Opportunity Model (explicitly marked as modeled industry opportunity, not observed clicks).

### Commerce Approval Flow

1. **Drift Detection:** Ingress or connector detects pricing or inventory mismatch across channels.
2. **Policy Evaluation:** `packages/policy_engine/` evaluates financial threshold and business impact.
3. **Approval Dispatch:** If threshold exceeded, an approval action is generated and dispatched to the WhatsApp transport (`packages/notifications/`).
4. **Human Decision:** Operator approves via WhatsApp message or Executive Dashboard.
5. **Resolution:** Action status updates atomically in the repository; downstream channel adjustments execute with audit trails.

## Key Abstractions

**SearchSignal:**
- Purpose: Structured representation of an SEO finding or opportunity with complete provenance.
- Contract: `id`, `category`, `provenance` (`OBSERVED` | `CALCULATED` | `MODELED`), `confidence`, `observationWindow`, `sampleSize`, `observedData`, `calculatedMetrics`, `benchmark`, `inference`, `recommendedAction`.
- File: `packages/seo-stack/src/signals/searchSignalsEngine.ts`

**Repository Contract:**
- Purpose: Storage-agnostic persistence boundary allowing transparent switching between PostgresStore and InMemoryStore.
- Files: `packages/domain_contract/persistence/` (per ADR 0002 and ADR 0004).

## Entry Points

- **SEO Worker Daemon:** `packages/seo-stack/dist/src/worker/workerDaemon.js` - Supervised by systemd (`sanocea-seo-worker.service`).
- **SEO Stack CLI:** `packages/seo-stack/dist/src/cli.js` - Standalone audit and fixture runner.
- **FastAPI Application:** `apps/api/main.py` - Supervised by systemd (`sanocea-api.service`).
- **Web SPA:** `website/index.html` -> `website/src/main.jsx` - Bundled by Vite into `/var/www/sanocea/current`.

## Architectural Constraints

- **Single Flagship Autonomous Tenant:** Autonomous background executions and live credential usage are exclusively permitted for the `sanocea` tenant. Prospect tenants must remain strictly isolated and read-only.
- **Truth Integrity Invariance:** No synthetic or modeled data may be presented as observed Search Console or search engine telemetry. When Google privacy thresholds withhold queries (<10 impressions), the UI must explicitly reflect zero query rows.
- **SQLite WAL Concurrency:** Node.js workers and CLI instances connect to `seo_monitoring.sqlite` using Write-Ahead Logging (`PRAGMA journal_mode = WAL;`) with busy timeouts to avoid lock contention.

## Anti-Patterns

### Metric Conflation (Fabricated Telemetry)

- **What happens:** Blending modeled keyword volumes into Google Search Console telemetry tables.
- **Why it's wrong:** Misleads stakeholders into believing the site has thousands of live search clicks when Search Console actually observed 11 clicks.
- **Do this instead:** Visually separate the Observed GSC Layer from the Modeled SEO Opportunity Layer, as enforced in `website/src/components/DashboardView.jsx`.

### Premature Multi-Tenant Background Mutation

- **What happens:** Allowing background workers to apply remediations across prospect tenant environments without explicit tenant credentials or permissions.
- **Why it's wrong:** Risks modifying external assets or leaking state between competitors.
- **Do this instead:** Restrict autonomous remediations strictly to `sanocea` tenant and require human approval gates for all client actions.

---

*Architecture analysis: 2026-09-30*
