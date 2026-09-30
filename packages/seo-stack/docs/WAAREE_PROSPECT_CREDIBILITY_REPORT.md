# Waaree Energies — Prospect Credibility Report
**Prepared:** 2026-09-29 · **Scope:** Final pre-meeting audit of all claims made in the Waaree demo environment

---

> [!IMPORTANT]
> This report classifies every claim in the Waaree demo into three categories. Nothing is blurred between them. The goal: the demo survives a skeptical Waaree ecommerce/IT person asking "How do you know this, and can you actually execute it against our stack?"

---

## Three-Category Classification Framework

| Category | Label | Meaning |
|:---|:---|:---|
| **A** | `[O] Observed` | Independently verified on public pages: Wayback Machine, live DOM, structured data, PDPs, and verified support portal URLs. Can be demonstrated against actual Waaree URLs. |
| **B** | `SANOCEA Simulation` | Demonstrated in SANOCEA demo state store. The operating model, workflow, and approval flow are real. The state update happens in the demo. **Not proven against Waaree's production systems.** |
| **C** | `Requires Validation` | Requires Waaree API credentials, internal system access, or SOP documents. Clearly labelled in the demo UI. |

---

## A — Proven from Public Evidence (`[O] Observed`)

All 22 `[O]` findings are independently verifiable at the source URLs listed in `waareeData.js` under `sourceEvidence`. A skeptical prospect can open these URLs during the meeting.

| Ref | Category | Finding | Source |
|:---|:---|:---|:---|
| C1 | Catalogue | 12+ category card alt-text contradictions (595Wp DCR alt says "615Wp Non-DCR") | 8 category pages + matching PDPs (PAGE-VERIFIED, 2026-09-29) |
| C2 | Catalogue | Cell tech contradictions: Mono PERC vs TOPCon on same SKU | 4 PDPs (PAGE-VERIFIED) |
| C3 | Catalogue | Template spec default leaks: 144 cells `(12x6)` across 10W–500W | 5 PDPs (PAGE-VERIFIED) |
| C4 | Catalogue | Missing GTIN across all 25 sampled structured data entries | 25 PDPs (PAGE-VERIFIED) |
| C5 | Catalogue | Image file names encode incorrect wattage/specs | 10 PDPs (PAGE-VERIFIED) |
| C8 | Catalogue | Wattage mismatch between URL/H1 and product title | 8 PDPs (PAGE-VERIFIED) |
| C14 | Catalogue | 0/17 datasheet links functional (404 or relative paths) | 17 PDP link scans (PAGE-VERIFIED) |
| X1 | Datasheets | 9 PDPs link a generic 1-page commercial overview PDF instead of a technical datasheet | 9 PDPs (PAGE-VERIFIED) |
| X2 | Datasheets | 4 products link a different model's datasheet | 4 PDPs (PAGE-VERIFIED) |
| I1 | Inventory | JSON-LD hardcodes `InStock` on all 25/25 sampled pages regardless of true stock | 25 PDPs (PAGE-VERIFIED) |
| I3 | SLA | OOS products display "In 24 HOURS", "In 30 Days", "In 4-6 Week" dispatch promises | 6 PDPs (PAGE-VERIFIED) |
| I8 | Marketplace | 2 Waaree ASINs show "Currently unavailable" with no price or seller | Amazon ASINs (PAGE-VERIFIED) |
| P1 | Pricing | Two conflicting discount baselines rendered simultaneously; Was-price hidden by CSS | 15 PDPs (PAGE-VERIFIED) |
| P3 | Pricing | D2C priced above Amazon (+4.5%) while showing "Lowest Price" badge on 25/25 PDPs | 4 cross-channel comparisons (PAGE-VERIFIED) |
| P5 | Pricing | 540Wp DCR pack of 2: Amazon ₹9,099/unit vs D2C ₹15,199 (−40% unit dilution) | Cross-channel comparison (PAGE-VERIFIED) |
| P8 | Marketplace | MNP Global Enterprises listed on Waaree's own Radiance 3.2kW ASIN | Amazon ASIN B0H14Q722S (PAGE-VERIFIED) |
| R1 | Warranty | Strict 30-day defect discovery notice deadline (Clause 3.2) | Waaree Module Warranty PDF §3.2 (PAGE-VERIFIED) |
| R3 | Warranty | 9-item documentation prerequisite for warranty claims | Waaree Module Warranty PDF §3.1 (PAGE-VERIFIED) |
| R6 | Warranty | Conflicting warranty terms across channels (D2C 12/30yr · Flipkart 12/27yr · Amazon 15yr) | D2C, Flipkart, Amazon PDPs (PAGE-VERIFIED) |
| R7 | Complaints | 5 parallel complaint intake portals across 3 subdomains | 5 verified intake URLs (PAGE-VERIFIED) |
| R8 | Complaints | Helpdesk explicitly excludes L&T-SuFin & Moglix B2B orders | customerservice.waaree.online/ecom (PAGE-VERIFIED) |
| D1 | SLA | 4 conflicting dispatch promises on the same storefront (72h, 48h, 2-6 weeks, 24h) | shop.waaree.com PDP modal + /shipping-returns/ (PAGE-VERIFIED) |

