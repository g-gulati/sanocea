# SANOCEA ERP — n8n ECOSYSTEM & INTEGRATION ARCHITECTURAL AUDIT

**Document Identifier:** `ARCH-AUDIT-2026-N8N-01`  
**Target Repository:** SANOCEA Autonomous Multi-Merchant E-Commerce ERP  
**Reference Tenant Baseline:** `ref_anchal_heritage` (*Anchal Heritage Organics*) — Certified Baseline  
**Scope:** Research & Architectural Evaluation Only (Zero Implementation / Zero Mutation)  
**Date:** September 16, 2026  
**Auditor:** SANOCEA Autonomous Architecture & Systems Review  

---

## A. Executive Conclusion & Strategic Recommendation

### 1. The Core Verdict: LIMITED ADOPTION (Peripheral Transport & Notification Layer Only)

SANOCEA should **ADOPT n8n in a strictly bounded, non-authoritative capacity** as an **external transport bridge, notification distributor, and messy file retriever**. 

SANOCEA must **REJECT n8n as a business logic orchestrator, state machine, reconciliation engine, credential store, or approval authority**.

```
+---------------------------------------------------------------------------------------+
|                                    OUTSIDE WORLD                                      |
|  Supplier Inboxes, Google Drive, Sheets, SFTP, WhatsApp, Slack, Non-Tier-1 SaaS      |
+---------------------------------------------------------------------------------------+
                                           | (Transport / Ingest)
                                           v
+---------------------------------------------------------------------------------------+
|                         n8n PERIPHERAL INTEGRATION LAYER                              |
|  - Role: Transport, Polling, Ingestion Bridge, Payload Routing, Notification Dispatch |
|  - Authority: ZERO. Holds NO business state, NO identity, NO master keys.             |
|  - Multi-Tenancy: Worker tagged with tenant_id; requests authenticated via scoped API. |
+---------------------------------------------------------------------------------------+
                                           | (Standard REST/Multipart API)
                                           v
+---------------------------------------------------------------------------------------+
|                               SANOCEA ERP CORE (AUTHORITY)                            |
|  - Canonical Identity, Provenance, Complete Fact Validation, Policy Engine            |
|  - DB-Atomic Inventory Reservations, Multi-Location Allocation, Order State Machine   |
|  - Live Shopify / Marketplace Mutations & External Read-Back Verification             |
|  - Settlement Reconciliation, Financial Ledgers, Procurement & Supplier Lifecycle     |
|  - Append-Only Tamper-Proof Audit Ledger (PostgreSQL Triggers)                        |
|  - Scoped Credential Authority (AES-256-GCM Envelope Encryption)                      |
+---------------------------------------------------------------------------------------+
                                           | (Current: API Polling / Future: Event Webhook)
                                           v
+---------------------------------------------------------------------------------------+
|                         n8n PERIPHERAL INTEGRATION LAYER                              |
|  - Distributes alerts to Slack / WhatsApp / Email with signed approval links          |
|  - Current-safe trigger: SANOCEA API polling; future option: outbound event webhook   |
+---------------------------------------------------------------------------------------+
```

### 0. Evidence Pass Performed on 2026-09-16

This audit was refreshed against the current repository, not phase labels alone. The evidence pass traced `apps/api/app.py`, `packages/runtime/service_graph.py`, `packages/product_onboarding/*`, `packages/domain_contract/*`, `packages/finance/operations.py`, `packages/post_order/operations.py`, `packages/procurement/operations.py`, `workers/workflow/*`, `workers/reconciliation_worker.py`, the live Shopify connector, marketplace connector implementations, and the certified Reference Merchant artifacts.

Key current-state corrections:

- The Reference Merchant `ref_anchal_heritage` is certified against real ERP paths and live Shopify Dev Store read-back, per `docs/audits/REFERENCE_MERCHANT_CERTIFICATION.md` and `tests/fixtures/reference_merchant/generated/reference_merchant_certification_report.json`.
- Amazon and Flipkart connectors are more than mock shells: they contain public-API implementation paths, credential flows, reads/writes, and settlement/order logic, but no live seller certification was found in the repository. They are therefore **PARTIAL / IMPLEMENTED BUT LIVE-UNTESTED**, not production-certified.
- Meesho is scaffolded around confirmed authentication while business schemas remain unconfirmed.
- SANOCEA does not currently contain an outbound notification dispatcher or event-webhook emitter. A zero-code n8n POC must poll SANOCEA APIs after ingestion or be limited to notifications triggered by n8n's own API call result. Any SANOCEA-pushed event webhook would be future work requiring review.
- Temporal support remains a capability proof and is explicitly not wired into current authoritative business flows. The current recovery worker is a plain scheduled worker, not Temporal.

### 2. The Architectural Invariant

> **The Sovereign Core Invariant:**  
> In commercial enterprise operations, integration middleware that mutates business state outside the database's atomic guarantees produces irrecoverable financial and inventory drift.  
> **n8n may transport, poll, trigger, transform transport syntax, and notify. SANOCEA alone decides, allocates, reconciles, approves, mutates, and audits.**

If an n8n workflow goes down, is edited mid-flight, or drops an execution log, **zero commercial facts or financial commitments in SANOCEA can be lost or corrupted**.

---

## B. Current SANOCEA Architecture Map & Capability Classification

Every capability below has been inspected in the active codebase and traced along actual execution paths rather than inferred from filenames:

| Subsystem / Capability | Current Implementation Code Path | Classification | Execution Realities & Architectural Boundaries |
| :--- | :--- | :--- | :--- |
| **Messy File Ingestion** | `packages/product_onboarding/ingestion.py` | **CERTIFIED** | Handles XLSX (merged cells, formulas), CSV (jagged, Indian ₹), PDF tables via PyMuPDF. Verified in Stages 3-4 & Ref Merchant. |
| **Ballast Quarantine** | `packages/product_onboarding/ingestion.py` | **CERTIFIED** | Quarantines binary trash (`.DS_Store`, corrupt binaries) to MinIO S3; writes `file_quarantined` audit event. |
| **Email / Mailbox Ingestion**| None | **MISSING** | No IMAP, POP3, or Gmail API listener exists in the repository. |
| **Catalogue & Drafts** | `packages/product_onboarding/workflow.py` | **CERTIFIED** | Full lifecycle: Draft -> ExtractedAttribute -> Evidence -> Validation -> Publication. |
| **Product Identity** | `packages/product_onboarding/identity.py` | **CERTIFIED** | Deterministic merchant-scoped SKU/barcode resolution. Fuzzy/LLM heuristics generate candidates only; never auto-resolve. |
| **Variant Resolution** | `packages/product_onboarding/variants.py` | **CERTIFIED** | Normalizes color/size matrices, handles missing variant attributes, resolves parent/child linkages. |
| **Commercial Fact Provenance**| `packages/product_onboarding/provenance.py`| **CERTIFIED** | Formula preservation (`=130*1.20` + cached value), cell/page locators (`Sheet!C5`, `page=1`), hidden sheet quarantine. |
| **Validation Engine** | `packages/product_onboarding/validation.py`| **CERTIFIED** | `ProductCompletenessValidator`. Enforces HSN, MRP, Tax, Title, Weight completeness before publication. |
| **Approval Engine** | `packages/domain_contract/models.py`, `apps/api` | **CERTIFIED** | Formal `Approval` model. Gated conflict resolution (`resolve_fact_conflict`), PO approvals, refund limits. |
| **Publication Gating** | `packages/product_onboarding/publication.py` | **CERTIFIED** | Fail-closed publication gate. Returns `EXCEPTION` upon conflicts, incomplete attributes, or unapproved data. |
| **Shopify Channel** | `connectors/shopify_live/` | **CERTIFIED** | Certified against live Dev Store (`sanocea-commerce-os-dev.myshopify.com`). OAuth token management, GraphQL `2026-07`. |
| **External Read-Back** | `connectors/shopify_live/connector.py` | **CERTIFIED** | Queries Shopify Admin GraphQL post-mutation to independently verify status is `ACTIVE` and options match database truth. |
| **Marketplace Connectors** | `connectors/amazon/`, `flipkart/`, `meesho/` | **PARTIAL** | Amazon and Flipkart contain implemented public-API execution paths, credential flows, order/listing/inventory operations, and settlement hooks, but no live seller certification was found. Meesho has confirmed auth scaffolding while business endpoint schemas remain unconfirmed. |
| **Inventory Allocation** | `packages/post_order/allocation.py` | **CERTIFIED** | Deterministic multi-hub priority ranking (`rank_candidate_locations`), SLA distance weighting. |
| **Atomic Reservations** | `packages/domain_contract/postgres_store.py`| **CERTIFIED** | PostgreSQL `SELECT FOR UPDATE` atomic reservations (`reserve_inventory_atomic`). Eliminates oversell races. Idempotent. |
| **Order Management** | `packages/domain_contract/models.py`, `apps/api` | **CERTIFIED** | Canonical `Order`, `OrderLine`, webhook ingestion, state transition lifecycle. |
| **Fulfilment Monitoring** | `packages/post_order/operations.py` | **CERTIFIED** | `monitor_fulfilment`: Moves reservation from `reserved` to `consumed` upon dispatch signal. |
| **3PL Logistics** | `packages/post_order/operations.py` | **SIMULATED** | Simulated courier commands (`request_return_pickup`, `ndr_reattempt`). |
| **Returns & Restocking** | `packages/post_order/operations.py` | **CERTIFIED** | `progress_return`: Distinguishes acceptance from restockability. Restocks consumed units upon `inspection_passed`. |
| **Financial Refunds** | `packages/post_order/operations.py` | **CERTIFIED** | Policy threshold gating (`_refund_decision`). Auto-permits under limit; gates over limit to human approval. |
| **Customer Support** | `workers/workflow/support_orchestrator.py` | **WORKING** | Chatwoot webhook integration; policy-gated intent evaluation. |
| **Finance & Ledger** | `packages/finance/operations.py` | **WORKING** | Double-entry journal records, fee tracking, currency conversion. |
| **Settlement Reconciliation**| `packages/finance/operations.py` | **CERTIFIED** | Batch matching: `MATCHED`, `PARTIAL`, `UNDER`, `OVER`, `DUPLICATE`, `ADJUSTMENT`, `EXCEPTION`. |
| **Procurement & POs** | `packages/procurement/operations.py` | **WORKING** | PO creation, approval, supplier submission, acknowledgement handling, inbound shipment, goods receipt. |
| **Outbound Notifications** | None | **MISSING** | No outbound push dispatchers for WhatsApp, Slack, SMS, or Email. Only logs audit and exception records. |
| **Scheduled Background Jobs**| `workers/reconciliation_worker.py` | **WORKING** | Bounded-retry recovery worker (`run_once`). Runs via manual/cron trigger; no embedded cron scheduler daemon. |
| **External Webhook Receiver**| `apps/api/app.py` | **CERTIFIED** | HMAC-verified webhooks for Shopify and Chatwoot. Rejects invalid signatures with HTTP 401 before mutation. |
| **Merchant Onboarding** | `packages/onboarding/merchant.py` | **WORKING** | `/admin/merchants` endpoint. Validates config schemas, creates channel mappings, seeds credentials. |
| **Credential Storage** | `packages/domain_contract/credentials.py` | **CERTIFIED** | AES-256-GCM envelope encryption. Production requires master key env vars; zero plaintext secrets in database. |
| **Audit Ledger** | `packages/domain_contract/migrations/` | **CERTIFIED** | PostgreSQL trigger `prevent_audit_update_delete()` prevents any `UPDATE` or `DELETE` on `audit_events`. Append-only. |
| **Exception Handling** | `packages/exceptions/service.py` | **CERTIFIED** | Categorized exceptions (`INVENTORY_CONFLICT`, `FULFILMENT_DELAY`, etc.) with remediation options. |
| **Mutation Recovery** | `packages/post_order/operations.py` | **WORKING** | Read-back verification and idempotent recovery for uncertain connector mutations (`recover_refund_mutation`). |
| **Temporal Runtime** | `workers/workflow/temporal_runtime.py` | **SCAFFOLDED** | Verified capability proof (connects to server, runs test workflow). Explicitly NOT wired into production business paths. |
| **Fake Temporal Engine** | `workers/workflow/engine.py` | **SCAFFOLDED** | In-memory test harness from Phase 0. |
| **Operator Dashboard API** | `apps/api/app.py` | **WORKING** | FastAPI authenticated REST endpoints (`/operator/summary`, queries, commands). |
| **Operator Dashboard UI** | None | **MISSING** | No web/React frontend. Operator commands driven via API/CLI. |
| **Reference Merchant** | `packages/reference_merchant/*`, `scripts/run_reference_merchant_certification.py` | **CERTIFIED** | `ref_anchal_heritage` completed messy package ingestion, formula provenance, PDF facts, approval, live Shopify publication, read-back, inventory allocation, returns/refunds, and immutable audit verification. |

---

## C. Current n8n Ecosystem Research

Primary sources used for n8n research:

- Official deployment choice documentation: `https://docs.n8n.io/choose-how-to-use-n8n/`
- Official self-hosting documentation: `https://docs.n8n.io/deploy/host-n8n/`
- Official community license documentation: `https://docs.n8n.io/n8n-community-license/`
- Official self-hosted feature comparison: `https://docs.n8n.io/deploy/host-n8n/community-edition-features/`
- Official integration and workflow library pages: `https://n8n.io/integrations/` and `https://n8n.io/workflows/`

### 1. Architectural Topology & Execution Engine
- **Distributed Queue Mode:** In production, n8n scales horizontally by decoupling into:
  1. **Main Process (Control Plane):** Manages UI, workflow editor, scheduling, and webhook listeners. Enqueues execution jobs into Redis.
  2. **Redis Message Broker:** Holds the Bull/BullMQ job queue. Requires Append-Only File (AOF) persistence to prevent job loss.
  3. **Worker Pool (Execution Plane):** Headless Node.js worker processes that pull execution jobs from Redis, execute workflow nodes, and write state to PostgreSQL.
  4. **PostgreSQL Database:** Shared state store holding workflow JSON graphs, encrypted credential blobs, and execution history.
- **Node Execution Semantics:** n8n nodes pass data as arrays of JSON objects (`[{ json: { ... }, binary: { ... } }]`). Transformations happen in V8 JavaScript memory. There is **no transactional rollback across nodes**. If node 5 fails after node 4 executed an external HTTP POST, node 4's remote side effect has already occurred.

### 2. Core Nodes & Integration Capabilities Relevant to ERP
- **Transport & Polling:**
  - `Webhook`: Native HTTP trigger supporting GET, POST, PUT with custom header validation, basic auth, or custom webhook secret checks.
  - `HTTP Request`: Full-featured REST client supporting OAuth2, Bearer tokens, multipart file uploads, custom retries, and pagination.
  - `Cron / Schedule Trigger`: Cron-expression-based triggering (e.g., polling supplier SFTP every 30 minutes).
- **Messy File & Mailbox Ingestion:**
  - `Gmail / IMAP / Microsoft Outlook`: Listens for new messages, filters by subject/sender, extracts binary attachments (PDF, XLSX, CSV).
  - `Google Drive / Google Sheets / OneDrive`: Watches folders for uploaded supplier price lists; reads rows and cell values.
  - `Read / Write Files from Disk / FTP / SFTP`: Securely pulls files from legacy supplier servers.
- **Communication & Notification:**
  - `Slack / Microsoft Teams / Discord`: Sends formatted Block Kit messages, cards, and threaded exception alerts.
  - WhatsApp can be reached through HTTP API patterns or providers such as Twilio/Gupshup where available; this must be treated as provider-specific transport, not approval authority.
- **Human-in-the-Loop:**
  - `Wait Node ("On Webhook Call")`: Suspends workflow execution and generates a unique dynamic `resumeUrl` (`{{ $execution.resumeUrl }}`).
  - `n8n Form Trigger / Form Node`: Generates basic web forms for human data entry.

### 3. Licensing & Commercial Restrictions: The Sustainable Use License (SUL)
- **Fair-Code Licensing:** n8n is released under the **Sustainable Use License (SUL)**. It is **not OSI-approved open source**.
- **Allowed Under Free Self-Hosted Tier:**
  - Internal business automation within the operating company.
  - Consulting/services where n8n is configured on client-managed infrastructure.
  - Custom internal workflow authoring.
