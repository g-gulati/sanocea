# SANOCEA ERP Current State Audit

**Date:** 2026-09-16  
**Auditor:** Antigravity (Automated Deep Technical Audit)  
**Audit Basis:** Direct, read-only inspection of source code, database migrations, model definitions, connectors, APIs, background workers, and live execution of the unit, integration, and end-to-end workload suites against real local infrastructure (PostgreSQL 16, MinIO S3, Temporal Server).  
**Constraint Adherence:** Strict feature freeze maintained. Zero lines of speculative business logic added. Production VPS (`217.217.249.68`) kept in 100% frozen soak state.

---

## A. Executive Summary

SANOCEA ERP is a Python 3.13 / FastAPI commerce-operations backend designed around multi-tenant isolation, tenant-scoped configuration, deterministic policy gates, append-only event ledgers, and formal approval/exception state machines.

**Verdict: NOT READY FOR A FIRST REAL MERCHANT TODAY.**

The system possesses a robust, highly-disciplined **simulated local core**:
- The unit test suite passes cleanly (**359 passed in 4.31s**).
- The integration test suite running against real local infrastructure (PostgreSQL 16 on port 55432, MinIO S3 on port 59000, Temporal on port 57233) passes cleanly (**102 passed, 0 failed, 18 skipped**; all 18 skipped tests are WooCommerce container tests).
- The live executable commerce workload (`scripts/run_phase46_integration_workload.py`) successfully executed against real PostgreSQL in 45.71s, validating multi-tenant isolation, webhook HMAC verification, inventory reservation idempotency, purchase order workflows, goods receipts, and financial reconciliation.

However, the codebase cannot be deployed for a real commercial merchant due to seven fundamental blockers:
1. **Zero Live External Integrations:** Every external channel (Shopify, Amazon, Flipkart, Meesho, payments, logistics, couriers, WhatsApp) is either completely simulated in memory or implemented against API documentation but never certified/tested against a live merchant account.
2. **Zero Frontend / Merchant Dashboard:** There is no UI. The `/dashboard` route in `apps/dashboard/app.py` is an unstyled, 74-line debugging script returning raw JSON dumps inside `<pre>` HTML tags. The "397 automated events, 7 require attention" control surface is not implemented.
3. **Temporal Disconnect:** Temporal is not used in the live application order/fulfilment/support path. While an isolated capability proof exists (`RealOrderWorkflow`), the live ERP runs synchronously via `OrderOrchestrator` wrapping an in-memory `FakeTemporalEngine`.
4. **Catalogue Ingestion Fragmented:** Ingestion of messy source files (PDF, images, Docling OCR) exists only as isolated worker scripts (`workers/ingestion/docling_ingestion.py`), completely disconnected from the main `/catalogue/ingest` API (which accepts only structured CSV/XLSX).
5. **Missing Commercial Compliance Schema:** The canonical schema lacks dedicated, typed fields for Indian e-commerce legal compliance (GST %, HSN code, country of origin, package dimensions, volumetric weight), leaving them in untyped `attributes` dicts where fact invention cannot be schema-enforced.
6. **No Active Background Workers:** While classes exist for recovery and reconciliation (`ReconciliationWorker`), no background daemon, systemd unit, or cron schedule is actively running to poll channels or recover uncertain mutations.
7. **Storefront Registry Instance Split Bug:** In `packages/runtime/storefront_registry.py`, `resolve()` caches connectors under key `merchant_id`, while `resolve_for_channel_type()` caches under `f"{merchant_id}:{channel_type}"`. This creates two independent, desynchronized connector instances for the same merchant, causing duplicate in-memory state and failing adversarial publication checks.

---

## B. Actual Architecture

