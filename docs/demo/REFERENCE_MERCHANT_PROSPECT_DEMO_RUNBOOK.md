# SANOCEA REFERENCE MERCHANT PROSPECT DEMO RUNBOOK (COMMAND CENTER EDITION)

**Audience:** Prospective Enterprise Merchants, D2C Founders, E-Commerce VPs of Supply Chain, Technical Due Diligence Teams  
**Duration:** 5 to 10 Minutes  
**Presentation Interface:** SANOCEA Operations Command Center (`http://127.0.0.1:8080/ui`)  
**External Verification Target:** Live Shopify Dev Store (`sanocea-commerce-os-dev.myshopify.com/admin/products`)  
**Reference Tenant:** `ref_anchal_heritage` (*Anchal Heritage Organics*)  
**Date:** September 2026  
**Status:** Certified & Demo-Ready (Command Center Graphical Presentation)  

---

## 1. Executive Demonstration Philosophy

When demonstrating SANOCEA to prospective clients:
1. **Prioritize Commercial Value & Safeguards over Developer Code:** Prospects care about protecting margin, avoiding stockouts, eliminating price errors, and automating repetitive toil. Frame every technical check as a financial safeguard.
2. **Never Show Faked Success States:** Every action in the Operations Command Center queries real database schemas, real MinIO S3 object storage, and real Shopify Admin GraphQL APIs.
3. **Emphasize Fail-Closed Governance:** In commercial operations, an ERP that fails closed and halts an unsafe action is worth 100x more than an AI tool that hallucinates a plausible price or SKU and causes real financial loss.
4. **n8n is Internal Plumbing (Do Not Expose):** n8n is an unbranded external transport and alert distributor. Never open n8n's visual canvas or workflow editor to the prospect.

---

## 2. Four-Tier Operational Classification Key

Every capability demonstrated is tagged with its formal operational classification:
- **`[LIVE / CERTIFIED]`**: Real external APIs (Shopify Admin GraphQL), PostgreSQL engine-level triggers, or AES-256-GCM encrypted credential vault.
- **`[SYNTHETIC DATA / REAL LOGIC]`**: Reference Merchant fictional data (`ref_anchal_heritage`) running through genuine SANOCEA production code.
- **`[POC-CERTIFIED INTEGRATION]`**: Peripheral integration architecture proven locally (n8n dropzone retrieval and alert dispatch).
- **`[SIMULATED / UNAVAILABLE]`**: Simulated marketplace channels (Amazon/Flipkart) or capabilities not yet implemented (live Razorpay/Stripe webhooks).

---

## 3. Pre-Demo Setup Checklist (2 Minutes Before Demo)

Ensure the following 3 windows/tabs are pre-staged on the presenter's screen:
1. **Browser Tab 1:** SANOCEA Operations Command Center (`http://127.0.0.1:8080/ui`) — Open to **Operations Overview**.
2. **Browser Tab 2:** Live Shopify Admin portal (`sanocea-commerce-os-dev.myshopify.com/admin/products`).
3. **Application 1 (Microsoft Excel):** Open `tests/fixtures/reference_merchant/supplier_price_list_messy.xlsx` showing cell `C5` with formula `=130*1.20`.

*(Optional for Technical Due Diligence: Keep a background terminal open to run raw SQL queries against PostgreSQL if a CTO asks for engine-level trigger verification).*

---

## 4. The 5–10 Minute Graphical Demonstration Flow

```
[Screen 1: Operations Overview] ➔ Messy Operational Input & Anomaly Detection
    │
    ▼
[Screen 2: Exceptions Queue] ➔ SANOCEA Refuses Unsafe Action (Conflict Gate)
    │
    ▼
[Screen 3: Evidence & Conflict Review] ➔ Side-by-Side Provenance & Operator Decision
    │
    ▼
[Screen 4: Publication & Verification] ➔ Live Shopify GraphQL Mutation & Read-Back
    │
    ▼
[Browser Tab 2: Shopify Admin UI] ➔ External Independent Proof
    │
    ▼
[Screen 5: Orders & Inventory] ➔ Multi-Location Atomic SQL Reservation & Proximity
    │
    ▼
[Screen 6: Returns & Refunds] ➔ Restock & Auto-Permitted vs Approval-Gated Refunds
    │
    ▼
[Screen 7: Audit Timeline] ➔ Immutable PostgreSQL 16 Compliance Trail
```