- **Strictly Prohibited Under Free Tier (Requires Commercial / Enterprise OEM License):**
  - **Embedding n8n inside a commercial SaaS platform** sold to external third parties.
  - **White-labeling or reselling n8n workflow execution as a paid customer-facing feature.**
  - Exposing the n8n UI canvas directly to external merchants as "SANOCEA Workflow Builder".
- **Enterprise-Gated Capabilities:**
  - Advanced RBAC, Projects/Workspaces multi-tenancy, SAML/SSO, external secrets manager backends (HashiCorp Vault, AWS Secrets Manager), and git-based environment promotion are locked behind paid Enterprise tiers.

---

## D. SANOCEA ↔ n8n Capability Matrix

| Operational Capability | Native SANOCEA Core | n8n Workflow / Node Ecosystem | Comparative Assessment |
| :--- | :--- | :--- | :--- |
| **Messy Excel / PDF Parsing** | Custom Python (`openpyxl`, `PyMuPDF`) with formula preservation and exact cell/page locators. | `Spreadsheet File`, `Extract from PDF` nodes. Converts to raw JSON. | **SANOCEA is vastly superior.** n8n loses formula text, sheet-level quarantine, and bounding locators. |
| **Product Identity Resolution** | Deterministic merchant-scoped SKU, Barcode, parent-variant engine (`ProductIdentityResolver`). | Naive JS matching in Function nodes or fuzzy LLM nodes. | **SANOCEA is authoritative.** n8n lacks multi-attribute deterministic conflict rules. |
| **Catalog Publication Gate** | Fail-closed `apply_publication_policy`. Blocks unapproved or conflicted drafts. | `IF` nodes checking arbitrary boolean fields. | **SANOCEA is authoritative.** Business policy must not be encoded in visual drag-and-drop IF statements. |
| **Storefront Mutation (Shopify)**| Certified Live GraphQL connector (`2026-07`) with atomic idempotency and rate limiting. | Official `Shopify Node` (Admin REST / GraphQL wrapper). | **SANOCEA is certified.** Using n8n Shopify node would bypass SANOCEA's certified idempotency and read-back. |
| **External Read-Back Verification**| Automated post-mutation GraphQL read-back verifying `ACTIVE` status and variant IDs. | Requires manual HTTP Request node query chained after mutation. | **SANOCEA is certified.** Read-back is an intrinsic invariant of SANOCEA's connector contract. |
| **Multi-Location Inventory Allocation**| `rank_candidate_locations` with warehouse priority, distance, and SLA weighting. | None. Would require complex, brittle custom JavaScript scripting. | **SANOCEA is authoritative.** Core ERP logic belongs in Python domain services. |
| **Atomic Inventory Reservations**| PostgreSQL row-level locks (`SELECT FOR UPDATE`) with idempotency ledger keys. | None. n8n executes outside DB transaction boundaries. | **SANOCEA is authoritative.** Attempting stock reservation in n8n creates catastrophic oversell races. |
| **Settlement Reconciliation** | Batch matching engine: `MATCHED`, `UNDER`, `OVER`, `DUPLICATE`, `EXCEPTION`. | Naive loops comparing CSV lines to Shopify orders. | **SANOCEA is authoritative.** Financial reconciliation requires double-entry integrity and exact fee auditing. |
| **Mailbox & Drive Monitoring**| None (Missing). | Pre-built, battle-tested Gmail, Outlook, Google Drive, SFTP trigger nodes. | **n8n is vastly superior.** Zero reason for SANOCEA to write IMAP/OAuth Gmail polling daemons. |
| **Multi-Channel Push Alerts** | None (Missing). | Battle-tested Slack Block Kit, WhatsApp Business API, Twilio, Teams nodes. | **n8n is vastly superior.** Rebuilding webhook dispatchers for 10 chat apps is wasted engineering. |
| **Tamper-Proof Audit History** | PostgreSQL engine triggers (`prevent_audit_update_delete()`). Immutable. | n8n execution database (`execution_entity`). Pruned or mutated by DB admin. | **SANOCEA is authoritative.** n8n execution history is operational logging, not an immutable audit ledger. |
| **Credential Encryption** | AES-256-GCM envelope encryption (`CredentialProvider`) with master key rotation. | AES-256 encrypted credential store in SQLite/PostgreSQL (`N8N_ENCRYPTION_KEY`). | **SANOCEA is authoritative.** n8n Community has no tenant scoping; storing merchant keys in n8n violates isolation. |

---

## E. ADOPT / INTEGRATE / BORROW / REJECT / ALREADY_COVERED Decisions

| Capability / Workflow Pattern | Decision | Rationale & Architectural Rule |
| :--- | :--- | :--- |
| **Gmail / Outlook Attachment Ingestion** | **INTEGRATE** | n8n polls merchant inboxes, extracts attachments (PDF, XLSX, CSV), and POSTs multipart streams to SANOCEA's `/catalogue/ingest` endpoint. Saves weeks of email OAuth/IMAP plumbing. |
| **Google Drive / SFTP Folder Watcher** | **INTEGRATE** | n8n watches remote folders, detects new supplier price lists, and routes them to SANOCEA ingestion API. SANOCEA processes, extracts provenance, and quarantines ballast. |
| **Outbound Slack / Teams Alerting** | **INTEGRATE** | Current zero-code path: n8n polls or reacts to its own SANOCEA API call results, then formats rich Block Kit / Adaptive Card notifications. Future path: SANOCEA emits non-authoritative event webhooks after design review. |
| **WhatsApp Template Dispatcher** | **INTEGRATE** | n8n handles Meta Cloud API rate limits, template IDs, and phone number formatting to deliver operational alerts to merchant owners. |
| **Shopify Product Publishing** | **ALREADY_COVERED** | SANOCEA's certified `ShopifyLiveConnector` already implements Admin GraphQL mutations, variant matrices, and read-back verification. Replacing with n8n Shopify node introduces regressions. |
| **Shopify Webhook Ingestion** | **ALREADY_COVERED** | SANOCEA already exposes `/webhooks/shopify/{merchant_id}` with per-merchant HMAC-SHA256 signature verification. Passing through n8n weakens cryptographic non-repudiation. |
| **Multi-Location Inventory Sync** | **REJECT** | n8n templates that sync stock between Shopify and Amazon execute in Node.js memory without DB locks, causing fatal race conditions. Inventory allocation and reservation must remain in SANOCEA. |
| **Marketplace Settlement Reconciliation**| **REJECT** | n8n lacks the financial precision, fee audit contracts, and idempotency guarantees of SANOCEA's reconciliation engine. n8n may only transport the raw bank/marketplace CSV to SANOCEA. |
| **Human Approval Wait Node (`resumeUrl`)**| **BORROW** | The concept of an asynchronous pause-and-resume approval is valuable. However, n8n's raw `resumeUrl` is vulnerable to bot/crawler clicks. SANOCEA borrows the pattern by emitting signed approval tokens requiring authenticated login. |
| **AI Product Description Generator** | **REJECT** | Violates SANOCEA's **Zero-Invention Principle**. Generative AI copywriting without deterministic fact verification hallucinates specifications and creates legal/regulatory liability. |
| **Customer Support Chatbot** | **ALREADY_COVERED** | SANOCEA already implements Chatwoot integration with deterministic policy evaluations in `SupportOrchestrator`. Building conversational bot workflows in n8n duplicates logic and leaks tenant data. |
| **Automated Purchase Order Creation** | **ALREADY_COVERED** | SANOCEA's `ProcurementService` already calculates replenishment thresholds, supplier lead times, and PO approval authority. n8n must not calculate reorder quantities. |
| **Tally / Zoho Accounting Bridge** | **INTEGRATE** | n8n reads reconciled journal batches from SANOCEA's `/finance/reconciliations` API and translates them into XML/JSON formats required by local Indian ERPs (Tally, Zoho Books). |

---

## F. Authority-Boundary Architecture

To prevent architectural decay, the system boundary is governed by an explicit contract:

```
                                  AUTHORITY BOUNDARY
      EXTERNAL / UNTRUSTED                                CANONICAL / TRUSTED
+-------------------------------+               +---------------------------------------+
|          n8n MAY:             |               |          n8n MUST NOT:                |
|                               |               |                                       |
| - Watch IMAP/Gmail/Drive/SFTP |               | - Infer product/variant identity      |
| - Retrieve raw files/payloads |               | - Guess missing prices or HSN codes   |
| - Validate transport syntax   |               | - Evaluate catalog publication policy |
| - Call SANOCEA ingest APIs    |    ======>    | - Execute storefront mutations        |
| - Listen to SANOCEA webhooks  |  REST / HMAC  | - Calculate inventory availability    |
| - Format Block Kit/WhatsApp   |               | - Execute financial reconciliations   |
| - Bridge 3rd-party SaaS APIs  |               | - Authorize customer refunds          |
| - Buffer high-volume triggers |               | - Store master merchant credentials   |
| - Poll legacy non-API sources |               | - Alter or prune audit event records  |
+-------------------------------+               +---------------------------------------+
```

### Invariant Rules of the Boundary:
1. **The Ingestion Rule:** n8n sends raw bytes and metadata (`filename`, `mime_type`, `source_system`) to SANOCEA. n8n never extracts attributes or attempts catalog normalization before calling SANOCEA.
2. **The Mutation Rule:** n8n never issues direct `POST`, `PUT`, or `DELETE` calls to Shopify, Amazon, Razorpay, or Shiprocket for core commerce mutations. All mutations route through SANOCEA's connector pipeline.
3. **The Notification Rule:** n8n receives event payloads from SANOCEA webhooks. If an event requires human sign-off, n8n delivers a link containing an authenticated SANOCEA callback token; it never accepts raw unauthenticated responses as business authority.

---

## G. Merchant-Specific Integration Strategy (5 Tiers)

E-commerce merchants exhibit extreme software heterogeneity. SANOCEA isolates this variability through a 5-tier integration hierarchy:

```
+---------------------------------------------------------------------------------------+
| TIER 1: Native SANOCEA Connector (Core Authority)                                     |
| - Live Shopify, Live WooCommerce, Amazon SP-API, Database-Atomic PostgreSQL Store     |
| - Requirement: High volume, strict idempotency, read-back verification, financial SLA |
+---------------------------------------------------------------------------------------+
                                           |
+---------------------------------------------------------------------------------------+
| TIER 2: n8n Integration Bridge (Commodity Transport & Peripheral SaaS)                |
| - Google Drive, Sheets, Gmail, SFTP, Tally XML, Shiprocket Webhooks, Slack, WhatsApp  |
| - Requirement: Merchant-specific SaaS, file retrieval, notifications, format bridging|
+---------------------------------------------------------------------------------------+
                                           |
+---------------------------------------------------------------------------------------+
| TIER 3: Controlled Deterministic Browser Automation (Playwright Headless)             |
| - Legacy supplier portals with no API, government tax portals (GST e-way bill)       |
| - Requirement: Headless script, fixed selectors, deterministic DOM assertions         |
+---------------------------------------------------------------------------------------+
                                           |
+---------------------------------------------------------------------------------------+
| TIER 4: AI Browser Agent (Vision + LLM Navigation)                                   |
| - Dynamic merchant portals with volatile DOMs, anti-bot challenges, irregular layouts |
| - Requirement: Read-only data extraction; output routed to SANOCEA ingestion gate     |
+---------------------------------------------------------------------------------------+
                                           |
+---------------------------------------------------------------------------------------+
| TIER 5: Human Exception & Review (Fail-Closed Fallback)                               |
| - Conflicting commercial facts, unverified HSNs, refunds > automatic limits           |
| - Requirement: Authenticated operator signature written to immutable audit ledger     |
+---------------------------------------------------------------------------------------+
```

### Merchant Case Study Mapping:
- **Merchant A (Shopify + Razorpay + Shiprocket + Tally):**
  - Shopify: **Tier 1** (Native certified connector).
  - Razorpay: **Tier 1** (Payment observation & webhook HMAC verification).
  - Shiprocket: **Tier 2** (n8n webhook receiver -> SANOCEA tracking command).
  - Tally: **Tier 2** (n8n reads reconciled journal batches from SANOCEA -> generates Tally XML).
- **Merchant B (Amazon + Flipkart + Unicommerce + Excel):**
  - Amazon & Flipkart: **Tier 1** (Marketplace connector contracts).
  - Excel Price Lists: **Tier 2** (n8n watches Google Drive -> calls `/catalogue/ingest`).
  - Unicommerce: **Tier 2** (n8n pulls settlement reports via Unicommerce REST API -> passes to SANOCEA finance).
- **Merchant C (Shopify + Supplier CSV + Gmail + Google Drive):**
  - Shopify: **Tier 1** (Native connector).
  - Gmail & Google Drive: **Tier 2** (n8n watches inbox & Drive folder -> streams CSV/PDF to SANOCEA).
- **Merchant D (Amazon + JioMart + Blinkit + Internal Legacy ERP):**
  - Amazon: **Tier 1** (Native connector).
  - Blinkit / JioMart Partner Portal (No Public API): **Tier 3/4** (Deterministic Playwright automation downloads daily sales CSV -> n8n -> SANOCEA ingestion).
  - Internal ERP: **Tier 2** (n8n bridges legacy database views via SQL node to SANOCEA REST API).

---

## H. Ecommerce Workflow & Template Research

An audit of the official n8n workflow library and community search results evaluated representative e-commerce and operations templates against SANOCEA's architectural standards. The purpose was not to count templates, but to identify reusable transport and notification patterns that do not seize ERP authority.

| Workflow / Template Name | Source URL / Identifier | Claimed Purpose | Relevant SANOCEA Module | Technical & Security Quality | Verdict | Architectural Rationale |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Shopify & WooCommerce Inventory Sync with Google Sheets Alerts** | Official workflow library search result: `https://n8n.io/workflows/` | Syncs store inventory into Sheets and alerts. | Inventory | Low for SANOCEA authority. Spreadsheet-driven stock creates check-then-update risk and no database locks. | **REJECT** | Inventory truth must reside in SANOCEA's PostgreSQL database. n8n may notify on SANOCEA inventory exceptions, not synchronize stock directly. |
| **Invoices from Gmail to Drive and Google Sheets** | `https://n8n.io/workflows/3016-invoices-from-gmail-to-drive-and-google-sheets/` | Watches Gmail, stores invoice PDFs, extracts fields with AI, writes Sheets rows. | Ingestion / Finance | Good mailbox/file transport pattern; unsafe if AI extraction becomes financial truth. | **INTEGRATE** | Reuse Gmail attachment retrieval and file routing. Send raw files to SANOCEA; reject n8n/LLM as invoice or settlement authority. |
| **Extract Invoice Data from Email to Google Sheets using GPT-4o** | `https://n8n.io/workflows/4376-extract-invoice-data-from-email-to-google-sheets-using-gpt-4o-ai-automation/` | Email invoice extraction into spreadsheet. | Ingestion / Provenance | Useful attachment trigger; LLM extraction lacks SANOCEA provenance and approval controls. | **BORROW** | Borrow the trigger/filter pattern only. SANOCEA must preserve source facts and classify AI-derived values. |
| **Recognize Invoices / Receipts from Google Drive and Put Them into Google Sheets** | `https://n8n.io/workflows/2389-recognize-invoices-receipts-from-google-drive-and-put-them-into-google-sheets/` | Watches Drive folder, OCRs receipts, writes structured data. | Document ingestion | Good Drive watcher; external OCR/Sheets result is not authoritative. | **INTEGRATE** | Use Drive watcher as byte transport to SANOCEA ingestion. Keep OCR/provenance/validation in ERP. |
| **Invoice Processor & Validator with OCR, AI & Google Sheets** | `https://n8n.io/workflows/4247-invoice-processor-and-validator-with-ocr-ai-and-google-sheets/` | Extracts and validates invoice data against Sheets. | Finance / Procurement | Validation-in-Sheets conflicts with ERP controls. | **BORROW** | Borrow the exception-notification shape; implement validation in SANOCEA's domain services. |
| **Log Invoice Approval Decisions from Slack to Google Sheets** | `https://n8n.io/workflows/14515-log-invoice-approval-decisions-from-slack-to-google-sheets/` | Slack approval buttons logged to Sheets. | Approvals | Unsafe for sensitive approvals if Slack click is treated as authority. | **BORROW** | Use Slack/Teams/WhatsApp only to notify and deep-link to SANOCEA's authenticated approval surface. |
| **Automated Expense Tracking with AI Receipt Analysis & Google Sheets** | `https://n8n.io/workflows/5442-automated-expense-tracking-with-ai-receipt-analysis-and-google-sheets/` | Telegram receipt ingestion, AI extraction, Sheets logging. | Finance / Support | Paid template with community-node and AI trust concerns. | **REJECT** | Not appropriate for ERP financial truth. At most, the chat-file capture idea can be reimplemented as transport. |
| **Amazon SP-API Order Fetcher** | Community / GitHub | Polls Amazon SP-API for unshipped orders. | Orders / Connectors | Low. Lacks RDT (Restricted Data Token) rotation and PII encryption. | **REJECT** | Marketplace connectivity requires strict credential handling in native SANOCEA connector. |
| **Shopify Order to WhatsApp Notification** | `n8n.io/workflows/2014` | Sends customer order status via WhatsApp Business. | Post-Order / Fulfilment | Medium. Directly connects Shopify to WhatsApp, bypassing ERP. | **BORROW** | Pattern is sound, but trigger must come from SANOCEA's verified fulfillment state, not raw Shopify. |
| **Multi-Step Human Approval via Slack** | `n8n.io/workflows/1825` | Pauses workflow with Wait node; posts approve button. | Approvals | Low (Security). Raw `resumeUrl` triggers on link previews or bots. | **BORROW** | Borrow asynchronous wait concept, but require authenticated login to SANOCEA before approval. |
| **PDF Invoice Data Extraction with LLM** | `n8n.io/workflows/2150` | Uses OpenAI node to parse supplier invoices into JSON. | Ingestion / Provenance | Unacceptable. Hallucinates values; lacks cell/bounding locators. | **REJECT** | Violates Zero-Invention Principle. SANOCEA uses PyMuPDF with deterministic bounding boxes. |
| **Daily Sales MIS Report to Email/Slack** | `n8n.io/workflows/1630` | Queries database at 8 AM, builds CSV, emails executives. | Finance / Reporting | High. Straightforward read-transform-dispatch job. | **INTEGRATE** | n8n queries SANOCEA's `/merchants/{id}/operator/summary` and delivers formatted PDF/CSV summaries. |