### 1. Application & Service Layout
- **API Surface (`apps/api/app.py`):** FastAPI application with `CorrelationMiddleware`. Exposes unauthenticated operational routes (`/health`), service-key gated admin routes (`/admin/merchants`, `/admin/api-keys`), and operator-scoped merchant routes under `/merchants/{merchant_id}/*`.
- **Domain Contract & Models (`packages/domain_contract/models.py`):** Pydantic v2 models for all commerce entities: `Merchant`, `Channel`, `ProductDraft`, `Publication`, `ListingVerification`, `Inventory`, `InventoryReservation`, `Order`, `OrderLine`, `Shipment`, `TrackingEvent`, `Cancellation`, `Return`, `Exchange`, `Refund`, `PaymentObservation`, `SettlementBatch`, `SettlementEntry`, `Supplier`, `PurchaseOrder`, `GoodsReceipt`, `Approval`, `ExceptionRecord`, `AuditEvent`.
- **Persistence (`packages/domain_contract/postgres_store.py`):** Durable PostgreSQL backend. Stores entities in dedicated JSONB tables keyed by `id` and scoped by `merchant_id`. Implements atomic SQL operations using row-level locking (`SELECT ... FOR UPDATE`), conditional updates (`UPDATE ... WHERE available >= %s`), and advisory locks (`pg_try_advisory_lock`).
- **In-Memory Store (`packages/domain_contract/store.py`):** Phase 0 memory dictionary store used for high-speed unit testing.
- **Database Migrations (`packages/domain_contract/migrations/0001_phase05.sql`):** A monolithic 630-line SQL script creating 55 tables, comprehensive compound indexes, foreign keys, and an append-only trigger (`prevent_audit_update_delete`) that raises an exception if any `UPDATE` or `DELETE` is attempted on `audit_events`.
- **Tenancy & Authentication (`packages/authn/deps.py`):** Bearer token authentication against the `api_keys` table using SHA-256 key hashing. Two roles: `service` (cross-tenant, administrative) and `operator` (strictly bounded to a single `merchant_id`). Any request where `token.merchant_id != path.merchant_id` is rejected with HTTP 403.
- **Credentials Management (`packages/domain_contract/credentials.py`):** `DurableEncryptedCredentialProvider` encrypts merchant API secrets in PostgreSQL using AES-256-GCM authenticated encryption with key versioning (`SANOCEA_CRED_MASTER_KEY_CURRENT` and `SANOCEA_CRED_MASTER_KEY_<V>`). Dev/in-memory fallback (`EnvCredentialProvider`) is prohibited in production.
- **Service Graph (`packages/runtime/service_graph.py`):** Dependency injection container wiring connectors, stores, domain services, and workflow orchestrators into a unified `Services` dataclass.
- **Object Storage (`packages/object_storage/`):** S3/MinIO abstraction with SHA-256 checksum verification, content-type detection, and bucket isolation.

### 2. Workflow & Orchestration Reality
- **The Temporal Reality:** Despite architecture documentation emphasizing Temporal, **Temporal is NOT used in the ERP's live execution path**.
- The live order flow executes synchronously in `OrderOrchestrator` (`workers/workflow/order_orchestrator.py`), which calls `FakeTemporalEngine` (`workers/workflow/engine.py`).
- `TemporalRuntime` (`workers/workflow/temporal_runtime.py`) and `RealOrderWorkflow` exist purely as a standalone integration proof (`tests/integration/test_temporal_runtime.py`). They are not invoked when orders arrive via API or webhooks.
- (Note: Postiz on the VPS uses Temporal for its social publishing schedules, but SANOCEA ERP core does not).

---

## C. Control Surface & Dashboard Audit

### 1. Does an Actual UI Exist?
**NO.** There is no React, Vue, Next.js, Angular, Svelte, or even server-rendered Tailwind/Bootstrap template UI anywhere in the repository.

### 2. What Exists Today?
- `apps/dashboard/app.py` is a 74-line FastAPI app mounted separately or alongside the API.
- It exposes a single GET route returning raw Python model dictionaries formatted with `json.dumps(..., default=str)` inside raw HTML `<pre>` tags.
- It provides no buttons, no interactive forms, no filtering, no sorting, no approval click actions, and no pagination.

### 3. Implementation of the "397 Automated Events, 7 Require Attention" Principle
- **Control Principle Status: SCAFFOLDED IN BACKEND / MISSING IN FRONTEND.**
- The backend API (`/merchants/{merchant_id}/operator/summary`) computes raw counts:
  - `open_exceptions`: Count of `ExceptionRecord` with status `open`.
  - `pending_approvals`: Count of `Approval` with status `pending`.
  - `needs_attention`: Boolean flag (`True` if open exceptions or pending approvals exist).
