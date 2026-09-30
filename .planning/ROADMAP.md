# Roadmap: SANOCEA Autonomous Commerce OS & SEO Sentinel Stack

## Overview

SANOCEA's journey transitions from foundational commerce domain contracts and infrastructure validation into an autonomous, evidence-backed SEO Sentinel stack with verified Google Search Console integration, evolving toward full RankCommand-style autonomous SEO feature parity.

## Phases

- [x] **Phase 1: Domain Contracts & In-Memory Harness** - Foundation domain models, repository abstraction, and deterministic test proof (ADR 0001, ADR 0002).
- [x] **Phase 2: Production Infrastructure Validation** - PostgreSQL persistence, MinIO S3 object storage, Temporal Python worker, and Docling document extraction (ADR 0003, ADR 0004).
- [x] **Phase 3: Multi-Channel Connectors & Operational Store** - Shopify/WooCommerce connector SDK, marketplace feeds, and reactive operational store.
- [x] **Phase 4: WhatsApp Operations & Interactive Simulator** - Human-in-the-loop approval workflows, WhatsApp Cloud API alert dispatch, and 5-tenant simulation console.
- [x] **Phase 5: Autonomous SEO Sentinel & Crawler Engine** - Technical DOM auditing (Cheerio + Playwright), structured data validation, parameter explosion filtering, and closed-loop remediation.
- [x] **Phase 6: Live GSC Telemetry & Truth Provenance Integration** - Verified service account authentication, live Search Analytics pipeline for `sc-domain:sanocea.com`, SQLite WAL persistence, systemd daemon, and strict 4-way epistemological segregation.
- [ ] **Phase 7: SERP Trajectory Engine & External Provider Adapters** - Real-time keyword ranking tracking via third-party SERP provider adapters (DataForSEO / SerpAPI) to bridge the GSC privacy withholding threshold, daily position movement (start vs current), and velocity analytics.
- [ ] **Phase 8: Generative Engine Optimization (GEO) & AEO Citations** - Tracking citation visibility across Perplexity, ChatGPT Search, and Google AI Overviews, with automated `llms.txt` generation and AI bot directive enforcement.
- [ ] **Phase 9: Competitive Intelligence & External Backlink Index** - Competitor sitemap monitoring, shared keyword gap analysis, and commercial backlink API integration for domain authority tracking.

## Phase Details

### Phase 1: Domain Contracts & In-Memory Harness (COMPLETE)
**Goal**: Establish core Pydantic domain models and tenant-isolated repository boundaries with deterministic unit tests.
**Depends on**: Initial codebase
**Requirements**: REQ-COM-01, REQ-COM-02
**Success Criteria**:
  1. All domain models enforce strict Pydantic v2 schemas.
  2. In-memory repository allows 100% offline deterministic test execution without database credentials.
**Status**: Completed & Archived.

### Phase 2: Production Infrastructure Validation (COMPLETE)
**Goal**: Validate real infrastructure backends behind domain contracts.
**Depends on**: Phase 1
**Requirements**: REQ-COM-03, REQ-COM-04, REQ-COM-05
**Success Criteria**:
  1. PostgresStore implements repository interface with mandatory `merchant_id` tenant isolation.
  2. Temporal workflows orchestrate distributed operations.
  3. MinIO S3 client handles object storage.
**Status**: Completed & Archived.

### Phase 3: Multi-Channel Connectors & Operational Store (COMPLETE)
**Goal**: Provide connector abstractions for Shopify, WooCommerce, and marketplaces with a reactive frontend store.
**Depends on**: Phase 2
**Requirements**: REQ-CH-01, REQ-CH-02, REQ-CH-04
**Success Criteria**:
  1. Channel degradation and reconnection cycles are test-verified.
  2. Frontend operational store isolates tenant state with deep-freeze cloning.
**Status**: Completed & Archived.