**2 `[I]` Inferred findings** (strong operational inference, not directly evidenced):

| Ref | Finding | Inference Basis |
|:---|:---|:---|
| M1 | No single governed master data source | Inferred from C1–C14 alt-text and spec contradictions |
| M6 | Complaint systems keyed on disconnected identifiers from order systems | Inferred from customerservice.waaree.online input schema vs order data |

---

## B — Demonstrated in SANOCEA Simulation Sandbox

These actions are **accurately represented as simulations in the UI.** The operating model (Detect → Explain → Prepare → Approve → Execute → Audit) is demonstrated. State updates happen in SANOCEA's demo state store.

| Action | What the Demo Shows | What It Doesn't Claim |
|:---|:---|:---|
| `act-waa-01` Availability Feed Override | Operator approves; 3kW-HYB inventory status changes from OOS → OPTIMAL; ₹3.45L risk clears; WhatsApp confirmation appended; Immutable Audit #SAN-WAA-84021 written | Does **not** claim to have pushed OutOfStock to BigCommerce or Google Shopping feeds |
| `act-waa-02` Master Specification Lock | Operator approves; exception log shows RESOLVED; simulation state confirms attribute conflict cleared | Does **not** claim to have written corrected alt-text to BigCommerce catalog or Amazon SP-API |
| `act-waa-03` Price Parity Alignment | Operator approves; state shows parity enforced; WhatsApp syncs | Does **not** claim to have changed Amazon or D2C live prices |
| `act-waa-04` Complaint Unification | Operator approves; exception resolved; warranty standardization staged | Does **not** claim to have bridged L&T-SuFin POs into Waaree's live complaint portal |

**UI labelling in place:**
- All 4 action cards show: `🛡️ Demonstrated in SANOCEA Simulation Sandbox. Live production execution requires [specific credential/scope].`
- All 4 WhatsApp execution loop cards show an amber `SANOCEA SIMULATION SANDBOX` header with the same notice.
- Resolution receipts say: `IMMUTABLE AUDIT RECEIPT: SAN-WAA-84021` (not "cryptographic").
- Resolution text explicitly includes: "Simulated execution verified: … Live production rollout requires [BigCommerce API scopes / Amazon SP-API credentials]."

---

## C — Requires Waaree Validation / API Access

These 7 internal systems are clearly labelled in the demo UI as `Discovery / API Validation Required`:

| System | Purpose | What's Needed |
|:---|:---|:---|
| Unicommerce COM-OMS | Central order lifecycle | API version, webhook schema, serial number recording at dispatch |
| BigCommerce Storefront `s-unnwlv5df8` | D2C catalogue, pricing, feeds | V3 API read/write scopes for feed overrides |
| SAP S/4HANA (FI, CO, MM, SD) | Group ERP & Finance | Confirm whether product master data originates in SAP or BigCommerce |
| DMS (Dealer Management System) | Dealer orders & claims | Confirm scope overlap with e-commerce operations |
| Amazon SP-API & Flipkart Partner API | Live telemetry, Buy-Box, order routing | Official developer authorization for Waaree Energies Ltd |
| Customer Complaint Portals (5 URLs) | Ticket intake | MySQL/PHP export or REST webhook access |
| Settlement & Fee Reports | Finance reconciliation | Marketplace settlement CSVs, L&T-SuFin deduction schedules |

---

## Wording Corrections Applied