- However, the "397 automated vs. 7 attention" ratio is not computed or surfaced. Workload counters (`packages/metrics/`) track automated rates in test scripts (`run_phase11_simulation.py`), but this is not exposed via any merchant-facing query or dashboard endpoint.

---

## D. Complete 28-Stage Merchant Journey Audit

Every stage of the merchant journey is classified below based on verifiable codebase truth:

| # | Journey Stage | Status | Verification & Codebase Evidence |
|---|---|---|---|
| 1 | Ingestion / messy source processing (PDF, Excel, scanned sheets, Docling, OCR, email, WhatsApp) | **PARTIALLY WORKING** | CSV and Excel (`.xlsx`, `.xlsm`) work cleanly via `StructuredProductIngestor`. Docling PDF text extraction exists in `workers/ingestion/docling_ingestion.py` but is completely disconnected from `/catalogue/ingest`. Scanned OCR is incomplete. Email and WhatsApp ingestion do not exist. |
| 2 | Normalization & Canonical Schema mapping | **WORKING** | `StructuredProductIngestor` normalizes headers (aliases for SKU, price, colour, size). `ProductCompletenessValidator` enforces canonical types, cleans currency, and standardizes color/size values. |
| 3 | Human-in-the-loop review & confidence thresholding | **WORKING** | `Approval` records are automatically created with `action="approve_product_facts"` whenever confidence < 1.0 or supplier profile is unverified. APIs `/catalogue/drafts/{id}/approve-facts` allow operator resolution. |
| 4 | Catalogue storage & versioning | **PARTIALLY WORKING** | `ProductDraft` stored with JSONB attributes and extracted evidence. However, formal versioning (history of changes across revisions) is not implemented; drafts are overwritten in-place. |
| 5 | Channel preparation & payload generation | **WORKING** | `ProductPublicationService._prepare_publish_payload()` generates platform-neutral payloads. Each connector translates this into platform-specific wire format. |
| 6 | Multi-channel listing publication | **SIMULATED ONLY** | Publication logic exists with DB idempotency (`uq_publications_draft_channel`), but execution is certified only against simulated in-memory storefronts. Real connectors are untested live. |
| 7 | Channel sync & read-back verification | **WORKING (Local) / SIMULATED (Live)** | `ProductPublicationService.verify()` performs immediate read-back against the channel, comparing title, SKU, price, and active status. Records `PUBLICATION_VERIFICATION_MISMATCH` on drift. Tested against simulators. |
| 8 | Inventory pool configuration & reservation system | **WORKING** | `PostOrderOperationsService.reserve_inventory_for_order()` uses atomic database updates (`UPDATE inventory SET available = available - %s WHERE available >= %s`) and idempotent reservation keys (`uq_inventory_reservations_idempotency`). |
| 9 | Inventory synchronization & safety stock rules | **PARTIALLY WORKING** | Safety stock thresholds exist in merchant config (`replenishment.default.safety_stock`). However, automated background synchronization pushed out to external channels is not running. |
| 10 | Order intake / webhook & polling | **PARTIALLY WORKING** | Webhook ingress routes exist for Shopify, WooCommerce, and Chatwoot with HMAC validation and replay deduplication (`raw_external_events` uniqueness). Polling exists in connector code but has no scheduler running. |
| 11 | Order validation & fraud / risk check | **PARTIALLY WORKING** | Basic schema validation, financial status check, and order sequence monotonicity checks exist. Dedicated fraud scoring or velocity checks do not exist. |
| 12 | Order routing & multi-warehouse allocation | **WORKING** | Multi-location inventory allocation implemented in `packages/post_order/allocation.py` (`MultiLocationInventoryService`). Allocates from primary, secondary, or fallback locations with shortage tracking. |
| 13 | Logistics / 3PL assignment & label generation | **SIMULATED ONLY** | `SimulatedLogisticsConnector` mints mock tracking numbers (`simship-...`) and labels in-memory. Zero live integrations with Shiprocket, Delhivery, Bluedart, or courier aggregators. |
| 14 | Manifestation & dispatch tracking | **SIMULATED ONLY** | `ingest_tracking` parses simulated courier events and transitions order status to `shipped` or `delivered`. Courier webhook ingestion is mock-only. |
| 15 | Real-time buyer notifications (WhatsApp, email, SMS) | **MISSING** | No messaging connectors (Twilio, Gupshup, SendGrid, SES) exist in `connectors/`. Notifications are completely absent from the runtime. |
| 16 | Post-order customer service & support ticket routing | **PARTIALLY WORKING** | Chatwoot webhook ingress validates signatures and creates `SupportConversation`. Maps customer email/phone to canonical orders. |
| 17 | Automated support resolutions (AI agent, rules, escalation) | **WORKING (Rules) / SIMULATED (AI)** | Deterministic intent classification for 22 intents. Automatically resolves status questions from canonical DB. Escalates unknown intents to `ExceptionRecord`. `DeterministicAIProvider` is substring-based; zero generative LLM capability. |
| 18 | Return request intake & validation | **WORKING** | `evaluate_return()` enforces return window policies (`config.returns.window_days`), checks order eligibility, and creates `Return` records. |
| 19 | Reverse logistics / pickup generation | **SIMULATED ONLY** | Reverse pickup calls `logistics_connector.create_return_pickup()` which generates mock reverse AWB numbers in memory. |
| 20 | Return inspection & restock / scrap grading | **WORKING** | `progress_return()` handles `inspected` events. If `restockable=True`, it atomically increases canonical inventory via `_restock_order_reservations()`. |
| 21 | Refund issuance & ledger posting | **WORKING** | Strict financial controls: `evaluate_refund()` enforces max refundable order capacity (`uq_refund_return_id`), applies policy limits (`automatic_limit` vs `REQUIRE_APPROVAL`), and records refund transactions. |
| 22 | Exchange order orchestration | **WORKING** | `evaluate_exchange()` checks variant availability, reserves exchange stock, monitors return receipt, and creates the replacement order. |
| 23 | Supplier catalogue & vendor onboarding | **WORKING** | `MerchantOnboardingService` creates `Supplier` and `SupplierSku` records with cost prices, MOQs, pack sizes, and lead times. |
| 24 | Purchase order generation & supplier communication | **WORKING (Internal) / SIMULATED (Ext)** | `ProcurementService` generates POs from replenishment recommendations, checks spending approval thresholds, and dispatches via `SimulatedSupplierConnector`. |
| 25 | Goods receipt note (GRN) & inventory intake | **WORKING** | `record_goods_receipt()` performs three-way matching against PO lines and inbound shipments, atomically increasing sellable inventory. |
| 26 | Multi-channel reconciliation (payments, fees, returns, settlement) | **WORKING** | `FinanceOperationsService` ingests settlement batches, performs line-item matching against payments/refunds, checks fee tolerances, and surfaces discrepancies as exceptions. |
| 27 | Merchant financial ledger & profit/margin analytics | **PARTIALLY WORKING** | Underlying ledger rows exist (`settlement_entries`, `payment_observations`, `purchase_orders`). Aggregate profit/margin analytics API is not implemented. |
| 28 | Automated audit, compliance & anomaly detection | **WORKING** | Append-only PostgreSQL audit trigger (`prevent_audit_update_delete`). Idempotency violation traps, sequence regression prevention, and reconciliation discrepancy exception generators are fully active. |

