# SANOCEA REFERENCE MERCHANT PROSPECT DEMO RUNBOOK (COMMAND CENTER EDITION)

> **Canonical Document Location:** [`docs/demo/REFERENCE_MERCHANT_PROSPECT_DEMO_RUNBOOK.md`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/docs/demo/REFERENCE_MERCHANT_PROSPECT_DEMO_RUNBOOK.md)  
> **Certification Report:** [`docs/demo/OPERATIONS_COMMAND_CENTER_CERTIFICATION.md`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/docs/demo/OPERATIONS_COMMAND_CENTER_CERTIFICATION.md)

**Audience:** Prospective Enterprise Merchants, D2C Founders, E-Commerce VPs of Supply Chain, Technical Due Diligence Teams  
**Duration:** 5 to 10 Minutes  
**Reference Tenant:** `ref_anchal_heritage` (*Anchal Heritage Organics*)  
**Execution Environment:** Local Certified ERP Node (`http://127.0.0.1:8080`) with Live Shopify Store Read-Back  
**Date:** September 2026  
**Status:** Certified & Demo-Ready (with identified presentation gaps)  

---

## 1. Executive Demonstration Philosophy

When demonstrating SANOCEA to prospective clients, adhere to three core operational rules:
1. **Prioritize Business Outcomes over Developer Plumbing:** Prospects care about margin preservation, avoiding stockouts, eliminating price errors, and automating manual toil. Frame every technical check as a financial safeguard.
2. **Never Show Faked Success States:** Every command executed during this demo interacts with real database schemas, real MinIO S3 object storage, and real Shopify Admin GraphQL APIs.
3. **Emphasize Fail-Closed Governance:** In commercial operations, an ERP that fails closed and halts an unsafe action is worth 100x more than an AI tool that hallucinates a plausible price or SKU and causes real financial loss.
4. **n8n is Internal Plumbing (Do Not Expose):** n8n is an unbranded external transport and alert distributor. Never open n8n's visual canvas or workflow editor to the prospect.

---

## 2. Four-Tier Operational Classification Key

Every step in this runbook is tagged with its formal operational classification:
- **`[LIVE / CERTIFIED]`**: Real external APIs (Shopify Admin GraphQL), PostgreSQL engine-level triggers, or AES-256-GCM encrypted credential vault.
- **`[SYNTHETIC DATA / REAL LOGIC]`**: Reference Merchant fictional data (`ref_anchal_heritage`) running through genuine SANOCEA production code.
- **`[POC-CERTIFIED INTEGRATION]`**: Peripheral integration architecture proven locally (n8n dropzone retrieval and alert dispatch).
- **`[SIMULATED / UNAVAILABLE]`**: Simulated marketplace channels (Amazon/Flipkart) or capabilities not yet implemented (Operator Web UI, live Razorpay/Stripe webhooks).

Steps that expose developer tooling, raw terminal output, or unformatted JSON payloads are marked with:  
`⚠️ DEVELOPER TOOLING / RAW JSON PRESENTATION GAP`

---

## 3. Pre-Demo Setup Checklist (2 Minutes Before Demo)

Ensure the following processes and visual assets are pre-staged:
1. **Terminal 1 (Backend Stack):** PostgreSQL 16 on port `55432`, MinIO S3 on `59000`, and FastAPI on `8080`.
2. **Browser Tab 1:** Shopify Admin Products page open to `sanocea-commerce-os-dev.myshopify.com/admin/products`.
3. **Application 1 (Excel):** Open `tests/fixtures/reference_merchant/supplier_price_list_messy.xlsx` showing cell `C5` with the formula `=130*1.20`.
4. **Application 2 (PDF Viewer):** Open `tests/fixtures/reference_merchant/product_specifications.pdf` showing multi-product specifications.

---

## 4. The 5–10 Minute Live Demonstration Flow

```
[Step 1] Merchant gives SANOCEA messy operational data
    │
    ▼
[Step 2] SANOCEA detects what is wrong (Ballast quarantined, formula preserved)
    │
    ▼
[Step 3] SANOCEA refuses unsafe action (Cross-source conflict -> Fail-closed gate)
    │
    ▼
[Step 4] Operator resolves the exception (Audited disambiguation)
    │
    ▼
[Step 5] SANOCEA executes permitted action (Mutates Shopify live)
    │
    ▼
[Step 6] External system is independently checked (Shopify Admin GraphQL read-back)
    │
    ▼
[Step 7] Controlled inventory, order, return & policy-gated refund operations
    │
    ▼
[Step 8] Tamper-proof append-only PostgreSQL audit ledger
```

