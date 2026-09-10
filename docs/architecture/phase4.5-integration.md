# Phase 4.5 - Commerce OS Integration & Operationalization

Status: `LOCAL/HARNESS VALIDATED - INTEGRATED RUNTIME PROVEN`

## Scope

Not a new business-domain module. Converts the independently-tested Phase 0-4.1 engines into one
coherent, continuously operating system: external event -> authenticated ingress -> canonical truth ->
workflow -> deterministic engine -> external mutation where required -> reconciliation ->
exception/approval -> operator visibility. Acceptance standard: proof that an event entering the
running FastAPI application actually traverses the existing engines through real HTTP + auth +
workflow plumbing - passing direct-service unit tests alone is no longer sufficient evidence.

## What was built

- **Refund canonical-truth split** (`packages/domain_contract/models.py::Refund`): `status`
  (operational lifecycle) and `financial_reconciliation_status` (`pending`/`matched`/`discrepancy`,
  written ONLY by `FinanceOperationsService._apply_refund_reconciliation_to_canonical`) are now
  distinct fields on the same canonical row, never collapsed into one ambiguous status.
  `packages/runtime/queries.py::get_refund_full_state()` is the one place both are read together.
- **Runtime orchestration layer**: `packages/runtime/commands.py` (state-changing dispatch, zero
  business logic) and `packages/runtime/queries.py` (read-only, operator-facing) sit between
  `apps/api` routes and the existing domain services (`PostOrderOperationsService`,
  `FinanceOperationsService`, `ProcurementService`). Routes validate/authenticate/authorize and
  dispatch; business logic never lives in a route handler.
- **`workers/workflow/order_orchestrator.py::OrderOrchestrator`**: duck-typed drop-in for
  `FakeTemporalEngine` wherever a `workflow` object is expected by the Shopify connector. On a
  paid order it drives `PostOrderOperationsService.reserve_inventory_for_order`, making the
  workflow-execution row (`WorkflowExecution.current_step`) reflect real orchestration progress
  rather than being bookkeeping decoration - the Phase 4.5 audit's "fake workflow bookkeeping"
  finding is closed by having the orchestrator actually call into the engine, not merely record
  a status string.
- **`packages/authn`**: hashed API keys (`sk_` prefix, SHA-256 at rest, returned raw exactly once),
  `operator` (merchant-scoped) and `service` (merchant-agnostic) roles, `require_operator`
  cross-checks the authenticated key's bound merchant against `request.path_params["merchant_id"]`
  so a caller can never choose a different merchant via the URL.
- **Webhook verification**: confirmed (not newly built - a correction to an earlier audit
  assumption) that `connectors/shopify/connector.py` already had real HMAC verification, webhook-id
  idempotency, and stale-sequence rejection from Phase 0. Phase 4.5 wires an invalid signature to a
  401 *before* any canonical mutation at the route layer (`apps/api/app.py`).
- **`packages/audit/context.py`**: `contextvars.ContextVar`-based correlation ID, set by
  `CorrelationMiddleware` per request, read by `AuditLedger.record()` and `ExceptionService.create()`
  without touching ~50 existing call sites.
- **`workers/reconciliation_worker.py::ReconciliationWorker`**: read-external-truth-first, bounded
  retry (default 5 attempts), terminal escalation (`severity="critical"`) recovery primitive for
  uncertain PO submissions and uncertain refund executions, plus stale-`WorkflowExecution` flagging.
  Not wired to a scheduler yet (tracked debt).
- **`packages/onboarding/merchant.py::MerchantOnboardingService.onboard()`**: config-driven
  onboarding (finance tolerances, procurement spending authority, logistics, returns/cancellation
  policy, supplier/offer seeding, credentials-by-reference) validated *before* any persistence
  (`ConfigValidationError` -> HTTP 422), issuing one operator API key. `onboard_phase1()` kept
  unchanged for backward compatibility.
- **`apps/api/app.py`**: ~30 merchant-scoped routes under `/merchants/{merchant_id}/...` (orders,
  inventory, refunds/returns/exchanges/cancellations, fulfilment/shipment/NDR, payments/settlement,
  procurement/PO/inbound/goods-receipt, exceptions, operator summary), `/admin/api-keys` and
  `/admin/merchants` (service-role only), all behind `require_operator`/`require_service`.

## Bugs found and fixed during this phase's own validation

1. **`IdempotencyService` reservation leak on the reserve-inventory path** was not present here (that
   was Phase 4); this phase's genuine find was in the workload harness, not production code (below),
   plus one real fix in `packages/domain_contract/postgres_store.py`'s `list_where()` boundary being
   exercised for the first time under concurrent operator-summary reads - no defect found, confirmed
   safe by the integration test suite.
2. **`_PHASE45_TABLES` reset list included `audit_events`**, which is DB-trigger-enforced append-only
   (cannot be deleted). Deleting the `merchants` row for re-onboarding also cascaded into
   `audit_events` via foreign key, hitting the same trigger. Both removed from the reset routine;
   re-onboarding relies on `Merchant.put()`'s `ON CONFLICT (id) DO UPDATE` idempotency instead of a
   delete-then-recreate cycle.