---

## E. Control, Safety & Data Provenance Audit

### 1. Source Document Lineage
- Raw uploaded spreadsheets (CSV/XLSX) are persisted to S3/MinIO under keys `supplier/{filename}`.
- For structured files, every extracted field creates an `ExtractedAttribute` recording:
  - `source_file`: Full S3 URI of raw document.
  - `source_locator`: JSON object with `{"sheet": ..., "row": ..., "column": ...}`.
  - `evidence_ref`: URI anchor `#row=X&column=Y`.
  - `confidence`: Float (1.0 for verbatim spreadsheet cell values).
  - `verified`: Boolean flag.

### 2. Commercial Fact Invention Prohibitions
- **Code vs. Prompt Reality:** Prohibition of fact invention is enforced via **deterministic Python code**, not LLM system prompts.
- `ProductCompletenessValidator` checks required fields (`sku`, `title`, `price`, `currency`, `product_type`).
- If price is missing or invalid: state becomes `INVALID`.
- If required attributes are missing: state becomes `INCOMPLETE`.
- If conflicting values exist across rows/sources: state becomes `CONFLICTED`.
- If extracted attributes are not approved/verified: state becomes `NEEDS_APPROVAL`.
- **CRITICAL COMPLIANCE GAP (P0):** The canonical schema (`Product`, `Variant`) does NOT have strongly-typed fields for Indian e-commerce statutory requirements:
  - GST rate (%)
  - HSN code
  - Country of origin
  - Package dimensions (L x W x H) & dead weight
  These are stored in an untyped `attributes: dict[str, Any]` JSONB field. Therefore, the system cannot enforce DB-level non-null constraints or strict type validation on tax/statutory fields before publication.

