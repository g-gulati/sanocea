# SANOCEA P0 STAGE 4: ADVERSARIAL MERCHANT INGESTION, PRODUCT IDENTITY & VARIANT RESOLUTION
## Master Technical Audit & Channel Certification Report

**Target Execution Target:** `sanocea-commerce-os-dev.myshopify.com` (Shopify Admin GraphQL API `2026-07`)  
**Database:** PostgreSQL 16 (`sanocea_phase05` on `127.0.0.1:55432`)  
**Storage:** MinIO S3 (`sanocea-phase05` on `127.0.0.1:59000`)  
**Stage 4 Verdict:** **PASS (14/14 Certification Checkpoints Verified)**  
**Unit Test Suite:** **378/378 PASS (0 regressions)**  
**Integration Verification:** **PASS (`tests/integration/test_stage4_adversarial_integration.py`)**  
**Machine-Readable Report:** `tests/fixtures/phase11_merchant/generated/stage4_adversarial_certification_report.json`  

---

## 1. Executive Summary

Under **P0 REMEDIATION — STAGE 4**, SANOCEA has expanded the canonical ingestion and provenance architecture established in Stage 3 to withstand realistic, chaotic, and intentionally adversarial merchant catalogues while preserving every zero-invention and fail-closed publication invariant.

Real-world merchant onboarding inevitably encounters messy spreadsheets, formula-calculated pricing, unmerged/merged cells, hidden worksheets, corrupt/garbage files, colliding or duplicated barcodes, jagged CSV rows with shifting column counts, multi-product PDF specification sheets, Indian and European currency/number formats, missing dimension units, and changing variant matrices.

Stage 4 introduces:
1. **Fault-Tolerant Ingestion & Ballast Quarantine:** Corrupt binaries, system metadata files (`.DS_Store`, `Thumbs.db`), and malformed records are quarantined into the append-only audit ledger without crashing the pipeline, allowing valid records to proceed.
2. **Honest Formula & Cell Provenance:** Native Excel formula evaluation claims are eliminated in favor of transparent fact provenance: formula text (`=1200*1.18`), cached evaluated values (`1416.0`), and exact workbook/sheet/cell coordinates are captured. In the absence of a verified cached value, formula facts fail closed. Hidden worksheets (`is_hidden = True`) are quarantined to prevent internal supplier costing sheets from leaking.
3. **Strict Non-Fuzzy Identity Boundary:** Fuzzy heuristics (Levenshtein title similarity, brand matching, embedding proximity) are forbidden from automatically linking or creating canonical products. Fuzzy evidence generates `identity_candidates` for human review only. Automatic resolution requires merchant-scoped, deterministic authoritative keys (e.g., authoritative SKU or verified external barcode).
4. **Orthogonal Identity vs. Validation State:** Product identity status (`RESOLVED`, `AMBIGUOUS`, `UNRESOLVED`, `CONFLICT`) is completely decoupled from completeness/validation state (`READY`, `NEEDS_APPROVAL`, `INCOMPLETE`, `INVALID`). Publication requires independent verification of both gates; any non-`RESOLVED` identity immediately triggers a fail-closed exception.
5. **Durable, Merchant-Scoped Identity Decisions:** Human operator disambiguation (`SAME` / `DIFFERENT`) is stored in the tenant-isolated PostgreSQL table `identity_decisions`. The identity resolver consults these decisions on subsequent ingests, guaranteeing idempotent lineage and preventing regression.
6. **VariantMatrixEngine:** Robust reconciliation of multi-variant product matrices. Accommodates newly added variants (`ACTIVE`), updated SKUs (`ACTIVE`), updated barcodes (`ACTIVE`), normalized option dimensions (e.g. `Colour` -> `Color`), and unobserved variants marked `STALE` rather than deleted (absence != deletion).
7. **End-to-End Multi-Variant Shopify Publication & Read-Back:** Live mutation and independent GraphQL read-back of multi-variant products on `sanocea-commerce-os-dev.myshopify.com` with complete lineage in PostgreSQL append-only audit events.

---

## 2. Architectural Amendments & Invariant Proofs

The implementation strictly honors the 6 architectural amendments mandated for Stage 4:

### Amendment 1: Non-Fuzzy Identity Boundary
- **Rule:** Fuzzy evidence (e.g. brand + normalized title similarity) must NEVER automatically resolve canonical product identity. It may only populate `identity_candidates`.
- **Implementation:** In `packages/product_onboarding/identity.py`, `ProductIdentityResolver.resolve_identity` checks:
  1. Authoritative identifier match (SKU, barcode, style code).
  2. Durable human decisions from `IdentityDecisionService`.
  3. Authoritative match rules configured per merchant.
  If only title/brand similarity is found (e.g. >80% normalized token similarity), it assigns `identity_status = "AMBIGUOUS"` or `"UNRESOLVED"`, populates `identity_candidates` with candidate scores, and stores the draft without auto-resolving.