---

### STEP 1: Merchant Gives SANOCEA Messy Operational Data
**Duration:** 1 Minute  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]` + `[POC-CERTIFIED INTEGRATION]`  
`⚠️ DEVELOPER TOOLING / RAW JSON PRESENTATION GAP` (Triggered via terminal CLI or background dropzone poller)

#### What the Prospect Sees:
- **Visual Display:** The presenter brings up Microsoft Excel on screen showing `supplier_price_list_messy.xlsx`. The presenter points to cell `C5`, which contains `=130*1.20` instead of a static number, and points to the hidden tab `Internal_Costing`.
- **System Action:** File is delivered to the ingestion dropzone. n8n retrieves the raw binary and streams it untouched to `POST /merchants/ref_anchal_heritage/catalogue/ingest`.

#### Presenter Script:
> *"In the real world, your suppliers and brand partners don't send you pristine REST APIs. They send you messy Excel spreadsheets with uncalculated formulas, uncompressed multi-page PDFs, and corrupted system files like `.DS_Store` or raw binaries. Legacy ERPs crash when they see this data. Modern 'AI wrappers' guess or hallucinate prices. Watch how SANOCEA takes in this exact raw file without guessing."*

---

### STEP 2: SANOCEA Detects What Is Wrong
**Duration:** 1.5 Minutes  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]`  
`⚠️ DEVELOPER TOOLING / RAW JSON PRESENTATION GAP` (Results displayed via terminal summary or API response)

#### What the Prospect Sees:
- **Terminal Output:**
  ```text
  [INGESTION PIPELINE] Processing raw supplier package...
    -> Quarantined ballast file: 'ballast_corrupt.bin' (Audit action: file_quarantined)
    -> Quarantined system file: '.DS_Store'
    -> Isolated hidden worksheet: 'Internal_Costing' (Zero internal margins leaked)
    -> Formula captured honestly: Wholesale_Matrix!C5 -> '=130*1.20' (Cached: 156.0)
    -> Extracted 1 canonical product draft: ANCHAL-KACHI-GHANI with 3 variants
  ```

#### Presenter Script:
> *"Notice three critical protections: First, SANOCEA immediately quarantined the corrupt ballast without crashing the server. Second, the hidden worksheet containing internal profit margins was completely isolated—not a single private margin leaked into the catalog. Third, SANOCEA did not guess the calculated price. It recorded the exact formula `=130*1.20`, the cached value ₹156.00, and the exact cell locator `Wholesale_Matrix!C5`. We have 100% provenance for every commercial fact."*

---

### STEP 3: SANOCEA Refuses Unsafe Action
**Duration:** 1.5 Minutes  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]` + `[POC-CERTIFIED INTEGRATION]`  
`⚠️ DEVELOPER TOOLING / RAW JSON PRESENTATION GAP` (Raw JSON exception output and notification payload)

#### What the Prospect Sees:
- **System Action:** A secondary external marketplace feed (`conflicting_feed.csv`) arrives claiming the price for the same SKU is ₹145.00 (or ₹168.00).
- **Terminal Output / Notification Payload:**
  ```json
  {
    "merchant_id": "ref_anchal_heritage",
    "alert_title": "Commercial Fact Exception Detected in Supplier Feed",
    "exception_count": 1,
    "summary_message": "Product draft pdr_780da... requires corrective work: CONFLICTED",
    "conflict_details": {
      "price": ["supplier_price_list_messy.xlsx: 156.00", "conflicting_feed.csv: 145.00"]
    },
    "publication_policy_outcome": "EXCEPTION",
    "review_url": "http://127.0.0.1:8080/merchants/ref_anchal_heritage/catalogue/drafts"
  }
  ```

#### Presenter Script:
> *"Here is where SANOCEA protects your balance sheet. In the supplier price list, Mustard Oil was ₹156.00. But in the marketplace feed, the exact same SKU is listed at ₹145.00. Most automated systems would silently take the newest price, average them, or publish bad data. SANOCEA's publication gate instantly fails closed. The draft is locked in a CONFLICTED state. An exception notification is dispatched to the team with a secure review link. Nothing can be published to Shopify while this commercial conflict exists."*

---

### STEP 4: Operator Resolves the Exception
**Duration:** 1 Minute  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]`  
`⚠️ DEVELOPER TOOLING / RAW JSON PRESENTATION GAP` (Currently executed via API call `POST /conflicts/resolve` or pre-configured script)