---

## I. Marketplace Reconciliation Case Study

Reconciliation of high-volume Indian marketplace settlements (Amazon EasyShip, Flipkart Smart, Blinkit, JioMart) is notoriously error-prone due to deduction penalties, weight discrepancies, return fees, and GST TDS. 

### End-to-End Execution Trace:

```
[External Sources]
Amazon MWS/SP-API Settlement Reports, Flipkart Settlement CSV, Blinkit Partner Portal, Razorpay Batch
                                           |
                                           v
[n8n Layer: Transport & Fetcher]
1. Scheduled cron triggers at 02:00 UTC.
2. n8n fetches raw settlement CSVs via API, SFTP, or portal download.
3. n8n packages file as raw binary stream with metadata (provider="amazon", batch_date="2026-09-16").
4. n8n calls SANOCEA API: POST /merchants/{merchant_id}/finance/settlement-batches
                                           |
                                           v
[SANOCEA Layer: Canonical Normalization & Ingestion]
5. API authenticates request via merchant operator key.
6. Writes raw payload to MinIO S3 immutable storage (`s3://sanocea-phase05/finance/batches/...`).
7. Creates canonical `SettlementBatch` entity in PostgreSQL.
8. Writes AuditEvent: action="settlement_batch_ingested".
                                           |
                                           v
[SANOCEA Layer: Deterministic Reconciliation Engine]
9. Engine locks order and payment records using PostgreSQL row-level locks.
10. Matches external transaction IDs against internal `Order` and `Payment` entities.
11. Computes fee variance: Market Commission, Payment Fee, Pick & Pack, Courier Freight, GST TDS.
12. Classifies each line item:
    - MATCHED: Payout matches order expected amount within tolerance.
    - UNDERPAYMENT: Marketplace deducted unverified fees -> Creates ExceptionRecord.
    - OVERPAYMENT: Marketplace credited unexpected bonus/reversal.
    - DUPLICATE: Payout transaction already processed in prior batch -> Ignores.
    - EXCEPTION: Order ID not found in ERP -> Creates ExceptionRecord (category="settlement_orphan").
13. Generates double-entry ledger entries in `reconciliation_results`.
14. Database commit triggers PostgreSQL append-only audit trigger.
                                           |
                                           v
[SANOCEA Layer: Current Notification Exposure]
15. Today, SANOCEA persists the reconciliation, audit events, and exceptions. n8n can safely poll authenticated summary/exception APIs after submitting the batch. A future outbound event webhook may replace polling after architectural review.
                                           |
                                           v
[n8n Layer: Notification & Escalation]
16. n8n formats rich Slack/Email summary from SANOCEA's authoritative API response or poll result:
    "Batch Amazon-2026-09-16: Reconciled 1,420 orders (₹18.4L). 4 Fee Exceptions detected (₹6,400 weight discrepancy)."
17. Includes secure button linking to: `https://erp.sanocea.com/merchants/{id}/finance/batches/bat_123`
```

**Why n8n must NOT be the reconciliation engine:**  
If n8n performed the reconciliation in a JavaScript Function node, memory crashes during large batches would drop transaction rows, leaving the general ledger out of balance with zero database audit trail.

---

## J. Notification & Approval Architecture

### 1. Multi-Channel Notification Dispatch
In the current repository SANOCEA does not yet include an outbound event dispatcher. The safe current pattern is API polling or response-driven notification by n8n after it has called a SANOCEA endpoint. A future outbound event webhook can be added later if it remains non-authoritative. n8n distributes notifications across merchant-configured channels:
- **Critical Operational Alerts (Severity: P0):** WhatsApp Business message + SMS to operations director (*e.g., Inventory shortfall during flash sale, webhook HMAC verification failure*).
- **Operational Exceptions (Severity: P1):** Threaded Slack message to fulfillment channel (*e.g., Return inspection failed, PO submission timeout*).
- **Daily Commercial Summaries (Severity: P2):** Formatted email report to finance team (*e.g., Daily settlement reconciliation report, reorder recommendations*).

### 2. The Fallacy of Unauthenticated Messaging Approvals
A naive integration pattern permits operators to reply `"YES"` to a WhatsApp message or click a raw link (`https://n8n.instance/webhook/resume?approved=true`) to approve financial transactions.

**Fatal Vulnerabilities of Naive Approval:**
1. **Link Crawler Execution:** Corporate security filters (Microsoft Defender Safe Links, Google Workspace, Slack link unfurlers) automatically send HTTP GET requests to inspect links in messages. **This instantly approves the transaction before a human ever sees it.**
2. **Identity Spoofing:** A WhatsApp message comes from a phone number, which can be spoofed or forwarded. There is no cryptographic non-repudiation.
3. **Replay Attacks:** A captured URL clicked twice could trigger duplicate state transitions if not strictly protected.

### 3. The Secure Authenticated Approval Pattern

```
SANOCEA Core (Exception/Approval Created)
        |
        v  (Webhook with approval_id, merchant_id, expires_at, signature)
n8n Notification Node
        |
        v  (Dispatches Slack Block Kit / WhatsApp with secure link)
Operator Receives Alert
        |
        | Click Link: "https://erp.sanocea.com/approvals/{approval_id}?token={signed_nonce}"
        v
SANOCEA Web Frontend / Mobile Auth Gate
        |
        +---> Operator must be authenticated (Active Session / 2FA / API Key)
        +---> Validates HMAC signature and verifies token has not expired
        +---> Verifies operator has required RBAC authority for this action
        +---> Executes mutation atomically inside PostgreSQL transaction
        +---> Writes operator principal_id and timestamp to immutable AuditLedger
        |
        v
Outbound Webhook to n8n (action="approval_completed")
        |
        v
n8n updates Slack message: "Approved by rahul@anchal.com at 14:32 IST"
```

---

## K. Security Audit & Credential Architecture

### 1. The Threat of Credential Storage in n8n
If n8n stores merchant credentials directly:
- n8n Community Edition stores all credentials in a single shared database table encrypted with a single global key (`N8N_ENCRYPTION_KEY`).
- Any user or workflow with access to the n8n canvas can inspect or export credentials via simple JavaScript nodes (`$node["HTTP Request"].credentials`).
- There is **no merchant-scoped isolation** in n8n Community. Tenant B's workflow can read Tenant A's Shopify access token.
- Community nodes installed from npm execute with full Node.js process permissions, creating severe supply-chain vulnerabilities.

