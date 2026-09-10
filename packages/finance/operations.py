from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    ExternalIdMapping,
    FinanceReconciliation,
    Order,
    Payment,
    PaymentObservation,
    Refund,
    SettlementBatch,
    SettlementEntry,
    now_utc,
)
from sanocea.packages.exceptions import ExceptionService


@dataclass
class FinanceCounters:
    payment_observations: int = 0
    payment_reconciliations: int = 0
    reconciliation_results: int = 0
    settlement_batches: int = 0
    settlement_entries: int = 0
    matched: int = 0
    expected_lag: int = 0
    divergences: int = 0
    unmatched_entries: int = 0
    duplicate_entries: int = 0
    missing_refunds: int = 0
    partial_settlements: int = 0
    over_settlements: int = 0
    under_settlements: int = 0
    unresolved_references: int = 0
    adjustments_recorded: int = 0
    fee_discrepancies: int = 0
    courier_charge_discrepancies: int = 0
    cod_discrepancies: int = 0
    exceptions: int = 0
    auto_reconciled: int = 0
    approval_touches: int = 0
    corrective_interventions: int = 0
    ai_calls: int = 0
    duplicate_financial_mutations: int = 0
    cross_tenant_violations: int = 0

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        total = max(self.reconciliation_results, 1)
        data["automation_rate"] = round((self.matched + self.expected_lag) / total, 4)
        data["corrective_intervention_rate"] = round(self.corrective_interventions / total, 4)
        data["ai_dependency_rate"] = round(self.ai_calls / total, 4)
        return data