---

### STEP 1 & 2: Messy Input & Anomaly Detection (1.5 Minutes)
**Screen:** Microsoft Excel ➔ Command Center Tab 1 (**Operations Overview**)  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]` + `[POC-CERTIFIED INTEGRATION]`  

#### What the Prospect Sees:
1. **Excel Display:** Presenter shows `supplier_price_list_messy.xlsx`. Points to cell `C5` containing the formula `=130*1.20`, and points to the hidden worksheet `Internal_Costing`.
2. **Command Center Overview:** Presenter switches to Browser Tab 1 (`http://127.0.0.1:8080/ui`).
   - The top banner displays the merchant identity: *Anchal Heritage Organics*, GSTIN `07AAAAA0000A1Z5`, Currency `INR (₹)`, and active live Shopify store.
   - The **7-Stage Lifecycle Tracker** shows:
     - `1. Observe`: XLSX & PDF Ingested (Green).
     - `2. Detect`: Ballast Quarantined, Zero Invention Policy Enforced (Green).
     - `3. Block`: Commercial Conflict Active (Red Alert).

#### Presenter Script:
> *"In the real world, your suppliers don't send you pristine API feeds. They hand you messy Excel files with uncalculated formulas, uncompressed multi-page PDFs, and corrupted system files. Legacy ERPs crash; modern 'AI wrappers' hallucinate prices. Watch what SANOCEA did: it quarantined the corrupt binary file without crashing, completely isolated the hidden internal costing tab so zero margins leaked, and captured the formula `=130*1.20` honestly with its exact cell locator `Wholesale_Matrix!C5`. We preserve 100% provenance without guessing."*

---

### STEP 3: SANOCEA Refuses Unsafe Action (1.5 Minutes)
**Screen:** Command Center Tab 2 (**Exceptions Queue**)  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]`  

#### What the Prospect Sees:
- Presenter clicks on **Exceptions Queue** in the top navigation.
- The queue displays 1 active critical card:
  - **Category:** `CONFLICTING_PRODUCT_EVIDENCE` (P1 Commercial Risk badge)
  - **Affected SKU:** `ANCHAL-KACHI-GHANI`
  - **Status:** `BLOCKED / OPEN`
  - **Why SANOCEA Stopped Execution:**
    > *"Supplier feed price (₹145.00) conflicts with established catalogue price (₹156.00). SANOCEA has refused automatic publication to protect commercial margins."*
- A prominent button invites the operator: `[ Review & Resolve ]`.

#### Presenter Script:
> *"Here is where SANOCEA protects your balance sheet. In the supplier price list, Mustard Oil was listed at ₹156.00. But an incoming marketplace feed claims the exact same product is ₹145.00. Most automated tools would take the newest price, average them, or publish bad data. SANOCEA's publication gate instantly fails closed. The draft is locked in a CONFLICTED state. An alert was dispatched to our team. Nothing can reach Shopify while this commercial conflict exists."*

---

### STEP 4: Evidence & Conflict Review & Human Resolution (2 Minutes)
**Screen:** Command Center Tab 3 (**Evidence & Conflict Review**) — *THE CORE SCREEN*  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]`  

#### What the Prospect Sees:
- Presenter clicks `Review & Resolve`. The Evidence & Conflict Review screen opens:
  - **Top Banner:**  
    > **SANOCEA Zero-Invention Rule:** SANOCEA has not changed the commercial fact. Publication remains blocked pending resolution.
  - **Canonical Product Identity:** Displays title, Parent SKU `ANCHAL-KACHI-GHANI`, Identity Key `sku:ANCHAL-KACHI-GHANI` (`RESOLVED`), and 3 variants.
  - **Side-by-Side Fact Comparison Cards:**
    - **Source A (Established Catalogue):** Price **₹156.00**, Source `supplier_price_list_messy.xlsx`, Locator `Wholesale_Matrix!C5`, Formula `=130*1.20`, Cached `156.0`.
    - **Source B (Incoming Feed):** Price **₹145.00**, Source `conflicting_feed.csv`, Locator `Line 2`, Discrepancy: `- ₹11.00 (-7.05% margin loss)`.
  - **Operator Decision Panel:**
    - Radio buttons to select the authoritative value.
    - Presenter selects `Adopt ₹156.00` and leaves audit note: *"Approved wholesale margin formula (=130*1.20) as authoritative retail rate."*
    - Presenter clicks **"1. Resolve Conflict in SANOCEA"**.
    - Notification appears: `✓ Conflict successfully resolved to ₹156.00 in SANOCEA`.
    - Presenter clicks **"2. Sign-off & Approve Commercial Facts"**.
    - Status pill turns green: `DRAFT STATE: READY`.