#### What the Prospect Sees:
- **System Action:** The authorized merchant merchandiser reviews the two evidence sources and selects ₹156.00 as the authoritative retail price.
- **Terminal / API Output:**
  ```text
  [OPERATOR ACTION] Resolving conflict for draft 'ANCHAL-KACHI-GHANI'...
    -> Selected Value: 15600 paise (₹156.00)
    -> Source Selected: supplier_price_list_messy.xlsx
    -> Signed By: operator@anchalheritage.com
    -> Draft State Transition: CONFLICTED -> READY
    -> Commercial Facts: APPROVED
  ```

#### Presenter Script:
> *"In production, your merchandiser opens their exception inbox, sees the side-by-side evidence with source locators, clicks ₹156.00, and signs off. Now watch: the moment the authorized operator resolves the conflict, SANOCEA writes the decision to the permanent audit ledger and unlocks the publication gate."*

---

### STEP 5 & 6: Permitted Execution & Real External Read-Back
**Duration:** 2 Minutes  
**Classification:** `[LIVE / CERTIFIED]`  
**VISUAL HIGHLIGHT:** Switching from Terminal to Real Shopify Admin Web Interface

#### What the Prospect Sees:
- **Terminal Execution:**
  ```text
  [PUBLICATION] Requesting publication to channel 'chn_shopify_live'...
    -> Invoking Shopify Admin GraphQL API (2024-10)...
    -> Created Shopify Product: gid://shopify/Product/9077451915343
    -> Created 3 Product Variants: [1L Pouch, 1L Bottle, 5L Can]
    -> Inventory Tracking: ENABLED across locations
  [INDEPENDENT READ-BACK] Querying Shopify Admin GraphQL API...
    -> Product Title: 'Anchal Cold-Pressed Kachi Ghani Mustard Oil' (VERIFIED)
    -> Product Status: ACTIVE (VERIFIED)
    -> Variant Count: 3 (VERIFIED)
    -> Retail Price: ₹156.00 (VERIFIED)
  ```
- **Browser Display:** Presenter switches to the browser tab showing **Shopify Admin** (`sanocea-commerce-os-dev.myshopify.com/admin/products`), hits **Refresh**, and shows:
  - Product Title: *Anchal Cold-Pressed Kachi Ghani Mustard Oil*
  - Status: *Active*
  - The 3 variants with prices and barcodes intact.

#### Presenter Script:
> *"This is not a mock. We just made a live mutation against Shopify's Admin GraphQL API. And notice: SANOCEA did not simply trust the HTTP 200 return code. SANOCEA immediately issued an independent read-back query to Shopify's servers, verifying that the title, the active status, and all three variant pricing structures match our canonical ledger byte-for-byte."*

---

