# Phase 4.6 - Commerce Core Completion

Status: `LOCAL/HARNESS VALIDATED - CORE INTERNALLY COMPLETE`

## Scope

Removes the internal application/runtime blockers the Phase 4.5 report identified, so the Commerce
Operations core is internally complete and the remaining blockers to a first real merchant are
predominantly external live integrations/certification and deployment - not disconnected Sanocea
functionality.

## What was built

- **Catalogue/product operations (Journey A) wired end to end**: `ProductOnboardingWorkflow` rewritten
  to actually apply `ProductCompletenessValidator.apply_publication_policy()` (ALLOW/REQUIRE_APPROVAL/
  EXCEPTION) - closing a real gap where the old `approve_and_publish()` force-published every draft
  handed to it, never consulting policy at all. New safe entrypoints: `ingest_file`,
  `approve_product_facts`, `request_publication`, `approve_publication`, `reverify`. HTTP surface:
  `POST .../catalogue/ingest` (multipart file upload), `.../drafts`, `.../drafts/{id}/approve-facts`,
  `.../drafts/{id}/publish`, `.../drafts/{id}/publish/approve`, `.../publications`,
  `.../publications/{id}/reverify`.
- **Duplicate publication protection, DB-enforced**: `Publication.put()` now uses the same
  savepoint-guarded id-first-upsert pattern as `PurchaseOrder`/`GoodsReceipt`, backed by a new partial
  unique index `uq_publication_draft_channel` on `(merchant_id, product_draft_id, channel_id)` - a
  genuine concurrent race (not just a duplicate sequential request) can no longer mint two Publication
  rows for the same draft+channel. Combined with the pre-existing connector-mutation idempotency key
  (`publish:{draft_id}:{channel_id}`), a duplicate publish request can never create a duplicate external
  product/listing - proven live (two publish requests -> one external product, one Publication row).
- **Support wired as a real runtime path**: `SupportWorkflowService` now accepts an optional
  `post_order` service and dispatches `refund_request`/`return_request`/`cancellation_request` into the
  real, already-tested, policy-gated `evaluate_refund`/`evaluate_return`/`evaluate_cancellation` methods
  - never a support-only shortcut, never executing the mutation itself (support only ever *requests*;
  execution/approval flows through the same operator path a direct API call would use). New
  `workers/workflow/support_orchestrator.py::SupportOrchestrator` mirrors `OrderOrchestrator`'s role,
  invoked from inside `ChatwootConnector`'s own idempotency-guarded webhook handler - a duplicate
  Chatwoot delivery can never trigger a second classification/action. Shipment-status answers now read
  the real `Shipment` row (including NDR state), not just `Order.status`.
- **A real, previously-invisible bug fixed**: `SupportWorkflowService.handle_conversation`'s
  `APPROVAL-GATED` branch never actually existed - an approval-gated support request (refund/return/
  cancellation) silently produced no `Approval`, no `ExceptionRecord`, nothing visible to any operator
  query surface. Closed by dispatching into the real engines above (whose `evaluate_*` methods already
  create real, queryable `Approval` rows) instead of inventing a second approval mechanism.
- **Recovery runner, production-shaped**: `scripts/run_recovery_worker.py` - pure stdlib
  (argparse/logging/signal/time), `--once` (cron/timer) or loop mode (`--interval-seconds`,
  `--max-iterations`), SIGTERM/SIGINT graceful shutdown, structured logging, distinct exit codes.
  Locking via a new `PostgresStore.advisory_lock()` / `Phase0Store.advisory_lock()` context manager
  (`pg_try_advisory_lock`, non-blocking, session-scoped) so two overlapping invocations can never
  process the same work concurrently - proven against real Postgres with two separate connections.
  Example (not installed) systemd units under `infra/systemd/`.
- **Real Temporal decision (documented, not decorative)**: NO - not wired into any live path. See
  `TemporalRuntime`'s docstring and "Real Temporal decision" below.
- **Refund external-reference debt closed**: `SettlementEntry.provider_refund_reference` (mirrors
  `provider_order_reference`), resolved through `external_id_mappings` exactly like payment/cod entries
  since Phase 3.1. `PostOrderOperationsService.execute_refund` now registers the mapping
  (`_register_refund_reference`) the moment a real external refund reference is confirmed - the same
  moment `observe_payment` already does for orders. Tested: valid, unknown, corrupted, duplicate, and
  cross-merchant references (`tests/unit/test_phase46_refund_reference.py`,
  `tests/integration/test_phase46_refund_reference_real_infra.py`).
- **`packages/runtime/service_graph.py::build_service_graph()`**: the full connector/service/orchestrator
  graph factored out of `apps/api/app.py` so the recovery runner (and any future out-of-process
  consumer) builds an identical graph without duplicating the wiring.

## Bugs found and fixed while building this phase's own evidence

