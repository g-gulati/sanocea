# Requirements: SANOCEA Commerce OS & SEO Sentinel Stack

**Defined:** 2026-09-30
**Core Value:** Verifiable, evidence-backed autonomous commerce operations and search visibility with absolute truth integrity — zero fabricated or conflated metrics.

## Completed Requirements (Milestones 1–6)

### Domain Contracts & Storage (M1 & M2)
- [x] **REQ-COM-01**: Domain models use Pydantic v2 with strict type validation (`packages/domain_contract/models/`).
- [x] **REQ-COM-02**: Tenant-aware repository abstraction with deterministic in-memory test backend (ADR 0002).
- [x] **REQ-COM-03**: Real PostgresStore backend with mandatory `merchant_id` schema columns and isolation tests (ADR 0003, ADR 0004).
- [x] **REQ-COM-04**: Temporal Python SDK integration for durable multi-step workflows (`infra/temporal/`).
- [x] **REQ-COM-05**: MinIO / S3 object storage integration via Boto3 (`packages/object_storage/`).

### Multi-Channel Connectors & Operations (M3 & M4)
- [x] **REQ-CH-01**: Connector SDK with Shopify and WooCommerce adapters (`packages/connector_sdk/`).
- [x] **REQ-CH-02**: Channel degradation detection and automated reconnection cycle.
- [x] **REQ-CH-03**: Human-in-the-loop approval workflow with WhatsApp Cloud API notifications (`packages/approvals/`, `packages/notifications/`).
- [x] **REQ-CH-04**: Multi-tenant operational store with deep-freeze cloning and state reset (`website/src/data/store.js`).
- [x] **REQ-CH-05**: Interactive WhatsApp ops simulator supporting numbered menu interaction and approval callbacks.

### Autonomous SEO Sentinel & Audit Engine (M5)
- [x] **REQ-SEO-01**: Multi-mode crawler supporting Cheerio static DOM parsing and Playwright headless Chromium execution (`packages/seo-stack/src/crawler/`).
- [x] **REQ-SEO-02**: Extended structured data validation for WebSite SearchAction, FAQPage, Article, and Product schema (`packages/seo-stack/src/auditors/schemaAuditor.ts`).
- [x] **REQ-SEO-03**: Core Web Vitals and image intelligence (missing dimensions, legacy formats, oversized assets) (`packages/seo-stack/src/auditors/performanceAuditor.ts`).
- [x] **REQ-SEO-04**: Faceted navigation & combinatorial URL parameter explosion classifier (`packages/seo-stack/src/auditors/parameterClassifier.ts`).
- [x] **REQ-SEO-05**: Outbound link health auditing and broken link detection (`packages/seo-stack/src/auditors/linkAuditor.ts`).
- [x] **REQ-SEO-06**: Closed-loop technical remediator with DOM patch verification and SQLite WAL receipt generation (`packages/seo-stack/src/remediation/autonomousRemediator.ts`).

### Live Search Console & Truth Provenance (M6)
- [x] **REQ-GSC-01**: Live Google Search Console service account integration (`sanocea-gsc@sanocea-demo.iam.gserviceaccount.com`) querying `sc-domain:sanocea.com`.
- [x] **REQ-GSC-02**: Sites API permission verification confirming "full" permission.
- [x] **REQ-GSC-03**: Search Analytics API query pipeline returning HTTP 200 with live 28-day telemetry snapshot (11 clicks, 28 impressions, 39.29% CTR, 2.43 avg position).
- [x] **REQ-GSC-04**: Truth Provenance Model with 4 explicit epistemological categories: `[OBSERVED]`, `[CALCULATED]`, `[MODELED]`, `[REQUIRES_ACCESS]`.
- [x] **REQ-GSC-05**: Zero query rows handling with explicit explanation of GSC privacy threshold withholding (<10 impressions).
- [x] **REQ-GSC-06**: Absolute segregation of Observed GSC Telemetry from Modeled SEO Opportunity tables in UI and datasets.
- [x] **REQ-GSC-07**: SQLite WAL persistence for crawl snapshots, SERP trajectories, and remediation receipts (`packages/seo-stack/seo_monitoring.sqlite`).
- [x] **REQ-GSC-08**: Background systemd Sentinel supervision (`sanocea-seo-worker.service`).

## Active & Upcoming Requirements (Milestones 7–9)

### SERP Movement & Rank Tracking (M7)
- [ ] **REQ-SERP-01**: Third-party SERP provider adapter (e.g. DataForSEO / SerpAPI) to fetch live Google SERP positions for target keywords independently of GSC query rows.
- [ ] **REQ-SERP-02**: Daily SERP position tracking with start-of-day vs current-day rank movement, position delta, and trajectory momentum.
- [ ] **REQ-SERP-03**: Keyword intent classification (commercial, transactional, informational, navigational) and semantic clustering.
- [ ] **REQ-SERP-04**: Interactive SERP trajectory visualization showing historical progression without fabricated backfill.

### Generative Engine & Answer Engine Optimization (M8)
- [ ] **REQ-AEO-01**: Tracking of citation presence across AI search engines: Perplexity, ChatGPT Search, and Google AI Overviews.
- [ ] **REQ-AEO-02**: Automated compliance auditing of `robots.txt` AI crawler directives (GPTBot, ClaudeBot, CCBot, PerplexityBot).
- [ ] **REQ-AEO-03**: Generation and validation of `llms.txt` and `llms-full.txt` standards for clean LLM ingestion.
- [ ] **REQ-AEO-04**: FAQ and structured Q&A schema optimization targeting featured snippets and conversational answers.

### Competitive & Backlink Intelligence (M9)
- [ ] **REQ-COMP-01**: Competitor sitemap monitoring and shared-keyword rank comparison.
- [ ] **REQ-COMP-02**: Commercial backlink index integration for domain rating and referring domain tracking.
- [ ] **REQ-COMP-03**: Automated gap analysis identifying competitor-held SERP real estate.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Synthetic Query Generation | Falsifies Search Console telemetry when Google privacy threshold withholds queries. |
| Background Mutation on Prospect Tenants | Modifying external customer sites without authorization violates security boundaries. |
| Conflated Metric Display | Presenting modeled industry search volume as observed site traffic destroys credibility. |
| Instantaneous Ranking Guarantees | Search engines have crawl and re-indexing latency that software cannot bypass. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| REQ-COM-01 – REQ-COM-05 | Phase 1 & 2 | Complete |
| REQ-CH-01 – REQ-CH-05 | Phase 3 & 4 | Complete |
| REQ-SEO-01 – REQ-SEO-06 | Phase 5 | Complete |
| REQ-GSC-01 – REQ-GSC-08 | Phase 6 | Complete |
| REQ-SERP-01 – REQ-SERP-04 | Phase 7 | Active |
| REQ-AEO-01 – REQ-AEO-04 | Phase 8 | Planned |
| REQ-COMP-01 – REQ-COMP-03 | Phase 9 | Planned |