### 3. Read-Back Verification
- `ProductPublicationService.verify()` performs immediate read-back verification:
  1. Calls `storefront.fetch(merchant_id, "product", external_product_id)`.
  2. Compares fetched `title`, `sku`, `price`, and `status` against canonical `ProductDraft`.
  3. If any field differs, it marks outcome as `MISMATCH`, creates an `ExceptionRecord` of category `PUBLICATION_VERIFICATION_MISMATCH`, and records an audit event.

### 4. Autonomous Execution vs. Human Approval Gates
- **Autonomous Operations (Permitted without approval):**
  - Webhook order intake and deduplication.
  - Inventory reservation for in-stock lines.
  - Shipment tracking observation.
  - Support status inquiries (reading existing canonical truth).
  - Clean product publication IF merchant config explicitly sets `publication.require_approval = False` AND all attributes have confidence 1.0.
  - Refunds below `config.policy.refund.automatic_limit` (e.g. <= ₹500).
  - PO generation below `config.procurement.spending.auto_approve_limit`.
- **Strictly Gated Operations (Require authenticated human approval):**
  - Any product draft with confidence < 1.0 or unverified supplier (`approve_product_facts`).
  - Product publication if `require_approval = True` (default).
  - Cancellations requested before fulfilment.
  - Refunds above automatic limit.
  - Purchase orders above spending limit.
  - PO cost changes exceeding tolerance (> 2% or > ₹10).
  - Customer exchange order finalization.
  - Any support request seeking mutations (cancellations/refunds/returns).

---

## F. Live vs. Simulated Integration Matrix

| Integration / Subsystem | Current Classification | Code Location & Implementation Details |
|---|---|---|
| **Shopify** | **SIMULATED / MOCKED IN CODE** | `connectors/shopify/connector.py`. Complete in-memory dictionary simulation (`self.external_orders`, `self.external_products`). High fidelity, but 100% mock. |
| **Shopify Live** | **REAL CODE BUT UNTESTED LIVE** | `connectors/shopify_live/`. Real GraphQL Admin API (version 2026-07) client with token refresh. Implemented cleanly, but explicitly marked untested against a live store. |
| **Amazon SP-API** | **REAL CODE BUT UNTESTED LIVE** | `connectors/amazon/`. Implemented against official OpenAPI schemas (Orders v0, Feeds 2021-06-30, Listings Items 2021-08-01, Reports 2021-06-30). Lacks live seller credentials. |
| **Flipkart** | **REAL CODE BUT UNTESTED LIVE** | `connectors/flipkart/`. Implemented against Seller API v2/v3 (OAuth, orders, listings). Untested live. |
| **Meesho** | **SCAFFOLDED (STUB)** | `connectors/meesho/`. 92 lines of scaffolded auth headers. Zero business endpoints implemented (catalog, orders, inventory endpoints are missing). |
| **WooCommerce** | **REAL CODE BUT UNTESTED LIVE** | `connectors/woocommerce/`. Real REST API v3 client with RFC 5849 OAuth 1.0a HMAC-SHA256 request signing. Tested against recording/mock; skipped in integration suite without local container. |
| **BigCommerce** | **REAL CODE BUT UNTESTED LIVE** | `connectors/bigcommerce/`. Real REST API v3 client with API token auth. Untested live. |
| **Logistics (Shiprocket / Delhivery / Bluedart)** | **SIMULATED / MOCKED IN CODE** | `connectors/logistics/`. `SimulatedLogisticsConnector` with in-memory dictionaries. No real carrier APIs implemented. |
| **Payments (Razorpay / Cashfree / Stripe)** | **SIMULATED / MOCKED IN CODE** | `connectors/payments/`. `SimulatedPaymentConnector` with in-memory dictionaries. No real gateway APIs implemented. |
| **Chatwoot (Customer Support)** | **REAL CODE (Ingress) / MOCKED (Outbound)** | `connectors/chatwoot/`. Webhook ingress validates real HMAC signatures. Outbound `send_message` appends to in-memory list `self.sent_messages`. |
| **WhatsApp Business / Gupshup** | **MISSING** | No connector code exists. |
| **Email (SES / SendGrid / SMTP)** | **MISSING** | No email sending connector exists. |
| **Docling / Document OCR** | **REAL CODE (Worker Only)** | `workers/ingestion/docling_ingestion.py`. Real Docling and PDF text layer extraction working in isolation, but not integrated into the main API catalogue workflow. |
| **Temporal (Self-Hosted / Cloud)** | **REAL CODE (Isolated Test Only)** | `workers/workflow/temporal_runtime.py`. Real Temporal SDK integration verified via integration tests, but bypassed in live ERP runtime. |
| **Object Storage (S3 / MinIO)** | **REAL LIVE WORKING** | `packages/object_storage/`. Fully operational against local MinIO (`127.0.0.1:59000`) and S3-compatible endpoints. |
| **PostgreSQL** | **REAL LIVE WORKING** | `packages/domain_contract/postgres_store.py`. Fully operational against PostgreSQL 16 (`127.0.0.1:55432`). |

