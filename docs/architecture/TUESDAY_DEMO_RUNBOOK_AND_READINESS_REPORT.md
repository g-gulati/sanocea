# Tuesday Demo Runbook & Readiness Report: The Premium Basket

**Target Date:** Tuesday Presentation  
**Target Merchant:** The Premium Basket (Gourmet Dry Fruits, Nuts, Dates & Confectionery)  
**Integration Target:** Dedicated Safe Sandbox Store (`sanocea-commerce-os-dev.myshopify.com`, Storefront Password: `sanocea`)  
**Primary Merchant Interface:** WhatsApp (Self-Contained Executive Operating Loop)  
**Internal Operations & Audit:** Sanocea Command Center (`http://127.0.0.1:8080`)  

---

## 1. Executive Summary & Safety Policy

This runbook defines the complete presentation sequence, operational guarantees, and architectural hardening verified for Tuesday's executive demonstration to The Premium Basket.

### Strict Zero-Leak Safety Boundary
* **No Access to Merchant Systems:** Sanocea does **NOT** access, connect to, or require credentials for The Premium Basket's live Shopify store, inventory, order, or customer records.
* **Representative Sandbox:** All demonstration scenarios operate against our dedicated, private Shopify development store (`sanocea-commerce-os-dev.myshopify.com`).
* **Clear Labeling:** All sandbox products are explicitly prefixed with `[DEMO-SANDBOX]` and published to the live Online Store sales channel for real-time storefront verification.

---

## 2. Live vs. Simulated Verification Matrix

| Capability | Real (Live) | Simulated | Verification Details |
| :--- | :---: | :---: | :--- |
| **Shopify Admin API Integration** | **YES** | — | Real GraphQL API (`2026-07`) using client-credentials grant via `ShopifyAccessTokenManager`. |
| **Catalog & Multi-Location Inventory Ingress** | **YES** | — | Imports products, variants, SKUs, locations, and inventory levels directly from Shopify GraphQL. |
| **Catalog Anomaly Detection** | **YES** | — | Detects blank SKUs (TPB-027), duplicate SKUs (TPB-028), unit pricing inversions (TPB-016), compare-at anomalies (TPB-018), low stock, and quarantine holds. |
| **Live Store Mutation (Price Correction)** | **YES** | — | Synchronously mutates variant price and compare-at price in Shopify via `productVariantsBulkUpdate`. |
| **WhatsApp Notification & Approval Ingress** | **YES** | — | Real WhatsApp messaging via WAHA (NOWEB) session `default` (`919988940640@c.us`) delivering notifications and receiving replies. |
| **Location-Scoped ATS & Atomic Reservation** | **YES** | — | Atomic reservation across locations via Postgres `SELECT ... FOR UPDATE` ensuring quarantined stock is never reserved. |
| **Operational vs. Financial Status Separation** | **YES** | — | Orders track operational delivery (`DELIVERED`) independently from financial settlement (`UNRECONCILED`). |
| **Webhook Deduplication & Out-of-Order Protection** | **YES** | — | HMAC-SHA256 verification, `X-Shopify-Webhook-Id` idempotency, and timestamp monotonicity guard. |
| **Bank Settlement Feed** | — | **SIMULATED** | Payout settlement event is simulated from synthetic bank clearing batch. |
| **Order Placement** | — | **HYBRID** | Real Shopify order payloads ingested via webhook/API; live checkout requires manual entry. |

---

## 3. Representative Sandbox Catalog Baseline

The sandbox catalog mirrors the high-value gourmet product lines and operational exceptions identified during the public catalog audit:

1. **Blank SKU Finding (`TPB-027`):**
   * **Product:** `[DEMO-SANDBOX] Pure Roasted Makhana` (`gid://shopify/Product/9089093664847`)
   * **Variant:** Default Title (`gid://shopify/ProductVariant/46832696688879`), Selling Price: ₹299.00
   * **Defect:** SKU field is empty string (`""`). Breaks downstream WMS routing and marketplace cross-listing.

2. **Duplicate SKU Finding (`TPB-028`):**
   * **Product:** `[DEMO-SANDBOX] Goan Cashews W240 Grade` (`gid://shopify/Product/9089095434319`)
   * **Variants:** 250g Zip Pouch (₹499) vs. 250g Airtight Jar (₹549)
   * **Defect:** Both variants share the exact same SKU: `DEMO-PB-ND-CA-GOP-0250G`. Sanocea's hardened upsert savepoint prevents database collisions while flagging the duplicate.

