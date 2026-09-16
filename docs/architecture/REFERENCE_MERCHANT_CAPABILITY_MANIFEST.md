# SANOCEA REFERENCE MERCHANT CAPABILITY MANIFEST
**Tenant Identifier:** `ref_anchal_heritage`  
**Merchant Entity:** Anchal Heritage Organics (Direct-to-Consumer Reference Tenant)  
**GSTIN:** `07AAAAA0000A1Z5` | **State:** Delhi (DL)  
**Target Execution Environment:** Local Multi-Service Infrastructure (PostgreSQL 16, MinIO S3, Shopify Dev Store)  
**Status:** Certified Demonstration Baseline  
**Date:** September 2026  

---

## 1. Executive Summary & Purpose

The SANOCEA Reference Merchant (`ref_anchal_heritage`) is a persistent, deterministically resettable reference tenant built directly inside the production codebase. It allows engineering, operations, and prospective enterprise clients to inspect and verify the real autonomous ERP capabilities of SANOCEA without mock business logic or fabricated success states.

To preserve absolute technical integrity and adhere to the **Zero-Invention Principle**, this document serves as the authoritative, honest declaration of system capability across three non-negotiable tiers:
1. **TIER 1: CERTIFIED (Production-Safe)** — Exercised on real infrastructure, passing all deterministic validation suites, verified against live Shopify Admin GraphQL APIs, and backed by PostgreSQL append-only triggers.
2. **TIER 2: SIMULATED (Synthetic / In-Memory Harnesses)** — Validated against contract schemas using local connector simulators (e.g., synthetic Amazon/Flipkart/Meesho connectors and mock 3PL logistics carriers).
3. **TIER 3: UNAVAILABLE / ROADMAP** — Features not implemented, uncertified, or explicitly excluded from the ERP core. Sales demonstrations must never claim these are operational today.

---

## 2. Three-Tier Capability Matrix