1. **`packages/runtime/commands.py::create_or_observe_shipment` had its return values swapped since
   Phase 4.5** (`shipment_ref, error = post_order.create_or_observe_shipment(...)`, when the real
   signature returns `(status_label, external_ref)`) - silently wrong because nothing had ever called
   this HTTP route until this phase's own integration workload exercised the shipment/tracking journey
   for the first time and hit a `KeyError` trying to use the status label `"created"` as a real shipment
   reference.
2. **`GET /merchants` was dead code returning `[]` unconditionally** - it called
   `store.list(Merchant, "system")`, but every real `Merchant` row's own `merchant_id` field equals its
   own `id` (never the literal string `"system"`), so this query could never match anything. No test
   exercised the route either. Fixed with a new, deliberate cross-tenant enumeration method,
   `list_all_merchants()` (both stores), and the route is now gated behind `require_service` since it
   returns real cross-tenant data once fixed.
3. **A genuine, reproducible Inventory race**: `ProcurementService._adjust_confirmed_inbound` /
   `_apply_goods_receipt_to_inventory` did read-if-exists-else-create-new + `store.put()`. Two
   concurrent first-time writes to the same `(merchant, sku, location)` Inventory row (e.g. two
   concurrent supplier acknowledgements for a SKU with no prior Inventory row) raced: at best a
   `UniqueViolation` crash (found via Phase 4.1's own `test_concurrent_acknowledgement_delivery_does_not_lose_updates`,
   which the Inventory crash had been silently masking the whole time it existed), at worst a silent
   lost update. Fixed with `PostgresStore.atomic_adjust_inventory()` - a single atomic
   `INSERT ... ON CONFLICT DO UPDATE` using nested `jsonb_set` to adjust `confirmed_inbound`/`quantity`/
   `available` together, no application-level lock needed - and a lock-guarded equivalent on
   `Phase0Store`. The pre-existing test itself also had a design bug (both concurrent threads used the
   identical `sequence=1`, which legitimately collides with the Phase 4.1 sequence-staleness guard) -
   rewritten to test the atomic store primitives directly, decoupled from that unrelated business rule.

## Real Temporal decision

**Not wired into any live path.** Every operational workflow Sanocea runs today is either a short
synchronous sequence completing within one HTTP request (order intake -> inventory reservation, refund/
return/cancellation evaluation) or an already-solved bounded-retry-with-terminal-escalation background
job (`workers/reconciliation_worker.py`) - neither needs a durable orchestration engine's timers/signals/
process-restart-survival. `TemporalRuntime`/`RealOrderWorkflow` (Phase 0) remain a validated CAPABILITY
PROOF - a real Temporal worker connecting to a real server and executing real activities/timers/signals/
retries - kept for the day a genuinely long-running, durable, multi-day workflow appears in Sanocea's
scope (e.g. a multi-week B2B procurement SLA with real wall-clock waits spanning process restarts). The
`/health` endpoint's optional Temporal check is documented as a connectivity probe only, never evidence
that Temporal is authoritative for any business state.

## Integrated zero-tolerance results (measured live, `scripts/run_phase46_integration_workload.py`)

All 13 Phase 4.5 conditions re-verified (not carried over as a stale claim) plus 7 new:

| Condition | Result |
|---|---|
| (13 Phase 4.5 conditions, unchanged) | all **PASS** |
| duplicate_catalogue_publication | **PASS** |
| invalid_unauthorized_catalogue_mutation | **PASS** |
| support_answer_contradicting_canonical_truth | **PASS** |
| support_performing_unauthorized_mutation | **PASS** |
| duplicate_support_event_causing_duplicate_business_action | **PASS** |
| refund_settlement_matched_using_fabricated_identity | **PASS** |
| recovery_runner_overlap_causing_duplicate_mutation | **PASS** |

## Tracked debt (explicitly deferred, not forgotten)

1. **Recovery runner not activated in this environment.** `scripts/run_recovery_worker.py` is real,
   tested, and portable; `infra/systemd/*.example` units are provided but not installed - per this
   phase's explicit "do not deploy it yet."
2. **Refund settlement has no cross-entry cumulative accounting.** Unlike orders (Phase 3.1's
   `reconcile_cumulative_settlement`), two different valid external references both resolving to the
   same refund are each reconciled independently, not summed into one cumulative verdict - a narrower
   residual gap than the reference-resolution debt this phase closed.
3. **Full Prometheus/OpenTelemetry/alerting stack remains deliberately deferred**, per this phase's own
   scope boundary.
4. **`migrations/0001_phase05.sql` remains a single, ever-growing file** - unchanged carryover, now
   larger again.
5. **No real Temporal worker** - see the decision above; deliberate, not an oversight.

None of these require live external credentials to close - they are local, deterministic gaps, and none
contradict any zero-tolerance PASS above.