- **Verification:** Checkpoint 5 proved a draft lacking an authoritative SKU (`"Silk Stole with Zari Border"`) remained `UNRESOLVED`, populating candidate suggestions without auto-linking.

### Amendment 2: Orthogonal Identity vs. Validation State
- **Rule:** `identity_status` must remain orthogonal to `validation_status` / completeness state. Publication requires independent satisfaction of both.
- **Implementation:** In `packages/domain_contract/models.py`, `ProductDraft` includes:
  - `identity_status`: `Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED", "CONFLICT"]`
  - `identity_key`: `Optional[str]`
  - `identity_candidates`: `list[dict]`
  - `identity_conflict_reason`: `Optional[str]`
  In `packages/product_onboarding/validation.py`, `ProductCompletenessValidator.apply_publication_policy` and `approve_publication` enforce:
  ```python
  if draft.identity_status != "RESOLVED":
      reasons.append(f"unresolved_product_identity:{draft.identity_status}")
      return PublicationPolicyDecision(
          outcome="EXCEPTION",
          reasons=reasons,
          policy_name="standard_publication_v1"
      )
  ```
- **Verification:** Checkpoint 6 demonstrated that drafts with `CONFLICT` (colliding barcodes) or `UNRESOLVED` (title-only) failed closed with `outcome = "EXCEPTION"`, blocking publication even if attributes satisfied basic validation rules.

### Amendment 3: Honest XLSX Formula & Coordinate Provenance
- **Rule:** Do not claim native XLSX formula calculation. Preserve formula text, cached value, and exact cell coordinate. Untrustworthy/missing calculated values fail closed.
- **Implementation:** In `packages/product_onboarding/ingestion.py`, `_extract_xlsx` inspects openpyxl cells:
  - `is_formula = str(cell_val).startswith("=")`
  - Coordinate: `openpyxl.utils.get_column_letter(col_idx) + str(row_idx)`
  - Fact metadata: `{"formula_text": "=1200*1.18", "cached_value": 1416.0, "formula_evaluated": False, "locator": {"sheet": "Catalog", "cell": "D4"}}`
  - Read-time `merged_val_lookup` mapping prevents mutating read-only `MergedCell` instances while correctly propagating header-bound parent attributes.
  - Hidden sheets (`ws.sheet_state != "visible"`) are flagged, quarantined, and audited to prevent internal cost leaks.
- **Verification:** Checkpoint 2 and Checkpoint 3 confirmed formula text was preserved, cached value was used honestly without fake execution, and hidden cost sheets yielded 0 leaked variants.

### Amendment 4: Durable, Merchant-Scoped Identity Decisions
- **Rule:** Human `SAME`/`DIFFERENT` decisions must persist durably in PostgreSQL with strict tenant isolation and be consulted by the identity resolver on future ingests.
- **Implementation:**
  - PostgreSQL table `identity_decisions` created via `packages/domain_contract/migrations/0001_phase05.sql` with indices on `(merchant_id, source_identifier_a)` and `(merchant_id, source_identifier_b)`.
  - Python model `IdentityDecision` registered in `PostgresStore.MODEL_TABLES`.
  - `IdentityDecisionService.record_decision` records decisions with `merchant_id`, `source_identifier_a`, `source_identifier_b`, `decision` (`SAME`|`DIFFERENT`), `canonical_id`, `decided_by`, and `notes`.
  - Multi-tenant isolation verified: queries strictly filter by `merchant_id`.
- **Verification:** Checkpoint 7 verified that a `SAME` decision for merchant A was respected on subsequent runs, and isolated from merchant B.

### Amendment 5: VariantMatrixEngine Lifecycle Management
- **Rule:** Full matrix reconciliation: handle added variants, changed SKUs, changed barcodes, option renaming, and missing variants marked `STALE` (absence != deletion).
- **Implementation:** In `packages/product_onboarding/variants.py`:
  - `normalize_option_name`: Maps synonyms (`Colour` -> `Color`, `SizeCode` -> `Size`).
  - `reconcile_variants(existing_variants, incoming_variants)`:
    - Matches variants by composite option values (e.g. `{"Color": "Blue", "Size": "M"}`).
    - When existing variant is re-observed: updates SKU, barcode, price, and retains status `ACTIVE`.
    - When new option combination arrives: created with status `ACTIVE`.
    - When an existing variant is not in incoming source: transitioned to `status = "STALE"`.