---

## G. Test Suite Execution & Runtime Verification

### 1. Test Suite Results
Three test suites were executed against the codebase:

1. **Unit Test Suite (`tests/unit/`):**
   - Command: `python -m pytest tests/unit -q`
   - **Result: 359 passed in 4.31s (100% pass rate).**
   - Coverage: Domain entities, state machines, policy rules, HMAC verifications, JSON serialization, in-memory store.

2. **Integration Test Suite (`tests/integration/`):**
   - Command: `python -m pytest tests/integration/ -q` (executed against PostgreSQL 55432, MinIO 59000, Temporal 57233).
   - **Result: 102 passed, 0 failed, 18 skipped in 244.67s (4m 04s).**
   - Skipped Tests Analysis: All 18 skipped tests belong to `test_woocommerce_connector_contract_real_infra.py` (5 tests) and `test_woocommerce_oauth1_signing.py` (13 tests). They are gated on `SANOCEA_WOOCOMMERCE_CONSUMER_KEY` and require a local `wp-env` WooCommerce Docker container.
   - Fixed State: The two previously reported infra failures (procurement PO acknowledgement and MinIO thumbnail access) executed completely cleanly and passed in this run.

3. **E2E Test Suite (`tests/e2e/`):**
   - Command: `python -m pytest tests/e2e/ -v`
   - **Result: 1 passed, 3 skipped in 0.89s.**
   - Passed: `test_phase1_local_capability.py` (representative local workload).
   - Skipped: 2 tests requiring live Shopify/Chatwoot credentials, 1 test requiring process daemon flag.

---

## H. Realistic Run Trace: Messy Merchant Simulation

### 1. Workload Execution
The full integrated commercial workload (`scripts/run_phase46_integration_workload.py`) was executed live against the real PostgreSQL database with encrypted credential master keys:
- Total Runtime: **45.71 seconds**.
- Tested Entities: Merchant C (primary test merchant) and Merchant D (cross-tenant isolation probe).
- Scenarios Tested: 17 adversarial edge-case scenarios and 20 zero-tolerance commercial invariants.

