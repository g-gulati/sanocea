# SANOCEA OPERATIONS COMMAND CENTER — CERTIFICATION REPORT

**Document Identifier:** `CERT-COMMAND-CENTER-2026-01`  
**Tenant Under Test:** `ref_anchal_heritage` (*Anchal Heritage Organics*)  
**Presentation Layer URL:** `http://127.0.0.1:8080/ui`  
**Test Harness / Runner:** [`scripts/verify_command_center_certification.py`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/scripts/verify_command_center_certification.py)  
**Machine-Readable Report:** [`tests/fixtures/reference_merchant/generated/command_center_certification_report.json`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/tests/fixtures/reference_merchant/generated/command_center_certification_report.json)  
**Date:** September 16, 2026  
**Auditor / Reviewer:** SANOCEA Autonomous Architecture & Core Governance Review  
**Certification Verdict:** **PASS (8/8 CHECKPOINTS VERIFIED)**

---

## 1. Executive Summary & Architectural Invariant

The **SANOCEA Operations Command Center** has been implemented and certified locally against the Reference Merchant tenant (`ref_anchal_heritage`). 

The Command Center serves as a **pure presentation and human-in-the-loop interaction layer** for commercial prospect demonstrations. It replaces developer CLI invocations and unformatted JSON walls with a clean, executive B2B operations interface.

### Hard Architectural Invariants Certified:
1. **Zero Business Decision Logic in UI:** The frontend (`apps/command_center/app.js`, `index.html`) contains no fact extraction, no formula evaluation, no identity resolution algorithms, no price calculations, and no direct database access.
2. **Authoritative SANOCEA Control:** SANOCEA core services (`packages/product_onboarding`, `packages/post_order`, `packages/domain_contract`) remain 100% authoritative for commercial fact integrity, fail-closed publication policy, inventory allocation, and audit records.
3. **Stateless UI Execution:** Refreshing, reloading, or disconnecting the browser UI cannot alter ERP database records or phantom states.
4. **Gate Bypass Immunity:** Unapproved drafts cannot be published, conflicting evidence cannot reach Shopify, and refunds above ₹500 cannot bypass human financial approvals from the UI.
5. **Real External Read-Back:** The publication screen connects to genuine Shopify Admin GraphQL mutations and independent read-back queries against `sanocea-commerce-os-dev.myshopify.com`.

---

## 2. Implemented Screens & Authoritative API Mappings

The Command Center implements all 7 required operational views, mapped directly to SANOCEA REST endpoints:

| Screen | Operational Purpose | Authoritative SANOCEA APIs Used |
|---|---|---|
| **1. Operations Overview** | Tenant identity, GSTIN/currency configuration, 7-stage lifecycle pipeline, and real-time operational counts. | `GET /merchants/{id}/profile`<br>`GET /merchants/{id}/operator/summary`<br>`GET /merchants/{id}/catalogue/drafts`<br>`GET /merchants/{id}/audit` |
| **2. Exceptions Queue** | Human-readable cards for open `ExceptionRecord`s detailing why SANOCEA halted execution. | `GET /merchants/{id}/exceptions`<br>`GET /merchants/{id}/catalogue/drafts` |
| **3. Evidence & Conflict Review** | Side-by-side commercial fact provenance comparison (formula `=130*1.20` vs ₹145.00 CSV line 2) with operator resolution controls. | `GET /merchants/{id}/catalogue/drafts/{draft_id}`<br>`POST /merchants/{id}/catalogue/drafts/{draft_id}/conflicts/resolve`<br>`POST /merchants/{id}/catalogue/drafts/{draft_id}/approve-facts` |
| **4. Publication & Verification** | Publication lifecycle stepper (`BLOCKED → READY → PUBLISHING → VERIFIED`), live Shopify dev store product link, and independent read-back query. | `GET /merchants/{id}/catalogue/publications`<br>`POST /merchants/{id}/catalogue/drafts/{draft_id}/publish`<br>`POST /merchants/{id}/catalogue/drafts/{draft_id}/publish/approve`<br>`POST /merchants/{id}/catalogue/publications/{pub_id}/reverify` |
| **5. Orders & Inventory** | Multi-location warehouse stock balances (Delhi, Mumbai, Bengaluru), atomic SQL reservations, proximity routing, and idempotency proof. | `GET /merchants/{id}/inventory`<br>`GET /merchants/{id}/orders` |
| **6. Returns & Refunds** | Customer return inspection condition, inventory restoration to warehouse shelf, and automatic (≤ ₹500) vs approval-gated (> ₹500) refund policy comparison. | `GET /merchants/{id}/returns`<br>`GET /merchants/{id}/refunds`<br>`GET /merchants/{id}/approvals` |
| **7. Audit Timeline** | Chronological immutable event stream read directly from PostgreSQL 16 append-only ledger with trigger protection indicators. | `GET /merchants/{id}/audit` |

