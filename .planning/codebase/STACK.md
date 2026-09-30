---
last_mapped_commit: ee202cf2d03a25f8a2a597e5a2348729f29a2eca
last_mapped_at: 2026-09-30
---
# Technology Stack

**Analysis Date:** 2026-09-30

## Languages

**Primary:**
- TypeScript 5.3+ (`packages/seo-stack/`) - Autonomous SEO Sentinel daemon, crawler engine, SERP trajectory engine, SQLite WAL persistence, CLI tooling
- JavaScript (ES modules) / JSX (`website/`) - Responsive SPA console, WhatsApp interactive simulator, SEO intelligence views, operational store
- Python 3.11+ (`apps/api/`, `packages/*`) - Commerce OS core, domain contracts, policy engine, approval workflow, content engine, Temporal workflows

**Secondary:**
- SQL (SQLite & PostgreSQL 17 dialects) - Schema definitions, WAL transactional queries, tenant isolation indexes
- HTML5 / CSS3 (Tailwind-like utility tokens) - Vite SPA presentation layer

## Runtime

**Environment:**
- Node.js v20.11+ (`packages/seo-stack/`, `website/`) - Native Node.js test runner (`node --test`), ES module native execution
- Python 3.11 (`apps/api/`, `packages/`) - Managed via `uv` and virtual environment at `/opt/sanocea/repo/.venv`
- Systemd (`infra/systemd/`) - Process supervisor for production background daemons (`sanocea-seo-worker.service`, `sanocea-api.service`)

**Package Manager:**
- npm (Node.js) - Monorepo/sub-package manifests (`packages/seo-stack/package.json`, `website/package.json`), lockfiles present (`package-lock.json`)
- uv / pip (Python) - Managed via `pyproject.toml` and `.venv/`

## Frameworks

**Core:**
- FastAPI (`apps/api/`) - High-performance async REST API framework for Commerce OS
- React 19 (`website/`) - Component-based SPA dashboard and interactive simulator
- Cheerio 1.0 (`packages/seo-stack/`) - Fast server-side HTML DOM parser for technical SEO audits
- Playwright 1.63 (`packages/seo-stack/`) - Headless Chromium browser automation for dynamic DOM rendering and live visual audits
- Better-SQLite3 12.11 (`packages/seo-stack/`) - High-throughput synchronous SQLite driver with WAL mode

**Testing:**
- Node.js Native Test Runner (`node --test`) - Fast, zero-dependency test runner executing 125 total passing tests across `packages/seo-stack/` (73 tests) and `website/` (52 tests)
- Pytest (`tests/unit`, `tests/integration`, `tests/e2e`) - Test framework for Python backend contracts and workflows

**Build/Dev:**
- Vite 6.1 (`website/vite.config.js`) - Modern frontend bundler and HMR dev server
- TypeScript Compiler `tsc` (`packages/seo-stack/tsconfig.json`) - Strict TypeScript build compilation

## Key Dependencies

**Critical:**
- `better-sqlite3` (`packages/seo-stack/src/persistence/sqlitePersistence.ts`) - Provides ACID SQLite WAL storage for SEO audit snapshots, SERP movements, and remediation receipts
- `cheerio` & `playwright` (`packages/seo-stack/src/crawler/`) - Multi-mode crawler executing static HTML DOM audits and headless JS execution
- `pydantic>=2` (`packages/domain_contract/`) - Strict data validation contracts across all commerce domains
- `fastapi` (`apps/api/main.py`) - API routing, middleware, and request validation
- `framer-motion` (`website/src/`) - UI animations and interactive state transitions

**Infrastructure:**
- `temporalio` (`infra/temporal/`) - Orchestrates distributed multi-step commerce workflows and long-running jobs
- `psycopg2-binary` (`packages/domain_contract/persistence/`) - PostgreSQL adapter for production transactional storage
- `boto3` (`packages/object_storage/`) - S3-compatible object storage client for media and PDF generation
- `google-api-python-client` & `google-auth-oauthlib` - Google APIs client library for service account auth

## Configuration

**Environment:**
- Configured via environment variables and systemd service environments
- Production SEO Worker environment:
  - `SANOCEA_GSC_CREDENTIALS_PATH=/opt/sanocea/repo/config/credentials/google-search-console.json`
  - `SANOCEA_GSC_PROPERTY=sc-domain:sanocea.com`
  - `NODE_ENV=production`
- Backend environment:
  - `SANOCEA_PG_DSN` - PostgreSQL connection string
  - `SANOCEA_ENV` - Environment identifier

**Build:**
- `website/vite.config.js` - Vite SPA configuration
- `packages/seo-stack/tsconfig.json` - TypeScript compiler options (`module: ESNext`, `moduleResolution: NodeNext`, `strict: true`)
- `pyproject.toml` - Python project metadata, dependencies, and pytest configuration

## Platform Requirements

**Development:**
- Linux or POSIX environment with Node.js 20+, Python 3.11+, and uv/npm
- Local SQLite3 development storage

**Production:**
- Linux (Ubuntu 24.04 LTS), systemd supervision
- Caddy / Nginx reverse proxy serving static SPA from `/var/www/sanocea/current` and proxying API/Worker endpoints
- Persistent paths:
  - Repository: `/opt/sanocea/repo`
  - Credentials: `/opt/sanocea/repo/config/credentials/google-search-console.json`
  - SQLite WAL: `/opt/sanocea/repo/packages/seo-stack/seo_monitoring.sqlite`

---

*Stack analysis: 2026-09-30*
