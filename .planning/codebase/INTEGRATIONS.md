---
last_mapped_commit: ee202cf2d03a25f8a2a597e5a2348729f29a2eca
last_mapped_at: 2026-09-30
---
# External Integrations

**Analysis Date:** 2026-09-30

## APIs & External Services

**Search & Telemetry:**
- Google Search Console API - Verified production service account integration (`sanocea-gsc@sanocea-demo.iam.gserviceaccount.com`) querying `sc-domain:sanocea.com`.
  - SDK/Client: Direct Google OAuth2 Service Account HTTP / REST integration (`packages/seo-stack/src/worker/gscClient.ts` and `apps/api/`)
  - Endpoints: Sites API (`webmasters/v3/sites`), Search Analytics API (`searchconsole/v1/urlTestingTools/mobileFriendlyTest:run`, `searchanalytics/query`)
  - Auth: Credentials file at `/opt/sanocea/repo/config/credentials/google-search-console.json`
- Chrome User Experience Report (CrUX) / PageSpeed Insights API - Core Web Vitals telemetry (LCP, CLS, INP, FCP)
  - Client: `packages/seo-stack/src/auditors/performanceAuditor.ts`
- SERP Intelligence Adapters (Planned / Extensible):
  - Architecture ready for DataForSEO / SerpAPI / ValueSERP adapters for real-time external ranking telemetry across target keywords

**Messaging & Collaboration:**
- WhatsApp Cloud API (Meta Graph API) - Operations transport for human-in-the-loop approvals, anomaly alerts, executive reports, and interactive command console
  - Client: `packages/notifications/whatsapp.py` and `website/src/data/whatsappInteractiveFlow.js`
  - Auth: `WHATSAPP_API_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`
- Gmail Ingress / Google Workspace - Transactional email monitoring and procurement exception detection
  - Client: `packages/gmail_watch/`, `packages/email_ingress/`

**Ecommerce Channels & Connectors:**
- Shopify REST & GraphQL Admin APIs - Catalog, inventory, order, and metafield sync
  - Client: `packages/connector_sdk/shopify/`
- WooCommerce REST API - WordPress / WooCommerce store integration
  - Client: `packages/connector_sdk/woocommerce/`
- Marketplaces (Amazon SP-API, Flipkart) - Inventory feeds and settlement reconciliation
  - Client: `packages/channel_ops/`

## Data Storage

**Databases:**
- SQLite (WAL mode):
  - Connection: `packages/seo-stack/seo_monitoring.sqlite`
  - Client: `better-sqlite3` (`packages/seo-stack/src/persistence/sqlitePersistence.ts`)
  - Tables: `audit_snapshots`, `serp_trajectories`, `remediation_receipts`, `gsc_snapshots`, `search_signals`
- PostgreSQL 17:
  - Connection: `SANOCEA_PG_DSN`
  - Client: `psycopg2-binary` (`packages/domain_contract/persistence/postgres_store.py`)
  - Schema: Multi-tenant tables with mandatory `merchant_id` columns, composite unique indexes, and audit logs (per ADR 0004)

**File Storage:**
- MinIO / S3-compatible object storage:
  - Client: `boto3` (`packages/object_storage/`)
  - Usage: Product catalog media assets, prospect demo evidence packs, generated PDF audit reports

**Caching:**
- In-memory tenant state store (`website/src/data/store.js`) with deterministic cloning and deep freeze
- SQLite WAL read cache for high-frequency dashboard queries

## Authentication & Identity

**Auth Provider:**
- Custom Token & Service Account Authentication:
  - GSC: Google Cloud IAM Service Account JWT with `https://www.googleapis.com/auth/webmasters` scope
  - API: Bearer token authentication in `apps/api/middleware.py` and tenant-scoped session contracts

## Monitoring & Observability

**Error Tracking:**
- Systemd Journald - Standard error stream capture for background services:
  - `journalctl -u sanocea-seo-worker.service -f`
  - `journalctl -u sanocea-api.service -f`

**Logs & Provenance:**
- Structured JSON logs emitted by Sentinel workers and API services
- Truth provenance classification system enforced on all signals:
  - `[OBSERVED]` - Directly returned by external APIs (GSC clicks, impressions, HTTP status)
  - `[CALCULATED]` - Deterministic arithmetic derivations (CTR, position deltas, crawl ratios)
  - `[MODELED]` - External opportunity estimations and projections (clearly segregated)
  - `[REQUIRES_ACCESS]` - Prospect-gated metrics requiring tenant credentials

## CI/CD & Deployment

**Hosting:**
- Production Server: Linux Ubuntu 24.04 (`/opt/sanocea/repo`)
- Web Static Release: `/var/www/sanocea/current` (symlinked timestamped releases)
- Reverse Proxy: Caddy / Nginx serving HTTPS on `sanocea.com` and `www.sanocea.com`

**CI Pipeline:**
- Local atomic verification scripts and regression suites running before production deployment

## Environment Configuration

**Required env vars:**
- `SANOCEA_GSC_CREDENTIALS_PATH`: Path to service account JSON
- `SANOCEA_GSC_PROPERTY`: GSC property URL (e.g., `sc-domain:sanocea.com`)
- `SANOCEA_PG_DSN`: PostgreSQL connection string (when running database-backed API)
- `NODE_ENV`: `production` or `development`

**Secrets location:**
- Filesystem-isolated directory: `/opt/sanocea/repo/config/credentials/` (restricted permissions `0600`, excluded from git via `.gitignore`)

## Webhooks & Callbacks

**Incoming:**
- `/api/v1/webhooks/whatsapp` - Meta WhatsApp webhook receiver
- `/api/v1/webhooks/shopify` - Shopify order, product, and inventory event webhooks

**Outgoing:**
- Meta Graph API HTTP POST - Dispatching interactive alerts and approval requests to WhatsApp operators

---

*Integration audit: 2026-09-30*
