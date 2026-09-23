# Phase 3 Finance Operations & Reconciliation

Status: `LOCAL/HARNESS VALIDATED - HARDENED (Phase 3.1: settlement integrity)`

## Phase 3.1 - Settlement integrity hardening

A follow-up narrow hardening pass fixed two structural defects that survived the first hardening pass:

1. **Cross-batch cumulative settlement reconciliation.** The same order settling under two different
   external entry ids - within one batch or, worse, across several - independently reconciled `MATCH`
   each time, concealing duplicate/over-settlement. `FinanceOperationsService.reconcile_cumulative_settlement()`
   now sums EVERY payment/cod_collection settlement entry ever persisted for an order (across all
   batches, any time) against the order's expected total, producing one authoritative verdict per order
   per reconciliation pass: `MATCH`, `PARTIAL_SETTLEMENT` (open, more may arrive), `UNDER_SETTLED`
   (closed short - caller must explicitly mark the settlement window final; there is no wall-clock
   SLA/timer inferring this), or `OVER_SETTLED` (with an explicit duplicate-remittance flag when two
   contributing entries share the same amount). Retransmission of the exact same provider entry stays
   idempotent for free, because it relies on the same `uq_settlement_entry_external` uniqueness that
   already prevents a duplicate row from ever contributing to the sum.
2. **External-ID resolution, not `order.id` as provider identity.** `SettlementEntry` no longer accepts
   a Sanocea `order.id` directly for `payment`/`cod_collection` entries. It carries
   `provider_order_reference` - the provider's own transaction reference, exactly as it arrives - which
   `ingest_settlement_batch()` resolves through `external_id_mappings` (a mapping row is registered by
   `observe_payment()` at the moment a payment is first observed, mirroring how a real gateway
   integration would already have this correlation). An unresolved, incorrect, or currency-ambiguous
   reference now produces `UNRESOLVED_REFERENCE` (or an explicit currency-mismatch exception) and is
   never treated as a match. `SimulatedSettlementProvider` was rewritten to never embed `order.id` in
   generated settlement payloads.

Also fixed opportunistically while touching this code: duplicate settlement-entry detection (both the
app-level pre-check and the DB-race-detected path) now produces the explicit `DUPLICATE` result instead
of being mislabeled `DIVERGENCE`, and `adjustment` entries are recorded as `ADJUSTMENT_RECORDED` evidence
instead of falling into the generic `UNKNOWN` bucket.

Two new permanent zero-tolerance regression guards, both measured live every run (not asserted):
`cross_batch_settlement_integrity` (the four required scenarios - 6000+4000=MATCH,
10000+10000=OVER_SETTLED/duplicate-risk, 6000-only=PARTIAL/UNDER_SETTLED, idempotent retransmission - all
re-verified fresh) and `unresolved_reference_never_matches` (valid/unknown/incorrect/ambiguous-currency
references all resolve correctly). See `cumulative_settlement_proof` and
`external_reference_resolution_proof` in the workload report for the live evidence.

New tests: `tests/unit/test_phase31_settlement_integrity.py` (10 tests, in-memory) and two additions to
`tests/integration/test_phase3_finance_real_infra.py` proving both fixes against real Postgres.

Explicitly out of scope for Phase 3.1 (unchanged): refund settlement entries still reference `refund_id`
directly rather than resolving through `external_id_mappings` - refunds were not part of this narrow
phase's mandate. COD's lifecycle and the Phase 2.1 refund-truth write-back gap are also unchanged - see
tracked debt below.

## Hardening pass (post-audit)

An independent audit of the original Phase 3 implementation found that its reported PASS verdict was
not justified: the zero-tolerance safety gate hardcoded several "no failure detected" results instead
of measuring them, `PaymentObservation` had no idempotency protection (a duplicate webhook delivery
created two business records), missing-refund-settlement detections were invisible to every metric and
never became an exception, and settlement charge types with no merchant configuration silently
auto-matched themselves. All four were fixed, independently proven against real Postgres (including a
genuine two-connection concurrency race, not a SELECT-before-INSERT check), and are now permanent
regression guards inside `scripts/run_phase3_finance_workload.py::_zero_tolerance()`:

- `duplicate_financial_mutation` - measured by actually replaying a settlement-batch ingestion and a
  payment-observation delivery each run and confirming no new rows are created.
- `missing_refund_silently_ignored` - measured by confirming every missing-refund-settlement
  reconciliation carries a linked `ExceptionRecord`.
- `unconfigured_charge_silently_matched` - measured by confirming no settlement entry with an
  unconfigured charge type ever resolves to `MATCH`.
- A zero-tolerance condition this workload cannot currently measure is reported as `UNVERIFIED`, never
  silently coerced to `False`.