### 2. Architectural Comparison: Credential Models

| Model | Storage Location | Security Risk | Operational Overhead | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Model A: Credentials in n8n** | n8n PostgreSQL database | **EXTREME.** Cross-tenant leakage, zero RBAC in community tier. | Low | **REJECT** |
| **Model B: Credentials in SANOCEA Core** | SANOCEA DB (AES-256-GCM envelope) | **MINIMAL.** Strictly tenant-isolated, master key required. | Medium | **CERTIFIED BASELINE** |
| **Model C: Scoped Integration Credentials**| n8n holds only scoped SANOCEA API keys | **LOW.** Key limited to specific endpoints (`/catalogue/ingest`). | Low | **RECOMMENDED FOR N8N** |
| **Model D: Token Broker / Proxy** | SANOCEA mints short-lived signed JWTs | **VERY LOW.** Tokens expire in 15 minutes, non-reusable. | High | **TARGET FOR STAGE 5+** |

### 3. The Recommended Token-Broker Architecture
1. **Production Storefront & Gateway Credentials** (Shopify tokens, Amazon SP-API keys, Razorpay secrets) remain **100% inside SANOCEA's encrypted credential store**. n8n never sees them.
2. **n8n Credentials:** n8n holds **only a tenant-scoped SANOCEA Operator API Key** (`Bearer san_op_...`).
3. If n8n needs to call an external API that requires an authenticated merchant token, n8n calls SANOCEA's proxy or requests a short-lived scoped delegate token.

---

## L. Multi-Tenancy Deployment Analysis

SANOCEA is a multi-merchant platform. Deploying n8n across multiple merchants must be carefully evaluated:

| Deployment Topology | Description | Security & Isolation | Infrastructure Cost | Operational Complexity | Feasibility / Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Option 1: Single Global n8n Instance** | One n8n server with workflows tagged by `merchant_id`. | **FAIL.** Shared database, shared logs, credentials visible across tenants. | Lowest (~$10/mo) | Low | **REJECT FOR PRODUCTION.** Violates merchant data isolation. |
| **Option 2: n8n Enterprise Projects** | One instance partitioned into Projects/Workspaces. | Good soft isolation, but relies on paid n8n Enterprise license. | High (License fees) | Medium | **REJECT.** Violates zero-subscription-cost constraint. |
| **Option 3: Container per Merchant** | Dedicated Docker container for each merchant tenant. | **EXCELLENT.** Hard isolation of memory, disk, database, and network. | High (RAM scaling: ~300MB per tenant) | High (Container orchestration) | **VIABLE FOR HIGH-TIER MERCHANTS ONLY.** |
| **Option 4: Internal Isolated Hub (Hybrid)** | Single n8n instance hosted on private VPC; accessible ONLY to SANOCEA core. | **STRONG.** Never exposed to merchants. Only executes system workflows with strict SANOCEA API tokens. | Low (~1 VM, 2 vCPU, 4GB RAM) | Low | **RECOMMENDED ARCHITECTURE.** |

### Recommended Topology: Option 4 (Private Operations Integration Hub)
- n8n is deployed inside SANOCEA's private virtual network (`10.0.x.x`).
- The n8n UI is accessible **only to internal SANOCEA DevOps via VPN / SSH tunnel**.
- Merchants **never log in to n8n**. Merchants interact only with SANOCEA's API, Chatwoot, and their storefronts.
- n8n runs stateless integration workflows that always authenticate to SANOCEA using per-merchant API keys.

---

## M. Temporal vs. n8n Decision Matrix

A critical architectural pitfall is running two workflow engines managing the same business state transition.

### The Clear Boundary:
- **Temporal** is a **durable code-based execution engine** for long-running, fault-tolerant state machines with deterministic replay and wall-clock sleeps (days/weeks).
- **n8n** is a **visual integration and I/O pipeline tool** for event routing, webhook parsing, format transformation, and notification dispatch.

| Workload / State Transition | Engine Owner | Primary Rationale |
| :--- | :--- | :--- |
| **Catalog File Retrieval (Gmail/Drive)** | **n8n** | Commodity transport; built-in connectors; ephemeral execution. |
| **Product Draft Extraction & Validation** | **SANOCEA Sync** | Requires Python `openpyxl`, `PyMuPDF`, and deterministic validation rules. |
| **Live Storefront Publication** | **SANOCEA Sync** | Must maintain certified atomic idempotency and immediate read-back verification. |
| **Order Intake & Inventory Reservation** | **SANOCEA Sync** | Requires millisecond-level database atomic locks (`SELECT FOR UPDATE`). |
| **Order Dispatch Monitoring** | **SANOCEA Sync** | Evaluates SLA thresholds; consumes inventory reservations synchronously. |
| **Multi-Day B2B Procurement Lifecycle** | **Temporal (Future)** | Multi-week PO acknowledgement, delayed shipping, goods receipt, supplier dispute. |
| **Outbound Exception Notifications** | **n8n** | Event-driven format transformation to Slack Block Kit, WhatsApp, Email. |
| **Settlement File Ingestion** | **n8n** | Downloads large batch CSVs from bank/portal and streams to SANOCEA API. |
| **Settlement Batch Reconciliation** | **SANOCEA Sync/Worker** | Financial precision; double-entry ledger entries; audit trigger enforcement. |
| **Failed Mutation Recovery Polling** | **SANOCEA Worker** | `ReconciliationWorker`: Bounded retries with read-back verification before retry. |

> **The Rule of Single Orchestration:**  
> Temporal and n8n will **never manage the same state transition**. n8n handles transport and notification outside SANOCEA; Temporal (when wired) handles long-running multi-day business processes inside SANOCEA.

---

## N. Adversarial Failure Semantics & Recovery Analysis

| Adversarial Failure Scenario | What Happens? | Authoritative State Location | Can Duplicate Effects Occur? | Recovery Mechanism | Audit Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. n8n Node Crashes Offline** | Webhooks dropped; scheduled polls pause. | Untouched in SANOCEA & external services. | **NO.** Zero mutations triggered. | Restart container; n8n replays missed cron; webhooks retry via external sender. | None in SANOCEA (never reached). |
| **2. Duplicate Webhook from Channel** | n8n receives duplicate order webhook. | SANOCEA PostgreSQL. | **NO.** SANOCEA API enforces idempotency key (`shopify_order_id`). Second call is a no-op. | Returns cached 200 OK to n8n. | `audit_events` records initial creation; duplicate is dropped or signaled. |
| **3. Webhooks Delivered Out of Order** | `fulfilled` arrives before `created`. | SANOCEA Order state machine. | **NO.** SANOCEA rejects fulfillment on non-existent order (`HTTP 404`); queues for retry. | Background worker or sender retry matches after order is created. | ExceptionRecord logged: `order_not_found`. |
| **4. Mutation Timeout to External Store** | SANOCEA calls Shopify; connection drops. | SANOCEA ConnectorCommand (`status="uncertain"`). | **NO.** Marks command uncertain; halts duplicate execution. | `recover_cancellation_mutation` queries Shopify Admin GraphQL read-back before retrying. | `audit_events` records mutation requested, uncertain state, and read-back resolution. |
| **5. n8n Retries Failed Mutation** | n8n workflow retries POST `/refunds/{id}/execute`. | SANOCEA Refund state. | **NO.** SANOCEA idempotency service (`run_once`) catches identical key and returns original result. | Safe replay returns existing Refund record. | `audit_events` records idempotent replay attempt. |
| **6. Workflow Edited During Execution** | DevOps edits n8n canvas while batch runs. | SANOCEA PostgreSQL. | **NO.** In-flight node may fail; SANOCEA transactions rollback on incomplete HTTP requests. | Retry failed batch from SANOCEA API. | Failed API call logged in web server logs; no corrupt state in DB. |
| **7. Merchant Credentials Expire** | Shopify OAuth or Amazon token expires. | SANOCEA Credential Store. | **NO.** Connector raises `ShopifyAuthenticationError` and halts mutation. | SANOCEA raises P0 ExceptionRecord; n8n dispatches Slack alert to renew credentials. | ExceptionRecord: `channel_auth_failure`. |
| **8. SANOCEA API Unavailable** | n8n cannot reach SANOCEA (502/503). | External source & n8n Redis queue. | **NO.** Zero database state touched. | n8n BullMQ retries HTTP Request with exponential backoff until SANOCEA recovers. | n8n execution log records retries. |
| **9. Marketplace API Unavailable** | Amazon/Flipkart returns 503 Service Unavailable. | SANOCEA ConnectorCommand (`failed`). | **NO.** Atomic reservation preserved; order marked pending retry. | `ReconciliationWorker` polls external status on next scheduled pass. | `audit_events` records connector retry attempt. |
| **10. Notification Delivered Twice** | Slack/WhatsApp alert sent twice by n8n. | SANOCEA Approval state. | **NO.** Both alerts link to the SAME `approval_id`. Once approved, second click is a no-op. | SANOCEA approval endpoint returns "Already Approved". | Single `approval_resumed` audit event. |
| **11. Approval Response Replayed** | Attacker replays signed approval URL. | SANOCEA Approval entity (`status="approved"`). | **NO.** Single-use cryptographic nonce is invalidated upon first database commit. | SANOCEA rejects replay with HTTP 409 Conflict. | ExceptionRecord: `approval_replay_rejected`. |
| **12. n8n Worker Process Crashes** | Active execution killed mid-flight. | Redis queue + SANOCEA DB. | **NO.** In-flight HTTP request severed; SANOCEA rolls back uncommitted SQL transaction. | Redis BullMQ detects stalled job and reassigns to another worker. | Server access logs record aborted connection. |
| **13. PostgreSQL Engine Unavailable** | Database unreachable during reservation. | PostgreSQL (crash state). | **NO.** Connection pool drops; API raises 500; no partial stock deduction. | PostgreSQL restarts; WAL replay restores consistent state. | DB WAL recovery logs. |
| **14. n8n Execution History Deleted** | Admin wipes `execution_entity` in n8n. | SANOCEA PostgreSQL `audit_events`. | **NO.** SANOCEA audit log is completely independent and trigger-protected. | Zero operational impact on ERP business truth. | Complete immutable history remains intact in SANOCEA. |
| **15. Raw SQL Delete on Audit Table** | Malicious admin attempts `DELETE FROM audit_events`. | SANOCEA PostgreSQL. | **NO.** Blocked by trigger `prevent_audit_update_delete()`. | SQL query fails with `ERROR: audit_events is append-only`. | PostgreSQL server error log. |