### Phase 4: WhatsApp Operations & Interactive Simulator (COMPLETE)
**Goal**: Enable mobile operator approvals via WhatsApp Cloud API and web interactive simulator.
**Depends on**: Phase 3
**Requirements**: REQ-CH-03, REQ-CH-05
**Success Criteria**:
  1. WhatsApp alert dispatch triggers on policy threshold breach.
  2. Numbered menu choices and approval buttons synchronize state across dashboard and simulator.
**Status**: Completed & Archived.

### Phase 5: Autonomous SEO Sentinel & Crawler Engine (COMPLETE)
**Goal**: High-performance multi-tier crawler, SEO auditing, and closed-loop technical remediations.
**Depends on**: Phase 4
**Requirements**: REQ-SEO-01, REQ-SEO-02, REQ-SEO-03, REQ-SEO-04, REQ-SEO-05, REQ-SEO-06
**Success Criteria**:
  1. Cheerio and Playwright crawlers detect schema, performance, and URL parameter defects.
  2. Autonomous remediator patches DOM and generates verifiable receipts in SQLite WAL.
**Status**: Completed & Archived (73 tests passing).

### Phase 6: Live GSC Telemetry & Truth Provenance Integration (COMPLETE)
**Goal**: Connect live Google Search Console API for `sc-domain:sanocea.com`, persist snapshots into SQLite WAL, and enforce strict truth integrity.
**Depends on**: Phase 5
**Requirements**: REQ-GSC-01, REQ-GSC-02, REQ-GSC-03, REQ-GSC-04, REQ-GSC-05, REQ-GSC-06, REQ-GSC-07, REQ-GSC-08
**Success Criteria**:
  1. Production service account authentication verified against live GSC API with HTTP 200 response.
  2. GSC privacy threshold withholding handled explicitly with zero synthesized query rows.
  3. UI strictly separates Observed GSC Telemetry from Modeled SEO Opportunity tables.
  4. 125 total tests passing across `@sanocea/seo-stack` and `website`.
**Status**: Completed & Operational.

### Phase 7: SERP Trajectory Engine & External Provider Adapters (ACTIVE)
**Goal**: Deliver keyword-level ranking tracking and daily rank velocity (todays rank at start vs current) via third-party SERP provider adapters, bridging GSC query withholding.
**Depends on**: Phase 6
**Requirements**: REQ-SERP-01, REQ-SERP-02, REQ-SERP-03, REQ-SERP-04
**Success Criteria**:
  1. Real-time SERP positions fetched for target keywords independently of GSC query rows.
  2. Daily rank movement ledger records start-of-day vs current rank with position delta math.
  3. Visual SERP velocity component shows live trajectory progression in executive dashboard.
**Plans**: 2 plans
- [ ] 07-01: SERP Provider Adapter & Daily Rank Movement Ledger
- [ ] 07-02: Executive Dashboard SERP Velocity Visualization & Live Telemetry Wiring

### Phase 8: Generative Engine Optimization (GEO) & AEO Citations (PLANNED)
**Goal**: Monitor brand citation presence across Perplexity, ChatGPT, and Google AI Overviews, and enforce AI bot directives.
**Depends on**: Phase 7
**Requirements**: REQ-AEO-01, REQ-AEO-02, REQ-AEO-03, REQ-AEO-04
**Success Criteria**:
  1. Automated citation tracking queries across generative search engines.
  2. Compliance auditor verifies `robots.txt` AI crawler directives and `llms.txt` standard.
**Plans**: 2 plans

### Phase 9: Competitive Intelligence & External Backlink Index (PLANNED)
**Goal**: Competitor discovery, shared keyword SERP comparisons, and external backlink indexing.
**Depends on**: Phase 8
**Requirements**: REQ-COMP-01, REQ-COMP-02, REQ-COMP-03
**Success Criteria**:
  1. Competitor sitemap monitoring detects newly indexed product pages.
  2. External backlink index API provides domain rating and referring domain counts.
**Plans**: 2 plans