3. **Inverted Unit Pricing & Compare-At Anomaly (`TPB-016` & `TPB-018`):**
   * **Product:** `[DEMO-SANDBOX] Smoky Hickory Barbecue Almonds & Cashew` (`gid://shopify/Product/9089094778959`)
   * **Variant 1:** 100g Pack of 1 — Price: ₹349.00, Compare-at: ₹499.00 (Unit Rate: ₹3.49/g)
   * **Variant 2:** 100g Pack of 2 — Price: ₹998.00, Compare-at: ₹499.00 (Unit Rate: ₹4.99/g)
   * **Defects:**
     * *Inversion:* 2-pack has a **43% higher** per-gram rate than buying two single packs.
     * *Legal Metrology Violation:* Selling price (₹998.00) exceeds compare-at MRP (₹499.00).

4. **Multi-Location ATS & Quarantined Inventory:**
   * **Product:** `[DEMO-SANDBOX] Stuffed Dates Gift Box - 12 Medjool Dates` (`gid://shopify/Product/9089095041103`)
   * **Location 1 (Shop Location):** 45 total units in Shopify. In Sanocea: 40 sellable, 5 in quarantine (`ats` = 40).
   * **Location 2 (Custom Location):** 8 units in Shopify. In Sanocea: 8 sellable (`ats` = 8, triggers low-stock risk against safety threshold of 10).

---

## 4. Tuesday Presentation Script & Step-by-Step Runbook

### Scene 1: The Executive Morning Briefing (WhatsApp)
* **Action:** Trigger the daily morning briefing.
* **Demonstration:** Show WhatsApp on phone or projector.
* **Message Received:**
  ```text
  📊 Sanocea Daily Operational Briefing - Premium Basket

  Catalog & Store Health:
  • Products Active: 4
  • Locations Monitored: 2

  Inventory & ATS Status:
  • Total Stock Lines: 7
  • Low Stock Risk: 1 SKU(s) below safety threshold (10 units)
  • Quarantined Stock: 5 unit(s) across 1 SKU(s) held for QA

  Orders & Settlement:
  • Total Orders: 5
  • Fulfillment: 3 Delivered
  • Financial Status: 2 Unreconciled / Pending Bank Settlement

  Action Required (1 pending decision):
  • APP-PB-PRICE-01: Price Change - Correct inverted unit pricing & compare-at anomaly...

  Reply APPROVE <ref> to execute, or DETAILS <ref> for full impact analysis.
  ```
* **Talking Point:** *"The owner does not need to log into multiple dashboards every morning. Sanocea condenses multi-location ATS, damaged/quarantined stock, unreconciled orders, and critical catalog exceptions directly into WhatsApp."*

---

### Scene 2: Interactive Exception Management (WhatsApp)
* **Action:** Merchant replies `DETAILS APP-PB-PRICE-01`.
* **System Response:** Sanocea sends instant technical & commercial breakdown without modifying the pending status:
  ```text
  📋 Decision Breakdown: APP-PB-PRICE-01
  • Action: Price Change
  • Summary: Correct inverted unit pricing & compare-at anomaly on Smoky Hickory BBQ Almonds (Pack of 2)
  • Recommended: Reduce selling price to ₹629.00 with compare-at MRP ₹998.00
  • Likely Impact: +18% projected conversion lift; restores 10% volume discount vs pack-of-1; complies with MRP regulation
  • SKU: DEMO-PB-BBQ-100G-2P
  • Price Adjustment: ₹998.00 -> ₹629.00

  To execute: Reply APPROVE APP-PB-PRICE-01
  To decline: Reply REJECT APP-PB-PRICE-01
  To postpone: Reply LATER APP-PB-PRICE-01
  ```
* **Action (Optional Snooze):** Merchant replies `LATER APP-PB-PRICE-01`. Sanocea confirms snooze, keeping the approval safely in the queue.
* **Talking Point:** *"Decisions are never black-box. The merchant can review the exact financial and legal impact before deciding, right inside WhatsApp."*

---

### Scene 3: One-Tap Approval & Live Execution
* **Action:** Merchant replies `APPROVE APP-PB-PRICE-01`.
* **System Execution:**
  1. `DemoApprovalNotificationService` validates sender identity and authorization.
  2. Resolves approval through `ApprovalService.resolve(decision="approved")`.
  3. Dispatches mutation to `ShopifyLiveConnector.update_variant_price()`.
  4. Real Shopify Admin GraphQL mutation executes: updates variant `46832702455887` price to ₹629.00 and compare-at to ₹998.00.
  5. Records immutable audit event in PostgreSQL ledger.
  6. Sends immediate WhatsApp confirmation:
     ```text
     ✅ Approved APP-PB-PRICE-01 (Price Change)

     Action executed successfully. The store and inventory have been updated and logged in the immutable audit ledger.
     ```
