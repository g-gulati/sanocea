# Phase 4 - Inventory Planning, Procurement & Supplier Operations

Status: `LOCAL/HARNESS VALIDATED`

## Scope

Closes the loop: sales -> inventory consumption -> demand -> replenishment -> supplier -> purchase
order -> inbound -> goods receipt -> inventory reconciliation.

## Reused infrastructure (per "inspect before implementing")

- `Decision` enum (`packages/policy_engine/engine.py`) reused directly for procurement authority
  outcomes (ALLOW/REQUIRE_APPROVAL/DENY) - no parallel decision type introduced.
- `GuardedConnector.execute_mutation` + `IdempotencyService.run_once` (DB-enforced, PRIMARY KEY
  (scope, key)) reused for PO submission idempotency - the same primitive proven in Phase 2.1
  (refund execution) and Phase 3 (nothing new needed).
- `ExceptionRecord`/`ExceptionService` reused for all procurement exceptions (free-form categories,
  no new "ProcurementException" model - mirrors Phase 3's finance exceptions).
- `Inventory` model extended (not duplicated) with `confirmed_inbound: int` - the existing
  on-hand/reserved/available fields from Phase 2 are unchanged.
- `ExternalIdMapping` is not reused for PO submission (a fresh external_ref is minted per PO by the
  connector itself, mirroring `ConnectorCommand`'s own idempotency-key pattern) but the Phase 3.1
  external-reference-resolution *pattern* directly informed the design discipline applied here.
- `DemandObservation` was deliberately NOT created - recent sales velocity is computed on demand from
  canonical `Order`/`OrderLine` data Sanocea already owns.
- `ProcurementPolicy` was deliberately NOT created as a persisted entity - like Phase 3's finance
  tolerances, it lives in `store.get_config(merchant_id)["procurement"]`.

## New canonical entities

`Supplier`, `SupplierSku` (covers "SupplierOffer" + availability + cost + MOQ + pack quantity + lead
time + preferred/alternate in one object), `ReplenishmentRecommendation`, `PurchaseOrder`,
`PurchaseOrderLine`, `SupplierAcknowledgement`, `InboundShipment`, `InboundShipmentLine`,
`GoodsReceipt`, `GoodsReceiptLine`.

## The confirmed-inbound-not-sellable invariant

`Inventory.confirmed_inbound` rises only via an *applied* `SupplierAcknowledgement`. It is used only in
`inventory_position()`'s planning-oriented `inventory_position` figure
(`on_hand - reserved + confirmed_inbound`) - never in `available_to_sell`. The ONLY code path that
converts confirmed inbound into sellable stock is `record_goods_receipt()`, and only for lines it can
confidently resolve to a known PO line; an unresolved/wrong-SKU/unexpected-item line never touches
inventory at all. See `cumulative_settlement_proof`-style live evidence in the workload report's
`inbound_invariant_proof` section.

## Bugs found and fixed during this phase's own validation

1. **`IdempotencyService.run_once` never released a reservation whose operation raised** - a genuine
   retry after a mid-mutation failure would poll forever for a result that would never arrive, then
   silently return `None` (or crash the caller). Fixed with `release_idempotency()` on both store
   backends, only releasing reservations that never completed.
2. **`PurchaseOrder`/`GoodsReceipt` upsert bug**: both are the first entities in this codebase with a
   genuine multi-step lifecycle that re-persists the SAME row many times while keeping a business key
   (`idempotency_key` / `external_receipt_ref`) set. The original `ON CONFLICT (business_key) DO
   NOTHING` upsert (correct for Phase 3's write-once entities) silently discarded every status update
   after the first insert. Fixed with an id-based primary upsert path plus a savepoint-guarded
   business-key safety net against genuinely duplicate creation. Mirrored in `Phase0Store`.
3. **Acknowledgement/shipment/receipt could be applied to a PO that never legitimately reached that
   state** (e.g. a still-`BLOCKED` draft) - added explicit PO-state guards to all three recording
   methods.
4. **Workload-script-level bugs** (not core logic): reusing one shared supplier across multiple
   adversarial fault scenarios let an early deliberate rejection correctly tank that supplier's
   `reliability_score` to 0.0, blocking every later scenario from reaching `SUBMITTED` (the reliability
   engine was behaving correctly; the test design was wrong). A scoped merchant-config mutation for one
   scenario leaked into every later scenario because it was never restored. Both fixed in the workload
   script.

## Tracked debt

See `tracked_debt` in the Phase 4 workload report (`scripts/run_phase4_procurement_workload.py`) for
the live, versioned list. Summary: no PDF/Docling/AI supplier ingestion path (no current requirement to
justify it - CSV/XLSX only, matching Phase 1's proven pattern); no OVER_CONFIRMED detection for
acknowledgements exceeding ordered quantity (mirrors Phase 3.1's OVER_SETTLED but not implemented here);
`InboundShipment`/`GoodsReceipt` line resolution uses direct SKU string matching rather than
`external_id_mappings` (PO submission and acknowledgement DO use real external-reference resolution);
the single ever-growing migration file debt from Phase 3 is unchanged and now larger.