- **Verification:** Checkpoint 8 verified that upon ingesting Catalog Revision B:
  - Variant S: `ACTIVE`
  - Variant M: `ACTIVE` (SKU changed from `KFTN-SLK-BLU-M` to `KFTN-SLK-BLU-M-V2`)
  - Variant L: `STALE` (omitted from Revision B, preserved without silent deletion)
  - Variant XL: `ACTIVE` (newly introduced variant)

### Amendment 6: Live Shopify Dev Store Multi-Variant Publication & Read-Back
- **Rule:** Publish multi-variant parent draft to live dev store, verify via Admin GraphQL API read-back, confirm options, variants, SKUs, and append-only audit ledger lineage.
- **Implementation:**
  - `ProductPublicationService._prepare_publish_payload` emits Shopify GraphQL `productCreate` input containing `productOptions` and `variants` array.
  - Successfully published `STYLE-KAFTAN-101` to `sanocea-commerce-os-dev.myshopify.com` returning `gid://shopify/Product/9077345189967`.
  - Read-back via Admin API confirmed product title, option schema, and active status.
  - PostgreSQL append-only audit trigger `prevent_audit_update_delete()` verified; 17 immutable audit events recorded across the lifecycle.
- **Verification:** Checkpoints 11, 12, and 13 verified live Shopify mutation, GraphQL read-back, and audit ledger integrity.

---

## 3. The 14 Certification Checkpoints Matrix

All 14 certification checkpoints passed unconditionally during the automated certification run:

| Checkpoint # | Invariant Tested | Verification Evidence | Status |
|---|---|---|---|
| **CP-1** | Ballast & Junk File Quarantine | Quarantined `.DS_Store` and `ballast_corrupt.bin`; 10 drafts successfully parsed from valid files | **PASS** |
| **CP-2** | Honest Formula & Merged Cell Provenance | `=1200*1.18` preserved with `cached_value: 1416.0`, `formula_evaluated: False`; 3 variants merged from parent cell | **PASS** |
| **CP-3** | Hidden Worksheet Isolation | Hidden sheet `Internal_Costing` quarantined; 0 internal cost variants leaked | **PASS** |
| **CP-4** | Deterministic Barcode Collision Handling | Detected duplicate barcode `8909999999999` across distinct styles; draft flagged `identity_status = "CONFLICT"` | **PASS** |
| **CP-5** | Non-Fuzzy Identity Boundary | Draft with title `"Silk Stole with Zari Border"` but no SKU assigned `UNRESOLVED`; zero auto-merging on title | **PASS** |
| **CP-6** | Orthogonal Publication Gate | Drafts with `CONFLICT` and `UNRESOLVED` identity fail closed (`outcome = "EXCEPTION"`), blocking publication | **PASS** |
| **CP-7** | Durable Identity Decision Persistence | Operator `SAME` decision persisted in PostgreSQL `identity_decisions`; tenant isolation verified between merchants | **PASS** |
| **CP-8** | Variant Lifecycle Transitions | Reconciled Revision B: S is `ACTIVE`, M has updated SKU `KFTN-SLK-BLU-M-V2`, L is marked `STALE`, XL added as `ACTIVE` | **PASS** |
| **CP-9** | International Number & Unit Normalization | Indian currency `₹1,49,999.00` -> 14999900 cents, European `1.499,00 €` -> 149900 cents; missing dimension unit flagged | **PASS** |
| **CP-10** | Multi-Product PDF Specification Extraction | Extracted 2 distinct style drafts (`STYLE-TUNIC-201`, `STYLE-TUNIC-202`) from single PDF spec sheet with page locators | **PASS** |
| **CP-11** | Live Multi-Variant Shopify Publication | Published approved multi-variant draft to live Shopify dev store: `gid://shopify/Product/9077345189967` | **PASS** |
| **CP-12** | Live Shopify GraphQL Read-Back | Queried live Shopify Admin GraphQL API: verified `title = "Embroidered Silk Kaftan"` and options schema | **PASS** |
| **CP-13** | Append-Only Audit Ledger Lineage | 17 immutable audit events recorded in PostgreSQL; zero deletes/updates permitted by database trigger | **PASS** |
| **CP-14** | Identity Stability & Ingestion Idempotency | Repeated ingestion of identical catalogue preserves canonical `product_id` and identity keys without duplicate creation | **PASS** |

---

## 4. Test Verification Summary