#### Presenter Script:
> *"Notice the side-by-side evidence matrix: your merchandiser sees the exact formula from the Excel sheet, the incoming CSV line, and the financial margin impact (-7.05%). When our authorized operator selects ₹156.00 and signs off, SANOCEA does not just flip a boolean flag in memory. It records the digital signature, updates the canonical commercial fact, and unlocks the publication gate."*

---

### STEP 5 & 6: Live Execution & Real External Read-Back (2 Minutes)
**Screen:** Command Center Tab 4 (**Publication & Verification**) ➔ Browser Tab 2 (**Shopify Admin**)  
**Classification:** `[LIVE / CERTIFIED]`  

#### What the Prospect Sees:
1. **Command Center Publication Screen:**
   - Presenter clicks **Publication & Verification**.
   - The Stepper shows: `1. Conflict Gate (✓ Passed)` ➔ `2. Facts Approved (✓ Ready)`.
   - Target Channel card shows: `Anchal Online Store (Shopify D2C)`, Domain: `sanocea-commerce-os-dev.myshopify.com`.
   - Presenter clicks **"Publish to Live Shopify Store"**.
   - Stepper advances to `3. Live Mutation` and then `4. External Read-Back (VERIFIED)`.
   - The **Independent Read-Back Proof Card** populates:
     - Shopify Product GID: `gid://shopify/Product/9077451915343`
     - External State: `ACTIVE`
     - Verification: `VERIFIED BY SANOCEA GRAPHQL INSPECTOR`
2. **Switch to Shopify Admin (Browser Tab 2):**
   - Presenter switches to the real Shopify Admin tab and hits **F5 (Refresh)**.
   - The product *Anchal Cold-Pressed Kachi Ghani Mustard Oil* is live, with:
     - Status: Active
     - 3 Variants: 1L Pouch, 1L Bottle, 5L Can
     - Exact Price: ₹156.00

#### Presenter Script:
> *"This is not a mock or a staging clone. SANOCEA just executed a live mutation against Shopify's Admin GraphQL API. And notice: SANOCEA didn't just trust Shopify's HTTP 200 return code. SANOCEA immediately issued an independent read-back query to Shopify's servers, verifying that the title, active status, and all three variant prices match our database byte-for-byte. When we switch to Shopify Admin and refresh, here is the live product ready to accept customer orders."*

---

### STEP 7: Controlled Inventory, Orders, Returns & Refunds (1.5 Minutes)
**Screen:** Command Center Tabs 5 (**Orders & Inventory**) & 6 (**Returns & Refunds**)  
**Classification:** `[SYNTHETIC DATA / REAL LOGIC]`  

#### What the Prospect Sees:
1. **Orders & Inventory Tab:**
   - Displays multi-location warehouse table:
     - **Delhi Central Hub:** Available stock drops atomically `150 ➔ 145` (5 units reserved for Order `#ORD-10928`).
     - **Mumbai Logistics Park:** 100 available.
     - **Bengaluru South Node:** 50 available.
   - Proximity routing: Delhi Hub automatically selected for Delhi customer (`110001`).
   - Idempotency status: `CONFIRMED (Duplicate webhooks ignored without double-deduction)`.
2. **Returns & Refunds Tab:**
   - Return card shows: Order `#ORD-10928`, Warehouse Inspection `PASSED`, Stock restored to Delhi Hub (`145 ➔ 150`).
   - Policy Engine Comparison:
     - **Case A (Standard Return - ₹156.00):** Within ₹500 limit ➔ `AUTOMATICALLY PERMITTED (Green)`.
     - **Case B (High-Value Return - ₹840.00):** Exceeds ₹500 limit ➔ `HELD FOR FINANCIAL APPROVAL (Amber)`. Payout blocked until finance manager signs off.