See `packages/finance/operations.py` (`observe_payment`, `reconcile_payment`, `reconcile_settlement_batch`,
`_reconcile_charge`), `packages/domain_contract/postgres_store.py` (`PaymentObservation`/`SettlementBatch`/
`SettlementEntry` branches of `put()`), and `packages/domain_contract/migrations/0001_phase05.sql`
(`uq_payment_observation_external`) for the implementation. Regression tests:
`tests/unit/test_phase3_finance.py` (sequential/in-memory) and
`tests/integration/test_phase3_finance_real_infra.py` (real Postgres, including genuine concurrency).

## Tracked debt (explicitly deferred, not forgotten)

These are known, real gaps. They do not block Phase 3/3.1 from being marked PASS, and they must not be
silently dropped when Phase 4 work starts:

1. **COD is not a distinct lifecycle** (unchanged by Phase 3.1 - deliberately out of its narrow scope).
   `cod_collection` settlement entries are reconciled through the same cumulative-accounting path as
   ordinary gateway payments. There is no delivered -> collected -> remitted state machine, no linkage
   to `Shipment`/`TrackingEvent` delivery confirmation, and no distinct handling for partial COD
   remittance or failed/RTO COD.
2. **Phase 3 finance truth does not feed back into the canonical Phase 2.1 Refund lifecycle** (unchanged
   by Phase 3.1). `packages/post_order/operations.py::reconcile_refund()` and Phase 3's settlement-based
   refund reconciliation are two independent systems. A `refund_reconciliation_discrepancy` does not
   change `Refund.status` or trigger support/workflow escalation.
3. **RESOLVED (payment/cod path) in Phase 3.1, residual gap on the refund path.** Payment/cod_collection
   settlement entries now resolve through `external_id_mappings` instead of trusting a raw `order.id`
   (see `cumulative_settlement_proof`/`external_reference_resolution_proof` in the workload report).
   Refund settlement entries still reference `refund_id` directly - refunds were not part of Phase 3.1's
   explicit mandate. A live gateway/marketplace refund reference would need the same treatment.
4. **`migrations/0001_phase05.sql` is a single, ever-growing file, not incremental/versioned
   migrations** (unchanged by Phase 3.1). Adding `uq_payment_observation_external` in the Phase 3
   hardening pass required manually deduplicating pre-existing rows before the migration could apply
   cleanly - there is still no forward-migration mechanism for an already-deployed database.
5. **RESOLVED in Phase 3.1.** Settlement matching was keyed only on `(provider, external_entry_id)`,
   with no cross-batch/cross-entry duplicate-order detection - the same order settling twice under two
   different entry ids (discovered via the `multi_batch.same_payment_across_batches` probe) independently
   reconciled `MATCH` both times. `reconcile_cumulative_settlement()` now catches this as `OVER_SETTLED`
   (with a duplicate-risk flag). See the workload report's `multi_batch.same_payment_across_batches.note`.

None of these require live external credentials to fix - they are local, deterministic gaps.

Live external certification:

- `LIVE SHOPIFY E2E: PENDING - credentials unavailable`
- Live payment gateway settlement certification: pending credentials
- Live courier charge certification: pending credentials
- Live marketplace settlement certification: pending credentials

Runtime note:

- `RUNTIME-001 - Windows local lifecycle / process termination instability` remains open as a host/runtime defect.
- Phase 3 product development uses the known-good clean local runtime and does not use the damaged Postgres 55432 cluster.

## Scope

Phase 3 extends Commerce OS into deterministic finance operations on top of canonical orders, payments, refunds and returns.

Implemented locally:

- payment observations
- payment reconciliation
- settlement batches
- settlement entries
- cross-batch cumulative settlement reconciliation (Phase 3.1)
- external-ID resolution for settlement entries via external_id_mappings (Phase 3.1, payment/cod path)
- gateway settlement reconciliation
- COD collection reconciliation
- refund settlement reconciliation
- fee and courier-charge discrepancy detection
- unresolved/unmatched settlement entries
- duplicate settlement entry suppression
- merchant-configurable tolerances
- finance exceptions and audit evidence

Out of scope for this phase:

- accounting general ledger
- tax filing
- bank-feed ingestion
- payout forecasting
- billing/subscriptions
- live external certification without credentials

## Ownership Boundary

Sanocea owns expected-vs-observed reconciliation, exceptions, audit evidence, merchant tolerances and workflow state.

External systems remain source of observed settlement/payment truth. Simulators reproduce payment gateway, courier charge, marketplace deduction and settlement behaviours for local validation.

AI is not used in Phase 3. All finance authorization and reconciliation behaviour is deterministic.