| System Domain | Specific Capability | Status | Evidence / Verification Target | Architectural Boundary & Disclosure |
| :--- | :--- | :--- | :--- | :--- |
| **Catalog & Ingestion** | Messy File Ingestion (XLSX, CSV, PDF) | **CERTIFIED** | `scripts/run_reference_merchant_certification.py` (Checkpoints 2-4) | Real openpyxl, csv.excel, PyMuPDF engine. Handles merged cells, messy delimiters, and multi-page tables. |
| **Catalog & Ingestion** | Corrupt Ballast Quarantine | **CERTIFIED** | `packages/product_onboarding/ingestion.py` | Quarantines binary trash and OS artifacts (`.DS_Store`, `.bin`). Generates audit records. |
| **Catalog & Ingestion** | Honest Formula Provenance | **CERTIFIED** | Checkpoint 3; `packages/product_onboarding/provenance.py` | Preserves formula string (`=130*1.20`) and cached value separately. Never guesses missing calculations. |
| **Catalog & Ingestion** | Multi-Product PDF Specification Parsing | **CERTIFIED** | Checkpoint 4; PyMuPDF integration | Extracts discrete products across PDF pages with precise page and bounding locators. |
| **Catalog & Ingestion** | Hidden Sheet & Metadata Quarantine | **CERTIFIED** | Checkpoint 3; `packages/product_onboarding/ingestion.py` | Isolates hidden sheets (`Internal_Costing`) into quarantined provenance chunks. |
| **Identity & Governance** | Cross-Source Conflict Detection | **CERTIFIED** | Checkpoint 5; `packages/product_onboarding/validation.py` | Identifies conflicting commercial facts across feeds (e.g., price ₹156 vs ₹168). |
| **Identity & Governance** | Fail-Closed Publication Gate | **CERTIFIED** | Checkpoint 5; `apply_publication_policy` | Blocks unapproved, draft, or conflicting entities from publication (`EXCEPTION`). |
| **Identity & Governance** | Audited Human Disambiguation & Approval | **CERTIFIED** | Checkpoint 6; `Approval` model | Resolves conflicts with explicit actor identity (`operator_prospect_demo`). |
| **Sales Channels** | Live Shopify Multi-Variant Publication | **CERTIFIED** | Checkpoint 7; Live Dev Store (`gid://shopify/Product/...`) | Live GraphQL Admin API mutation (`2026-07`). Creates active products and variant matrices. |
| **Sales Channels** | Live Shopify External Read-Back Verification | **CERTIFIED** | Checkpoint 8; Shopify Admin GraphQL query | Independent read-back verifies titles, handles, and SKU options match canonical truth. |
| **Sales Channels** | Marketplace Connectors (Amazon, Flipkart, Meesho) | **SIMULATED** | `tests/unit/test_flipkart_connector.py`, `test_amazon_connector.py` | Simulated connectors adhering to `MarketplaceConnector` contracts; no live seller tokens attached. |
| **Inventory Management** | Multi-Location Inventory Allocation | **CERTIFIED** | Checkpoint 9; `rank_candidate_locations` | Multi-node allocation across priority warehouses (`loc_delhi_hub`, `loc_mumbai_hub`). |
| **Inventory Management** | DB-Atomic Reservation & Idempotency | **CERTIFIED** | Checkpoint 9; `store.reserve_inventory_atomic` | PostgreSQL atomic reservation prevents overselling; duplicate calls return `already_done=True`. |
| **Fulfillment & Logistics** | Order Fulfillment Monitoring | **CERTIFIED** | Checkpoint 10; `monitor_fulfilment` | Moves inventory from reserved to consumed upon merchant dispatch signal. |
| **Fulfillment & Logistics** | 3PL Carrier Integration (Shiprocket / Bluedart) | **SIMULATED** | `packages/post_order/operations.py` (simulated logistics commands) | Simulates carrier status transitions (`pickup_requested`, `in_transit`, `delivered`). |
| **Post-Order Operations** | Return Inspection & Inventory Restocking | **CERTIFIED** | Checkpoint 10; `progress_return` | Restocks physically consumed inventory upon `inspection_passed` only. |
| **Post-Order Operations** | Policy-Gated Financial Refund Limits | **CERTIFIED** | Checkpoint 10; `_refund_decision` | Auto-permits under-threshold refunds (₹168); gates above-threshold refunds (₹840) to human approval. |
| **Audit & Compliance** | Append-Only Tamper-Proof Audit Ledger | **CERTIFIED** | Checkpoint 11; `audit_events` table | Enforced by PostgreSQL trigger `prevent_audit_update_delete()`. Mutation raises SQL exception. |
| **Audit & Compliance** | Strict Tenant Isolation | **CERTIFIED** | Checkpoint 1; `packages/domain_contract/postgres_store.py` | Every SQL query and S3 key is scoped by `merchant_id`. Cross-tenant queries return empty sets. |
| **Security & Cryptography** | Tenant Credential Encryption | **CERTIFIED** | Checkpoint 1; `CredentialProvider` | AES-256-GCM authenticated envelope encryption with zero plain-text storage of API keys. |
| **UI & Experience** | Web / React Operator Dashboard | **UNAVAILABLE** | None (CLI and REST/GraphQL API only) | Roadmap. Operator interactions are driven via authenticated REST APIs (`apps/api`). |
| **Marketing & Copywriting** | Autonomous Generative AI Product Descriptions | **UNAVAILABLE** | Explicitly excluded | Anti-hallucination boundary. SANOCEA does not invent copy, SEO fluff, or unverified claims. |
| **Customer Support** | WhatsApp Conversational AI Agent | **UNAVAILABLE** | Out of Scope | SANOCEA core focuses on physical and commercial truth, not conversational front-ends. |
| **Pricing & Revenue** | Algorithmic Multi-Channel Dynamic Price Wars | **UNAVAILABLE** | Out of Scope | Pricing decisions require authoritative merchant policy or explicit human approval. |

---

## 3. Invariant Commitments for Live Demonstrations

When presenting SANOCEA to prospective merchants, partners, or technical evaluators, the following invariants are strictly guaranteed by the software:

1. **Zero Silent Commercial Inventions:**
   If a supplier spreadsheet leaves an HSN code, barcode, or package dimension blank, SANOCEA will never prompt an LLM to "hallucinate" a plausible number. It flags the attribute as `UNRESOLVED` and halts publication.
2. **Deterministic Precedence over Probabilistic Guessing:**
   Probabilistic models (such as Docling or OCR) may propose candidates, but only authoritative merchant-scoped deterministic rules or explicit human signatures can confirm product identity.
3. **Fail-Closed Gatekeeper:**
   A product draft with conflicting prices, unverified variants, or missing mandatory channel attributes cannot be published. The system returns an `EXCEPTION` and logs an audit trail.
4. **Physical Inventory Accounting:**
   An item is reserved upon order confirmation and consumed upon dispatch. It can only be restocked if it was physically consumed and passes return inspection.
5. **Database-Enforced Audit Immutability:**
   Audit logs are not merely write-only in application code; they are protected by a PostgreSQL `BEFORE UPDATE OR DELETE` trigger that halts any administrative or operational attempt to alter history.
