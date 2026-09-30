---
last_mapped_commit: ee202cf2d03a25f8a2a597e5a2348729f29a2eca
last_mapped_at: 2026-09-30
---
# Codebase Structure

**Analysis Date:** 2026-09-30

## Directory Layout

```
/opt/sanocea/repo/
├── apps/                        # Application entry points and servers
│   ├── api/                     # FastAPI backend application & routers
│   ├── command_center/          # Operations console backend services
│   └── dashboard/               # Administrative views and handlers
├── packages/                    # Domain packages and shared engines
│   ├── ai/                      # AI orchestration and prompt templates
│   ├── approvals/               # Human-in-the-loop approval workflows
│   ├── audit/                   # Audit logging and trail persistence
│   ├── authn/                   # Authentication and API token verification
│   ├── channel_ops/             # Marketplace channel connectors & feeds
│   ├── connector_sdk/           # External commerce adapters (Shopify, Woo)
│   ├── content_engine/          # Content generation and strategy pipeline
│   ├── domain_contract/        # Canonical Pydantic v2 domain schemas & DB
│   ├── email_ingress/           # Transactional email ingestion
│   ├── exceptions/              # Operational drift and error classifiers
│   ├── finance/                 # Financial reconciliation and ledger
│   ├── gmail_watch/             # Gmail Pub/Sub webhook listener
│   ├── idempotency/             # Distributed idempotency key checks
│   ├── metrics/                 # Business metric aggregators
│   ├── notifications/           # WhatsApp & email alert dispatchers
│   ├── object_storage/          # S3 / MinIO client wrapper
│   ├── onboarding/              # Merchant onboarding automation
│   ├── outreach/                # Cold email & prospect campaign manager
│   ├── policy_engine/           # Business rule validation engine
│   ├── post_order/              # Order lifecycle & fulfillment tracking
│   ├── procurement/             # Purchase order & supplier workflows
│   ├── product_onboarding/      # Catalog enrichment and normalization
│   ├── prospect_demo/           # Interactive multi-company demo state
│   ├── reference_merchant/      # Sample tenant test fixtures
│   ├── runtime/                 # Process management and environment config
│   ├── seo-stack/               # Autonomous SEO Sentinel & Crawler engine
│   ├── support/                 # Customer support ticket escalation
│   └── tally_integration/       # Tally ERP accounting sync
├── website/                     # Frontend Vite + React 19 web application
│   ├── src/                     # React application source code
│   │   ├── components/          # Dashboard, SEO, and simulator UI views
│   │   ├── data/                # Operational stores and demo datasets
│   │   └── App.jsx              # Main SPA router and shell
│   ├── tests/                   # Native Node.js test runner suites
│   ├── public/                  # Static assets and favicons
│   ├── dist/                    # Compiled production build
│   └── vite.config.js           # Vite build configuration
├── infra/                       # Infrastructure configuration and deployment
│   ├── systemd/                 # Production systemd unit files & examples
│   ├── docker/                  # Local development container templates
│   ├── temporal/                # Temporal workflow definitions & worker
│   └── woocommerce-dev/         # Local WooCommerce testing fixture
├── docs/                        # Project documentation & architectural records
│   └── adr/                     # Architectural Decision Records (0001-0004)
├── .planning/                   # GSD Core specification & planning directory
│   ├── codebase/                # 7 canonical codebase intelligence maps
│   ├── onboarding/              # Brownfield onboarding records & summary
│   ├── phases/                  # Milestone phase definitions
│   └── config.json              # Project GSD configuration
├── tests/                       # Python test suites (unit, integration, e2e)
├── pyproject.toml               # Python dependencies and pytest configuration
└── README.md                    # Repository documentation
```

## Directory Purposes

**`packages/seo-stack/`:**
- Purpose: High-performance autonomous SEO Sentinel, crawler engine, and search intelligence.
- Contains: TypeScript modules for technical, ecommerce, and GEO audits, SQLite WAL persistence, SERP trajectory engine, and systemd daemon.
- Key files:
  - `packages/seo-stack/src/worker/workerDaemon.ts`: Main background loop.
  - `packages/seo-stack/src/worker/gscClient.ts`: Live Google Search Console API client.
  - `packages/seo-stack/src/signals/searchSignalsEngine.ts`: Truth-provenance signal derivations.
  - `packages/seo-stack/src/persistence/sqlitePersistence.ts`: SQLite WAL database queries.
  - `packages/seo-stack/src/remediation/autonomousRemediator.ts`: Closed-loop technical fixes.