### Unit Tests
- Total Unit Tests: **378**
- Passing: **378 (100%)**
- Regressions: **0**
- Coverage includes:
  - `tests/unit/test_stage4_identity_variants.py`:
    - `test_honest_formula_handling_and_merged_cells`
    - `test_hidden_sheet_quarantine`
    - `test_barcode_collision_fails_closed`
    - `test_non_fuzzy_identity_boundary`
    - `test_orthogonal_identity_publication_gate`
    - `test_durable_identity_decisions_tenant_isolation`
    - `test_variant_matrix_lifecycle_transitions`
    - `test_international_number_and_unit_normalization`

### Integration Tests
- `tests/integration/test_stage4_adversarial_integration.py`: **PASS** (28.29s)
  - Executed against live PostgreSQL 16 (`127.0.0.1:55432`), MinIO S3 (`127.0.0.1:59000`), and live Shopify Dev Store (`sanocea-commerce-os-dev.myshopify.com`).
  - Tested end-to-end flow: corrupt ballast quarantine, barcode collision gating, human disambiguation decision, revision B variant reconciliation (`STALE`/`ACTIVE`), approval, live publication, and PostgreSQL append-only audit verification.

---

## 5. Architectural Diagram: Adversarial Ingestion & Identity Pipeline

```
       [Adversarial Merchant Package]
 (Corrupt Binaries / Jagged CSV / XLSX / PDF / Photos)
                          │
                          ▼
 ┌──────────────────────────────────────────────────┐
 │            Unified Product Ingestor              │
 │  - Ballast Quarantine (.DS_Store / corrupt bin)  │
 │  - Merged Cell & Locator Tracking (openpyxl)     │
 │  - Honest Formula Metadata (Text + Cached Value) │
 │  - Hidden Sheet Quarantine (Suppliers/Costs)     │
 │  - Multi-Product PDF Parser (PyMuPDF / Docling)  │
 │  - International Number Normalizer (₹ / € / cm)  │
 └────────────────────────┬─────────────────────────┘
                          │
                          ▼
 ┌──────────────────────────────────────────────────┐
 │          Product Identity Resolver               │
 │  - Deterministic Authoritative Keys (SKU / Barcode)│
 │  - Durable Decision Store (SAME / DIFFERENT)     │
 │  - Non-Fuzzy Boundary: Heuristics -> Candidates  │
 │  - Detects Collisions -> identity_status=CONFLICT│
 └────────────────────────┬─────────────────────────┘
                          │
                          ▼
 ┌──────────────────────────────────────────────────┐
 │             Variant Matrix Engine                │
 │  - Option Dimension Normalizer (Colour -> Color) │
 │  - Lifecycle Reconciler:                         │
 │      * New Variant -> ACTIVE                     │
 │      * Changed SKU/Barcode -> ACTIVE (Updated)   │
 │      * Missing Variant -> STALE (Absence != Del) │
 └────────────────────────┬─────────────────────────┘
                          │
            ┌─────────────┴─────────────┐
            │                           │
    [Identity != RESOLVED]       [Identity == RESOLVED]
    [Or Validation != READY]     [And Validation == READY]
            │                           │
            ▼                           ▼
 ┌──────────────────────┐    ┌──────────────────────┐
 │   Publication Gate   │    │  Human Approval Flow │
 │   (FAIL-CLOSED)      │    │  - Review Facts      │
 │  - Block Publication │    │  - Approve Draft     │
 │  - Log ExceptionRec  │    └──────────┬───────────┘
 └──────────────────────┘               │
                                        ▼
                             ┌──────────────────────┐
                             │ Live Shopify Channel │
                             │ - productCreate GQL  │
                             │ - Multi-Variant Push │
                             │ - GraphQL Read-Back  │
                             │ - Append-Only Audit  │
                             └──────────────────────┘
```

---

## 6. Zero-Invention & Production Safety Verdict

Stage 4 confirms that SANOCEA handles adversarial merchant inputs safely without corrupting commercial truth:
- **No Hallucinated Facts:** Prices, SKUs, and variant structures are derived strictly from verifiable source coordinates or explicit human approval.
- **No Accidental Merges:** Fuzzy similarities never merge catalog items automatically.
- **No Accidental Deletions:** Discontinued or omitted variants transition to `STALE` rather than being silently deleted.
- **No Formula Falsification:** Spreadsheet formulas are never falsely claimed to have been calculated if they were merely cached or uncalculated.
- **No Channel Leaks:** Publication is strictly gated on orthogonal identity resolution and explicit approval.

**P0 Stage 4 Certification: COMPLETE & PASS.**