---

## O. Zero-Subscription-Cost Analysis

A key mandate is avoiding expensive recurring middleware fees (Zapier, Make, Celigo, MuleSoft).

### 1. The Cost Comparison: Commercial Middleware vs. Self-Hosted n8n

| Integration Solution | Tier / Pricing Model | Estimated Annual Cost (50k tasks/mo) | Operational Limitations |
| :--- | :--- | :--- | :--- |
| **Zapier** | Company Plan | **$12,000 to $24,000 / year** | Per-task pricing explodes with high-volume inventory webhooks; zero on-premise privacy. |
| **Make.com (Integromat)** | Enterprise Plan | **$3,600 to $9,000 / year** | Execution caps; data leaves VPC; rate-limited webhooks. |
| **Celigo / Boomi** | E-Commerce Enterprise | **$20,000 to $60,000 / year** | Extremely expensive; proprietary closed-source lock-in. |
| **n8n Cloud** | Pro / Business Plan | **Recurring subscription; verify current quote before purchase** | Task execution quotas; cloud-hosted data. |
| **n8n Self-Hosted (SUL)** | **Community Edition** | **₹0 Software License** | Hosted on existing SANOCEA cloud VM / infrastructure. |

### 2. True Total Operating Cost (TOC) of Self-Hosted n8n

While the software license is ₹0, reliable operation incurs compute and maintenance costs:

- **Compute Sizing (Recommended Dedicated VM or Docker Sibling):**
  - CPU: 2 vCPU
  - Memory: 4 GB RAM (2 GB for Main/Editor, 1 GB for Redis, 1 GB for Workers)
  - Disk: 40 GB NVMe SSD (with automated weekly execution pruning: `EXECUTIONS_DATA_PRUNE=true`)
  - **Incremental Cloud Cost:** ~$15 to $25 / month (₹1,200 to ₹2,000 / month on Hetzner, AWS Lightsail, or DigitalOcean).
- **Maintenance & Engineering Overhead:**
  - Node.js container security patching: ~1 hour / month.
  - Periodic template validation & community node vetting: ~2 hours / month.
  - Automated backups of n8n PostgreSQL metadata: Included in standard backup scripts.
- **Verdict:** Self-hosted n8n under the Sustainable Use License achieves a **95% cost reduction** compared to Zapier or Celigo, easily satisfying the zero-subscription-cost requirement.

---

## P. Top 10 Quick Wins for SANOCEA (Ranked)

Ranked by **Engineering Effort Saved** vs. **Operational & Security Risk**:

| Rank | Quick-Win Integration | Effort Saved | Merchant Reuse | Security Risk | Operational Risk | Dependency Risk |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | **Gmail Supplier Catalog Ingestion** | **Very High (2 wks)** | High (80% of D2C) | Low (Scoped OAuth) | Low (Read-only) | Low (Standard IMAP) |
| **2** | **Google Drive Supplier Folder Watcher**| **High (1 wk)** | High (70% of D2C) | Low (Read-only) | Low | Low |
| **3** | **Multi-Channel Exception Alerts (Slack/Teams)**| **High (1.5 wks)** | Very High (95%) | Very Low (Outbound) | Very Low | Low |
| **4** | **WhatsApp Merchant Notification Bridge**| **High (1.5 wks)** | Very High (India) | Low (Template API) | Low | Medium (Meta API changes) |
| **5** | **Daily / Weekly Executive MIS PDF Dispatch**| **Medium (4 days)** | High (100%) | Very Low | Very Low | Low |
| **6** | **Tally / Zoho Books Reconciled Batch Sync**| **Very High (3 wks)** | Very High (India) | Medium | Medium | Medium (Tally XML format) |
| **7** | **Shiprocket Inbound Tracking Webhook Bridge**| **Medium (1 wk)** | High (India 3PL) | Low | Low | Low |
| **8** | **Raw Marketplace Settlement CSV Ingestion**| **Medium (1 wk)** | High (Multi-channel)| Low | Low | Low |
| **9** | **Customer Return Photo Ingestion (Google Form)**| **Medium (4 days)** | Medium | Low | Low | Low |
| **10**| **Carrier NDR (Non-Delivery) Notification**| **Medium (1 wk)** | High (COD heavy) | Low | Medium | Medium |

---

## Q. Commodity Work SANOCEA Should Stop Rebuilding

SANOCEA's core engineering differentiation is:
- Commercial fact provenance
- Zero-invention catalog validation
- Database-atomic multi-location inventory allocation
- Certified read-back storefront mutations
- Append-only audit ledgers
- Mathematical settlement reconciliation

**SANOCEA should NEVER write custom Python code for:**
1. **IMAP / POP3 / Gmail API polling daemons:** Handling MIME boundaries, base64 email attachment decoding, and mailbox refresh tokens is commodity toil. Let n8n retrieve the bytes.
2. **Google Drive / OneDrive folder watchers:** Polling cloud storage changes and managing webhook subscriptions is already solved by n8n.
3. **Chat App Layout Engines:** Formatting JSON payloads for Slack Block Kit, Microsoft Teams Adaptive Cards, or Discord embeds is a waste of core engineering time.
4. **SFTP Polling Daemons:** Connecting to legacy supplier SFTP drops over SSH keys is a standard, battle-tested n8n node.
5. **One-Off Indian ERP Format Adapters:** Generating Tally XML schemas or Zoho Books CSVs should happen in peripheral n8n transformation nodes, keeping the SANOCEA general ledger clean.

---

## R. Reference Merchant Plan (`ref_anchal_heritage`)

To demonstrate n8n safely within the Reference Merchant environment **without introducing fake demo logic or weakening Stage 1–4 certified invariants**:

### The Certified Reference Demonstration Flow:

```
[Messy Supplier Input]
A supplier emails `wholesale_catalog_v2.xlsx` to `supplier-inbox@anchalheritage.com`
                                           |
                                           v
[n8n Ingestion Bridge]
1. n8n Gmail Node polls inbox and detects attachment.
2. Streams raw file to SANOCEA API: `POST /merchants/ref_anchal_heritage/catalogue/ingest-file` or package endpoint, depending on the file bundle.
                                           |
                                           v
[SANOCEA Core (Real Certified Business Logic)]
3. UnifiedProductIngestor extracts drafts, captures formula `=130*1.20`, and quarantines ballast.
4. ProductCompletenessValidator detects price conflict (₹156 vs ₹168).
5. Publication gate fails closed -> Generates ExceptionRecord + pending Approval.
6. Persists `ExceptionRecord`, `Approval`, and append-only audit events. Current zero-code bridge polls SANOCEA's exceptions/approvals APIs after ingestion; a future outbound webhook may emit `exception_created`.
                                           |
                                           v
[n8n Notification Bridge]
7. n8n formats Slack alert to `#anchal-ops`:
   "Commercial Fact Conflict on ANCHAL-KACHI-GHANI (₹156 vs ₹168). Review required."
   Includes link: `https://erp.sanocea.com/approvals/app_123`
                                           |
                                           v
[Authenticated Operator Action]
8. Operator logs into SANOCEA and confirms ₹168 as authoritative.
9. SANOCEA marks draft `READY` and publishes to live Shopify Dev Store.
10. Live read-back confirms product `gid://shopify/Product/9077451915343` is `ACTIVE`.
11. PostgreSQL trigger records append-only audit event.
```

**Why this demo is 100% authentic:**  
n8n simply handles the real email pickup and the real notification dispatch. Every catalog extraction, formula provenance chunk, fail-closed policy gate, Shopify mutation, and database audit event executes on **real certified SANOCEA production code**.

---

## S. Reusable Commercial Integration-Pack Proposal

SANOCEA can package reusable, versioned n8n workflow JSON bundles as **SANOCEA Integration Packs**:

1. **SANOCEA Supplier Inbox Pack (`pack-ingest-email-v1.json`):**
   - Pre-configured Gmail/IMAP triggers watching for supplier price lists.
   - Forwards binary streams to `/catalogue/ingest`.
2. **SANOCEA Drive Dropzone Pack (`pack-ingest-drive-v1.json`):**
   - Pre-configured Google Drive / OneDrive folder watcher.
   - Automatically ingests new catalogs dropped by warehouse managers.
3. **SANOCEA Operations Alert Pack (`pack-notify-slack-v1.json`):**
   - Formatted Block Kit templates for inventory shortfalls, publication exceptions, and PO approval requests.
4. **SANOCEA WhatsApp Merchant Pack (`pack-notify-whatsapp-v1.json`):**
   - Pre-approved WhatsApp Business message templates for daily commercial summaries and urgent exception alerts.
5. **SANOCEA Indian Accounting Bridge (`pack-finance-tally-v1.json`):**
   - Listens to SANOCEA settlement reconciliation webhooks and formats export files for Tally ERP 9 / TallyPrime XML ingestion.

Each pack is a simple JSON export stored in `integrations/n8n/packs/` that any merchant can import into their n8n instance in 30 seconds.

---

## T. Technical, Licensing, and Operational Risks & Mitigations

| Risk | Category | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **1. Sustainable Use License (SUL) Breach** | Legal / Licensing | High | **Never embed n8n UI inside SANOCEA's customer dashboard.** Keep n8n strictly as an internal backend integration middleware. |
| **2. Cross-Tenant Credential Leakage** | Security | Critical | **Never store master merchant API keys in n8n.** n8n holds only scoped SANOCEA Operator API tokens. |
| **3. Link Preview Auto-Approval** | Security | Critical | **Never use raw unauthenticated `resumeUrl` links for approvals.** All approvals require authenticated login to SANOCEA. |
| **4. Check-Then-Update Overselling** | Architecture | Critical | **Completely forbid inventory sync in n8n.** All inventory reservations execute via SANOCEA's DB-atomic primitives. |
| **5. Supply Chain Risk from Community Nodes**| Security | High | **Prohibit arbitrary npm community nodes.** Restrict n8n installation to official verified nodes only. |
| **6. Execution Database Bloat** | Operational | Medium | Configure automatic pruning: `EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=168` (7 days). |
| **7. Node.js Memory OOM on Large Files** | Operational | Medium | Use streaming file uploads; set Node memory limits (`--max-old-space-size=4096`). |

---

## U. Recommended Smallest Safe Proof-of-Concept (POC)

### Specification for the First Safe POC:
- **Title:** Supplier Drive Dropzone & Slack Exception Notification Bridge.
- **Workflow Steps:**
  1. Operator drops `supplier_price_list_messy.xlsx` into a dedicated Google Drive folder.
  2. n8n Google Drive Trigger detects the file upload.
  3. n8n streams the raw file to SANOCEA API (`POST /merchants/ref_anchal_heritage/catalogue/ingest`).
  4. SANOCEA core processes the file, isolates hidden sheets, extracts formula provenance, detects price discrepancy, and generates a commercial fact exception.
  5. n8n polls SANOCEA's authenticated exceptions/approvals APIs for the Reference Merchant, or reads the authoritative API response where available. A future SANOCEA outbound event webhook can replace polling after review.
  6. n8n Slack or email node posts a rich message to `#sanocea-alerts` with exact discrepancy details and a link to review.
- **Verification Criteria:**
  - Zero modifications to SANOCEA core code.
  - Zero merchant credentials stored in n8n.
  - Database-enforced audit trigger records all actions.
  - Passes in < 15 minutes of setup.

---

## V. Final Strategic Decision Summary (Answering the 14 Core Questions)

1. **Should SANOCEA adopt n8n?**  
   **YES, but strictly for LIMITED ADOPTION.** Use it as a peripheral transport bridge and notification dispatcher. Never as the core ERP engine.
2. **Exactly what role should n8n play?**  
   External transport layer: polling email inboxes, watching Google Drive, bridging webhook formats, formatting Slack/WhatsApp notifications, and translating accounting exports.
3. **What must remain inside SANOCEA?**  
   Product identity, commercial truth, formula provenance, completeness validation, publication gates, storefront mutations, read-back verification, multi-location inventory allocation, atomic reservations, return/refund lifecycles, settlement reconciliation, and append-only audit ledgers.
4. **Which existing SANOCEA components would n8n unnecessarily duplicate?**  
   Shopify connector, inventory reservation, order monitoring, settlement matching, and conflict resolution.
5. **What engineering work could we stop building ourselves?**  
   IMAP/Gmail polling, Google Drive watchers, Slack/Teams Block Kit formatters, WhatsApp Cloud API message formatting, and SFTP schedulers.
6. **What are the top reusable n8n integrations for merchants?**  
   Gmail supplier attachment ingestion, Google Drive dropzone, Slack exception alerts, WhatsApp alerts, and Tally accounting bridge.
7. **How should credentials be managed?**  
   Production credentials remain encrypted in SANOCEA (AES-256-GCM). n8n holds only scoped SANOCEA Operator API tokens.
8. **How should multi-tenancy be handled?**  
   Deploy a single private internal n8n hub accessible only to SANOCEA backend systems via internal VPC. Tag execution payloads with `merchant_id` and enforce tenant authentication at the SANOCEA API gateway.
9. **How should n8n interact with Temporal?**  
   Strict separation of concerns. n8n handles external I/O and notifications. Temporal (when wired) handles durable multi-day business processes inside SANOCEA. They never orchestrate the same state transition.
10. **What are the major risks?**  
    License violation (SUL), cross-tenant credential exposure, link-preview auto-approval vulnerabilities, and out-of-transaction inventory overselling.
11. **What is the expected infrastructure/maintenance burden?**  
    Minimal: One 2 vCPU / 4 GB RAM container stack (n8n + Redis + Postgres), costing ~$15–$25/month, requiring ~2 hours of monthly maintenance.
12. **Should n8n be included in the Reference Merchant?**  
    Yes, for external transport (email/Drive file drop) and notification dispatch (Slack alert), cleanly demonstrating end-to-end automation while preserving 100% authentic ERP logic.
13. **What is the smallest safe proof-of-concept?**  
    Google Drive supplier price list drop -> n8n -> SANOCEA ingestion API -> exception -> n8n Slack alert.
14. **What should NEVER be delegated to n8n?**  
    Canonical product/variant identity, commercial fact truth, inventory reservation/allocation, refund authorization, reconciliation decisions, storefront mutation authority, and audit logging.