class FinanceOperationsService:
    def __init__(self, store) -> None:
        self.store = store
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)

    def observe_payment(self, merchant_id: str, order: Order, provider: str, amount: int, currency: str, status: str, external_payment_id: str | None = None) -> PaymentObservation:
        """Record a payment observation.

        Idempotent by (merchant_id, provider, external_payment_id): repeated delivery of the same
        webhook/event (retry, replay, or a genuine concurrent race) must produce exactly one business
        observation. Database-enforced uniqueness (see migrations/0001_phase05.sql
        uq_payment_observation_external) is the final authority - PostgresStore.put() returns the
        pre-existing row on conflict instead of the freshly constructed one, and that is what callers
        must treat as canonical.
        """
        observation = PaymentObservation(
            merchant_id=merchant_id,
            order_id=order.id,
            provider=provider,
            external_payment_id=external_payment_id,
            amount=amount,
            currency=currency,
            status=status,
        )
        persisted = self.store.put(observation)
        is_duplicate = persisted.id != observation.id
        if external_payment_id is not None:
            # This is the moment a real gateway integration would establish its OWN transaction/order
            # reference for this order - exactly the reference that will later reappear on a settlement
            # feed. Recording it in external_id_mappings now (rather than letting settlement ingestion
            # invent a shortcut back to order.id) is what lets Phase 3.1 resolve settlement entries
            # through a real external-identifier lookup instead of Sanocea's own primary key.
            self.store.put_external_mapping(
                ExternalIdMapping(
                    merchant_id=merchant_id,
                    sanocea_entity_type="Order",
                    sanocea_id=order.id,
                    external_system=provider,
                    external_entity_type="order",
                    external_id=external_payment_id,
                )
            )
        self.audit.record(
            merchant_id=merchant_id,
            actor="finance",
            source=provider,
            action="payment_observation_duplicate_ignored" if is_duplicate else "payment_observed",
            object_type="Order",
            object_id=order.id,
            result=status,
        )
        return persisted

    def reconcile_payment(self, merchant_id: str, order: Order, observation: PaymentObservation) -> FinanceReconciliation:
        """Reconcile a payment observation against canonical order truth.

        Idempotent per observation: if this exact observation has already been reconciled (its id is
        tagged into evidence_refs on the prior result), that prior result is returned unchanged instead
        of appending a second reconciliation record for the same underlying business event. This matters
        because observe_payment() now returns the same PaymentObservation for a duplicate delivery, so a
        caller that always does observe-then-reconcile must not double-book the reconciliation either.
        """
        evidence_tag = f"payment_observation:{observation.id}"
        existing = next(
            (
                record for record in self.store.list(FinanceReconciliation, merchant_id)
                if record.object_id == order.id
                and record.scope.startswith("payment")
                and evidence_tag in record.evidence_refs
            ),
            None,
        )
        if existing:
            return existing
        tolerance = self._tolerance(merchant_id, "payment")
        mismatches = []
        if order.currency != observation.currency:
            mismatches.append("currency")
        if abs(order.total_amount - observation.amount) > tolerance:
            mismatches.append("amount")
        if order.payment_status == "paid" and observation.status not in {"paid", "settled", "captured"}:
            mismatches.append("status")
        if mismatches:
            return self._finance_exception(
                merchant_id,
                "payment_inconsistency",
                order.id,
                order.total_amount,
                observation.amount,
                order.currency,
                f"Payment mismatch for order {order.order_number}: {', '.join(mismatches)}",
                evidence_refs=[evidence_tag],
            )
        return self._record_reconciliation(
            merchant_id, "payment", "Order", order.id, order.total_amount, observation.amount, order.currency, "MATCH",
            evidence_refs=[evidence_tag],
        )

    def ingest_settlement_batch(self, merchant_id: str, provider: str, batch_payload: dict[str, Any]) -> SettlementBatch:
        existing = [
            batch for batch in self.store.list(SettlementBatch, merchant_id)
            if batch.provider == provider and batch.external_batch_id == str(batch_payload["external_batch_id"])
        ]
        if existing:
            return existing[-1]
        batch = SettlementBatch(
            merchant_id=merchant_id,
            provider=provider,
            external_batch_id=str(batch_payload["external_batch_id"]),
            settlement_date=batch_payload.get("settlement_date") or datetime.now(timezone.utc),
            currency=batch_payload.get("currency", "INR"),
            gross_amount=int(batch_payload.get("gross_amount", 0)),
            net_amount=int(batch_payload.get("net_amount", 0)),
        )
        # store.put() is idempotent on (merchant_id, provider, external_batch_id) at the DB layer: a
        # concurrent ingest of the same batch id (racing past the "existing" pre-check above) returns
        # the pre-existing persisted batch instead of creating a duplicate.
        batch = self.store.put(batch)
        seen: set[str] = set()
        for raw in batch_payload.get("entries", []):
            external_entry_id = str(raw["external_entry_id"])
            duplicate = external_entry_id in seen or any(
                entry.provider == provider and entry.external_entry_id == external_entry_id
                for entry in self.store.list(SettlementEntry, merchant_id)
            )
            seen.add(external_entry_id)
            if duplicate:
                self._finance_exception(
                    merchant_id, "duplicate_settlement_entry", batch.id, None, int(raw.get("amount", 0)), batch.currency,
                    f"Duplicate settlement entry {external_entry_id}", result="DUPLICATE",
                )
                continue
            entry_type = raw["entry_type"]
            provider_order_reference = raw.get("provider_order_reference")
            provider_refund_reference = raw.get("provider_refund_reference")
            resolved_order_id: str | None = None
            resolved_refund_id: str | None = None
            if entry_type in {"payment", "cod_collection"}:
                # Phase 3.1: settlement entries no longer accept a Sanocea order.id directly. The
                # provider's own reference must resolve through external_id_mappings (established when
                # the payment was first observed - see observe_payment()). An unresolved reference is
                # kept as evidence on the entry but produces no order_id, so it can never accidentally
                # reconcile against the wrong order (or any order at all) later.
                if provider_order_reference is not None:
                    mapping = self.store.get_external_mapping(merchant_id, provider, "order", str(provider_order_reference))
                    resolved_order_id = mapping.sanocea_id if mapping else None
            elif entry_type == "refund":
                # Phase 4.6: the same treatment, closing the Phase 3.1 debt on the refund side - never
                # trust an incoming refund_id directly, resolve the provider's own reference through
                # external_id_mappings (established at execute_refund time - see
                # PostOrderOperationsService._register_refund_reference()).
                if provider_refund_reference is not None:
                    mapping = self.store.get_external_mapping(merchant_id, provider, "refund", str(provider_refund_reference))
                    resolved_refund_id = mapping.sanocea_id if mapping else None
            else:
                resolved_order_id = raw.get("order_id")
            attempted = SettlementEntry(
                merchant_id=merchant_id,
                batch_id=batch.id,
                provider=provider,
                external_entry_id=external_entry_id,
                entry_type=entry_type,
                provider_order_reference=str(provider_order_reference) if provider_order_reference is not None else None,
                order_id=resolved_order_id,
                provider_refund_reference=str(provider_refund_reference) if provider_refund_reference is not None else None,
                refund_id=resolved_refund_id,
                amount=int(raw.get("amount", 0)),
                currency=raw.get("currency", batch.currency),
                description=raw.get("description"),
                evidence_ref=f"settlement://{provider}/{batch.external_batch_id}/{external_entry_id}",
            )
            # store.put() is idempotent on (merchant_id, provider, external_entry_id) at the DB layer
            # (uq_settlement_entry_external). This is the final authority against a genuine concurrent
            # ingestion race that slips past the application-level pre-check above (SELECT-then-check is
            # only a fast path, not the safety mechanism).
            persisted_entry = self.store.put(attempted)
            if persisted_entry.id != attempted.id:
                self._finance_exception(
                    merchant_id, "duplicate_settlement_entry", batch.id, None, int(raw.get("amount", 0)), batch.currency,
                    f"Duplicate settlement entry {external_entry_id} (race detected by database uniqueness)", result="DUPLICATE",
                )
        self.audit.record(merchant_id=merchant_id, actor="finance", source=provider, action="settlement_batch_ingested", object_type="SettlementBatch", object_id=batch.id, result="observed")
        return batch

    def reconcile_settlement_batch(self, merchant_id: str, batch_id: str, *, final_orders: set[str] | None = None) -> list[FinanceReconciliation]:
        """Reconcile every entry in a settlement batch.

        Payment/COD entries are no longer reconciled one-at-a-time against the order's full amount (that
        was Phase 3's bug: the same order settled under two different external entry ids - across one
        batch or several - would independently "MATCH" twice, concealing duplicate/over-settlement).
        Instead, every payment/cod_collection entry that resolves to a canonical order is only recorded
        as touching that order; the actual verdict is produced once per order by
        reconcile_cumulative_settlement(), which sums EVERY settlement entry ever persisted for that
        order (across all batches, this call and any previous one) against the order's expected total.

        `final_orders` lets a caller who knows no further settlement is coming for specific orders (e.g.
        an explicit end-of-cycle pass) turn a below-expected cumulative total from PARTIAL_SETTLEMENT
        (still open, more may arrive) into UNDER_SETTLED (closed short). Phase 3.1 has no wall-clock
        SLA/timer concept for this - it is an explicit input, not inferred, by design.
        """
        batch = self.store.get(SettlementBatch, merchant_id, batch_id)
        entries = [entry for entry in self.store.list(SettlementEntry, merchant_id) if entry.batch_id == batch.id]
        results: list[FinanceReconciliation] = []
        orders = {order.id: order for order in self.store.list(Order, merchant_id)}
        refunds = {refund.id: refund for refund in self.store.list(Refund, merchant_id)}
        final_orders = final_orders or set()
        touched_order_ids: set[str] = set()
        for entry in entries:
            if entry.currency != batch.currency:
                results.append(self._finance_exception(merchant_id, "settlement_currency_mismatch", entry.id, None, entry.amount, entry.currency, f"Settlement entry currency mismatch {entry.external_entry_id}"))
                continue
            if entry.entry_type in {"payment", "cod_collection"}:
                order = orders.get(entry.order_id or "")
                if not order:
                    # Unresolved OR ambiguous provider reference - must never MATCH.
                    results.append(
                        self._finance_exception(
                            merchant_id,
                            "unresolved_settlement_reference",
                            entry.id,
                            None,
                            entry.amount,
                            entry.currency,
                            f"Settlement entry {entry.external_entry_id} carries provider_order_reference="
                            f"{entry.provider_order_reference!r} which does not resolve to any known order "
                            f"via external_id_mappings for provider={entry.provider}",
                            result="UNRESOLVED_REFERENCE",
                            object_type="SettlementEntry",
                            scope="settlement",
                        )
                    )
                    continue
                if entry.currency != order.currency:
                    results.append(
                        self._finance_exception(
                            merchant_id, "settlement_order_currency_mismatch", entry.id, order.total_amount, entry.amount, entry.currency,
                            f"Settlement entry {entry.external_entry_id} currency {entry.currency} does not match order {order.order_number} currency {order.currency}",
                            object_type="SettlementEntry",
                        )
                    )
                    continue
                touched_order_ids.add(order.id)
            elif entry.entry_type == "refund":
                refund = refunds.get(entry.refund_id or "")
                if not refund:
                    if entry.provider_refund_reference:
                        # A reference WAS supplied but did not resolve via external_id_mappings - an
                        # unknown or corrupted refund reference must never be treated as merely
                        # "unmatched" (which would imply Sanocea simply hasn't executed a refund at all
                        # yet); it is a resolution failure and must be as visible as the equivalent
                        # payment/order case.
                        results.append(
                            self._finance_exception(
                                merchant_id,
                                "unresolved_settlement_reference",
                                entry.id,
                                None,
                                entry.amount,
                                entry.currency,
                                f"Settlement entry {entry.external_entry_id} carries provider_refund_reference="
                                f"{entry.provider_refund_reference!r} which does not resolve to any known refund "
                                f"via external_id_mappings for provider={entry.provider}",
                                result="UNRESOLVED_REFERENCE", object_type="SettlementEntry", scope="settlement",
                            )
                        )
                    else:
                        results.append(self._record_reconciliation(merchant_id, "settlement", "SettlementEntry", entry.id, None, entry.amount, entry.currency, "EXTERNAL_ONLY", "unmatched_refund_settlement_entry"))
                    continue
                expected = -abs(refund.amount)
                reconciliation = self._reconcile_amount(merchant_id, "refund_settlement", "Refund", refund.id, expected, entry.amount, refund.currency)
                results.append(reconciliation)
                self._apply_refund_reconciliation_to_canonical(merchant_id, refund.id, reconciliation)
            elif entry.entry_type in {"fee", "courier_charge", "marketplace_deduction"}:
                results.append(self._reconcile_charge(merchant_id, entry))
            elif entry.entry_type == "adjustment":
                # Sanocea has no independent source of truth for what a provider-initiated adjustment
                # "should" be - it is inherently ad-hoc. Record it as evidence for human review rather
                # than fabricating an expected value to compare it against.
                results.append(
                    self._record_reconciliation(
                        merchant_id, "settlement", "SettlementEntry", entry.id, None, entry.amount, entry.currency,
                        "ADJUSTMENT_RECORDED", "adjustment_recorded",
                    )
                )
            else:
                results.append(self._record_reconciliation(merchant_id, "settlement", "SettlementEntry", entry.id, None, entry.amount, entry.currency, "UNKNOWN", "unknown_settlement_entry_type"))

        for order_id in touched_order_ids:
            results.append(self.reconcile_cumulative_settlement(merchant_id, order_id, final=order_id in final_orders))

        for refund in refunds.values():
            if refund.status == "completed" and not any(entry.refund_id == refund.id for entry in entries):
                # A refund the canonical Refund lifecycle (Phase 2.1) marked "completed" has no
                # corresponding settlement entry at all. This is not a passive "canonical-only" data
                # point - money the merchant is owed may be missing from the provider's settlement.
                # It must be a real, human-visible finance exception, not just a silent DB row.
                missing_reconciliation = self._finance_exception(
                    merchant_id,
                    "missing_refund_settlement",
                    refund.id,
                    -abs(refund.amount),
                    None,
                    refund.currency,
                    f"Refund {refund.id} marked completed but has no matching settlement entry",
                    result="CANONICAL_ONLY",
                    object_type="Refund",
                    scope="refund_settlement",
                )
                results.append(missing_reconciliation)
                self._apply_refund_reconciliation_to_canonical(merchant_id, refund.id, missing_reconciliation)
        return results

    def _apply_refund_reconciliation_to_canonical(self, merchant_id: str, refund_id: str, reconciliation: FinanceReconciliation) -> None:
        """The ONLY code path that writes financial_reconciliation_status/_ref back onto the canonical
        Refund - this is what closes the Phase 3 <-> Phase 2.1 refund canonical-truth split. Phase 2.1's
        execution status (permitted/.../completed) is left completely untouched; this only ever writes
        the separate financial_reconciliation_* fields, so operational completion and financial
        reconciliation can never be silently collapsed into one ambiguous status.
        """
        refund = self.store.get(Refund, merchant_id, refund_id)
        new_status = "matched" if reconciliation.result == "MATCH" else "discrepancy"
        if refund.financial_reconciliation_status == new_status and refund.financial_reconciliation_ref == reconciliation.id:
            return
        refund.financial_reconciliation_status = new_status
        refund.financial_reconciliation_ref = reconciliation.id
        refund.financial_reconciliation_updated_at = now_utc()
        self.store.put(refund)
        self.audit.record(
            merchant_id=merchant_id, actor="finance", source="finance_reconciliation",
            action="refund_financial_reconciliation_applied", object_type="Refund", object_id=refund.id,
            result=new_status,
        )

    def reconcile_cumulative_settlement(self, merchant_id: str, order_id: str, *, final: bool = False) -> FinanceReconciliation:
        """The authoritative, cross-batch verdict for whether an order's settlement is correct.

        Sums EVERY payment/cod_collection settlement entry ever persisted for this order - across any
        number of batches, ingested at any time - and compares the cumulative total to the order's
        expected amount. This is what closes the Phase 3 defect where the same order settled under two
        different external entry ids (in one batch or across several) would independently "MATCH" twice.

        Retransmission of the exact same provider entry is already excluded from the sum: SettlementEntry
        persistence is idempotent on (merchant_id, provider, external_entry_id) at the database layer
        (uq_settlement_entry_external), so a duplicate delivery never contributes a second row here.

        Result states:
          MATCH               - cumulative observed == expected, within tolerance.
          PARTIAL_SETTLEMENT  - cumulative observed < expected, and this is not the final settlement
                                 pass for this order (more entries may legitimately still arrive).
          UNDER_SETTLED       - cumulative observed < expected AND the caller marked this order's
                                 settlement as final (no more entries expected) - a real shortfall.
          OVER_SETTLED        - cumulative observed > expected. If two or more contributing entries
                                 share the exact same amount, the exception explicitly flags a possible
                                 duplicate remittance (still OVER_SETTLED - a human decides whether it is
                                 a legitimate second charge or a duplicate).
        """
        order = self.store.get(Order, merchant_id, order_id)
        contributing = [
            entry for entry in self.store.list(SettlementEntry, merchant_id)
            if entry.order_id == order_id and entry.entry_type in {"payment", "cod_collection"} and entry.currency == order.currency
        ]
        cumulative_observed = sum(entry.amount for entry in contributing)
        tolerance = self._tolerance(merchant_id, "cumulative_settlement")
        evidence_refs = [f"settlement_entry:{entry.id}" for entry in contributing]
        delta = cumulative_observed - order.total_amount

        if abs(delta) <= tolerance:
            return self._record_reconciliation(
                merchant_id, "cumulative_settlement", "Order", order_id, order.total_amount, cumulative_observed, order.currency,
                "MATCH", evidence_refs=evidence_refs,
            )
        if delta > tolerance:
            amounts = [entry.amount for entry in contributing]
            possible_duplicate = len(set(amounts)) < len(amounts)
            category = "over_settled_duplicate_risk" if possible_duplicate else "over_settled"
            note = " (two or more entries share the same amount - possible duplicate remittance)" if possible_duplicate else ""
            return self._finance_exception(
                merchant_id, category, order_id, order.total_amount, cumulative_observed, order.currency,
                f"Cumulative settlement for order {order.order_number} exceeds expected across {len(contributing)} entr"
                f"{'y' if len(contributing) == 1 else 'ies'}: expected={order.total_amount} cumulative_observed={cumulative_observed}{note}",
                result="OVER_SETTLED", object_type="Order", scope="cumulative_settlement", evidence_refs=evidence_refs,
            )
        # delta < -tolerance: cumulative observed is short of expected.
        if final:
            return self._finance_exception(
                merchant_id, "under_settled", order_id, order.total_amount, cumulative_observed, order.currency,
                f"Cumulative settlement for order {order.order_number} closed below expected: "
                f"expected={order.total_amount} cumulative_observed={cumulative_observed} across {len(contributing)} entries",
                result="UNDER_SETTLED", object_type="Order", scope="cumulative_settlement", evidence_refs=evidence_refs,
            )
        return self._record_reconciliation(
            merchant_id, "cumulative_settlement", "Order", order_id, order.total_amount, cumulative_observed, order.currency,
            "PARTIAL_SETTLEMENT", "partial_settlement", evidence_refs=evidence_refs,
        )

    def _reconcile_amount(self, merchant_id: str, scope: str, object_type: str, object_id: str, expected: int, observed: int, currency: str) -> FinanceReconciliation:
        tolerance = self._tolerance(merchant_id, scope)
        if abs(expected - observed) <= tolerance:
            return self._record_reconciliation(merchant_id, scope, object_type, object_id, expected, observed, currency, "MATCH")
        return self._finance_exception(merchant_id, "refund_reconciliation_discrepancy", object_id, expected, observed, currency, f"{scope} expected={expected} observed={observed}", object_type=object_type)

    def _reconcile_charge(self, merchant_id: str, entry: SettlementEntry) -> FinanceReconciliation:
        config = self.store.get_config(merchant_id).get("finance", {})
        expected_charges = config.get("expected_charges", {})
        if entry.entry_type not in expected_charges:
            # No merchant configuration exists for this charge type. The observed amount must NEVER be
            # used as a stand-in expected value - that would make every unconfigured charge trivially
            # "match itself" and defeat discrepancy detection entirely. Surface it as an explicit
            # non-MATCH state that requires an operator to add configuration before it can be judged.
            return self._finance_exception(
                merchant_id,
                f"{entry.entry_type}_requires_configuration",
                entry.id,
                None,
                entry.amount,
                entry.currency,
                f"No expected_charges configuration for entry_type={entry.entry_type}; observed={entry.amount}. "
                "Cannot reconcile without merchant configuration - add finance.expected_charges."
                ,
                result="REQUIRES_CONFIGURATION",
                object_type="SettlementEntry",
                scope=entry.entry_type,
            )
        expected = int(expected_charges[entry.entry_type])
        tolerance = self._tolerance(merchant_id, entry.entry_type)
        if abs(expected - entry.amount) <= tolerance:
            return self._record_reconciliation(merchant_id, entry.entry_type, "SettlementEntry", entry.id, expected, entry.amount, entry.currency, "MATCH")
        category = f"{entry.entry_type}_discrepancy"
        return self._finance_exception(merchant_id, category, entry.id, expected, entry.amount, entry.currency, f"{entry.entry_type} expected={expected} observed={entry.amount}", object_type="SettlementEntry")

    def _finance_exception(
        self,
        merchant_id: str,
        category: str,
        object_id: str | None,
        expected: int | None,
        observed: int | None,
        currency: str | None,
        message: str,
        *,
        result: str = "DIVERGENCE",
        object_type: str = "FinanceObject",
        scope: str = "finance",
        evidence_refs: list[str] | None = None,
    ) -> FinanceReconciliation:
        exc: ExceptionRecord = self.exceptions.create(
            merchant_id=merchant_id,
            category=category,
            message=message,
            object_id=object_id,
            severity="warning",
            remediation_options=["reconcile_from_provider", "finance_review"],
        )
        return self._record_reconciliation(
            merchant_id, scope, object_type, object_id, expected, observed, currency, result, category, exc.id,
            evidence_refs=evidence_refs,
        )

    def _record_reconciliation(
        self,
        merchant_id: str,
        scope: str,
        object_type: str,
        object_id: str | None,
        expected: int | None,
        observed: int | None,
        currency: str | None,
        result: str,
        category: str | None = None,
        exception_id: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> FinanceReconciliation:
        record = FinanceReconciliation(
            merchant_id=merchant_id,
            scope=scope if category is None else f"{scope}:{category}",
            object_type=object_type,
            object_id=object_id,
            expected_amount=expected,
            observed_amount=observed,
            currency=currency,
            result=result,  # type: ignore[arg-type]
            tolerance=self._tolerance(merchant_id, scope),
            exception_id=exception_id,
            evidence_refs=evidence_refs or [],
        )
        self.store.put(record)
        self.audit.record(merchant_id=merchant_id, actor="finance", source="finance_reconciliation", action="finance_reconciled", object_type=object_type, object_id=object_id, result=result)
        return record

    def _tolerance(self, merchant_id: str, scope: str) -> int:
        config = self.store.get_config(merchant_id).get("finance", {})
        tolerances = config.get("tolerances", {})
        return int(tolerances.get(scope, tolerances.get("default", 0)))