---

## 3. Read-Only Presentation Endpoints & Safe Authentication Mechanism

To support the graphical Command Center without modifying existing business logic or exposing authentication shortcuts:

1. **`GET /merchants/{merchant_id}/audit`**
   - **Gap Documented:** `queries.get_audit_trail(store, merchant_id)` existed in `packages/runtime/queries.py`, but had no HTTP route.
   - **Resolution:** Exposes the existing query directly to authenticated operators (`require_operator`). Returns immutable `AuditEvent` records from PostgreSQL.
2. **`GET /merchants/{merchant_id}/profile`**
   - **Gap Documented:** `GET /operator/summary` returned counts, but omitted tenant legal entity, GSTIN, and location metadata needed for the identity banner.
   - **Resolution:** Queries `store.get(Merchant, merchant_id, merchant_id)` and `store.get_config(merchant_id)` to return static merchant metadata behind `require_operator`.
3. **Safe Local-Development Credential Mechanism (Zero Token Dispensing Endpoints):**
   - **Hard Rule:** No `/demo-token` endpoint exists. Any attempt to query `/demo-token` returns HTTP 404.
   - **Resolution:** The Command Center obtains its session credential through local-development mechanisms: URL parameters stripped on load (`?token=...`), `localStorage`, or an in-UI authentication modal. No bearer tokens or secrets are embedded in HTML or JS.
4. **`GET /ui` & Static Mount:**
   - Mounts `apps/command_center` at `/static` and serves `index.html` at `http://127.0.0.1:8080/ui`.

**Business Logic Added to UI or API:** **ZERO (`0`)**.

---

## 4. Verification Checkpoint Results (8/8 PASS — Integrity Certified)

Full automated suite executed via `C:\Python313\python.exe scripts/verify_command_center_certification.py`:

```
================================================================================
SANOCEA OPERATIONS COMMAND CENTER — VERIFICATION & CERTIFICATION
Merchant ID: ref_anchal_heritage
API Base URL: http://127.0.0.1:8080
================================================================================

[SETUP] Resetting Reference Merchant and preparing baseline + conflict state...
[CHECKPOINT 1] Verifying Command Center UI, Static Assets & No Embedded Credentials...
  -> CHECKPOINT 1 PASS: UI served (HTTP 200) with ZERO embedded credentials or /demo-token calls.

[CHECKPOINT 2] Verifying Authentication & Authorization Security Integrity...
  -> CHECKPOINT 2 PASS: /demo-token 404; unauthenticated 401; cross-tenant 403; scoped auth verified.

[CHECKPOINT 3] Verifying Screen 1 (Overview) & Screen 2 (Exceptions Queue) Data...
  -> CHECKPOINT 3 PASS: Exceptions query returned 1 real exception (conflicting_product_evidence).

[CHECKPOINT 4] Verifying Screen 3 (Side-by-Side Evidence Provenance)...
  -> CHECKPOINT 4 PASS: Provenance verified; commercial facts protected against silent invention.

[CHECKPOINT 5] Testing Operator Conflict Resolution & Fact Sign-off...
  -> CHECKPOINT 5 PASS: Conflict resolved and signed off; state transitioned to READY.

[CHECKPOINT 6] Testing Live Shopify Publication & External Read-Back...
  -> CHECKPOINT 6 PASS: Genuine external Shopify GID verified: gid://shopify/Product/9077451915343.
     Direct read-back: title='Anchal Cold-Pressed Kachi Ghani Mustard Oil', status=ACTIVE, price=INR 156.00.

[CHECKPOINT 7] Verifying Screens 5 & 6 (Warehouse Reconciliation & Refund Gates)...
  -> CHECKPOINT 7 PASS: Reconciled 3 canonical hubs (['loc_bengaluru_hub', 'loc_delhi_hub', 'loc_mumbai_hub']); 12 inventory rows; refund gates verified.

[CHECKPOINT 8] Verifying Screen 7 (Audit Timeline & PostgreSQL Immutability)...
  -> CHECKPOINT 8 PASS: All 321 audit events rendered from immutable PostgreSQL ledger.

================================================================================
COMMAND CENTER CERTIFICATION VERDICT: PASS (8/8)
Report saved to: tests/fixtures/reference_merchant/generated/command_center_certification_report.json
================================================================================
```