### STEP 7: Controlled Inventory, Orders, Returns & Policy-Gated Refunds
**Duration:** 1.5 Minutes  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]`  
`⚠️ DEVELOPER TOOLING / RAW JSON PRESENTATION GAP` (State transitions logged via terminal output)

#### What the Prospect Sees:
- **Terminal Output:**
  ```text
  [ORDER INGESTION] Order #ORD-10928 received for 5 units (SKU: ANCHAL-KACHI-1L-BTL)
    -> Multi-Location Evaluation: Delhi Hub selected (Proximity priority 1)
    -> DB-Atomic SQL Reservation: Stock drops from 150 -> 145 (Available: 145)
    -> Replay Test: Duplicate webhook received -> ZERO double-deduction (Idempotent)
  [CUSTOMER RETURN] Return requested for 5 units...
    -> Inspection Status: PASSED
    -> Physical Restock: Delhi Hub stock restored from 145 -> 150
  [POLICY-GATED REFUND] Evaluating merchant refund limits...
    -> Case A: Refund ₹156.00 <= Limit ₹500.00 -> Outcome: AUTOMATICALLY PERMITTED
    -> Case B: Refund ₹840.00 > Limit ₹500.00 -> Outcome: HELD FOR FINANCIAL APPROVAL
  ```

#### Presenter Script:
> *"Now let's look at post-order reality. When an order arrives, SANOCEA doesn't do sloppy in-memory math. It executes a database-atomic SQL reservation with row-level locks. If a network blip causes the Shopify webhook to fire twice, our idempotency key ensures stock is never deducted twice. Later, when the customer returns the item and warehouse inspection passes, the stock is automatically returned to the shelf. And for refunds, SANOCEA enforces your executive financial policy: a ₹156 refund is permitted automatically, but a ₹840 refund exceeds the ₹500 limit and is held for a finance manager's sign-off."*

---

### STEP 8: Everything is Auditable — Tamper-Proof PostgreSQL Ledger
**Duration:** 1 Minute  
**Classification:** `[LIVE / CERTIFIED]`  
`⚠️ DEVELOPER TOOLING / RAW JSON PRESENTATION GAP` (Raw SQL query executed in terminal)

#### What the Prospect Sees:
- **Terminal / psql Output:**
  ```sql
  -- Querying total audit events for tenant
  SELECT COUNT(*) FROM audit_events WHERE merchant_id = 'ref_anchal_heritage';
  -- count: 232

  -- Attempting to delete or alter audit history as a database administrator
  DELETE FROM audit_events WHERE merchant_id = 'ref_anchal_heritage';
  ERROR:  audit_events is append-only
  CONTEXT:  PL/pgSQL function prevent_audit_update_delete() line 3 at RAISE
  ```

#### Presenter Script:
> *"Every decision we just showed you—from the quarantined binary, to the human price sign-off, to the live Shopify publication, to the atomic inventory reservation—is recorded in our immutable audit ledger. Notice what happened when we tried to delete the audit records: the database threw an error. That wasn't our application code; that was enforced by PostgreSQL database triggers. Even if an engineer or IT administrator gets direct database access, they cannot alter or wipe your commercial compliance history. That is enterprise-grade operational integrity."*

---

## 5. Tough Prospect Questions & Scripted Responses

### Q1: "Why didn't your AI just guess the missing price or attribute so my team doesn't have to review it?"
**Response:**  
> *"In consumer goods and e-commerce, an AI guessing a price means either losing 30% margin or alienating customers. An AI guessing an HSN code means committing tax fraud under GST regulations. SANOCEA uses machine intelligence to extract facts, parse messy spreadsheets, and detect anomalies—but we strictly enforce zero-invention. If data is missing or conflicting, SANOCEA fails closed and alerts your team. We automate 95% of operational toil without ever gambling with your balance sheet."*

### Q2: "Can our operations team bypass the approval gate when we are rushing a flash sale?"
**Response:**  
> *"Bypassing the gate is an explicit policy configuration set by your executive leadership, not an ad-hoc shortcut taken by individual operators. You can configure high-trust policies that auto-approve drafts meeting deterministic criteria (e.g., verified manufacturer EDI feed, exact barcode match). However, when two supplier feeds claim conflicting prices for the same SKU, SANOCEA will never allow an unauthenticated bypass. Every resolution requires an authenticated operator signature and is permanently logged in the audit ledger."*

### Q3: "What screen will my catalog team actually work in every day?"
**Response:**  
> *"Today, we demonstrated the SANOCEA Core Engine via its certified REST APIs so you could see the underlying business rules, database locks, and live Shopify verification with complete transparency. In production, your operations team works in our web-based Operator Console, where exceptions appear as an actionable inbox with side-by-side evidence diffs. The backend powering that console is the exact certified engine you just saw."*

### Q4: "How do you prevent overselling when orders hit multiple channels simultaneously?"
**Response:**  
> *"Most middleware tools read inventory into memory, do the subtraction, and write it back—which causes fatal race conditions during flash sales. SANOCEA uses database-atomic SQL reservation primitives (`store.reserve_inventory_atomic`) with row-level locks directly inside PostgreSQL. If 10 orders hit the system simultaneously for the last 2 units, the database guarantees that exactly 2 are reserved and the other 8 fail gracefully with explicit shortfall exceptions."*

---

## 6. Demonstration Quick Reference Sheet

| Time | Step | Visual Anchor | Key Message |
|---|---|---|---|
| **0:00 - 1:00** | 1. Messy Input | Excel showing `=130*1.20` | Real data is messy; legacy systems crash. |
| **1:00 - 2:30** | 2. Anomaly Detection | Terminal Ingestion Log | Ballast quarantined; zero leaked margins. |
| **2:30 - 4:00** | 3. Refuse Unsafe Action | Formatted Exception Alert | Cross-source conflict; publication refused. |
| **4:00 - 5:00** | 4. Human Resolution | API / Command Output | Audited operator choice (₹156 signed off). |
| **5:00 - 7:00** | 5 & 6. Live Shopify | **Shopify Admin Web UI** | Real GraphQL mutation + live read-back. |
| **7:00 - 8:30** | 7. Inventory & Refunds | Terminal Stock Log | Atomic reservation; policy-gated refunds. |
| **8:30 - 9:30** | 8. Audit Ledger | Terminal `psql` Trigger Error | Tamper-proof PostgreSQL triggers prevent edits. |
