# SANOCEA REFERENCE MERCHANT — n8n POC CERTIFICATION REPORT

**Document Identifier:** `CERT-N8N-POC-2026-01`  
**Tenant Under Test:** `ref_anchal_heritage` (*Anchal Heritage Organics*)  
**Architecture Specification:** [`N8N_ECOSYSTEM_AUDIT.md`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/docs/architecture/integrations/N8N_ECOSYSTEM_AUDIT.md)  
**Test Suite / Harness:** [`scripts/run_n8n_poc_certification.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/scripts/run_n8n_poc_certification.py)  
**Machine-Readable Report:** [`tests/fixtures/reference_merchant/generated/n8n_poc_certification_report.json`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/tests/fixtures/reference_merchant/generated/n8n_poc_certification_report.json)  
**Workflow Template:** [`integrations/n8n/poc/supplier_catalog_ingestion_workflow.json`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/integrations/n8n/poc/supplier_catalog_ingestion_workflow.json)  
**Date:** September 16, 2026  
**Auditor / Certifier:** SANOCEA Autonomous Architecture & Core Governance Review  
**Certification Verdict:** **PASS (8/8 CHECKPOINTS VERIFIED)**

---

## 1. Executive Summary & Verification Context

Following the completion of [`N8N_ECOSYSTEM_AUDIT.md`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/docs/architecture/integrations/N8N_ECOSYSTEM_AUDIT.md), an empirical Proof-of-Concept (POC) was executed to formally certify the strict architectural boundary between external integration tooling (n8n) and the authoritative ERP control plane (SANOCEA).

The POC executed locally against the certified Reference Merchant tenant `ref_anchal_heritage`. It implemented the complete lifecycle:
```
[Google Drive Dropzone (Simulated)] 
               │
               ▼ (Raw Binary File Retrieval)
       [n8n Workflow Node] 
               │
               ▼ (Multipart POST to SANOCEA Core API)
  [SANOCEA Ingestion Engine] ──> [Zero-Invention & Conflict Detection]
                                                │
                                                ▼
                                    [SANOCEA Exception Record]
                                                │
                                                ▼ (Authenticated Query)
       [n8n Workflow Node] ◄────────────────────┘
               │
               ▼ (Formatted Alert JSON)
     [Notification Sink]
```

### Core Architectural Invariants Proven:
1. **Zero Business Authority in n8n:** n8n did not parse commercial facts, did not extract pricing or variants, did not resolve identities, and did not evaluate publication criteria.
2. **Zero Commercial Fact Invention:** Raw bytes passed untouched into SANOCEA's canonical ingestion and provenance pipeline.
3. **Fail-Closed Governance:** Discrepant supplier pricing triggered a native `conflicting_product_evidence` `ExceptionRecord` in SANOCEA.
4. **No Direct n8n Approvals:** The notification payload carried only SANOCEA-originated fact metadata and a direct link to SANOCEA's review surface. No `resumeUrl`, no webhooks with pre-authorized approval tokens, and no bypass paths existed in n8n.
5. **Scoped Operator Credential:** n8n operated under a scoped `operator` API key. Attempts to call tenant administration endpoints or cross into other merchant partitions failed closed (HTTP 403).

---

## 2. Infrastructure & Component Versions

| Component | Target / Version | Deployment Mode | Verification / Status |
|---|---|---|---|
| **SANOCEA API Server** | FastAPI / Uvicorn | `http://127.0.0.1:8080` | Live & Healthy |
| **Database Engine** | PostgreSQL 16 (`sanocea_phase05`) | `127.0.0.1:55432` | Schema migrations applied |
| **Object Storage** | MinIO S3 (`sanocea-phase05`) | `http://127.0.0.1:59000` | S3 API active |
| **n8n Runtime** | n8n v1.98.2 (Official Node CLI) | Local Isolated Profile (`.n8n_poc_data`) | CLI Execution |
| **Notification Collector** | Python HTTP Sink | `http://127.0.0.1:8085/notify` | Ephemeral Test Sink |
| **Community Nodes** | None (0 community nodes) | Enforced | Official core nodes only |

### Official n8n Node Specifications Used:
- `n8n-nodes-base.manualTrigger` (v1): Workflow entrypoint.
- `n8n-nodes-base.readWriteFile` (v1): Local filesystem read simulating cloud dropzone binary retrieval.
- `n8n-nodes-base.httpRequest` (v4.2): Authenticated transport to SANOCEA ingestion API, exceptions endpoint, and notification sink.
- `n8n-nodes-base.if` (v2): Binary routing on SANOCEA exception presence (`length > 0`).
- `n8n-nodes-base.set` (v3.4): JSON notification payload formatter with strict governance notice.

---

## 3. Checkpoint Execution & Evidence Log

### Checkpoint 1: End-to-End Dropzone Ingestion & Exception Notification
- **Scenario:** The Reference Merchant catalog has baseline messy XLSX pricing for `ANCHAL-KACHI-GHANI` (`=130*1.20` preserved as 15600 paise). The dropzone receives `conflicting_feed.csv` containing price ₹145.00 for the same parent SKU.
- **Workflow Action:** n8n retrieves the raw CSV, POSTs to `/merchants/ref_anchal_heritage/catalogue/ingest`, reads `/merchants/ref_anchal_heritage/exceptions`, and delivers notification.
- **ERP Verification:**
  - SANOCEA detected the conflict: `conflicting_product_evidence:price`.
  - Canonical `ProductDraft` state: `CONFLICTED`.
  - Stored price was NOT overwritten: remained 15600 paise.
  - An `ExceptionRecord` was created in PostgreSQL with category `conflicting_product_evidence`.
  - Notification received at sink contained exact draft ID, exception count (`1`), and SANOCEA review URL (`http://127.0.0.1:8080/merchants/ref_anchal_heritage/catalogue/drafts`).
  - Strict security verification confirmed `resumeUrl` and `approved=true` were absent from the payload.
- **Verdict:** **PASS**

### Checkpoint 2 (Failure Test 1): Ingestion Idempotency
- **Scenario:** The supplier drops the exact same file a second time (re-delivery/replay).
- **Workflow Action:** Workflow executes again against `conflicting_feed.csv`.
- **ERP Verification:**
  - `draft_kachi_after.id == draft_kachi.id` (Draft ID preserved).
  - Duplicate drafts created: `0`.
  - Price preserved: 15600 paise.
  - Re-delivery safely updated the existing canonical draft and did not spawn phantom product duplicates.
- **Verdict:** **PASS**

### Checkpoint 3 (Failure Test 2): Process Interruption & Database Resilience
- **Scenario:** Client upload stream is aborted / truncated mid-transfer during binary POST.
- **Verification:**
  - Ingestion endpoint caught truncated boundary and aborted cleanly.
  - Subsequent integrity check on PostgreSQL `ProductDraft` confirmed record was uncorrupted and accessible.
  - Zero half-written or corrupted state persisted in SANOCEA.
- **Verdict:** **PASS**

### Checkpoint 4 (Failure Test 3): SANOCEA API Unavailability Handling
- **Scenario:** SANOCEA core API becomes unreachable (simulated by directing HTTP node to inactive port `8999`).
- **Verification:**
  - n8n caught `ECONNREFUSED` connection failure cleanly.
  - No fake success was recorded.
  - Original supplier source file in the dropzone was verified intact and unmodified (`conflicting_feed.csv` stat size preserved).
- **Verdict:** **PASS**

### Checkpoint 5 (Failure Test 4): Malformed / Ballast Input Quarantine
- **Scenario:** An unparseable binary file (`ballast_corrupt.bin`) containing arbitrary corrupt bytes is pushed to the ingestion endpoint.
- **Verification:**
  - SANOCEA Ingestor evaluated file content, identified zero recognizable commerce entities.
  - Created drafts: `0`.
  - System logged append-only audit event: `action="file_quarantined"`, `object_id="ballast_corrupt.bin"`.
  - Ballast was quarantined without contaminating catalog state.
- **Verdict:** **PASS**

### Checkpoint 6 (Failure Test 5): Notification Sink Failure Isolation
- **Scenario:** Downstream notification destination (Slack/WhatsApp/HTTP sink) crashes and returns HTTP 500 Internal Server Error.
- **Verification:**
  - Notification dispatch node threw HTTP error.
  - Core SANOCEA PostgreSQL state was queried: `draft_kachi.price` remained exactly 15600 paise and status was unchanged.
  - Proved that external transport/notification failure has zero rollback or side-effects on authoritative ERP state.
- **Verdict:** **PASS**

### Checkpoint 7 (Failure Test 6): Credential Scope & Administrative Privilege Boundary
- **Scenario:** POC operator credential is used to attempt administrative privilege escalation (`POST /admin/api-keys`) and cross-tenant data access (`GET /merchants/other_tenant_id/catalogue/drafts`).
- **Verification:**
  - Call to `/admin/api-keys` returned HTTP 403 Forbidden.
  - Call to `/merchants/other_tenant_id/catalogue/drafts` returned HTTP 403 Forbidden.
  - Proved that an n8n workflow compromised at runtime cannot access global administrative APIs or read across merchant tenancy partitions.
- **Verdict:** **PASS**

### Checkpoint 8 (Failure Test 7): Execution History Purge vs Audit Ledger Immutability
- **Scenario:** The local n8n execution database (`.n8n_poc_data/.n8n/database.sqlite`) has its execution history wiped (`DELETE FROM execution_entity`).
- **Verification:**
  - SANOCEA PostgreSQL `audit_events` count before purge: `232`.
  - SANOCEA PostgreSQL `audit_events` count after purge: `232`.
  - All commercial fact extractions, validation errors, and quarantine events remained preserved in PostgreSQL.
  - Confirmed n8n does not host the compliance ledger.
- **Verdict:** **PASS**

---

## 4. Production Boundary & Security Assessment

```
                                      SECURITY BOUNDARY
      UNTRUSTED / PERIPHERAL                                      TRUSTED / AUTHORITATIVE
 +──────────────────────────────+                         +─────────────────────────────────────+
 │       n8n Automation         │                         │             SANOCEA ERP             │
 │  - Raw file transport        │      REST API (HTTPS)   │  - Identity & Variant Resolution    │
 │  - Zero business rules       │ ──────────────────────> │  - Provenance & Fact Classification│
 │  - Scoped Operator Token     │      (Bearer Token)     │  - Publication Gates (Fail-Closed)  │
 │  - Zero Master Keys          │                         │  - Order, Inventory, Ledgers        │
 │  - Notification Dispatcher   │ <────────────────────── │  - Append-Only PostgreSQL Audit     │
 │  - No Resume/Approval Tokens │     (Exceptions Query)  │  - AES-256-GCM Credential Vault     │
 +──────────────────────────────+                         +─────────────────────────────────────+
```

### Risk Controls Confirmed:
1. **No External Approval Links:** Approval actions cannot be taken from unauthenticated links embedded in notifications. Approvals require operator authentication within SANOCEA.
2. **Deterministic Tenancy:** The operator token is tied exclusively to `ref_anchal_heritage`. Any request attempting cross-tenant leakage is halted at the API gateway layer.
3. **No Phantom Catalog States:** Re-delivery or incomplete uploads cannot manufacture phantom products or corrupt PostgreSQL data.
4. **No Core Domain Modifications:** SANOCEA core packages (`packages/product_onboarding`, `packages/domain_contract`, `packages/reference_merchant`) required zero hacks, mocks, or modifications to support this transport bridge.

---

## 5. Formal Certification Matrix

| Checkpoint | Tested Invariant | Result | Evidence Ref |
|---|---|---|---|
| **Checkpoint 1** | End-to-End Dropzone Ingestion & Exception Notification | **PASS** | `pdr_780da715e2bf4ed88ee980b260f5850c`, 1 notif |
| **Checkpoint 2** | Idempotency (Duplicate file re-delivery) | **PASS** | Zero duplicate drafts; ID preserved |
| **Checkpoint 3** | Process Interruption Mid-Stream | **PASS** | Stream aborted; DB integrity uncorrupted |
| **Checkpoint 4** | Core API Unavailability Handling | **PASS** | `ECONNREFUSED` handled; source file preserved |
| **Checkpoint 5** | Malformed / Corrupt Input Quarantine | **PASS** | 0 drafts; `file_quarantined` audit event |
| **Checkpoint 6** | Notification Sink Failure Isolation | **PASS** | Sink HTTP 500; zero ERP rollback |
| **Checkpoint 7** | Credential Privilege & Tenancy Boundary | **PASS** | Admin & Cross-tenant endpoints rejected (403) |
| **Checkpoint 8** | Execution History Purge vs Audit Immutability | **PASS** | SQLite purged; 232 PostgreSQL audit events intact |