---

## 5. Security & Gate Enforcement Proof

| Security Invariant | Test Method | Result |
|---|---|---|
| **No Demo Token Endpoint** | HTTP GET `/merchants/ref_anchal_heritage/demo-token`. | HTTP 404 Not Found. Route removed. |
| **No Embedded Secrets in Frontend** | Automated string scan on `index.html` and `app.js`. | PASS. Zero bearer tokens, zero secrets. |
| **Unauthenticated API Rejection** | HTTP GET `/merchants/ref_anchal_heritage/profile` without header. | HTTP 401 Unauthorized. |
| **Tenant Boundary Enforcement** | HTTP GET `/merchants/unauthorized_tenant/profile` with scoped key. | HTTP 403 Forbidden. |
| **Live External Verification** | Direct GraphQL query against `sanocea-commerce-os-dev.myshopify.com`. | Verified: `gid://shopify/Product/9077451915343`, title, active status, price ₹156.00. |
| **Warehouse Determinism** | Query `/merchants/ref_anchal_heritage/inventory` after reset. | Exactly 3 canonical hubs (Delhi, Mumbai, Bengaluru) across 12 rows. |
| **Zero UI State Mutations** | Browser refreshed multiple times during active conflict state. | State remained `CONFLICTED` in PostgreSQL. Zero phantom transitions. |
| **Publication Gate Enforcement** | Attempted to call `/publish` on conflicted draft before operator sign-off. | Rejected by SANOCEA Policy Engine (Outcome: `EXCEPTION`). |
| **Financial Refund Gate** | Evaluated ₹840 refund against ₹500 threshold. | Output: `REQUIRE_APPROVAL`. Refund held; approval minted. |
| **Tamper-Proof Audit** | Attempted SQL `DELETE FROM audit_events`. | PostgreSQL trigger `trg_audit_no_update` aborted transaction with exception. |

| Security Invariant | Test Method | Result |
|---|---|---|
| **Zero UI State Mutations** | Browser refreshed multiple times during active conflict state. | State remained `CONFLICTED` in PostgreSQL. Zero phantom transitions. |
| **Publication Gate Enforcement** | Attempted to call `/publish` on conflicted draft before operator sign-off. | Rejected by SANOCEA Policy Engine (Outcome: `EXCEPTION`). |
| **Financial Refund Gate** | Evaluated ₹840 refund against ₹500 threshold. | Output: `REQUIRE_APPROVAL`. Refund held; approval minted. |
| **Tamper-Proof Audit** | Attempted SQL `DELETE FROM audit_events`. | PostgreSQL trigger `trg_audit_no_update` aborted transaction with exception. |
| **Multi-Tenant Isolation** | Scoped key attempted cross-tenant access. | Gateway returned HTTP 403 Forbidden. |

---

## 6. Known Presentation Limitations

1. **Desktop-Optimized Layout:** Designed specifically for 1280px+ desktop/laptop displays used during prospect video calls. Not optimized for mobile screens.
2. **Single Reference Tenant:** The Command Center is configured for `ref_anchal_heritage`. Multi-merchant tenancy switching is an administrative feature reserved for Stage 5.
3. **Simulated Channels Visually Isolated:** Simulated Amazon, Flipkart, and Meesho channels are not presented as active publication targets, preserving commercial credibility.
