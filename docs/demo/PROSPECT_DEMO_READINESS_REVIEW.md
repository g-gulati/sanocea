# SANOCEA REFERENCE MERCHANT — PROSPECT DEMO READINESS REVIEW

**Document Identifier:** `DEMO-REVIEW-2026-01`  
**Tenant Under Review:** `ref_anchal_heritage` (*Anchal Heritage Organics*)  
**Architecture Specification:** [`N8N_ECOSYSTEM_AUDIT.md`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/docs/architecture/integrations/N8N_ECOSYSTEM_AUDIT.md)  
**Certification References:**  
- Core Reference Merchant: [`docs/audits/REFERENCE_MERCHANT_CERTIFICATION.md`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/docs/audits/REFERENCE_MERCHANT_CERTIFICATION.md)  
- n8n Peripheral POC: [`docs/audits/N8N_REFERENCE_MERCHANT_POC_CERTIFICATION.md`](file:///D:/Autonomous%20E-Commerce%20ERP/sanocea/docs/audits/N8N_REFERENCE_MERCHANT_POC_CERTIFICATION.md)  
**Date:** September 16, 2026  
**Auditor / Reviewer:** SANOCEA Autonomous Architecture & Operations Group  

---

## 1. Executive Assessment & Overall Verdict

### DEMO READINESS: **READY WITH PRESENTATION GAPS**

The SANOCEA core ERP engine, Reference Merchant demonstration tenant (`ref_anchal_heritage`), peripheral transport/notification bridge (n8n POC), and live Shopify Dev Store publication/verification are **technically certified and functionally sound**. 

The operational narrative requested by leadership:
$$\text{Messy Data} \longrightarrow \text{Anomaly Detection} \longrightarrow \text{Fail-Closed Refusal} \longrightarrow \text{Human Resolution} \longrightarrow \text{Permitted Execution} \longrightarrow \text{External Read-Back} \longrightarrow \text{Controlled Operations} \longrightarrow \text{Append-Only Audit}$$
is fully supported by genuine production logic, real PostgreSQL schemas, real MinIO object storage, and real Shopify Admin GraphQL APIs.

However, there is **currently no operator web dashboard / graphical user interface**. All operations (file upload, conflict inspection, approval sign-off, inventory reservation, and audit ledger validation) currently surface through terminal CLI runners, raw JSON payloads via HTTP, and SQL queries. 

While this technical presentation is convincing for **technical due diligence teams (CTOs, VPs of Engineering)**, it presents **presentation friction for non-technical commercial buyers (D2C Founders, Heads of Supply Chain)** who expect a graphical operational portal.

---

## 2. Four-Tier Capability Classification

Every capability demonstrated to prospects must be strictly categorized into one of four tiers to maintain complete commercial and technical honesty:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   SANOCEA CAPABILITY TIERS                                       │
├──────────────────────────────┬─────────────────────────────────┬─────────────────────────────────┤
│ 1. LIVE / CERTIFIED          │ Real external APIs & triggers   │ Shopify Live, PG Triggers, Vault│
│ 2. SYNTHETIC DATA/REAL LOGIC │ Real production code + ref data │ Ingestion, Conflicts, Alloc, S3 │
│ 3. POC-CERTIFIED INTEGRATION │ Proven peripheral architecture  │ n8n Dropzone & Notification     │
│ 4. SIMULATED / UNAVAILABLE   │ Mocked or not yet implemented   │ Amazon/Flipkart, Web UI, Razorpay│
└──────────────────────────────┴─────────────────────────────────┴─────────────────────────────────┘
```

### Tier 1: LIVE / CERTIFIED
Actual SANOCEA production code executing against external third-party systems or tamper-proof system primitives:
- **Live Shopify Channel Publication & Read-Back:** Real mutations against Shopify Dev Store (`sanocea-commerce-os-dev.myshopify.com`) via Admin GraphQL API (version `2024-07`/`2024-10`). Generates real Shopify Product GIDs (`gid://shopify/Product/...`), multi-variant matrices, and verifies state via independent GraphQL query.
- **Append-Only Tamper-Proof Audit Ledger:** PostgreSQL engine-level triggers (`trg_audit_no_update` calling `prevent_audit_update_delete()`) that intercept and abort any SQL `UPDATE` or `DELETE` attempt, even from administrative database users.
- **Scoped Credential Vault:** AES-256-GCM envelope encryption with master key versioning (`SANOCEA_CRED_MASTER_KEY_*`) storing sensitive tokens at rest in PostgreSQL.

### Tier 2: SYNTHETIC DATA / REAL LOGIC
Fictional Reference Merchant data (`ref_anchal_heritage`) processed through genuine, untampered SANOCEA production engines:
- **Messy Multi-Source Ingestion:** Ingesting real Excel workbooks with formulas (`=130*1.20`), multi-page specification PDFs, and CSV feeds.
- **Ballast File & Hidden Sheet Quarantine:** Real ingestion parser that quarantines corrupt binaries (`ballast_corrupt.bin`), OS noise (`.DS_Store`), and hidden financial calculation tabs (`Internal_Costing`).
- **Commercial Fact Extraction & Provenance Tracking:** Zero-invention policy classifying facts (`SUPPLIER_OFFER`, `EXTRACTED`, `AI_ENRICHED`, `MISSING`) with exact cell and PDF page locators.
- **Cross-Source Commercial Conflict Detection:** Real validator detecting discrepancies (e.g. ₹156.00 in supplier catalog vs ₹145.00/₹168.00 in marketplace feeds).
- **Fail-Closed Publication Policy:** Real policy engine evaluating product completeness, commercial fact approval, and identity certainty, refusing publication when conflicts exist.
- **Human Approval & Conflict Resolution:** Real API endpoints (`/conflicts/resolve`, `/approve-facts`) capturing digital signatures and operator IDs before state transition.
- **Multi-Location Inventory Allocation & Reservation:** Real DB-atomic SQL reservation primitives (`store.reserve_inventory_atomic`) with row-level locks across Delhi, Mumbai, and Bengaluru hubs.
- **Post-Order Lifecycle & Policy-Gated Refunds:** Warehouse return inspection restock logic and financial refund policy enforcement (automatic refund under ₹500; financial approval hold above ₹500).

### Tier 3: POC-CERTIFIED INTEGRATION
Peripheral integration architecture proven locally against the certified Reference Merchant:
- **Dropzone File Transport (n8n):** Simulated Google Drive dropzone file retrieval preserving raw binary bytes without parsing or altering commercial facts.
- **Automated Exception Notification Bridge (n8n):** Polling SANOCEA exceptions API, routing via official nodes, formatting payload with SANOCEA review URL, and delivering to notification sink without embedding unauthenticated approval URLs.
- **Adversarial Resilience:** Verified across 7 failure scenarios (idempotency replay, transfer interruption, API unavailability, ballast quarantine, sink HTTP 500, credential privilege confinement, and execution database purge).

### Tier 4: SIMULATED / UNAVAILABLE
Capabilities that are not currently live-certified and must be acknowledged honestly if asked:
- **Simulated Sales Channels:** Amazon India (`chn_amazon_in`), Flipkart India (`chn_flipkart_in`), and Meesho (`chn_meesho_in`). The connector code and data mappings exist in the repository, but there is no active live seller account or external read-back verification.
- **Unavailable - Operator Web UI:** There is no graphical browser interface for SANOCEA operators. All interaction occurs via REST API, CLI scripts, or database queries.
- **Unavailable - Payment Gateway Webhooks:** Automatic debiting/crediting of customer bank accounts via Razorpay or Stripe is simulated as ledger transactions, not live bank API calls.
- **Unavailable - 3PL Carrier Webhooks:** Live tracking status updates from Shiprocket, Delhivery, or Bluedart are simulated via test payloads.
- **Unavailable - Customer Support Chat Widget:** Chatwoot support trail exists in database queries, but no live front-end chat widget is wired to a prospect-facing portal.

---

## 3. Analysis: Does the Absence of a Web UI Damage the Demo?

### Assessment by Prospect Persona

| Prospect Persona | Primary Concern | Impact of CLI / API Demo | Severity | Mitigation / Strategy |
|---|---|---|---|---|
| **VP of Engineering / CTO** | "Is this real software or a Figma wrapper with no backend?" | **POSITIVE / HIGH TRUST.** Demonstrating raw PostgreSQL triggers, cryptographic master keys, and direct GraphQL mutations against Shopify proves the system actually works. | LOW | Lean into the API and database triggers. Show the code and live Shopify store. |
| **D2C Founder / CEO** | "How does this make my business scale faster without errors?" | **MODERATE SKEPTICISM.** Understands the business narrative (avoiding price mistakes), but may feel the software is "too early" or "not user-friendly" for their team. | MEDIUM | Emphasize the live Shopify product page and the financial protection of fail-closed gates. |
| **Head of Supply Chain / E-Commerce Operations** | "What will my catalog and fulfillment operators stare at every day?" | **HIGH RISK.** Non-technical operators cannot work in PowerShell or inspect raw JSON. They will wonder if they have to hire software engineers to run their catalog. | HIGH | Clarify that the demo exercises the *core control engine/API layer*, and that the web operator console is the final frontend skin built on top of these certified endpoints. |

### Conclusion on Operator UI
The absence of a web UI **does not invalidate the demonstration**, provided the presenter frames the presentation accurately:
> *"Today we are showing you the SANOCEA Core Operations Engine—the brain that enforces business rules, inventory reservations, and audit compliance. Everything you see today is driven through our certified REST API. In production, your operations team interacts with our Operator Portal, while your suppliers drop files via email or Google Drive. But right now, we want to prove to you that the underlying commercial logic is bulletproof before skinning it in a browser."*

---

## 4. Prospect-Facing Presentation Gaps & Friction Points

The following table details every step of the current demonstration where developer tooling, raw JSON, or terminal commands are exposed, along with the friction it introduces:

| Demo Step | What the Prospect Currently Sees | Friction / Presentation Gap | Presenter Mitigation |
|---|---|---|---|
| **1. Tenant Reset** | Terminal scrolling PowerShell text from `scripts/reset_reference_merchant.py` | Looks like a developer test script rather than an enterprise platform feature. | Frame as: *"Cryptographic isolation and audit-clean environment setup in < 2 seconds."* |
| **2. Messy File Ingestion** | Python CLI invocation or n8n CLI execution; terminal log output. | Prospect cannot visually see the dropzone folder or the ingestion pipeline triggering. | Open the actual Excel file (`supplier_price_list_messy.xlsx`) in Microsoft Excel first to show the formula `=130*1.20` before running the command. |
| **3. Anomaly & Conflict Detection** | Raw JSON terminal output: `{"publication_policy_outcome": "EXCEPTION", "conflicts": ["price"]}` | Prospect must read unformatted JSON brackets and keys to understand that a price conflict occurred. | Read the formatted n8n notification payload or highlight the exact exception string: *"₹156 vs ₹145 conflict detected; publication refused."* |
| **4. Human Conflict Resolution** | Presenter executing a `curl` command or Python script calling `POST /conflicts/resolve` with a JSON body. | Commercial buyers do not approve prices using `curl` or terminal commands; this looks awkward to non-technical buyers. | Explain: *"This API call represents what happens when your merchandiser clicks 'Approve ₹168' in the portal."* Keep command pre-staged in a script. |
| **5. Live Shopify Publication** | Terminal log confirming `gid://shopify/Product/...` followed by switching to Chrome to view Shopify Admin. | **STRONGEST STEP IN DEMO.** Switching to the real Shopify Admin GUI provides immediate visual relief and undeniable external proof. | Maximize time spent here. Refresh the live Shopify store, show variants, inventory levels, and active status. |
| **6. Inventory Allocation & Post-Order** | Terminal output showing database inventory counts changing (`150 -> 145 -> 150`). | Abstract numbers in a terminal window. No visual warehouse map or packing slip. | Walk through the exact math slowly: 150 available - 5 ordered = 145 reserved. Order returned -> back to 150. |
| **7. Append-Only Audit Proof** | Terminal running raw `psql` command attempting `DELETE FROM audit_events` and receiving SQL trigger error. | Raw SQL commands can intimidate non-technical buyers, though technical buyers love it. | Focus on the punchline: *"Even a rogue IT administrator with full database access cannot erase the audit trail."* |

---

## 5. Minimum Presentation Layer Required (Before Public Rollout)

While the user has explicitly requested **not to build a UI yet**, the following constitutes the absolute minimum presentation layer recommended before demonstrating to non-technical commercial buyers:

1. **Near-Term (For Upcoming Demo - No Code Changes to Core):**
   - **Visual Asset Pre-staging:** Keep Microsoft Excel, the raw PDF, and the live Shopify Admin portal open in separate browser/app tabs.
   - **Formatted Terminal Script:** Run a single, polished demo script (`scripts/run_prospect_demo.py`) with rich, clean colored terminal output (no raw python tracebacks or JSON walls).
   - **Postman / Thunder Client Collection:** If demonstrating API interactions, use a pre-configured Postman collection with descriptive request names (*"1. Ingest Supplier Feed"*, *"2. View Detected Price Conflicts"*, *"3. Resolve Conflict to ₹168"*, *"4. Publish to Shopify"*) instead of running shell scripts.
2. **Medium-Term (Fast Follow - Post Demo):**
   - A single-page read-only **Operator Console Web UI** (React/Vite or lightweight Tailwind HTML) that simply queries the existing `/merchants/ref_anchal_heritage/operator/summary`, `/catalogue/drafts`, `/exceptions`, and `/approvals` endpoints. No new backend code required.

---

## 6. Demo Script Feasibility & Timing (5–10 Minutes)

```
[0:00 - 1:00] Step 1: The Commercial Problem & The Messy Source Files (Excel & PDF)
[1:00 - 2:30] Step 2: SANOCEA Ingestion, Anomaly Detection & Honest Formulas
[2:30 - 4:00] Step 3: The Fail-Closed Gate (Conflict Detected & Publication Refused)
[4:00 - 6:00] Step 4: Audited Operator Resolution & Live Shopify Publication
[6:00 - 7:30] Step 5: Real External Read-Back (Live Shopify Admin Inspection)
[7:30 - 9:00] Step 6: Atomic Inventory Allocation, Returns & Policy-Gated Refunds
[9:00 - 10:00] Step 7: Tamper-Proof PostgreSQL Audit Ledger & Wrap-up
```

Total Duration: **9 Minutes 30 Seconds** (Fits precisely within the 5–10 minute window).