### 2. Lifecycle Trace
1. **Merchant Onboarding:** Merchant C created via HTTP POST `/admin/merchants` with policies, supplier mappings, and encrypted credentials. API key issued.
2. **Catalogue Ingestion:** Ingested CSV with 1 product draft (`MC-PROD-1`). State initialized to `INCOMPLETE`.
3. **Approval:** Facts approved via POST `/catalogue/drafts/{id}/approve-facts`. State transitioned to `READY`.
4. **Publication:** Published to Shopify channel. Mismatch check passed (`outcome="VERIFIED"`).
5. **Order Intake:** 5 orders ingested via HMAC-signed Shopify webhook payloads. Webhook deduplication verified (same ID replayed resulted in 0 duplicate orders). Stale webhooks (lower sequence) rejected.
6. **Inventory Reservation:** Stock reserved atomically. Shortage correctly allocated to secondary warehouse.
7. **Support Inquiries:** Chatwoot webhooks processed. Tracking inquiries resolved automatically from canonical DB. Live courier mutation (`NDR`) immediately reflected in next customer answer.
8. **Unauthorized Mutation Protection:** Support conversation requesting refund created a `requested` action and `permitted` refund record; support did NOT execute the financial mutation.
9. **Procurement & Goods Receipt:** Low stock triggered replenishment recommendation. PO generated, auto-approved under ₹5,000 threshold. Inbound shipment acknowledged. Goods receipt note processed; stock rose from 3 to 63 on-hand.
10. **Financial Settlement:** Payment observations matched against settlement batch. Discrepant payment amount correctly surfaced 2 open exceptions in `/exceptions`. Unresolved external references flagged as `CANONICAL_ONLY` (never falsely matched).
11. **Recovery Worker:** Advisory lock acquisition tested. Second overlapping instance correctly skipped execution pass.

### 3. Deep Architectural Bug Uncovered During Trace
The workload returned a verdict of **`FAIL`** due to exactly 1 failing invariant out of 20:
```json
"duplicate_catalogue_publication": {
  "status": "FAIL",
  "evidence": "two publish requests for the same draft+channel: {'external_products_created': 0, 'first_external_id': 'gid://shopify/Product/858b25a8a38d', 'second_external_id': 'gid://shopify/Product/858b25a8a38d', 'publication_rows_for_draft_channel': 1, 'correct': False}"
}
```
**Root Cause Analysis:**
- In `packages/runtime/storefront_registry.py`:
  - `resolve(merchant_id)` caches connectors in `self._cache[merchant_id]`.
  - `resolve_for_channel_type(merchant_id, channel_type)` caches connectors in `self._cache[f"{merchant_id}:{channel_type}"]`.
- When `ProductPublicationService.publish()` ran, it used `resolve_for_channel_id()`, which resolved and mutated Connector Instance #1.
- But the test workload checked `client.app.state.storefronts.resolve(merchant_id)`, which resolved Connector Instance #2.
- Because the cache keys differed, two independent instances of `ShopifyConnector` existed in memory simultaneously for Merchant C, meaning Connector Instance #2 never saw the publication performed on Connector Instance #1!

---

## I. Technical Debt & Codebase Health

1. **Monolithic Migration Script:** All database DDL lives in a single 630-line file `0001_phase05.sql`. There is no versioned migration framework (Alembic / Flyway) to apply incremental schema updates safely.
2. **Top-Level App Construction Side Effect:** In `apps/api/app.py`, line 468 calls `app = create_app()` at import time. This triggers `_build_store()`, causing any script or test that imports from `apps.api.app` to immediately crash with `RuntimeError: SANOCEA_PG_DSN is required` unless database environment variables are pre-configured.
3. **Missing Background Daemon / Scheduler:** `ReconciliationWorker` and `run_recovery_worker.py` are designed to recover uncertain mutations, but they exist only as scripts without a persistent systemd timer or daemon process running.
4. **Hardcoded Test Ports:** Hardcoded port assumptions across tests and scripts (`55432` vs `55433` for PostgreSQL, `59000` for MinIO) cause friction when running workloads without exact environment overrides.
5. **Messy Working Tree Artifacts:** The repository contains historical backups (`migration-backups/`), website static dumps (`sanocea-site-v1.zip`), screen captures, and fixture files inside the root directory.

---

## J. Prioritized Action Backlog