| Before | After | Location |
|:---|:---|:---|
| "cryptographic audit receipt" | "immutable audit receipt" | WaareeIntelligenceSection.jsx operating loop Step 06, WhatsAppView.jsx audit footer, DashboardView.jsx resolution receipt |
| "Approve Availability Feed Correction" | "Prepare & Approve Automation" | All 4 urgentActions buttons in waareeData.js |
| "CLOSED-LOOP AUTOMATION" (for Waaree) | "SANOCEA SIMULATION SANDBOX" | WhatsApp execution loop card header |
| "✓ EXECUTED" (for Waaree) | "✓ SIMULATION COMPLETE" | WhatsApp execution loop status pill |
| "Exception resolved" (step 5, Waaree) | "Immutable audit logged" | WhatsApp Waaree execution plan step 5 |
| `AUDIT #SAN-{id}-VERIFIED` | `IMMUTABLE AUDIT #{resolutionAuditId}` | DashboardView.jsx resolution receipt |

---

## Automation Coverage Matrix — Boundary Honesty

| Function | Monitor | Detect | Recommend | Execute | Human Approval | Integration Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---|
| Catalogue & Specs | ✓ | ✓ | ✓ | Conditional | ✓ | Ready (BigCommerce API needed for writes) |
| Pricing & Margins | ✓ | ✓ | ✓ | Conditional | ✓ | Ready (Amazon SP-API + BC needed for writes) |
| Inventory & Feeds | ✓ | ✓ | ✓ | Conditional | ✓ | Ready (BC V3 API + OMS webhook needed) |
| Order Operations | ✓ | ✓ | ✓ | Conditional | ✓ | Requires Unicommerce API discovery |
| Marketplace Operations | ✓ | ✓ | ✓ | Conditional | ✓ | Read-only deployed; SP-API needed |
| Complaints & SLA | ✓ | ✓ | ✓ | Conditional | ✓ | Ready (portal webhook needed for production) |
| Warranty Operations | ✓ | ✓ | ✓ | Conditional | ✓ | Ready (claim system API needed) |
| Returns & Breakage | ✓ | ✓ | ✓ | Conditional | ✓ | Discovery required |
| Settlement & Reconcile | ✓ | ✓ | ✓ | Conditional | ✓ | Requires settlement files & SAP access |
| Reporting & Intelligence | ✓ | ✓ | ✓ | ✓ | — (Autonomous) | **Active & Deployed** |

> [!NOTE]
> No arbitrary automation percentages are stated anywhere in the demo. All execution columns say "Conditional (Approved)" — never "Fully Automated" — except Reporting which is genuinely autonomous report generation.

---

## State Synchronization Verification

All 17 automated tests pass, including:

- `Waaree Energies — Dashboard approval of act-waa-01 synchronizes state and overrides availability feed` — verifies KPI decrement, inventory status, exception log, stream event, and WhatsApp chat in a single action.
- `Waaree Energies — Resetting state restores pristine initial state` — confirms no stale seeded data persists after reset.
- `Waaree Energies — WhatsApp command routing: Option 1 includes evidentiary tags` — confirms `*[O] Observed*` prefixes appear on pending decisions in WhatsApp.

---

## Defensibility Under Technical Questioning

| Skeptic Question | Answer |
|:---|:---|
| "How do you know the JSON-LD says InStock?" | Verifiable on shop.waaree.com right now: `view-source:` any product page, search for `"@type": "Offer"`, observe `"availability": "https://schema.org/InStock"` |
| "Can you prove the 40% dilution claim?" | 540Wp DCR D2C ₹15,199 (D2C PDP) vs Amazon pack of 2 ₹18,199 / 2 = ₹9,099.50/unit. Screenshot-verifiable. |
| "Can SANOCEA actually write to our BigCommerce?" | Not yet. We need the V3 API write scopes. The demo shows the operating model and what we'd push. |
| "Is that audit receipt cryptographically signed?" | No. It's an immutable timestamped record within SANOCEA's state. We call it an immutable audit receipt, not a cryptographic one. |
| "Will this replace our Unicommerce?" | No. SANOCEA integrates alongside Unicommerce — we monitor and act on the data; Unicommerce remains the order routing source of truth. |
| "What about SAP?" | Discovery item. We need to understand whether product master data flows through SAP or originates in BigCommerce. |

---

*Report generated from `/opt/sanocea/repo/website/src/whatsapp-demo/data/waareeData.js` and associated component files. All `[O]` findings sourced from `WAAREE_ECOMMERCE_DEEP_OPERATIONAL_AUDIT.md`.*