* **Verification:**
  * Open `sanocea-commerce-os-dev.myshopify.com/products/demo-sandbox-smoky-hickory-barbecue-almonds-cashew` (password: `sanocea`).
  * Verify **Pack of 2** is now displayed at **₹629.00** with strikethrough MRP **₹998.00**!
* **Talking Point:** *"Approval doesn't just create a ticket—it executes safely and instantly on Shopify, with zero manual data entry and a 100% auditable record."*

---

### Scene 4: Inventory Quarantine & ATS Integrity
* **Demonstration:**
  * Inspect `[DEMO-SANDBOX] Stuffed Dates Gift Box` in Sanocea:
    * Total Shopify quantity = 45 units.
    * Sanocea sellable = 40 units; quarantined (damaged packaging hold) = 5 units.
    * Real Available-to-Sell (ATS) = 40 units.
  * Place a test order for 42 units.
  * **Result:** Order is flagged for shortage; Sanocea refuses to allocate the 5 quarantined units, preventing shipping damaged goods to a customer.
* **Talking Point:** *"Shopify only tracks raw numbers. Sanocea adds location-aware Available-to-Sell (ATS) and QA quarantine gates so defective packaging is never accidentally promised to buyers."*

---

### Scene 5: Delivery vs. Financial Reconciliation Separation
* **Demonstration:**
  * Open an imported order (e.g. Order `#1005`).
  * Show that when fulfillment is marked `DELIVERED`, the order's financial reconciliation status remains `UNRECONCILED`.
  * Ingest the simulated bank settlement clearing event.
  * Status transitions to `SETTLED` with exact bank batch reference.
* **Talking Point:** *"A delivered order is not money in the bank. Sanocea keeps operational status strictly separate from financial settlement, so accounting never books revenue that payment gateways haven't settled."*

---

### Scene 6: Webhook Fault Tolerance (Retries & Out-of-Order)
* **Demonstration:**
  * Ingest a webhook with duplicate `X-Shopify-Webhook-Id`.
  * Verify response: `idempotent_replay: true` with zero duplicate stock reservation.
  * Ingest a webhook with an older `updated_at` timestamp.
  * Verify response: `ignored: true` with audit event `out_of_order_event_ignored`.
* **Talking Point:** *"Shopify webhooks can retry up to 8 times or arrive out of sequence during network congestion. Sanocea's idempotency engine guarantees zero double-deductions."*

---

## 5. One-Click Demo Reset Runbook

To reset the sandbox store and Sanocea state back to the pre-demo baseline before the presentation, execute the reset script:

```powershell
# Reset Shopify live sandbox variant back to anomalous state
$env:PYTHONPATH = "D:\Autonomous E-Commerce ERP"
$env:SANOCEA_PG_DSN = "postgresql://sanocea:sanocea@127.0.0.1:55199/sanocea_phase05"
$env:SANOCEA_CRED_MASTER_KEY_CURRENT = "v1"
$env:SANOCEA_CRED_MASTER_KEY_V1 = "KioqKioqKioqKioqKioqKioqKioqKioqKioqKioqKio="

& "C:\Python313\python.exe" -c "
from sanocea.packages.domain_contract.postgres_store import PostgresStore
from sanocea.packages.domain_contract.credentials import build_production_credential_provider
from sanocea.packages.runtime.service_graph import build_service_graph

store = PostgresStore('$env:SANOCEA_PG_DSN', credential_provider=build_production_credential_provider('$env:SANOCEA_PG_DSN'))
graph = build_service_graph(store)
connector = graph.storefronts.resolve('prospect_premium_basket')

# Reset BBQ Pack of 2 to anomalous price
connector.update_variant_price(
    'prospect_premium_basket',
    variant_gid='gid://shopify/ProductVariant/46832702455887',
    product_gid='gid://shopify/Product/9089094778959',
    price=998.00,
    compare_at_price=499.00,
)
print('Demo sandbox reset to baseline: Price=998.00, CompareAt=499.00')
"
```

---

## 6. Pre-Pilot Gap Analysis (Transition to Real Merchant)

Before onboarding The Premium Basket's live production store in Phase 2, the following technical gates must be crossed:

1. **Meta WhatsApp Cloud API Onboarding:**
   * *Current:* Self-hosted WAHA (NOWEB) container on dedicated demo number.
   * *Production:* Official Meta WhatsApp Business API via BSP (Gupshup / Interakt / Twilio) with permanent template registration for transactional alerts.

2. **ERP & WMS Sync Connectors:**
   * Real-time sync with warehouse management system (e.g. Unicommerce or Increff) for automated quarantine status and multi-depot stock sync.

3. **Multi-User RBAC & Staff Quorum:**
   * Configure approval authorization levels (e.g. price adjustments <₹500 require store manager; >₹500 require owner sign-off).