3. **`idempotency_records` was never cleared by the workload's reset routine.** Because
   `idempotency_records` has no `merchant_id` column (the merchant is embedded as a string prefix in
   `scope`, e.g. `"{merchant_id}:webhook:shopify:{topic}"`), a re-run of the integrated workload
   replayed a *previous* run's cached webhook-idempotency result - returning an `order_id` from an
   already-wiped `orders` table and causing every subsequent `store.get(Order, ...)` in that run to
   raise `NotFoundError`. This looked identical to a concurrency/connection-reuse bug and cost
   significant investigation time (three isolated repro scripts, none reproducing it, before the
   actual discrepancy - the real script's reset sequence vs. the repros' - was found). Fixed by
   deleting `idempotency_records WHERE scope LIKE '{merchant_id}:%'` as part of the same reset. This
   is a workload-harness bug, not a defect in `IdempotencyService` or the API itself, but it is
   recorded here because it is exactly the class of bug this phase's "prove it through the real
   runtime, not direct service calls" mandate is designed to catch - the harness itself must be held
   to the same evidentiary standard as the code it exercises.
4. **`SANOCEA_PG_REUSE_CONNECTION` investigated as a hypothesis for the above and ruled out** as the
   cause of that specific bug, but the underlying observation is real and kept: a psycopg2 connection
   is not thread-safe, and FastAPI dispatches sync route handlers via `run_in_threadpool` (multiple
   OS threads). Connection-reuse mode must not be enabled for anything served through the API process;
   it remains acceptable only for single-threaded, single-connection workload/test scripts. Documented
   in the workload script rather than removed as a capability, since some future single-threaded
   tooling may still want it.
5. **`PostOrderOperationsService` constructed with `shopify_connector=None`** in `apps/api/app.py`'s
   service graph - confirmed safe by reading every use site (`self.shopify` is never read by that
   class), not merely assumed. Documented as a deliberate simplification: the connector was never
   needed on that side of the dependency graph, so no placeholder/stub was introduced.

## Integrated zero-tolerance results (measured live, `scripts/run_phase45_integration_workload.py`)

All 13 required conditions, re-verified against real Postgres through the running FastAPI app (see
the workload report's `zero_tolerance` block for full evidence strings):

| Condition | Result |
|---|---|
| duplicate_order_business_effect | PASS |
| duplicate_payment_refund_po_mutation | PASS |
| cross_tenant_access_or_mutation | PASS |
| unauthorized_approval | PASS |
| invalid_webhook_causing_mutation | PASS |
| refund_canonical_truth_contradiction | PASS |
| stale_event_regressing_state | PASS |
| inbound_becoming_sellable_prematurely | PASS |
| unauthorized_procurement_spend | PASS |
| financial_discrepancy_silently_swallowed | PASS |
| uncertain_mutation_blindly_retried | PASS |
| unresolved_external_reference_silently_matched | PASS |
| operator_critical_exception_invisible_to_control_plane | PASS |

Normal-workload and adversarial-workload metrics are reported separately in the workload report and
must not be blended into one pass rate.

## Tracked debt (explicitly deferred, not forgotten)

1. **Catalogue/product publication has no HTTP command surface.** Journey A's
   product -> canonical -> approval -> publication path remains reachable only via direct Phase 1
   service calls, not through `apps/api` - only post-order/finance/procurement were named in this
   phase's scope.
2. **Support engine has no HTTP command surface.** `packages/support/workflow.py` is unwired to
   `apps/api`; support-visible truth was proven by reading the same canonical Order/Refund rows via
   `queries.get_refund_full_state()`, not by exercising the support engine itself through HTTP.
3. **No real Temporal worker registration.** `OrderOrchestrator`/`FakeTemporalEngine` remain in-process
   orchestration; a durable Temporal workflow with real timers/retries across process restarts was not
   built.
4. **`ReconciliationWorker` has no scheduler/always-on process wrapper.** `run_once()` is a real,
   tested, safe recovery primitive; nothing yet runs it periodically (a systemd timer / cron / simple
   loop is a deployment-time gap, not a code gap).
5. **Full Prometheus/OpenTelemetry/alerting stack is deliberately deferred**, per this phase's explicit
   scope boundary (item 18: structured logging + correlation IDs + basic control-plane counters only).
6. **`migrations/0001_phase05.sql` remains a single, ever-growing file** (unchanged carryover from
   Phase 3/4) - still no incremental/versioned migration mechanism.
7. **Refund settlement entries still reference `refund_id` directly** rather than resolving through
   `external_id_mappings` (unchanged carryover from Phase 3.1 - out of this phase's mandate too).

None of these require live external credentials to close - they are local, deterministic gaps, and
none of them contradict any zero-tolerance PASS above.

## Ownership boundary

Sanocea owns canonical truth, orchestration, authorization, reconciliation, and operator visibility.
External systems (Shopify, payment gateways, suppliers, logistics) remain the source of observed
truth; all three connectors used in this phase's proof are simulators (`SimulatedSupplierConnector`,
`SimulatedPaymentConnector`, `SimulatedLogisticsConnector`) plus HMAC-signed synthetic Shopify webhook
payloads - no live external platform was exercised. AI is not used anywhere in Phase 4.5.