### P0 — Absolute Blockers for First Real Merchant (Do Not Onboard Before These)
1. **Build a Minimal Merchant Control UI:** Build a clean, secure operator web interface (Next.js/React or lightweight server-rendered HTMX) displaying the actual operational state: Pending Approvals, Open Exceptions, Active Orders, and Inventory Shortages. Must implement the "X automated / Y need attention" operational paradigm.
2. **Certify First Live Channel (Shopify):** Deploy and certify `connectors/shopify_live/` against a real Shopify Development Store. Verify OAuth callback, product creation, webhook intake, inventory sync, and order ingestion using real Shopify API credentials.
3. **Fix Storefront Registry Dual-Cache Bug:** Modify `packages/runtime/storefront_registry.py` so that `resolve(merchant_id)` delegates directly to `resolve_for_channel_type()`, ensuring exactly one singleton connector instance exists per merchant channel.
4. **Add First-Class Tax & Compliance Fields:** Extend `Product` and `Variant` database schema with strongly-typed columns for Indian e-commerce compliance: `hsn_code`, `gst_rate_percent`, `country_of_origin`, `length_cm`, `width_cm`, `height_cm`, `weight_grams`. Enforce that no product can be published without verified statutory compliance.
5. **Integrate Document Ingestion into API:** Unify `workers/ingestion/docling_ingestion.py` into the primary `/catalogue/ingest` pipeline so merchants can upload PDF price lists and supplier specification sheets directly through the API/UI.
6. **Activate Background Recovery Scheduler:** Deploy a systemd timer or background task running `scripts/run_recovery_worker.py` every 5 minutes to sweep and recover uncertain mutations and reconcile pending external records.

### P1 — Multi-Merchant & Operational Scaling Blockers
1. **Live Courier Integration:** Implement a real logistics connector for an Indian 3PL aggregator (Shiprocket or Delhivery) to generate real shipping labels and track real AWB statuses.
2. **Live Payment Gateway:** Implement a real payment connector (Razorpay or Cashfree) for order payment capture and webhook-driven automated refund execution.
3. **WhatsApp / Communication Ingress & Notifications:** Integrate Gupshup or WhatsApp Cloud API for buyer transactional notifications (order confirmed, dispatch, NDR address verification).
4. **Versioned Database Migrations:** Transition `migrations/0001_phase05.sql` into an Alembic migration suite with forward and rollback migration support.
5. **Decouple `app = create_app()` Import:** Refactor `apps/api/app.py` so that `create_app()` is only invoked inside `if __name__ == "__main__":` or via ASGI factory, eliminating import-time database connection requirements.

### P2 — Operational Hardening
1. **Marketplace Channel Certification:** Connect and certify `Amazon SP-API` and `Flipkart` connectors in developer sandbox environments.
2. **Complete Meesho Endpoints:** Flesh out `connectors/meesho/` from its current stub state to implement catalog upload, inventory push, and order polling.
3. **Merchant Analytics Ledger:** Add SQL aggregation queries for gross margin, return rate by SKU, NDR recovery rate, and courier SLA breach reporting.
4. **Repository Cleanup:** Move `migration-backups/`, website zip dumps, and test artifacts out of the primary codebase into isolated storage.

### P3 — Future Capabilities
1. **Real LLM Integration:** Upgrade `packages/ai/provider.py` from `DeterministicAIProvider` rules to a dual-tier generative AI engine (Gemini 1.5 Flash / Pro) with automated confidence scoring and strict hallucination guardrails.
2. **Production Temporal Engine:** Wire the live order and return lifecycle into Temporal workflows if multi-day human-in-the-loop timeouts require durable distributed state machines.

---

## K. Recommended Execution Sequence

1. **Step 1:** Fix the `StorefrontConnectorRegistry` cache key bug in `packages/runtime/storefront_registry.py` to restore 100% pass rate on adversarial workloads.
2. **Step 2:** Refactor `apps/api/app.py` top-level `create_app()` to permit clean imports across scripts without forcing database startup.
3. **Step 3:** Extend canonical `ProductDraft` / `Product` schema with typed GST, HSN, and dimension attributes.
4. **Step 4:** Build the minimum viable Operator Control Surface (UI) connecting to `/operator/summary`, `/approvals`, `/exceptions`, and `/orders`.
5. **Step 5:** Connect `connectors/shopify_live/` to a real test store and certify the live product-to-order-to-refund lifecycle.
6. **Step 6:** Activate `run_recovery_worker.py` under systemd supervision.
7. **Step 7:** Rehearse onboarding with messy CSV + PDF supplier data from end to end.