**`website/`:**
- Purpose: Vite + React 19 single-page application deployed to `/var/www/sanocea/current`.
- Contains: Executive dashboard, interactive WhatsApp simulator, SEO intelligence views, and operational store.
- Key files:
  - `website/src/App.jsx`: Main view switching and navigation.
  - `website/src/components/DashboardView.jsx`: Flagship executive scorecard, GSC observed metrics, and segregated modeled opportunities.
  - `website/src/components/SeoView.jsx`: Detailed technical SEO audit, SERP trajectory tracker, and remediation logs.
  - `website/src/data/store.js`: Deeply frozen tenant-isolated reactive operational store.
  - `website/src/data/tenantSeoRegistry.js`: Multi-tenant SEO configurations.

**`apps/api/` & `packages/domain_contract/`:**
- Purpose: Python FastAPI REST application and canonical domain contracts.
- Contains: Pydantic v2 models, repository interfaces, and HTTP endpoints.
- Key files:
  - `apps/api/main.py`: FastAPI server setup and routes.
  - `packages/domain_contract/models/`: Pydantic domain models.
  - `packages/domain_contract/persistence/`: PostgreSQL and in-memory repository abstractions.

**`infra/systemd/`:**
- Purpose: Production service supervisors on Ubuntu 24.04.
- Contains:
  - `infra/systemd/sanocea-seo-worker.service`: Active background Sentinel worker.
  - `infra/systemd/sanocea-api.service.example`: FastAPI service definition.

## Key File Locations

**Entry Points:**
- `packages/seo-stack/src/worker/workerDaemon.ts`: Background SEO Sentinel daemon.
- `packages/seo-stack/src/cli.ts`: SEO CLI executable.
- `apps/api/main.py`: Python FastAPI backend entry.
- `website/src/main.jsx`: React web application entry.

**Configuration:**
- `config/credentials/google-search-console.json`: Production GSC service account credentials.
- `packages/seo-stack/tsconfig.json`: TypeScript configuration.
- `website/vite.config.js`: Vite build configuration.
- `pyproject.toml`: Python project configuration.
- `.planning/config.json`: GSD workflow configuration.

**Testing:**
- `packages/seo-stack/dist/tests/*.test.js`: 73 passing Node.js native tests for SEO stack.
- `website/tests/*.test.js`: 52 passing Node.js native tests for website & store.
- `tests/unit/`: Pytest unit tests for Python packages.

## Naming Conventions

**Files:**
- TypeScript/JavaScript: `camelCase.ts` or `PascalCase.jsx` (components).
- Python: `snake_case.py`.
- Documentation & ADRs: `000X-short-description.md` or `UPPERCASE.md` (GSD codebase maps).

**Directories:**
- Python packages: `snake_case` (e.g., `domain_contract`, `policy_engine`).
- Node packages: `kebab-case` (e.g., `seo-stack`).

## Where to Add New Code

**New SEO Auditor or Check:**
- Implementation: `packages/seo-stack/src/auditors/` (e.g., `newAuditor.ts`).
- Registration: Export from `packages/seo-stack/src/index.ts` and add to `runAudit()` in `packages/seo-stack/src/crawler/engine.ts`.
- Tests: Add corresponding test suite in `packages/seo-stack/tests/`.

**New Intelligence Signal:**
- Implementation: Add derivation logic and benchmark rules to `packages/seo-stack/src/signals/searchSignalsEngine.ts`.
- Tests: Verify truth provenance in `packages/seo-stack/tests/searchSignalsEngine.test.ts`.

**New Commerce Domain Entity or Rule:**
- Contract: Add Pydantic model in `packages/domain_contract/models/`.
- Policy: Add evaluation rules in `packages/policy_engine/`.
- Tests: Add unit tests in `tests/unit/`.

**New Frontend UI Section:**
- Implementation: Create component in `website/src/components/`.
- Data Binding: Bind to operational store in `website/src/data/store.js`.
- Tests: Add DOM and behavior regression tests in `website/tests/`.

## Special Directories

- `packages/seo-stack/seo_monitoring.sqlite`: SQLite WAL database storing real-time audit snapshots, SERP trajectories, and remediation receipts (committed schema, ignored WAL/SHM files).
- `/opt/sanocea/repo/config/credentials/`: Secret credentials directory containing Google Service Account JSON (strictly `.gitignore`'d).
- `website/dist/`: Production Vite build artifact, symlinked to `/var/www/sanocea/current` during release.

---

*Structure analysis: 2026-09-30*