#### Presenter Script:
> *"Now look at post-order reality. When an order arrives, SANOCEA executes a database-atomic SQL reservation with row-level locks. If a network glitch causes Shopify's webhook to fire twice, our idempotency key ensures stock is never deducted twice. When the customer returns the item and inspection passes, stock is immediately restored to the shelf. And for refunds, SANOCEA enforces your executive financial policy: a ₹156 refund is permitted automatically, but an ₹840 refund exceeds your ₹500 limit and is held for a finance manager's sign-off."*

---

### STEP 8: Immutable Compliance Audit Trail (1 Minute)
**Screen:** Command Center Tab 7 (**Audit Timeline**)  
**Classification:** `[LIVE / CERTIFIED]`  

#### What the Prospect Sees:
- Presenter clicks **Audit Timeline**.
- Displays the chronological event stream directly from PostgreSQL:
  - Events: `file_quarantined`, `product_draft_created`, `commercial_conflict_detected`, `conflict_resolved`, `product_facts_approved`, `publish_product`, `listing_verified`, `order_inventory_reserved`, `return_inspection_passed`.
- The top banner highlights:
  > **PostgreSQL 16 Engine Trigger Protected:** The `audit_events` table is governed by trigger `trg_audit_no_update`. SQL `UPDATE` and `DELETE` operations are aborted with an exception at the database engine level.

#### Presenter Script:
> *"Every single decision we just walked through—from the quarantined binary, to the human price sign-off, to the live Shopify publication, to the atomic inventory reservation—is recorded in our immutable audit ledger. In SANOCEA, this isn't just an application log file. It is enforced by PostgreSQL database triggers. Even if an engineer or IT administrator gets direct database access, they cannot alter or delete your commercial compliance history. That is what enterprise operational integrity looks like."*

---

## 5. Tough Prospect Questions & Scripted Responses

### Q1: "Why didn't your AI just guess the missing price so my team doesn't have to review it?"
**Response:**  
> *"In e-commerce, an AI guessing a price means either losing 30% margin or alienating customers. An AI guessing an HSN code means committing tax fraud under GST regulations. SANOCEA uses machine intelligence to structure messy spreadsheets and detect anomalies—but we strictly enforce zero-invention. If data conflicts, SANOCEA fails closed and alerts your team. We automate 95% of operational toil without ever gambling with your balance sheet."*

### Q2: "Can our operations team bypass the approval gate when we are rushing a flash sale?"
**Response:**  
> *"Bypassing the gate is an explicit policy configuration set by your executive leadership, not an ad-hoc shortcut taken by individual operators. You can configure high-trust policies that auto-approve drafts meeting deterministic criteria (e.g., verified manufacturer EDI feed, exact barcode match). However, when two supplier feeds claim conflicting prices for the same SKU, SANOCEA will never allow an unauthenticated bypass. Every resolution requires an authenticated operator signature and is permanently logged in the audit ledger."*

### Q3: "Can our cloud database administrator edit or wipe audit events if an error occurs?"
**Response:**  
> *"No. The `audit_events` table in PostgreSQL is protected by an engine-level trigger (`trg_audit_no_update`) that intercepts every `UPDATE` and `DELETE` operation and raises an exception. Even a database superuser running manual SQL statements cannot delete or mutate audit records without dropping the system triggers—which is immediately detected and flagged by SANOCEA's integrity checks."*

---

## 6. Demonstration Quick Reference Sheet

| Time | Step | Screen / View | Key Message |
|---|---|---|---|
| **0:00 - 1:00** | 1. Messy Input | Excel showing `=130*1.20` | Real data is messy; legacy systems crash. |
| **1:00 - 2:00** | 2. Anomaly Detection | Overview Tab (`/ui`) | Ballast quarantined; zero leaked margins. |
| **2:00 - 3:00** | 3. Refuse Unsafe Action | Exceptions Queue Tab | Cross-source conflict; publication refused. |
| **3:00 - 5:00** | 4. Human Resolution | Evidence Review Tab | Side-by-side provenance; operator sign-off. |
| **5:00 - 7:00** | 5 & 6. Live Shopify | Publication Tab + **Shopify Admin** | Real GraphQL mutation + live read-back. |
| **7:00 - 8:30** | 7. Inventory & Refunds | Inventory & Refunds Tabs | Atomic reservation; policy-gated refunds. |
| **8:30 - 9:30** | 8. Audit Ledger | Audit Timeline Tab | Tamper-proof PostgreSQL triggers prevent edits. |
