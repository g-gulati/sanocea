from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sanocea.packages.audit import AuditLedger
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract.location import resolve_location_ref
from .allocation import AllocationRequirement, rank_candidate_locations
from sanocea.packages.domain_contract.models import (
    Approval,
    Cancellation,
    ConnectorCommand,
    DemoSessionContact,
    Exchange,
    ExternalIdMapping,
    FulfilmentObservation,
    Inventory,
    InventoryObservation,
    InventoryReservation,
    Merchant,
    Order,
    OrderLine,
    ReconciliationResult,
    Refund,
    Return,
    Shipment,
    ShipmentObservation,
    TrackingEvent,
    now_utc,
)
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService
from sanocea.packages.policy_engine import Decision, PolicyEngine


@dataclass
class Phase2Counters:
    inventory_observations: int = 0
    inventory_discrepancies: int = 0
    inventory_auto_reconciled: int = 0
    inventory_human_interventions: int = 0
    overselling_prevented: int = 0
    fulfilments_monitored: int = 0
    fulfilment_straight_through: int = 0
    fulfilment_sla_exceptions: int = 0
    fulfilment_auto_remediated: int = 0
    fulfilment_escalated: int = 0
    shipments: int = 0
    tracking_events: int = 0
    ndrs: int = 0
    ndrs_auto_resolved: int = 0
    rtos: int = 0
    delivery_exceptions: int = 0
    logistics_human_interventions: int = 0
    cancellation_requests: int = 0
    cancellations_auto_permitted: int = 0
    cancellations_approval_gated: int = 0
    duplicate_cancellations: int = 0
    return_requests: int = 0
    return_eligibility_determined: int = 0
    returns_approval_gated: int = 0
    returns_rejected_by_policy: int = 0
    returns_completed: int = 0
    returns_escalated: int = 0
    exchange_requests: int = 0
    exchanges_completed: int = 0
    exchanges_escalated: int = 0
    refund_requests: int = 0
    refund_eligibility_determined: int = 0
    refunds_auto_permitted: int = 0
    refunds_approval_gated: int = 0
    refunds_reconciled: int = 0
    uncertain_mutations: int = 0
    duplicate_refunds: int = 0
    refund_submitted: int = 0
    refund_completed: int = 0
    duplicate_returns: int = 0
    duplicate_exchanges: int = 0
    policy_approvals: int = 0
    capability_gap_escalations: int = 0
    genuine_human_judgment: int = 0
    deterministic_operations: int = 0
    ai_assisted_operations: int = 0
    straight_through_operations: int = 0
    automated_remediations: int = 0
    approval_only_touches: int = 0
    corrective_interventions: int = 0
    fully_manual_cases: int = 0
    ai_calls: int = 0
    zero_tolerance_failures: dict[str, bool] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        total = max(
            self.inventory_observations
            + self.fulfilments_monitored
            + self.shipments
            + self.cancellation_requests
            + self.return_requests
            + self.exchange_requests
            + self.refund_requests,
            1,
        )
        data["founder_human_intervention_rate"] = round((self.approval_only_touches + self.corrective_interventions + self.fully_manual_cases) / total, 4)
        data["ai_dependency_rate"] = round(self.ai_calls / total, 4)
        data["deterministic_first_resolution_rate"] = round((total - self.ai_calls) / total, 4)
        return data


class PostOrderOperationsService:
    def __init__(self, store, storefront_connector, logistics_connector, payment_connector=None) -> None:
        self.store = store
        # storefront_connector may be a single connector (existing single-platform callers, unchanged)
        # or a StorefrontConnectorRegistry (multi-merchant/multi-platform) - as_resolver() normalizes
        # both into one calling convention: self.storefront(merchant_id) -> the right connector for
        # THAT merchant. Domain code here never knows or branches on which platform that is.
        from sanocea.packages.runtime.storefront_registry import as_resolver

        self.storefront = as_resolver(storefront_connector)
        self.logistics = logistics_connector
        self.payments = payment_connector
        self.audit = AuditLedger(store)
        self.exceptions = ExceptionService(store)
        self.policy = PolicyEngine()
        self._inventory_cache: dict[tuple[str, str, str], Inventory] = {}
        self._shipment_by_order: dict[tuple[str, str], Shipment] = {}
        self._tracking_sequence: dict[tuple[str, str], int] = {}

    def reserve_inventory_for_order(self, merchant_id: str, order: Order, location: str | None = None) -> dict[str, Any]:
        """Phase 4.5: the missing link between order ingestion and inventory truth. Idempotent at the
        ORDER level (calling this twice for the same order, e.g. a retried workflow signal, must not
        double-reserve) via the same 'sanocea_internal' ConnectorCommand marker pattern already used
        elsewhere in this service (see _record_internal_command) - and, since the 2026-09 reservation-
        lifecycle fix, each per-SKU reservation is ALSO independently DB-atomic and idempotent via
        `store.reserve_inventory_atomic` (see its docstring: a plain read-then-write here is exactly the
        check-then-update oversell race that fix closes). The outer order-level check remains as a cheap
        fast path; the inner one is what actually guarantees correctness under concurrency.

        Step 3 - EXPLICIT LOCATION REMAINS AUTHORITATIVE: if `location` is supplied, that exact location
        is attempted and ONLY that location - no automatic allocation runs, matching Step 3's explicit
        boundary. If `location` is `None`, `_allocate_and_reserve_order` runs instead (deterministic,
        single-location, whole-order allocation across eligible locations - see that method and
        `packages.post_order.allocation.rank_candidate_locations`) rather than silently resolving to a
        single "default" location the way Step 2 did; a merchant with only one eligible location for the
        SKU is unaffected either way, since the allocator naturally degenerates to that one candidate.
        """
        idempotency_key = f"reserve_inventory:{order.id}"
        existing = [c for c in self.store.list(ConnectorCommand, merchant_id) if c.action == "reserve_inventory" and c.idempotency_key == idempotency_key]
        if existing:
            lines = existing[0].payload.get("lines", [])
            return {"reserved": not any(l.get("shortfall") for l in lines), "already_done": True, "lines": lines}

        order_lines = [l for l in self.store.list(OrderLine, merchant_id) if l.order_id == order.id and l.sku]

        if location is not None:
            line_results, any_shortfall = self._reserve_order_lines_at_location(merchant_id, order, order_lines, location)
        else:
            try:
                line_results, any_shortfall = self._allocate_and_reserve_order(merchant_id, order, order_lines)
            except Exception:
                # Part I taxonomy, INTERNAL_ALLOCATION_FAILURE - an unexpected technical failure (not a
                # normal contention/no-eligible-location outcome, which _allocate_and_reserve_order
                # already reports as a deterministic result, never an exception). Record that something
                # genuinely unexpected happened and RE-RAISE rather than manufacture a success-or-failure
                # result we cannot actually stand behind - "do not manufacture success evidence before DB
                # commit" applies equally to inventing a false deterministic failure reason here.
                self.audit.record(
                    merchant_id=merchant_id, actor="post_order", source="inventory_allocation", action="location_allocation_decision",
                    object_type="Order", object_id=order.id, result="failed",
                    requested_mutation={"reason": "INTERNAL_ALLOCATION_FAILURE"},
                )
                raise

        self._record_internal_command(merchant_id, "reserve_inventory", "Order", order.id, {"lines": line_results}, idempotency_key)
        self.audit.record(
            merchant_id=merchant_id, actor="post_order", source="inventory_reservation", action="order_inventory_reserved",
            object_type="Order", object_id=order.id, result="shortfall" if any_shortfall else "reserved",
        )
        return {"reserved": not any_shortfall, "already_done": False, "lines": line_results}

    def _reserve_order_lines_at_location(self, merchant_id: str, order: Order, order_lines: list[OrderLine], location: str) -> tuple[list[dict[str, Any]], bool]:
        """The EXPLICIT-location reservation path (Step 3's "explicit means explicit" - attempt exactly
        this location, no allocation, no fallback to another location on shortfall). Unchanged in
        substance from Step 1/2 - factored out so `reserve_inventory_for_order` can share it with the
        allocator's per-candidate attempts (`_attempt_reserve_order_at_location`), which additionally
        needs to know whether the WHOLE attempt fully succeeded, for rollback purposes.
        """
        line_results: list[dict[str, Any]] = []
        any_shortfall = False
        for line in order_lines:
            has_inventory_record = any(i.sku == line.sku and i.location_ref == location for i in self.store.list(Inventory, merchant_id))
            # Keyed by line.id, NOT line.sku (Step 1A traceability correction): two OrderLines sharing
            # the same SKU within one order would otherwise collide on a sku-only key, and the second
            # line's reservation attempt would be treated as an idempotent replay of the first -
            # silently reserving nothing for its own quantity. line.id is always unique per line.
            reservation = self.store.reserve_inventory_atomic(
                merchant_id, line.sku, location,
                quantity_requested=line.quantity, source_type="order", source_id=order.id, order_line_id=line.id,
                idempotency_key=f"reserve_inventory:{order.id}:{line.id}",
            )
            reserve_qty = reservation.quantity_reserved
            shortfall = line.quantity - reserve_qty
            line_results.append({"sku": line.sku, "requested": line.quantity, "reserved": reserve_qty, "shortfall": shortfall})
            if shortfall > 0:
                any_shortfall = True
                if not has_inventory_record:
                    self.exceptions.create(
                        merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT,
                        message=f"No inventory record for sku={line.sku} - cannot reserve for order {order.order_number}",
                        object_id=order.id, remediation_options=["create_inventory_record"],
                    )
                else:
                    self.exceptions.create(
                        merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT,
                        message=f"Insufficient inventory for sku={line.sku} on order {order.order_number}: requested {line.quantity}, reserved {reserve_qty}",
                        object_id=order.id, remediation_options=["expedite_replenishment", "cancel_line", "backorder"],
                    )
        return line_results, any_shortfall

    def _attempt_reserve_order_at_location(self, merchant_id: str, order: Order, order_lines: list[OrderLine], location: str) -> dict[str, Any]:
        """One candidate-location attempt within automatic allocation - Step 4: now a single call into
        `store.reserve_order_lines_atomic`, which reserves every line for this location in ONE database
        transaction (all commit together, or nothing is ever mutated). This replaces Step 3's
        sequential-per-line-with-Python-level-compensating-release design, which left a real gap: each
        line was its own separate transaction, so a concurrent transaction COULD observe an earlier line's
        committed reservation before a later line's failure triggered the compensating release. There is
        no longer any Python-level release-on-partial-failure here, because there is no longer any partial
        state to release - the DB transaction itself never commits a partial result.

        Idempotency key format is now `reserve_inventory:{order.id}:{line.id}` - UNCHANGED from, and
        unified with, the explicit-location path's format (no `:{location}` suffix). This is deliberate:
        `InventoryReservation`'s own DB-unique index on this key is what makes concurrent attempts at
        DIFFERENT locations for the SAME order-line safely conflict with each other (Part C/F), which a
        location-suffixed key could never do.

        Returns `{"outcome": "success"|"insufficient"|"conflict", "line_results": [...]}`.
        """
        lines = [
            {"sku": line.sku, "quantity_requested": line.quantity, "order_line_id": line.id, "idempotency_key": f"reserve_inventory:{order.id}:{line.id}"}
            for line in order_lines
        ]
        result = self.store.reserve_order_lines_atomic(merchant_id, "order", order.id, location, lines)
        if result["success"]:
            return {"outcome": "success", "line_results": result["line_results"]}
        if result["conflict"]:
            return {"outcome": "conflict", "line_results": result["line_results"]}
        return {"outcome": "insufficient", "line_results": result["line_results"]}

    def _allocate_and_reserve_order(self, merchant_id: str, order: Order, order_lines: list[OrderLine]) -> tuple[list[dict[str, Any]], bool]:
        """Step 3/4: deterministic, single-location, whole-order automatic allocation, hardened for
        concurrency and failure (Step 4). Runs only when the caller has NOT explicitly supplied a
        location. Never splits an order across locations; if no single eligible location can satisfy
        every line, reports a deterministic allocation failure.

        0. IDEMPOTENT REPLAY (Part C/F) - checked FIRST, before any ranking/candidate work: if this order
           already owns reservations (from a prior run, or a concurrent run that already committed), that
           existing allocation IS the answer - return it directly. This is what makes a replay of the same
           order request never allocate a second time to a different location, and what makes two
           concurrent requests for the SAME order converge on one outcome rather than a race.
        1. Discover candidate locations: every location_ref with an existing Inventory row for any of
           this order's SKUs (Step 3's definition of "eligible" - no distance/courier/warehouse-capacity
           rules, per the mandate's explicit exclusion list).
        2. Read each candidate's current ATS per SKU (a heuristic READ used only to build a deterministic,
           explainable ATTEMPT ORDER - not itself the safety mechanism; see step 4).
        3. Rank candidates via `rank_candidate_locations` (pure, deterministic).
        4. Attempt each ranked candidate in order via `_attempt_reserve_order_at_location` - now a TRUE
           whole-order-atomic transaction per candidate (Part A). Three outcomes:
           - "success": done, selected this location.
           - "insufficient": a genuine race - the candidate looked eligible at the heuristic read but
             locked reality said otherwise. Move to the NEXT ranked candidate (bounded, Part E).
           - "conflict": another concurrent attempt for THIS ORDER already committed reservations
             elsewhere (Part C/F). Stop trying candidates immediately - re-read the order's reservations
             (now guaranteed to exist) and return that as the idempotent-replay result. Trying further
             candidates after a conflict would risk creating a second allocation for the same order.
        5. If every candidate is exhausted without success or conflict, classify and report a deterministic
           failure (Part I taxonomy) - never split, never partially reserve anywhere.

        `default_location_ref` (Step 2) no longer means "always use this location even when another
        eligible location can fulfil" (Step 3's explicit correction) - if no `location_priority` is
        separately configured, a configured `default_location_ref` participates as an IMPLICIT
        single-item priority. A merchant with only one eligible location is unaffected either way.
        """
        existing_reservations = self._reservations_for_source(merchant_id, "order", order.id)
        if existing_reservations:
            line_results = [
                {"sku": r.sku, "requested": r.quantity_requested, "reserved": r.quantity_reserved, "shortfall": r.quantity_requested - r.quantity_reserved}
                for r in existing_reservations
            ]
            self.audit.record(
                merchant_id=merchant_id, actor="post_order", source="inventory_allocation", action="location_allocation_decision",
                object_type="Order", object_id=order.id, result="already_allocated",
                requested_mutation={"reason": "ALREADY_ALLOCATED", "selected_location": existing_reservations[0].location_ref},
            )
            return line_results, any(r["shortfall"] > 0 for r in line_results)

        requirements = [AllocationRequirement(sku=line.sku, quantity=line.quantity) for line in order_lines]
        if not requirements:
            return [], False

        required_skus = {r.sku for r in requirements}
        candidate_locations = sorted({i.location_ref for i in self.store.list(Inventory, merchant_id) if i.sku in required_skus})
        ats_by_location: dict[str, dict[str, int]] = {}
        for candidate_location in candidate_locations:
            ats_by_location[candidate_location] = {}
            for requirement in requirements:
                inv = next((i for i in self.store.list(Inventory, merchant_id) if i.sku == requirement.sku and i.location_ref == candidate_location), None)
                ats_by_location[candidate_location][requirement.sku] = (inv.quantity - inv.reserved) if inv else 0

        config = self.store.get_config(merchant_id)
        inventory_config = config.get("inventory") or {}
        priority = inventory_config.get("location_priority")
        if not priority:
            default_location_ref = inventory_config.get("default_location_ref")
            priority = [default_location_ref] if default_location_ref else []

        ranked = rank_candidate_locations(ats_by_location, requirements, priority=priority)
        trace_candidates = [{"location": loc, "ats": ats_by_location[loc]} for loc in candidate_locations]
        attempts_trace: list[dict[str, Any]] = []

        if not ranked:
            return self._record_allocation_failure(merchant_id, order, requirements, required_skus, trace_candidates, priority, attempts_trace, reason="NO_ELIGIBLE_LOCATION")

        for candidate_location in ranked:
            attempt = self._attempt_reserve_order_at_location(merchant_id, order, order_lines, candidate_location)
            attempts_trace.append({"location": candidate_location, "outcome": attempt["outcome"]})

            if attempt["outcome"] == "success":
                self.audit.record(
                    merchant_id=merchant_id, actor="post_order", source="inventory_allocation", action="location_allocation_decision",
                    object_type="Order", object_id=order.id, result="allocated",
                    requested_mutation={
                        "skus": sorted(required_skus), "candidates": trace_candidates, "priority": priority,
                        "selected_location": candidate_location, "policy": "priority_then_highest_ats", "attempts": attempts_trace,
                    },
                )
                return attempt["line_results"], False

            if attempt["outcome"] == "conflict":
                # Part C/F - another concurrent attempt for THIS order already committed elsewhere. Stop
                # immediately; re-read what actually exists and return it - never try another candidate
                # after a conflict, which would risk a second allocation for the same order.
                reservations = self._reservations_for_source(merchant_id, "order", order.id)
                line_results = [
                    {"sku": r.sku, "requested": r.quantity_requested, "reserved": r.quantity_reserved, "shortfall": r.quantity_requested - r.quantity_reserved}
                    for r in reservations
                ]
                self.audit.record(
                    merchant_id=merchant_id, actor="post_order", source="inventory_allocation", action="location_allocation_decision",
                    object_type="Order", object_id=order.id, result="already_allocated",
                    requested_mutation={
                        "skus": sorted(required_skus), "candidates": trace_candidates, "priority": priority,
                        "selected_location": reservations[0].location_ref if reservations else None,
                        "policy": "priority_then_highest_ats", "attempts": attempts_trace, "reason": "ALREADY_ALLOCATED",
                    },
                )
                return line_results, any(r["shortfall"] > 0 for r in line_results)
            # "insufficient" - a genuine race at this candidate; continue to the next ranked candidate
            # (bounded by `ranked`'s finite length, never an unbounded loop).

        # Every ranked candidate was tried and none succeeded, without any conflict ever being detected -
        # CONTENTION_EXHAUSTED (Part I): each looked eligible at the heuristic read, but every one lost
        # capacity by the time its atomic attempt actually ran.
        return self._record_allocation_failure(merchant_id, order, requirements, required_skus, trace_candidates, priority, attempts_trace, reason="CONTENTION_EXHAUSTED")

    def _record_allocation_failure(
        self, merchant_id: str, order: Order, requirements: list[AllocationRequirement], required_skus: set[str],
        trace_candidates: list[dict[str, Any]], priority: list[str], attempts_trace: list[dict[str, Any]], *, reason: str,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Part I failure taxonomy - NO_ELIGIBLE_LOCATION (the ranked candidate list was empty from the
        start - no location could satisfy every line even at the heuristic read) vs. CONTENTION_EXHAUSTED
        (candidates looked eligible but every bounded atomic attempt lost the race). Never split, never
        partially reserve anywhere - both reasons return a full shortfall for every line."""
        for requirement in requirements:
            self.exceptions.create(
                merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT,
                message=f"No single eligible location has sufficient inventory for sku={requirement.sku} on order {order.order_number} ({reason})",
                object_id=order.id, remediation_options=["expedite_replenishment", "manual_location_override", "await_split_fulfilment_support"],
            )
        self.audit.record(
            merchant_id=merchant_id, actor="post_order", source="inventory_allocation", action="location_allocation_decision",
            object_type="Order", object_id=order.id, result="failed",
            requested_mutation={
                "skus": sorted(required_skus), "candidates": trace_candidates, "priority": priority,
                "selected_location": None, "policy": "priority_then_highest_ats", "attempts": attempts_trace, "reason": reason,
            },
        )
        line_results = [{"sku": r.sku, "requested": r.quantity, "reserved": 0, "shortfall": r.quantity} for r in requirements]
        return line_results, True

    def _reservations_for_source(self, merchant_id: str, source_type: str, source_id: str) -> list[InventoryReservation]:
        return [r for r in self.store.list(InventoryReservation, merchant_id) if r.source_type == source_type and r.source_id == source_id]

    def evaluate_inventory_shortage(self, merchant_id: str, order: Order, line_results: list[dict[str, Any]]) -> Approval | None:
        """Mariyal demo - the bridge `reserve_inventory_for_order` never had: a shortfall used to stop
        at 'an Exception was recorded' (see the ExceptionCategory.INVENTORY_CONFLICT calls above) with
        no path to owner authority at all. This is that path - same PolicyEngine/Approval/audit
        primitives the certified channel-ops flow already uses, not a second approval architecture.
        Idempotent: a second call for an order that already has a pending or resolved shortage approval
        returns the existing one rather than creating a duplicate.
        """
        shortfall_lines = [l for l in line_results if l.get("shortfall", 0) > 0]
        if not shortfall_lines:
            return None
        existing = [
            a for a in self.store.list(Approval, merchant_id)
            if a.action == "resolve_inventory_shortage" and a.object_id == order.id
        ]
        if existing:
            return existing[0]

        config = self.store.get_config(merchant_id)
        context = {
            "total_requested": sum(l["requested"] for l in shortfall_lines),
            "total_available": sum(l["reserved"] for l in shortfall_lines),
        }
        decision = self.policy.decide(config.get("policy", {}), "inventory_shortage", context)

        observed = {l["sku"]: {"requested": l["requested"], "available": l["reserved"], "shortfall": l["shortfall"]} for l in shortfall_lines}
        evidence = {
            "order_number": order.order_number,
            "shortage": observed,
            "policy_decision": decision.value,
        }

        if decision != Decision.REQUIRE_APPROVAL:
            # ALLOW or DENY under an explicitly configured policy - proceed automatically (or explicitly
            # do nothing, for DENY) without interrupting the owner. No Approval is created either way;
            # this is the demo's deliberate contrast case ("SANOCEA knows what it's allowed to do").
            self.audit.record(
                merchant_id=merchant_id, actor="post_order", source="inventory_shortage", action="inventory_shortage_auto_decision",
                object_type="Order", object_id=order.id, result=decision.value, requested_mutation=evidence,
            )
            if decision == Decision.ALLOW:
                self._fulfil_available_quantities(merchant_id, order, {sku: v["available"] for sku, v in observed.items()})
            return None

        shortage_lines_text = "; ".join(f"{sku}: requested {v['requested']}, only {v['available']} available" for sku, v in observed.items())
        existing_refs = {a.reference for a in self.store.list(Approval, merchant_id) if a.reference}
        reference = f"OR-{order.id[-4:]}".upper()
        attempt = 0
        while reference in existing_refs and attempt < 5:
            attempt += 1
            reference = f"OR-{uuid4().hex[-6:]}".upper()

        approval = Approval(
            merchant_id=merchant_id, action="resolve_inventory_shortage", object_id=order.id,
            requested_by="post_order", reference=reference,
            summary=f"Order {order.order_number} cannot be fully stocked: {shortage_lines_text}.",
            evidence=evidence,
            recommendation="Ship the available quantity now and backorder the remainder.",
            alternative="Hold the entire order until fully restocked (no partial shipment).",
            risk_note="Shipping less than the customer ordered without confirmation can create a support "
                      "follow-up; holding the whole order delays a customer who could have received part of it today.",
            notify_channels=[], demo_provenance="SYNTHETIC_DEMO", expires_at=now_utc() + timedelta(hours=24),
        )
        self.store.put(approval)
        self.audit.record(
            merchant_id=merchant_id, actor="post_order", source="inventory_shortage", action="inventory_shortage_approval_required",
            object_type="Order", object_id=order.id, result="approval_required",
            requested_mutation=evidence, evidence_ref=approval.id,
        )
        self._auto_notify_whatsapp_if_no_queue(merchant_id, approval, order.channel_id)
        return approval

    # Same action set ApprovalService.resolve()/DemoApprovalNotificationService._handle_inbound_once
    # already dispatch on - kept as its own literal here rather than a shared import, matching how this
    # set is already duplicated across the codebase (see those two files' own copies of this list).
    _ORDER_FLOW_APPROVAL_ACTIONS = ("channel_operation_correction", "resolve_inventory_shortage", "cancel_order", "create_return", "refund")

    def _auto_notify_whatsapp_if_no_queue(self, merchant_id: str, approval: Approval, channel: str) -> None:
        """Sequential-delivery gate (explicit demo requirement): only auto-send THIS approval to
        WhatsApp immediately if no OTHER order-flow approval for this merchant is already pending AND
        already notified - i.e. no other message is currently awaiting the owner's reply. If one is,
        this approval is deliberately left unnotified (notify_channels/notifications_sent stay empty) -
        it still exists and is visible in Command Center - and ApprovalService.resolve() sends it,
        via notify_next_pending_approval, the moment the currently-outstanding one is resolved. This is
        what lets the owner reply a bare "APPROVE" every time instead of "APPROVE OR-XXXX": at most one
        approval is ever actually awaiting a reply at once."""
        outstanding = [
            a for a in self.store.list(Approval, merchant_id)
            if a.status == "pending" and a.action in self._ORDER_FLOW_APPROVAL_ACTIONS
            and a.id != approval.id and a.notifications_sent
        ]
        if outstanding:
            return
        self._auto_notify_whatsapp(merchant_id, approval, channel)

    def notify_next_pending_approval(self, merchant_id: str) -> None:
        """Called by ApprovalService.resolve() right after any approval is resolved - sends the
        OLDEST still-pending, not-yet-notified order-flow approval for this merchant, if any. Reads
        Order.channel_id fresh (never trusts a passed-in value) since the queued approval may belong
        to a different order than the one just resolved."""
        pending_unnotified = sorted(
            (
                a for a in self.store.list(Approval, merchant_id)
                if a.status == "pending" and a.action in self._ORDER_FLOW_APPROVAL_ACTIONS and not a.notifications_sent
            ),
            key=lambda a: a.sync.observed_at,
        )
        if not pending_unnotified:
            return
        next_approval = pending_unnotified[0]
        if next_approval.action == "channel_operation_correction":
            from sanocea.packages.domain_contract.models import ChannelOperation

            channel = self.store.get(ChannelOperation, merchant_id, next_approval.object_id).channel
        else:
            channel = self.store.get(Order, merchant_id, next_approval.object_id).channel_id
        self._auto_notify_whatsapp(merchant_id, next_approval, channel)

    def _auto_notify_whatsapp(self, merchant_id: str, approval: Approval, channel: str) -> None:
        """Closes the real gap found live in the Mariyal/Premium Basket rehearsal: the certified
        WhatsApp transport (packages/notifications) only ever SENT when an operator clicked "Send
        Approval to WhatsApp" in Command Center - the real order->exception->approval chain above was
        fully automatic, but the human-in-the-loop notification step was not, contradicting Priority 4's
        own requirement ("...requests owner approval...sends that approval to WhatsApp" as one
        continuous automatic sequence, not an operator action in between). This reuses the most recent
        non-expired DemoSessionContact already on file for this merchant (set once, earlier, via the
        existing Command Center form/API - never fabricated or guessed here) - if none exists yet, this
        is a no-op and the approval still appears in Command Center for a manual send, so first-time
        setup is unaffected. Never allowed to fail the exception/approval creation itself - a WhatsApp
        transport error must not prevent the real Approval from existing."""
        try:
            contacts = [c for c in self.store.list(DemoSessionContact, merchant_id) if c.cleared_at is None and c.expires_at > now_utc()]
            if not contacts:
                return
            contact = max(contacts, key=lambda c: c.consented_at)
            from sanocea.packages.notifications import DemoApprovalNotificationService
            from sanocea.packages.notifications.transport import WhatsAppDemoTransport

            transport = WhatsAppDemoTransport(
                waha_base_url=os.environ.get("SANOCEA_WAHA_BASE_URL", "http://127.0.0.1:3000"),
                api_key=os.environ.get("SANOCEA_WAHA_API_KEY"),
            )
            merchant = self.store.get(Merchant, merchant_id, merchant_id)
            DemoApprovalNotificationService(self.store, transport).send_approval(
                merchant_id, approval.id, contact, merchant.display_name, channel,
            )
        except Exception as exc:  # noqa: BLE001 - notification failure must never break approval creation
            self.audit.record(
                merchant_id=merchant_id, actor="post_order", source="inventory_shortage", action="auto_whatsapp_notify_failed",
                object_type="Approval", object_id=approval.id, result="failed", error=str(exc),
            )

    def resume_inventory_shortage(self, merchant_id: str, approval: Approval) -> dict[str, Any]:
        """Called by ApprovalService.resolve() once an inventory-shortage Approval is approved. Re-reads
        CURRENT reservation state (never trusts the approval's own stored evidence as still-current truth
        - the same 'revalidate against canonical state at execution time' discipline execute_cancellation
        already uses) and fulfils exactly what is actually available right now, nothing more."""
        order = self.store.get(Order, merchant_id, approval.object_id)
        reservations = self._reservations_for_source(merchant_id, "order", order.id)
        quantities = {r.sku: r.quantity_reserved for r in reservations if r.quantity_reserved > 0}
        if not quantities:
            self.exceptions.create(
                merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT,
                message=f"Approved inventory-shortage resolution for order {order.order_number} but no reserved quantity remains to fulfil",
                object_id=order.id,
            )
            return {"fulfilled": False, "reason": "no_reserved_quantity"}
        return self._fulfil_available_quantities(merchant_id, order, quantities)

    def _fulfil_available_quantities(self, merchant_id: str, order: Order, quantities: dict[str, int]) -> dict[str, Any]:
        """The real external action + readback for a partial (or, for the auto-ALLOW path, full)
        fulfilment: a real Shopify fulfillmentCreate for exactly the given per-sku quantities (never more
        than what's actually reserved), then a real readback of the resulting fulfillment state - the
        same 'external action -> read the external state back -> reconcile' shape every other certified
        flow in this codebase uses."""
        external_order_id = next((r.external_id for r in order.external_refs if r.entity_type == "order"), None)
        if not external_order_id:
            self.exceptions.create(
                merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN,
                message=f"Order {order.order_number} has no external order reference - cannot fulfil on the real channel",
                object_id=order.id,
            )
            return {"fulfilled": False, "reason": "no_external_ref"}
        connector = self.storefront(merchant_id)
        idempotency_key = f"partial_fulfil:{order.id}:{'-'.join(sorted(quantities))}"
        try:
            result = connector.execute_mutation(MutationRequest(
                merchant_id=merchant_id, action="create_fulfilment", object_type="Order",
                payload={"external_order_id": external_order_id, "quantities": quantities},
                idempotency_key=idempotency_key,
            ))
        except Exception as exc:  # noqa: BLE001 - a real, external connector failure must be recorded, never silently swallowed
            self.exceptions.create(
                merchant_id=merchant_id, category=ExceptionCategory.CONNECTOR_5XX,
                message=f"Fulfilment mutation failed for order {order.order_number}: {exc}", object_id=order.id,
            )
            self.audit.record(
                merchant_id=merchant_id, actor="post_order", source="inventory_shortage", action="inventory_shortage_fulfilment_failed",
                object_type="Order", object_id=order.id, result="failed", error=str(exc),
            )
            return {"fulfilled": False, "reason": "connector_error", "error": str(exc)}
        readback = connector.fetch(merchant_id, "order", external_order_id)
        order_lines = [l for l in self.store.list(OrderLine, merchant_id) if l.order_id == order.id]
        for line in order_lines:
            if line.sku in quantities:
                fully_covered = quantities[line.sku] >= line.quantity
                line.fulfillment_state = "fulfilled" if fully_covered else "partial"
                self.store.put(line)
        order.fulfillment_status = "fulfilled" if all(l.fulfillment_state == "fulfilled" for l in order_lines) else "partial"
        self.store.put(order)
        self.audit.record(
            merchant_id=merchant_id, actor="post_order", source="inventory_shortage", action="inventory_shortage_fulfilled",
            object_type="Order", object_id=order.id, result="resolved",
            requested_mutation={"quantities": quantities}, evidence_ref=str(readback),
        )
        return {"fulfilled": True, "quantities": quantities, "mutation_result": result.payload, "readback": readback}

    def observe_inventory(self, merchant_id: str, sku: str, canonical_qty: int, external_qty: int, location: str | None = None) -> str:
        # Step 2 Part A/E/G: resolved once, here - never a bare "default" literal. The lookup/update
        # below was ALREADY correctly scoped to whatever `location` value it receives (Part E's
        # requirement), so resolving the default is the only change needed for this method.
        location = resolve_location_ref(self.store, merchant_id, location)
        status = "observed"
        if external_qty < 0:
            status = "divergent"
        elif canonical_qty != external_qty:
            status = "divergent"
        inventory_key = (merchant_id, sku, location)
        inventory = self._inventory_cache.get(inventory_key)
        if inventory is None:
            existing_inventory = [
                item
                for item in self.store.list(Inventory, merchant_id)
                if item.sku == sku and item.location_ref == location
            ]
            inventory = existing_inventory[-1] if existing_inventory else Inventory(merchant_id=merchant_id, sku=sku, location_ref=location, quantity=external_qty)
        inventory.quantity = external_qty
        # `available` is a strict derived/cache value (quantity - reserved), never the raw synced
        # quantity - 2026-09 fix for a real bug the OSS-pattern review surfaced: this used to reset
        # available to external_qty unconditionally, silently discarding whatever was currently
        # reserved (e.g. quantity=10, reserved=4 -> a sync reporting quantity=10 must leave ATS at 6,
        # not reset it to 10, or outstanding reservations become instantly oversellable again).
        inventory.available = max(external_qty - inventory.reserved, 0)
        inventory.status = status
        self.store.put(inventory)
        self._inventory_cache[inventory_key] = inventory
        # Channel identity derived from the injected connector, not hardcoded - a real multi-platform
        # bug found while wiring the WooCommerce platform-independence test (2026-09): this literal
        # used to say "shopify" regardless of which connector was actually configured.
        self.store.put(InventoryObservation(merchant_id=merchant_id, sku=sku, observed_quantity=external_qty, source=self.storefront(merchant_id).name, status=status))
        if status == "divergent":
            exc = self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.INVENTORY_CONFLICT,
                message=f"Inventory divergence sku={sku} canonical={canonical_qty} external={external_qty}",
                object_id=inventory.id,
                remediation_options=["refresh_inventory", "manual_stock_check"],
            )
            self._append_reconciliation(merchant_id, "inventory", sku, canonical_qty, external_qty, "divergent", exc.id)
            return "exception"
        self._append_reconciliation(merchant_id, "inventory", sku, canonical_qty, external_qty, "matched", None)
        return "matched"

    def monitor_fulfilment(self, merchant_id: str, order: Order, status: str, age_hours: int) -> str:
        """2026-09 correction: `canonical == "fulfilled"` (the storefront platform's own "this order has
        been fulfilled/shipped" signal - e.g. Shopify's order fulfillment_status - already ingested and
        canonicalized here via `_canonical_fulfilment_status`) is the authoritative inventory-CONSUME
        trigger, replacing the earlier `TrackingEvent.status == "DELIVERED"` choice. Reasoning: fulfilment
        (goods physically leave the merchant's warehouse) and delivery (goods physically reach the
        customer) are different real-world events, days apart; consuming on DELIVERED left `quantity`
        overstated as physical on-hand truth for the entire transit window, contaminating reconciliation,
        procurement, and RTO semantics downstream. Confirmed against Medusa's own documented behavior
        (OSS-first check, 2026-09): "the stock deduction happens when the fulfillment is created, not
        when the shipment status is marked as shipped" - i.e. at merchant-side fulfilment action, not at
        carrier delivery confirmation. This is also the SAME write that closes the previously-dead
        `order.fulfillment_status` field: `evaluate_cancellation`'s existing `if order.fulfillment_status:
        status = "denied"` check was already correct, it just had nothing to read - no new cancellation
        logic was needed, only actually populating the field it already checks.
        """
        canonical = self._canonical_fulfilment_status(status)
        self.store.put(FulfilmentObservation(merchant_id=merchant_id, order_id=order.id, source=self.storefront(merchant_id).name, status=canonical))
        if canonical == "fulfilled" and order.fulfillment_status != "fulfilled":
            order.fulfillment_status = "fulfilled"
            self.store.put(order)
            self._consume_order_fulfilment(merchant_id, order.id)
        thresholds = self.store.get_config(merchant_id).get("sla_thresholds", {})
        limit = int(thresholds.get("order_unfulfilled_hours", 24))
        if canonical in {"pending", "ready"} and age_hours > limit:
            self.exceptions.create(
                merchant_id=merchant_id,
                category=ExceptionCategory.FULFILMENT_DELAY,
                message=f"Order {order.order_number} fulfilment delayed {age_hours}h",
                object_id=order.id,
                remediation_options=["refresh_fulfilment", "contact_fulfilment_partner"],
            )
            return "exception"
        return "straight_through"

    def create_or_observe_shipment(self, merchant_id: str, order: Order, simulate: str | None = None) -> tuple[str, str | None]:
        shipment_key = (merchant_id, order.id)
        cached_shipment = self._shipment_by_order.get(shipment_key)
        if cached_shipment:
            return "existing", self.logistics.shipments_by_order.get(order.id)
        if order.id in self.logistics.shipments_by_order:
            existing_shipments = [shipment for shipment in self.store.list(Shipment, merchant_id) if shipment.order_id == order.id]
            if existing_shipments:
                self._shipment_by_order[shipment_key] = existing_shipments[-1]
            return "existing", self.logistics.shipments_by_order.get(order.id)
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=self.logistics.name,
            action="create_shipment",
            object_type="Order",
            object_id=order.id,
            payload={"order_id": order.id} | ({"simulate": simulate} if simulate else {}),
            idempotency_key=f"shipment:{order.id}",
            policy_decision="ALLOW",
            status="approved",
        )
        self.store.put(command)
        try:
            result = self.logistics.execute_mutation(
                MutationRequest(
                    merchant_id=merchant_id,
                    action="create_shipment",
                    object_type="Order",
                    payload=command.payload,
                    idempotency_key=command.idempotency_key,
                )
            )
        except TimeoutError:
            existing = self.logistics.shipments_by_order.get(order.id)
            if existing:
                command.status = "succeeded"
                command.external_ref = existing
                self.store.put(command)
                return "auto_remediated_uncertain", existing
            command.status = "uncertain"
            self.store.put(command)
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message="Shipment mutation uncertain", object_id=order.id)
            return "uncertain", None
        except RuntimeError as exc:
            command.status = "failed"
            self.store.put(command)
            category = ExceptionCategory.CONNECTOR_RATE_LIMITED if "429" in str(exc) else ExceptionCategory.CONNECTOR_5XX
            self.exceptions.create(merchant_id=merchant_id, category=category, message=str(exc), object_id=order.id)
            return "failed", None
        command.status = "succeeded"
        command.external_ref = result.external_ref
        command.result = result.model_dump(mode="json")
        self.store.put(command)
        external = result.payload
        shipment = Shipment(
            merchant_id=merchant_id,
            order_id=order.id,
            carrier=external["carrier"],
            tracking_number=external["tracking_number"],
            status=external["status"],
        )
        self.store.put(shipment)
        self._shipment_by_order[shipment_key] = shipment
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id,
                sanocea_entity_type="Shipment",
                sanocea_id=shipment.id,
                external_system=self.logistics.name,
                external_entity_type="shipment",
                external_id=str(result.external_ref),
            )
        )
        return "created", result.external_ref

    def ingest_tracking(self, merchant_id: str, shipment_ref: str) -> str:
        external = self.logistics.fetch(merchant_id, "tracking", shipment_ref)
        mapping = self.store.get_external_mapping(merchant_id, self.logistics.name, "shipment", shipment_ref)
        if not mapping:
            self.exceptions.create(merchant_id=merchant_id, category="unknown_tracking_reference", message=f"Unknown tracking ref {shipment_ref}", object_id=None)
            return "exception"
        shipment = self.store.get(Shipment, merchant_id, mapping.sanocea_id)
        sequence_key = (merchant_id, shipment.id)
        latest_sequence = self._tracking_sequence.get(sequence_key, 0)
        result = "observed"
        for event in external.get("events", []):
            sequence = int(event.get("sequence", 0))
            if sequence < latest_sequence:
                self.audit.record(merchant_id=merchant_id, actor="logistics", source=self.logistics.name, action="stale_tracking_event_ignored", object_type="Shipment", object_id=shipment.id, result="ignored")
                continue
            tracking = TrackingEvent(
                merchant_id=merchant_id,
                shipment_id=shipment.id,
                carrier_code=external["carrier"],
                description=event["description"],
                occurred_at=datetime.fromisoformat(event["occurred_at"]),
                status=event["status"],
                external_sequence=sequence,
            )
            try:
                self.store.put(tracking)
            except Exception:
                continue
            latest_sequence = max(latest_sequence, sequence)
            shipment.status = event["status"]
            self.store.put(shipment)
            self._tracking_sequence[sequence_key] = latest_sequence
            self.store.put(ShipmentObservation(merchant_id=merchant_id, order_id=shipment.order_id, source=self.logistics.name, status=shipment.status, tracking_number=shipment.tracking_number, last_tracking_at=tracking.occurred_at))
            if event["status"] == "NDR":
                self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.NDR_DETECTED, message=f"NDR detected for {shipment.tracking_number}", object_id=shipment.id, remediation_options=["reattempt_delivery", "contact_customer"])
                result = "ndr"
            elif event["status"] == "RTO_DELIVERED":
                # The RTO parcel has PHYSICALLY arrived back at the warehouse - distinct from mere RTO
                # detection/initiation below, which must NOT restock (the parcel could still be reversed,
                # lost, or genuinely delivered late). Checked before the generic "RTO" prefix branch since
                # this status also starts with "RTO".
                self._restock_order_rto(merchant_id, shipment.order_id, shipment.id)
                result = "rto_delivered"
            elif event["status"].startswith("RTO"):
                self.exceptions.create(merchant_id=merchant_id, category="rto_detected", message=f"RTO state {event['status']} for {shipment.tracking_number}", object_id=shipment.id, remediation_options=["inventory_reconcile", "refund_review"])
                result = "rto"
            elif event["status"] in {"DELIVERY_FAILED", "EXCEPTION"}:
                self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.SHIPMENT_DELAY, message=f"Delivery exception {event['status']}", object_id=shipment.id)
                result = "exception"
            # DELIVERED is deliberately NOT an inventory event (2026-09 correction) - it means the
            # customer received the parcel, a different real-world event from fulfilment (goods leaving
            # the warehouse), which is now consumed earlier, in `monitor_fulfilment`. DELIVERED remains
            # purely observational here (shipment.status/ShipmentObservation update above, unconditional).
        return result

    def _consume_order_fulfilment(self, merchant_id: str, order_id: str) -> None:
        """The authoritative fulfilment-CONSUMPTION trigger (corrected 2026-09): fires from
        `monitor_fulfilment` when the storefront platform's own canonical fulfilment status reaches
        "fulfilled" - the merchant-side dispatch/fulfilment action, not carrier delivery confirmation.
        Confirmed against Medusa's own documented behavior (OSS-first check): stock deduction happens
        when the fulfillment is created, not when the shipment is later marked delivered.

        Whole-order semantic, not per-line: `Shipment` has no per-SKU/line granularity in the current
        model (no ShipmentLine entity, and `shipments_by_order` assumes one shipment per order) - so
        consuming every reservation this order owns, in full, is the strongest correct semantic the
        model can safely support today. Do not attempt partial/split consumption until a real per-line
        fulfilment signal exists (a disclosed Step 1 limitation, not invented here).

        Idempotency relies entirely on `adjust_reservation_atomic`'s own clamp-to-remaining behavior
        (proven no-op on a second call), combined with `monitor_fulfilment`'s own
        `order.fulfillment_status != "fulfilled"` guard against redundant re-triggering on repeated polls.
        """
        for reservation in self._reservations_for_source(merchant_id, "order", order_id):
            self.store.adjust_reservation_atomic(merchant_id, reservation.id, mode="consume", amount=reservation.quantity_reserved)
        self.audit.record(merchant_id=merchant_id, actor="post_order", source="post_order", action="order_fulfilment_consumed", object_type="Order", object_id=order_id, result="fulfilled")

    def _restock_order_reservations(self, merchant_id: str, order_id: str, *, object_type: str, object_id: str, idempotency_prefix: str, action: str) -> None:
        """Shared by restockable-return and RTO_DELIVERED restock (Step 2 Part D). Restocks exactly what
        was actually CONSUMED (`reservation.quantity_consumed`), never the originally-requested/reserved
        amount, so an order that was never actually dispatched (nothing consumed yet) correctly restocks
        nothing rather than inflating stock that was never removed.

        Step 2 Part D - LOCATION CORRECTNESS: restocks at `reservation.location_ref`, the location the
        goods actually consumed FROM - never a resolved/hardcoded merchant-default location. An order
        fulfilled from Surat must restock at Surat regardless of what a merchant's default location
        happens to be; a merchant with only one location is unaffected either way. Future return-to-a-
        different-location routing (Step 3+) is a deliberate, disclosed limitation, not implemented here
        - validated as a legitimate simplification by the Step 2 OSS check (Medusa itself treats return-
        destination as a separate, later routing decision a merchant can configure, not a day-one
        requirement).

        Default-restockable (no damage/condition disposition beyond `progress_return`'s own `restockable`
        parameter) - an accepted Step 1 limitation, not invented here. Idempotent per (flow, reservation)
        via `idempotency_prefix` (distinct namespaces for return-restock vs. RTO-restock - documented
        assumption: a single order's physical units are not expected to trigger both flows for the same
        consumed quantity, since Return and RTO are mutually exclusive real-world outcomes for one
        shipment; this is not separately enforced across flows).
        """
        for reservation in self._reservations_for_source(merchant_id, "order", order_id):
            if reservation.quantity_consumed <= 0:
                continue
            restock_key = f"{idempotency_prefix}:{reservation.id}"
            if any(c for c in self.store.list(ConnectorCommand, merchant_id) if c.action == "restock_inventory" and c.idempotency_key == restock_key):
                continue
            self.store.atomic_adjust_inventory(merchant_id, reservation.sku, reservation.location_ref, quantity_delta=reservation.quantity_consumed, available_delta=reservation.quantity_consumed)
            self._record_internal_command(merchant_id, "restock_inventory", object_type, object_id, {"sku": reservation.sku, "location": reservation.location_ref, "restocked": reservation.quantity_consumed}, restock_key)
        self.audit.record(merchant_id=merchant_id, actor="post_order", source="post_order", action=action, object_type=object_type, object_id=object_id, result="restocked")

    def _restock_order_rto(self, merchant_id: str, order_id: str, shipment_id: str) -> None:
        self._restock_order_reservations(
            merchant_id, order_id, object_type="Shipment", object_id=shipment_id,
            idempotency_prefix=f"restock_rto:{shipment_id}", action="rto_restocked",
        )

    def request_ndr_reattempt(self, merchant_id: str, shipment_ref: str) -> str:
        result = self._execute_logistics_command(
            merchant_id=merchant_id,
            action="request_ndr_action",
            object_type="Shipment",
            object_id=shipment_ref,
            payload={"shipment_ref": shipment_ref, "ndr_action": "REATTEMPT"},
            idempotency_key=f"ndr-reattempt:{shipment_ref}",
        )
        return "accepted" if result and result.status == "accepted" else "uncertain"

    def evaluate_cancellation(self, merchant_id: str, order: Order) -> Cancellation:
        existing = self._existing_for_order(Cancellation, merchant_id, order.id)
        if existing:
            return existing
        config = self.store.get_config(merchant_id)
        mode = config.get("cancellations", {}).get("before_fulfilment", "REQUIRE_APPROVAL")
        status = "eligible"
        approval_id = None
        if order.fulfillment_status:
            status = "denied"
        elif mode == "DENY":
            # Step 7A fix: previously an explicit DENY policy fell through neither branch below and
            # silently left status at the default "eligible" - the OPPOSITE of what a merchant
            # configuring DENY intends. A denied cancellation must never become executable and must
            # never even get an Approval created for it.
            status = "denied"
        elif mode == "REQUIRE_APPROVAL":
            approval = Approval(merchant_id=merchant_id, action="cancel_order", object_id=order.id, requested_by="policy")
            self.store.put(approval)
            approval_id = approval.id
            status = "approval_required"
        cancellation = Cancellation(merchant_id=merchant_id, order_id=order.id, status=status, reason="customer_request", approval_id=approval_id)
        self.store.put(cancellation)
        return cancellation

    def approve_cancellation(self, merchant_id: str, cancellation_id: str, approver_id: str) -> Cancellation:
        """Step 7A - closes the previously-incomplete cancellation-approval state machine, mirroring
        the EXISTING approve_refund/approve_purchase_order pattern exactly (take the domain object's own
        id directly, validate its own status, transition it, sync the linked Approval for evidence) -
        no generic ApprovalService exists anywhere in this codebase to reuse instead, and none is
        created here either (OSS-first check: pending-approval-then-execute is the standard shape for
        this kind of consequential action; the existing per-domain approve_X methods already implement
        it correctly, this simply extends the same shape to cancellation).

        Approval itself is pure AUTHORIZATION - it does not decide whether the cancellation is still
        business-executable (that revalidation against CURRENT canonical order state happens inside
        execute_cancellation, reused unchanged below, never duplicated here).
        """
        cancellation = self.store.get(Cancellation, merchant_id, cancellation_id)
        if cancellation.status == "approval_required":
            if cancellation.approval_id:
                approval = self.store.get(Approval, merchant_id, cancellation.approval_id)
                if approval.action != "cancel_order" or approval.object_id != cancellation.order_id:
                    # Failure case #7 - a linked Approval that does not actually correspond to this
                    # exact cancellation/order must never be trusted to authorize it.
                    self.exceptions.create(
                        merchant_id=merchant_id, category="cancellation_approval_mismatch",
                        message=f"Cancellation {cancellation.id}'s linked approval {approval.id} does not match (action={approval.action!r}, object_id={approval.object_id!r}) - refusing to approve",
                        object_id=cancellation.id, severity="error",
                    )
                    return cancellation
            else:
                approval = None
            # DB-atomic compare-and-swap, not a plain read-then-write: a concurrent execute_cancellation
            # triggered by another approval call racing this exact cancellation may already have
            # advanced status PAST "approval_required" (even all the way to "completed") by the time
            # this call reaches here - a blind write would silently REGRESS that progress. Whether or
            # not THIS call is the one that wins the transition, execute_cancellation below re-reads the
            # current state and handles every case idempotently, so it is always safe to fall through.
            if self.store.atomic_transition_cancellation_status(merchant_id, cancellation.id, {"approval_required"}, "approved"):
                if approval is not None and approval.status == "pending":
                    approval.status = "approved"
                    approval.decided_by = approver_id
                    approval.decided_at = now_utc()
                    self.store.put(approval)
                self.audit.record(merchant_id=merchant_id, actor=approver_id, source="post_order", action="cancellation_approved", object_type="Cancellation", object_id=cancellation.id, result="approved")
        elif cancellation.status != "approved":
            # Already rejected/completed/stale/eligible-without-ever-being-gated - never re-decide.
            return cancellation
        # Reuse the existing canonical execution path - it re-reads current order state and revalidates
        # (see execute_cancellation's stale-approval check) rather than trusting this approval alone.
        return self.execute_cancellation(merchant_id, cancellation.id)

    def reject_cancellation(self, merchant_id: str, cancellation_id: str, approver_id: str, reason: str | None = None) -> Cancellation:
        """On rejection: no order mutation, no reservation mutation, no refund/connector mutation - only
        the Cancellation and its linked Approval move to a terminal rejected/denied state. Idempotent:
        a second rejection call (or a rejection after someone already approved) is a no-op, never
        re-decided."""
        cancellation = self.store.get(Cancellation, merchant_id, cancellation_id)
        if cancellation.status != "approval_required":
            return cancellation
        # DB-atomic compare-and-swap (see approve_cancellation's docstring for the exact regression
        # race this prevents): a concurrent approve_cancellation call could have already advanced this
        # cancellation past "approval_required" by the time this rejection reaches here.
        if not self.store.atomic_transition_cancellation_status(merchant_id, cancellation.id, {"approval_required"}, "rejected"):
            return self.store.get(Cancellation, merchant_id, cancellation.id)
        if cancellation.approval_id:
            approval = self.store.get(Approval, merchant_id, cancellation.approval_id)
            if approval.action == "cancel_order" and approval.object_id == cancellation.order_id and approval.status == "pending":
                approval.status = "denied"
                approval.decided_by = approver_id
                approval.decided_at = now_utc()
                self.store.put(approval)
        cancellation = self.store.get(Cancellation, merchant_id, cancellation.id)
        self.audit.record(merchant_id=merchant_id, actor=approver_id, source="post_order", action="cancellation_rejected", object_type="Cancellation", object_id=cancellation.id, result="rejected", requested_mutation={"reason": reason} if reason else None)
        return cancellation

    def execute_cancellation(self, merchant_id: str, cancellation_id: str, simulate: str | None = None) -> Cancellation:
        cancellation = self.store.get(Cancellation, merchant_id, cancellation_id)
        if cancellation.status in {"completed", "external_confirmed", "stale_not_executable"}:
            return cancellation
        if cancellation.status not in {"eligible", "approved"}:
            return cancellation
        order = self.store.get(Order, merchant_id, cancellation.order_id)
        if order.fulfillment_status:
            # Step 7A - STALE APPROVAL: the order became fulfilled sometime between evaluation/approval
            # and this execution attempt. Approval only ever authorizes what was evaluated at request
            # time - it is not a standing license to cancel an order regardless of what happened since.
            # Revalidate against CURRENT canonical truth (the SAME signal evaluate_cancellation itself
            # already gates on) rather than trusting the earlier decision. No mutation, no reservation
            # touch, no connector call. DB-atomic CAS, not a blind write, for the same reason as every
            # other transition here.
            if self.store.atomic_transition_cancellation_status(merchant_id, cancellation.id, {"eligible", "approved"}, "stale_not_executable"):
                self.audit.record(merchant_id=merchant_id, actor="cancellation", source="post_order", action="cancellation_execution_not_allowed", object_type="Cancellation", object_id=cancellation.id, result="stale_not_executable")
            return self.store.get(Cancellation, merchant_id, cancellation.id)
        # Step 7A - CONCURRENT APPROVAL: two genuinely concurrent execute_cancellation calls for the
        # SAME cancellation (e.g. two operators approving at once) must produce exactly one logical
        # execution. This is the SAME atomic_transition_cancellation_status compare-and-swap used above
        # - only the caller that actually wins it proceeds past this point; every other caller gets
        # False and must not release reservations, call the logistics connector, or write a second
        # success audit record.
        claimed = self.store.atomic_transition_cancellation_status(merchant_id, cancellation.id, {"eligible", "approved"}, "completed")
        if not claimed:
            return self.store.get(Cancellation, merchant_id, cancellation.id)
        shipment_ref = self.logistics.shipments_by_order.get(order.id)
        if shipment_ref:
            result = self._execute_logistics_command(
                merchant_id=merchant_id,
                action="cancel_shipment",
                object_type="Cancellation",
                object_id=cancellation.id,
                payload={"shipment_ref": shipment_ref} | ({"simulate": simulate} if simulate else {}),
                idempotency_key=f"cancel:{order.id}",
            )
            if result is None:
                # Step 9 - UNKNOWN RESULT != FAILED RESULT: the completion CLAIM above already committed
                # status="completed" for correctness under concurrent claims (Step 7A's design), but the
                # shipment-cancel mutation itself is now of unknown outcome - establish authoritative
                # external truth via read-back before correcting that status, rather than blindly
                # collapsing both a genuine timeout AND a definitive connector rejection into the same
                # "mutation_uncertain" (that collapse was the exact defect Step 8's Part E trace found:
                # _execute_logistics_command already distinguishes "uncertain" vs "failed" one level
                # deeper on ConnectorCommand.status, but the caller discarded that distinction).
                command = self._latest_connector_command(merchant_id, "cancel_shipment", cancellation.id)
                verdict, external = self._cancellation_read_back(merchant_id, shipment_ref)
                return self._resolve_cancellation_uncertainty(merchant_id, cancellation, order, command, verdict, external, from_statuses={"completed"}, auto_retry=False)
        # atomic_transition_cancellation_status already persisted status="completed" for the winning
        # claim - re-fetch so this in-memory object reflects that (and so a subsequent local mutation
        # below is applied on top of the correct current row, not a stale pre-claim copy).
        cancellation = self.store.get(Cancellation, merchant_id, cancellation.id)
        order.status = "CANCELLED"
        self.store.put(order)
        # Reservation-lifecycle fix: reaching here means the order was NOT fulfilled at the stale check
        # above, so every reservation this order holds is still outstanding and must be RELEASED now -
        # never consumed, since the goods never left the building. `adjust_reservation_atomic` releases
        # exactly what this reservation actually owns (clamped to its own `quantity_reserved`, which may
        # be less than the order line's originally requested quantity if there was a shortfall at
        # reservation time, and clamped to zero if it was already consumed) and is safe to call again on
        # retry (idempotent via its own remaining-amount clamp).
        for reservation in self._reservations_for_source(merchant_id, "order", order.id):
            self.store.adjust_reservation_atomic(merchant_id, reservation.id, mode="release", amount=reservation.quantity_reserved)
            self.audit.record(merchant_id=merchant_id, actor="cancellation", source="post_order", action="inventory_reservation_released", object_type="Cancellation", object_id=cancellation.id, result="released")
        self.audit.record(merchant_id=merchant_id, actor="cancellation", source="post_order", action="cancellation_completed", object_type="Cancellation", object_id=cancellation.id, result="completed")
        return cancellation

    def evaluate_return(self, merchant_id: str, order: Order, reason: str) -> Return:
        existing = self._existing_for_order(Return, merchant_id, order.id)
        if existing:
            return existing
        config = self.store.get_config(merchant_id)
        return_days = int(config.get("returns", {}).get("window_days", 7))
        placed = order.placed_at or order.sync.observed_at
        eligible = placed > datetime.now(timezone.utc) - timedelta(days=return_days)
        status = "eligible" if eligible else "rejected"
        approval_id = None
        return_policy = config.get("returns", {})
        if eligible and return_policy.get("mode", "REQUIRE_APPROVAL") == "REQUIRE_APPROVAL" and not return_policy.get("auto_authorize", False):
            approval = Approval(merchant_id=merchant_id, action="create_return", object_id=order.id, requested_by="policy")
            self.store.put(approval)
            approval_id = approval.id
            status = "approval_required"
        if eligible and return_policy.get("auto_authorize", False) and not approval_id:
            status = "authorized"
        record = Return(merchant_id=merchant_id, order_id=order.id, status=status, reason=reason, eligibility="eligible" if eligible else "outside_window", approval_id=approval_id)
        self.store.put(record)
        return record

    def approve_return(self, merchant_id: str, order_id: str, approver_id: str) -> Return | None:
        """Real defect fixed here: evaluate_return creates an action="create_return" Approval when
        authority is required, but nothing previously transitioned the linked Return out of
        'approval_required' when that Approval was approved - it stayed stuck there indefinitely,
        identically to the cancel_order gap approve_cancellation already closes. Mirrors that method's
        shape (approval-is-pure-authorization, the Return's own status is what actually gates
        progress_return next)."""
        existing = self._existing_for_order(Return, merchant_id, order_id)
        if existing is None or existing.status != "approval_required":
            return existing
        existing.status = "authorized"
        self.store.put(existing)
        self.audit.record(
            merchant_id=merchant_id, actor=approver_id, source="post_order", action="return_approved",
            object_type="Return", object_id=existing.id, result="authorized",
        )
        return existing

    def progress_return(self, merchant_id: str, return_id: str, event: str, restockable: bool = True) -> Return:
        record = self.store.get(Return, merchant_id, return_id)
        if event == "pickup_requested":
            result = self._execute_logistics_command(
                merchant_id=merchant_id,
                action="request_return_pickup",
                object_type="Return",
                object_id=record.id,
                payload={"return_id": record.id, "order_id": record.order_id},
                idempotency_key=f"return-pickup:{record.id}",
            )
            if result is None:
                record.status = "mutation_uncertain"
                self.store.put(record)
                return record
        if event == "inspection_passed":
            # Reservation-lifecycle fix: acceptance and restockability are DISTINCT decisions - an
            # accepted return is not automatically sellable again (damaged/tampered/non-resalable goods
            # are accepted but never restocked). This is a pure physical-inventory RESTOCK
            # (quantity_delta=+N), never a reservation release: the original order's reservation was
            # already CONSUMED at fulfilment (permanently decremented), not left outstanding, so there is
            # nothing to release here - only new sellable quantity to add back.
            record.status = "accepted"
            record.restockable = restockable
            self.store.put(record)
            if restockable:
                self._restock_order_reservations(
                    merchant_id, record.order_id, object_type="Return", object_id=record.id,
                    idempotency_prefix=f"restock_return:{record.id}", action="inventory_restocked",
                )
            self.audit.record(merchant_id=merchant_id, actor="returns", source="post_order", action="return_inspection_passed", object_type="Return", object_id=record.id, result=record.status)
            # Step 7B - the Return -> Refund automatic trigger, fired from the SAME "accepted" transition
            # as the (independent, already-completed-above) restock decision - RESTOCKABLE != REFUNDABLE,
            # so this runs regardless of whether `restockable` was True or False. See
            # evaluate_return_refund's own docstring for the full eligibility/amount/idempotency story.
            self.evaluate_return_refund(merchant_id, record.id)
            return record
        transitions = {
            "authorize": "authorized",
            "pickup_requested": "pickup_requested",
            "picked_up": "in_transit",
            "received": "received",
            "inspection_failed": "rejected",
            "closed": "completed",
        }
        record.status = transitions.get(event, record.status)
        self.store.put(record)
        self.audit.record(merchant_id=merchant_id, actor="returns", source="post_order", action=f"return_{event}", object_type="Return", object_id=record.id, result=record.status)
        return record

    def evaluate_exchange(self, merchant_id: str, order: Order, requested_variant_sku: str, simulate: str | None = None, location: str | None = None) -> Exchange:
        existing = self._existing_for_order(Exchange, merchant_id, order.id)
        if existing:
            return existing
        # Step 2 Part A/B/G: resolved once, here - a fresh exchange reservation is a CREATION, exactly
        # like an order reservation, so it goes through the same resolver (explicit > merchant-configured
        # default > legacy "default"), never a hardcoded literal.
        location = resolve_location_ref(self.store, merchant_id, location)
        config = self.store.get_config(merchant_id)
        auto_reserve = config.get("exchanges", {}).get("auto_reserve", True)
        candidates = [i for i in self.store.list(Inventory, merchant_id) if i.sku == requested_variant_sku and i.location_ref == location]
        inv = candidates[-1] if candidates else None
        has_stock = inv is not None and (inv.quantity - inv.reserved) > 0
        status = "eligible" if has_stock else "escalated"
        if has_stock and auto_reserve:
            # 2026-09 reservation-lifecycle fix: routed through the same DB-atomic
            # `reserve_inventory_atomic` order reservations use - the old inline
            # read-available/mutate-in-Python/store.put(inv) here was exactly the check-then-update
            # oversell race Correction 1 forbids, just for exchange stock instead of order stock.
            reservation = self.store.reserve_inventory_atomic(
                merchant_id, requested_variant_sku, location,
                quantity_requested=1, source_type="exchange", source_id=order.id,
                idempotency_key=f"exchange-reserve:{order.id}:{requested_variant_sku}",
            )
            status = "reserved" if reservation.quantity_reserved > 0 else "escalated"
            if reservation.quantity_reserved > 0:
                self.audit.record(merchant_id=merchant_id, actor="exchange", source="post_order", action="exchange_inventory_reserved", object_type="Exchange", object_id=order.id, result="reserved")
        exchange = Exchange(merchant_id=merchant_id, order_id=order.id, requested_variant_sku=requested_variant_sku, status=status)
        self.store.put(exchange)
        if status == "escalated":
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.INVENTORY_CONFLICT, message=f"Exchange SKU unavailable: {requested_variant_sku}", object_id=order.id)
        return exchange

    def cancel_exchange(self, merchant_id: str, exchange_id: str) -> Exchange:
        """The missing counterpart to `evaluate_exchange`'s reservation - the reservation-lifecycle audit
        found no cancellation path existed for exchanges at all, so a cancelled/failed exchange's
        reserved unit was never released. Releases exactly what this exchange's own reservation owns
        (clamped by `adjust_reservation_atomic`), never more."""
        exchange = self.store.get(Exchange, merchant_id, exchange_id)
        if exchange.status in {"completed", "cancelled"}:
            return exchange
        for reservation in self._reservations_for_source(merchant_id, "exchange", exchange.order_id):
            self.store.adjust_reservation_atomic(merchant_id, reservation.id, mode="release", amount=reservation.quantity_reserved)
        exchange.status = "cancelled"
        self.store.put(exchange)
        self.audit.record(merchant_id=merchant_id, actor="exchange", source="post_order", action="exchange_cancelled", object_type="Exchange", object_id=exchange.id, result="cancelled")
        return exchange

    def complete_exchange(self, merchant_id: str, exchange_id: str) -> Exchange:
        exchange = self.store.get(Exchange, merchant_id, exchange_id)
        if exchange.status in {"eligible", "reserved"}:
            # Reservation-lifecycle fix: a completed exchange's reserved replacement unit has actually
            # shipped - it must be CONSUMED (permanently removed from `reserved` AND `quantity` together),
            # never just left "reserved" forever. Only reservations exist to consume when status was
            # "reserved" (auto_reserve was on and stock was found); an "eligible"-only completion (no
            # reservation was ever made) has nothing to consume, and the loop below is naturally a no-op
            # for it (_reservations_for_source finds nothing).
            for reservation in self._reservations_for_source(merchant_id, "exchange", exchange.order_id):
                self.store.adjust_reservation_atomic(merchant_id, reservation.id, mode="consume", amount=reservation.quantity_reserved)
            exchange.status = "completed"
        self.store.put(exchange)
        self.audit.record(merchant_id=merchant_id, actor="exchange", source="post_order", action="exchange_completed", object_type="Exchange", object_id=exchange.id, result=exchange.status)
        return exchange

    def evaluate_refund(self, merchant_id: str, order: Order, amount: int, *, return_id: str | None = None) -> Refund:
        """`return_id` (Step 7B): when set, this call is the Return -> Refund automatic trigger
        (see evaluate_return_refund). Ownership/idempotency for that path is by `return_id` alone (a
        DB-unique partial index, uq_refund_return_id - the real concurrency guarantee, not this
        application-level pre-check) rather than the legacy `(order_id, amount)` matching used for
        refunds requested directly (e.g. via the support/API path), which is preserved unchanged below.
        """
        if return_id is not None:
            existing_for_return = [r for r in self.store.list(Refund, merchant_id) if r.return_id == return_id]
            if existing_for_return:
                return existing_for_return[-1]
        else:
            existing = [
                refund
                for refund in self.store.list(Refund, merchant_id)
                if refund.order_id == order.id and refund.amount == min(amount, order.total_amount) and refund.return_id is None
            ]
            if existing:
                return existing[-1]
        config = self.store.get_config(merchant_id)
        decision = self._refund_decision(config, order, amount)
        # Step 7B fix: a genuine, found bug - DENY previously fell through to the SAME
        # status="approval_required" as REQUIRE_APPROVAL (the ternary only distinguished ALLOW from
        # "not ALLOW"), but no Approval object was created for it (the `if` below only fires for
        # REQUIRE_APPROVAL) - a denied refund was left permanently stuck in "approval_required" with
        # nothing that could ever approve it. DENY must be its own distinct, terminal, no-payment-
        # mutation state (mirrors the identical Step 7A fix already made for Cancellation's DENY policy).
        if decision == Decision.DENY:
            status = "denied"
        elif decision == Decision.REQUIRE_APPROVAL:
            status = "approval_required"
        else:
            status = "permitted"
        approval_id = None
        if decision == Decision.REQUIRE_APPROVAL:
            approval = Approval(merchant_id=merchant_id, action="refund", object_id=order.id, requested_by="policy")
            self.store.put(approval)
            approval_id = approval.id
        refund = Refund(merchant_id=merchant_id, order_id=order.id, return_id=return_id, amount=min(amount, order.total_amount), currency=order.currency, status=status, approval_id=approval_id)
        persisted = self.store.put(refund)
        return persisted

    def approve_refund(self, merchant_id: str, refund_id: str, approver_id: str) -> Refund:
        """Phase 4.5: approval identity is a real authenticated principal id (an api_keys.id, resolved
        by packages/authn), never free-text 'human'. Mirrors ProcurementService.approve_purchase_order
        for consistency across engines."""
        refund = self.store.get(Refund, merchant_id, refund_id)
        if refund.status != "approval_required":
            return refund
        refund.status = "approved"
        self.store.put(refund)
        if refund.approval_id:
            approval = self.store.get(Approval, merchant_id, refund.approval_id)
            if approval.status == "pending":
                approval.status = "approved"
                approval.decided_by = approver_id
                approval.decided_at = now_utc()
                self.store.put(approval)
        self.audit.record(merchant_id=merchant_id, actor=approver_id, source="post_order", action="refund_approved", object_type="Refund", object_id=refund.id, result="approved")
        return refund

    def execute_refund(self, merchant_id: str, refund_id: str, reason: str = "customer_refund", simulate: str | None = None) -> Refund:
        if self.payments is None:
            raise RuntimeError("payment connector required for refund execution")
        refund = self.store.get(Refund, merchant_id, refund_id)
        order = self.store.get(Order, merchant_id, refund.order_id)
        if refund.status not in {"permitted", "auto_approved", "approved", "reconciled", "completed"}:
            return refund
        if refund.status in {"reconciled", "completed"}:
            return refund
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=self.payments.name,
            action="create_refund",
            object_type="Refund",
            object_id=refund.id,
            payload={"order_id": order.id, "amount": refund.amount, "currency": refund.currency, "reason": reason} | ({"simulate": simulate} if simulate else {}),
            idempotency_key=f"refund:{order.id}:{refund.amount}:{refund.currency}:{reason}",
            policy_decision="ALLOW",
            status="approved",
        )
        self.store.put(command)
        refund.status = "mutation_submitted"
        self.store.put(refund)
        try:
            result = self.payments.execute_mutation(MutationRequest(merchant_id=merchant_id, action="create_refund", object_type="Refund", payload=command.payload, idempotency_key=command.idempotency_key))
        except TimeoutError:
            # Step 9 - UNKNOWN RESULT != FAILED RESULT: a timeout means the response was lost, not that
            # the mutation failed - establish authoritative provider truth before touching refund.status
            # again, never leave it collapsed at the transient "mutation_submitted" write above.
            command.status = "uncertain"
            self.store.put(command)
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message="Refund mutation timed out - resolving via provider read-back", object_id=refund.id)
            verdict, external = self._refund_read_back(merchant_id, order, refund, reason)
            return self._resolve_refund_uncertainty(merchant_id, refund, command, verdict, external, reason, auto_retry=False)
        except RuntimeError as exc:
            # Step 9 - a RuntimeError is the connector's own synchronous rejection (distinct from
            # TimeoutError's "connection disappeared" ambiguity), but this must still be CONFIRMED via
            # the same read-back rather than assumed - the connector's own contract determines whether
            # the mutation ran, not the exception type alone (see _refund_read_back's docstring). This is
            # what prevents a definitive rejection from masquerading as unresolved uncertainty: the
            # verdict below will resolve to CONFIRMED_NOT_APPLIED, not get stuck at "mutation_uncertain".
            command.status = "failed"
            self.store.put(command)
            category = ExceptionCategory.CONNECTOR_RATE_LIMITED if "429" in str(exc) else ExceptionCategory.CONNECTOR_5XX
            self.exceptions.create(merchant_id=merchant_id, category=category, message=str(exc), object_id=refund.id)
            verdict, external = self._refund_read_back(merchant_id, order, refund, reason)
            return self._resolve_refund_uncertainty(merchant_id, refund, command, verdict, external, reason, auto_retry=False)
        command.status = "succeeded"
        command.external_ref = result.external_ref
        command.result = result.model_dump(mode="json")
        self.store.put(command)
        refund.status = "external_confirmed"
        self.store.put(refund)
        self._register_refund_reference(merchant_id, refund.id, str(result.external_ref))
        return self.reconcile_refund(merchant_id, refund.id, str(result.external_ref))

    def evaluate_return_refund(self, merchant_id: str, return_id: str) -> Refund | None:
        """Step 7B - the Return -> Refund automatic trigger, closing the operational dead end Step 6
        found (an accepted/restocked return never automatically entered the refund workflow).

        REFUND-ELIGIBLE TRANSITION: `Return.status == "accepted"` (set by progress_return's
        "inspection_passed" branch) - the point where the merchant has physically inspected and ACCEPTED
        the return as legitimate, regardless of whether it is `restockable`. RESTOCKABLE != REFUNDABLE:
        a damaged, non-restockable return is still refund-eligible once accepted; inventory consequence
        (in progress_return, unchanged) and financial consequence (here) are two independent, parallel
        effects of the SAME "accepted" transition, never coupled to each other.

        Called synchronously from progress_return's "inspection_passed" branch (the automatic trigger),
        and is separately, safely callable again at any time afterward (a retry, or a second concurrent
        observation of the same transition) - both cases converge on exactly one Refund via
        evaluate_refund's `return_id`-keyed, DB-unique ownership (uq_refund_return_id), never a second
        one, and this method attempts no business logic of its own beyond amount derivation - policy,
        approval-gating, and execution are entirely the EXISTING evaluate_refund/execute_refund methods,
        reused unchanged.

        REPLAY/RETRY (failure-injection): this Return's OWNERSHIP of an existing Refund (via `return_id`)
        is checked FIRST, before any capacity claim - a genuine bug found while testing this: naively
        recomputing "already refunded across the whole order" on every call would count THIS RETURN's OWN
        already-created refund as "already refunded", making a legitimate replay/retry (e.g. after a
        crash between Refund creation and execute_refund) incorrectly compute zero remaining capacity and
        silently do nothing, rather than resuming. Checking ownership first closes that crash window: a
        replay always finds and resumes its own Refund (attempting execute_refund again if it is still
        "permitted" and unexecuted), never re-derives a fresh amount for a return that already owns one.

        REFUND AMOUNT AUTHORITY: `Return` has no per-line/per-quantity representation anywhere in the
        canonical model (no ReturnLine entity exists) - a Return is a WHOLE-ORDER-level record. This
        method therefore refunds the order's remaining REFUNDABLE amount (order.total_amount minus the
        sum of every non-denied Refund already recorded for this order, floored at 0) - the authoritative
        payment/order truth, never a fabricated catalogue-price calculation - rather than inventing
        partial-return-quantity arithmetic the domain model does not support. This is a disclosed,
        honest limitation (see the Step 7B report), not a silent full-order-refund-as-if-it-were-partial.

        Step 7B.1 - CROSS-RETURN CAPACITY RACE (a real, reproduced bug: 19/20 bounded-harness trials
        over-refunded before this fix): TWO DISTINCT Returns on the SAME order, evaluated concurrently,
        used to both read the same pre-refund remaining balance via a plain, unlocked SELECT+SUM and
        both create a full-amount Refund - together exceeding the order's authoritative refundable
        amount. `atomic_claim_refund_capacity` closes this with a DB-locked (Order row, SELECT ... FOR
        UPDATE) claim: re-read the authoritative total, re-read every FINANCIALLY COMMITTED Refund
        (every status except "denied" - "mutation_uncertain" and "permitted"/"approval_required" all
        continue reserving capacity, since none of them proves money did NOT move or definitely never
        will), and atomically claim whatever remains for this exact return, or claim nothing.

        DENY is resolved BEFORE ever attempting a claim (and therefore never contends for the Order
        lock at all): the two DENY conditions relevant here - `order.payment_status != "paid"` and an
        `permitted_order_states` mismatch - are both amount-independent, so a genuinely-denied return's
        outcome can be determined without knowing the exact remaining capacity. The amount-dependent
        ALLOW-vs-REQUIRE_APPROVAL threshold decision runs AFTER a successful claim, correcting the
        claimed Refund's neutral "permitted" placeholder status if the threshold demands
        REQUIRE_APPROVAL - safe because, by construction, a refund that reaches the claim step can never
        actually resolve to DENY (that path was already handled above), so there is no window where a
        transiently-still-placeholder "permitted" row could be miscounted as capacity by a racing
        sibling claim and later turn out to have been DENY all along.
        """
        ret = self.store.get(Return, merchant_id, return_id)
        if ret.status != "accepted":
            return None
        existing = next((r for r in self.store.list(Refund, merchant_id) if r.return_id == return_id), None)
        if existing is not None:
            if existing.status == "permitted" and self.payments is not None:
                existing = self.execute_refund(merchant_id, existing.id)
            return existing

        order = self.store.get(Order, merchant_id, ret.order_id)
        config = self.store.get_config(merchant_id)
        refund_policy = config.get("refunds") or config.get("policy", {}).get("refund", {})
        permitted_states = refund_policy.get("permitted_order_states")
        if order.payment_status != "paid" or (permitted_states and order.status not in permitted_states):
            # Amount-independent DENY - resolved via the EXISTING, unchanged evaluate_refund/
            # _refund_decision path, never contending for the cross-return capacity lock at all (a
            # denied refund reserves no capacity, so there is nothing to atomically claim for it).
            return self.evaluate_refund(merchant_id, order, order.total_amount, return_id=return_id)

        claimed = self.store.atomic_claim_refund_capacity(merchant_id, order.id, return_id, order.currency)
        if claimed is None:
            # Item 12 - a prior refund (from an earlier return, or a direct request) already exhausted
            # this order's refundable amount. No new Refund is created for this return.
            return None
        refund = Refund.model_validate(claimed)
        if refund.return_id != return_id:
            # Defensive: should be unreachable given the `existing` check above already ruled this out,
            # but atomic_claim_refund_capacity's own uq_refund_return_id race-recovery path could in
            # principle hand back a DIFFERENT return's row if called with a stale return_id - never treat
            # someone else's refund as this call's own result.
            return None

        if refund.status == "permitted":
            # Claimed capacity can only ever resolve to ALLOW or REQUIRE_APPROVAL here (DENY was already
            # handled above, before any claim was attempted) - apply the SAME threshold logic
            # _refund_decision uses, using the merchant's actual claimed amount.
            automatic_limit = int(refund_policy.get("automatic_limit", 0))
            if refund.amount > automatic_limit:
                above = refund_policy.get("above_limit", "REQUIRE_APPROVAL")
                decision = Decision(above if above in Decision._value2member_map_ else "REQUIRE_APPROVAL")
                if decision == Decision.REQUIRE_APPROVAL:
                    approval = Approval(merchant_id=merchant_id, action="refund", object_id=order.id, requested_by="policy")
                    self.store.put(approval)
                    refund.status = "approval_required"
                    refund.approval_id = approval.id
                    refund = self.store.put(refund)
                elif decision == Decision.DENY:
                    # A merchant-configured `above_limit: "DENY"` - correct the claimed placeholder to
                    # its true terminal state; it stops reserving capacity for any FUTURE claim from
                    # this point on (this method's own "financially committed" definition already
                    # excludes "denied").
                    refund.status = "denied"
                    refund = self.store.put(refund)

        if refund.status == "permitted" and self.payments is not None:
            # ALLOW policy needs no human gate - the merchant's own policy already authorized this
            # amount, so the chain completes automatically through the EXISTING, unchanged
            # execute_refund path. REQUIRE_APPROVAL/denied refunds correctly stop here: an operator must
            # call the existing approve_refund entrypoint, or nothing further happens, respectively. If
            # no payment connector is configured on this service instance, execute_refund cannot run
            # (matches its own explicit guard) - the refund stays "permitted", a safe, valid state an
            # operator/later call can still execute once a connector is available.
            refund = self.execute_refund(merchant_id, refund.id)
        return refund

    def _register_refund_reference(self, merchant_id: str, refund_id: str, external_ref: str) -> None:
        """Phase 4.6: the moment a real gateway integration would hand back ITS OWN reference for this
        refund - recorded in external_id_mappings so Phase 3's settlement-entry reconciliation can
        resolve a refund settlement entry through a real external-identifier lookup instead of trusting
        Sanocea's internal refund_id directly off an incoming settlement payload (mirrors observe_payment
        registering the equivalent Order mapping in Phase 3.1)."""
        self.store.put_external_mapping(
            ExternalIdMapping(
                merchant_id=merchant_id,
                sanocea_entity_type="Refund",
                sanocea_id=refund_id,
                external_system=self.payments.name,
                external_entity_type="refund",
                external_id=external_ref,
            )
        )

    def reconcile_refund(self, merchant_id: str, refund_id: str, external_ref: str) -> Refund:
        refund = self.store.get(Refund, merchant_id, refund_id)
        external = self.payments.fetch(merchant_id, "refund", external_ref)
        mismatches = []
        if int(external["amount"]) != refund.amount:
            mismatches.append("amount")
        if external["currency"] != refund.currency:
            mismatches.append("currency")
        if external["status"] != "succeeded":
            mismatches.append("status")
        if mismatches:
            exc = self.exceptions.create(merchant_id=merchant_id, category="refund_reconciliation_mismatch", message=f"Refund mismatch: {', '.join(mismatches)}", object_id=refund.id)
            self._append_reconciliation(merchant_id, "refund", refund.id, refund.model_dump(mode="json"), external, "divergent", exc.id)
            return refund
        refund.status = "reconciled"
        self.store.put(refund)
        self._append_reconciliation(merchant_id, "refund", refund.id, refund.model_dump(mode="json"), external, "matched", None)
        refund.status = "completed"
        self.store.put(refund)
        return refund

    def _append_reconciliation(self, merchant_id: str, scope: str, key: str, canonical: Any, external: Any, result: str, exception_id: str | None) -> None:
        if hasattr(self.store, "append_reconciliation_result"):
            self.store.append_reconciliation_result(
                ReconciliationResult(
                    merchant_id=merchant_id,
                    scope={"scope": scope, "key": key},
                    canonical_ref={"value": canonical},
                    external_ref={"value": external},
                    result=result,
                    exception_id=exception_id,
                )
            )

    def _execute_logistics_command(
        self,
        merchant_id: str,
        action: str,
        object_type: str,
        object_id: str | None,
        payload: dict[str, Any],
        idempotency_key: str,
    ):
        existing = [
            command
            for command in self.store.list(ConnectorCommand, merchant_id)
            if command.idempotency_key == idempotency_key and command.action == action and command.status == "succeeded"
        ]
        if existing:
            external_ref = existing[-1].external_ref
            payload = self.logistics.fetch(merchant_id, "shipment", external_ref) if external_ref and external_ref.startswith("simship-") else {"external_ref": external_ref}
            from sanocea.packages.connector_sdk import MutationResult

            return MutationResult(status="accepted", external_ref=external_ref, payload=payload)
        command = ConnectorCommand(
            merchant_id=merchant_id,
            connector=self.logistics.name,
            action=action,
            object_type=object_type,
            object_id=object_id,
            payload=payload,
            idempotency_key=idempotency_key,
            policy_decision="ALLOW",
            status="approved",
        )
        self.store.put(command)
        try:
            result = self.logistics.execute_mutation(
                MutationRequest(
                    merchant_id=merchant_id,
                    action=action,
                    object_type=object_type,
                    payload=payload,
                    idempotency_key=idempotency_key,
                )
            )
        except TimeoutError:
            command.status = "uncertain"
            self.store.put(command)
            self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message=f"{action} mutation uncertain", object_id=object_id)
            return None
        except RuntimeError as exc:
            command.status = "failed"
            self.store.put(command)
            category = ExceptionCategory.CONNECTOR_RATE_LIMITED if "429" in str(exc) else ExceptionCategory.CONNECTOR_5XX
            self.exceptions.create(merchant_id=merchant_id, category=category, message=str(exc), object_id=object_id)
            return None
        command.status = "succeeded"
        command.external_ref = str(result.external_ref) if result.external_ref else None
        command.result = result.model_dump(mode="json")
        self.store.put(command)
        return result

    def _record_internal_command(self, merchant_id: str, action: str, object_type: str, object_id: str | None, payload: dict[str, Any], idempotency_key: str, external_ref: str | None = None) -> None:
        existing = [command for command in self.store.list(ConnectorCommand, merchant_id) if command.idempotency_key == idempotency_key and command.action == action]
        if existing:
            return
        self.store.put(
            ConnectorCommand(
                merchant_id=merchant_id,
                connector="sanocea_internal",
                action=action,
                object_type=object_type,
                object_id=object_id,
                payload=payload,
                idempotency_key=idempotency_key,
                policy_decision="ALLOW",
                status="succeeded",
                external_ref=external_ref,
            )
        )

    def _canonical_fulfilment_status(self, status: str | None) -> str:
        mapping = {
            None: "pending",
            "unfulfilled": "pending",
            "ready": "ready",
            "processing": "processing",
            "fulfilled": "fulfilled",
            "partial": "partially_fulfilled",
            "cancelled": "cancelled",
            "failed": "failed",
        }
        return mapping.get(status, "unknown")

    def _refund_decision(self, config: dict[str, Any], order: Order, amount: int) -> Decision:
        refund_policy = config.get("refunds") or config.get("policy", {}).get("refund", {})
        if order.payment_status != "paid":
            return Decision.DENY
        if amount <= 0 or amount > order.total_amount:
            return Decision.DENY
        permitted_states = refund_policy.get("permitted_order_states")
        if permitted_states and order.status not in permitted_states:
            return Decision.DENY
        automatic_limit = int(refund_policy.get("automatic_limit", 0))
        if amount <= automatic_limit:
            return Decision.ALLOW
        above = refund_policy.get("above_limit", "REQUIRE_APPROVAL")
        return Decision(above if above in Decision._value2member_map_ else "REQUIRE_APPROVAL")

    def _existing_for_order(self, model, merchant_id: str, order_id: str):
        matches = [item for item in self.store.list(model, merchant_id) if item.order_id == order_id]
        return matches[-1] if matches else None

    def _latest_connector_command(self, merchant_id: str, action: str, object_id: str) -> ConnectorCommand | None:
        matches = [c for c in self.store.list(ConnectorCommand, merchant_id) if c.action == action and c.object_id == object_id]
        return matches[-1] if matches else None

    # --- Step 9: consequential-mutation read-back / recovery (refund + cancellation only) --------------
    #
    # UNKNOWN RESULT != FAILED RESULT. A mutation whose external response was lost to a connector
    # TimeoutError/RuntimeError is never blindly retried and never silently assumed to have failed -
    # authoritative external truth is read back first, and only a CONFIRMED verdict (never a guess)
    # advances the canonical record. Both helper pairs below (refund/cancellation) are deliberately
    # separate, narrow, domain-specific primitives - not a generic connector-recovery abstraction - since
    # only these two operations were asked for and their read-back mechanisms differ (payments.find_refund
    # vs logistics.fetch("shipment", ...)).

    def _refund_read_back(self, merchant_id: str, order: Order, refund: Refund, reason: str) -> tuple[str, dict[str, Any] | None]:
        """Authoritative external truth for a refund whose local execution outcome is unknown (lost to a
        TimeoutError or RuntimeError). Returns (verdict, external) with verdict one of
        CONFIRMED_SUCCEEDED / CONFIRMED_NOT_APPLIED / STILL_UNKNOWN.

        For SimulatedPaymentConnector, find_refund is a synchronous, strongly-consistent lookup against
        state written (or not) entirely within the original _execute_mutation call - there is no
        eventual-consistency window, so "not found" is proof of CONFIRMED_NOT_APPLIED here, not a guess.
        A real provider connector with an actual settlement delay must not reuse this same
        not-found-means-not-applied inference without an equivalent guarantee of its own (see Step 9
        report - "real vs simulated evidence").
        """
        try:
            external = self.payments.find_refund(merchant_id, order.id, refund.amount, refund.currency, reason)
        except Exception:
            return "STILL_UNKNOWN", None
        return ("CONFIRMED_SUCCEEDED", external) if external else ("CONFIRMED_NOT_APPLIED", None)

    def _resolve_refund_uncertainty(
        self, merchant_id: str, refund: Refund, command: ConnectorCommand, verdict: str,
        external: dict[str, Any] | None, reason: str, *, auto_retry: bool,
    ) -> Refund:
        """Applies a refund read-back verdict from EITHER execute_refund's own inline exception handling
        OR the standalone recover_refund_mutation entrypoint - the ONE place this decision is made, so
        both converge on identical, idempotency-safe behavior. Every transition is the DB-atomic CAS
        (atomic_transition_refund_status), never a plain write - a losing/concurrent caller always gets
        back current truth rather than regressing a row someone else already resolved.
        """
        from_statuses = {"mutation_submitted", "mutation_uncertain"}
        if verdict == "CONFIRMED_SUCCEEDED":
            command.status = "succeeded"
            command.external_ref = external["external_ref"]
            self.store.put(command)
            if self.store.atomic_transition_refund_status(merchant_id, refund.id, from_statuses, "external_confirmed"):
                self._register_refund_reference(merchant_id, refund.id, str(external["external_ref"]))
                self.audit.record(merchant_id=merchant_id, actor="recovery", source="post_order", action="refund_mutation_confirmed_succeeded", object_type="Refund", object_id=refund.id, result="external_confirmed")
                return self.reconcile_refund(merchant_id, refund.id, str(external["external_ref"]))
            return self.store.get(Refund, merchant_id, refund.id)
        if verdict == "CONFIRMED_NOT_APPLIED":
            command.status = "failed"
            self.store.put(command)
            if self.store.atomic_transition_refund_status(merchant_id, refund.id, from_statuses, "permitted"):
                self.audit.record(merchant_id=merchant_id, actor="recovery", source="post_order", action="refund_mutation_confirmed_not_applied", object_type="Refund", object_id=refund.id, result="permitted")
                if auto_retry:
                    return self.execute_refund(merchant_id, refund.id, reason=reason)
                return self.store.get(Refund, merchant_id, refund.id)
            return self.store.get(Refund, merchant_id, refund.id)
        # STILL_UNKNOWN - never retried, never marked failed/succeeded on a guess.
        command.status = "uncertain"
        self.store.put(command)
        self.store.atomic_transition_refund_status(merchant_id, refund.id, from_statuses, "mutation_uncertain")
        self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message="Refund mutation uncertain - provider read-back could not establish truth", object_id=refund.id)
        self.audit.record(merchant_id=merchant_id, actor="recovery", source="post_order", action="refund_mutation_still_unknown", object_type="Refund", object_id=refund.id, result="mutation_uncertain")
        return self.store.get(Refund, merchant_id, refund.id)

    def recover_refund_mutation(self, merchant_id: str, refund_id: str) -> Refund:
        """Step 9 - deliberate, out-of-band recovery for a refund stuck at "mutation_uncertain" (or the
        pre-resolution "mutation_submitted"). execute_refund's own inline exception handling already
        attempts this same read-back synchronously on every attempt (see below); this entrypoint exists
        for whenever that inline attempt itself came back STILL_UNKNOWN and a later, separate recovery
        pass (operator-triggered or scheduled) needs to try again. Unlike the inline path, this method
        auto-chains into execute_refund on a confirmed-not-applied verdict (a deliberately, separately
        invoked recovery call is the "controlled retry" itself - the inline path never auto-retries, to
        avoid immediately hammering back into e.g. a live rate limit).
        """
        refund = self.store.get(Refund, merchant_id, refund_id)
        if refund.status not in {"mutation_uncertain", "mutation_submitted"}:
            return refund
        order = self.store.get(Order, merchant_id, refund.order_id)
        command = self._latest_connector_command(merchant_id, "create_refund", refund.id)
        if command is None:
            # No persisted evidence of what was even attempted - cannot safely reconstruct the read-back
            # inputs (reason), so this must remain unknown rather than guessing.
            return refund
        reason = command.payload.get("reason", "customer_refund")
        verdict, external = self._refund_read_back(merchant_id, order, refund, reason)
        return self._resolve_refund_uncertainty(merchant_id, refund, command, verdict, external, reason, auto_retry=True)

    def _cancellation_read_back(self, merchant_id: str, shipment_ref: str) -> tuple[str, dict[str, Any] | None]:
        """Authoritative external truth for a cancellation shipment-cancel mutation whose local outcome
        is unknown. Looks for an actual CANCELLED event in the shipment's event HISTORY, not merely
        today's top-level `status` (a later, unrelated event could have overwritten that) - do not
        convert "not currently showing cancelled" into proof the mutation failed unless the connector's
        own history genuinely lacks a CANCELLED event.

        For SimulatedLogisticsConnector, fetch("shipment", ...) is a synchronous, strongly-consistent
        read against state written (or not) entirely within the original _execute_mutation call - no
        eventual-consistency window, so an absent CANCELLED event is proof of CONFIRMED_NOT_APPLIED here,
        not a guess. See Step 9 report - "real vs simulated evidence" for the same caveat as refund.
        """
        try:
            shipment = self.logistics.fetch(merchant_id, "shipment", shipment_ref)
        except Exception:
            return "STILL_UNKNOWN", None
        if any(event.get("status") == "CANCELLED" for event in shipment.get("events", [])):
            return "CONFIRMED_SUCCEEDED", shipment
        return "CONFIRMED_NOT_APPLIED", shipment

    def _resolve_cancellation_uncertainty(
        self, merchant_id: str, cancellation: Cancellation, order: Order, command: ConnectorCommand | None,
        verdict: str, external: dict[str, Any] | None, *, from_statuses: set[str], auto_retry: bool,
    ) -> Cancellation:
        """Applies a cancellation read-back verdict from EITHER execute_cancellation's own inline
        exception handling OR the standalone recover_cancellation_mutation entrypoint - the ONE place
        this decision is made. `from_statuses` differs by caller: the inline path is correcting a
        completion CLAIM already committed as "completed" before the logistics call was attempted (Step
        7A's design - see execute_cancellation), so it CASes FROM {"completed"}; the standalone recovery
        entrypoint runs later, once the row is already persisted at "mutation_uncertain", so it CASes
        FROM {"mutation_uncertain"}. Every transition is the DB-atomic CAS
        (atomic_transition_cancellation_status), never a plain write.
        """
        if verdict == "CONFIRMED_SUCCEEDED":
            if command is not None:
                command.status = "succeeded"
                if external is not None and external.get("external_ref"):
                    command.external_ref = str(external["external_ref"])
                self.store.put(command)
            if self.store.atomic_transition_cancellation_status(merchant_id, cancellation.id, from_statuses, "completed"):
                cancellation = self.store.get(Cancellation, merchant_id, cancellation.id)
                order.status = "CANCELLED"
                self.store.put(order)
                for reservation in self._reservations_for_source(merchant_id, "order", order.id):
                    self.store.adjust_reservation_atomic(merchant_id, reservation.id, mode="release", amount=reservation.quantity_reserved)
                    self.audit.record(merchant_id=merchant_id, actor="recovery", source="post_order", action="inventory_reservation_released", object_type="Cancellation", object_id=cancellation.id, result="released")
                self.audit.record(merchant_id=merchant_id, actor="recovery", source="post_order", action="cancellation_mutation_confirmed_succeeded", object_type="Cancellation", object_id=cancellation.id, result="completed")
            return self.store.get(Cancellation, merchant_id, cancellation.id)
        if verdict == "CONFIRMED_NOT_APPLIED":
            if command is not None:
                command.status = "failed"
                self.store.put(command)
            if self.store.atomic_transition_cancellation_status(merchant_id, cancellation.id, from_statuses, "approved"):
                self.audit.record(merchant_id=merchant_id, actor="recovery", source="post_order", action="cancellation_mutation_confirmed_not_applied", object_type="Cancellation", object_id=cancellation.id, result="approved")
                if auto_retry:
                    return self.execute_cancellation(merchant_id, cancellation.id)
                return self.store.get(Cancellation, merchant_id, cancellation.id)
            return self.store.get(Cancellation, merchant_id, cancellation.id)
        # STILL_UNKNOWN
        self.store.atomic_transition_cancellation_status(merchant_id, cancellation.id, from_statuses, "mutation_uncertain")
        self.exceptions.create(merchant_id=merchant_id, category=ExceptionCategory.EXTERNAL_MUTATION_UNCERTAIN, message="Cancellation mutation uncertain - provider read-back could not establish truth", object_id=cancellation.id)
        self.audit.record(merchant_id=merchant_id, actor="recovery", source="post_order", action="cancellation_mutation_still_unknown", object_type="Cancellation", object_id=cancellation.id, result="mutation_uncertain")
        return self.store.get(Cancellation, merchant_id, cancellation.id)

    def recover_cancellation_mutation(self, merchant_id: str, cancellation_id: str) -> Cancellation:
        """Step 9 - deliberate, out-of-band recovery for a cancellation stuck at "mutation_uncertain".
        execute_cancellation's own inline handling already attempts this same read-back synchronously
        (see below); this entrypoint is for whenever that came back STILL_UNKNOWN and a later, separate
        pass needs to try again. Auto-chains into execute_cancellation on a confirmed-not-applied verdict
        (see recover_refund_mutation's docstring for why this differs from the inline path)."""
        cancellation = self.store.get(Cancellation, merchant_id, cancellation_id)
        if cancellation.status != "mutation_uncertain":
            return cancellation
        order = self.store.get(Order, merchant_id, cancellation.order_id)
        command = self._latest_connector_command(merchant_id, "cancel_shipment", cancellation.id)
        shipment_ref = command.payload.get("shipment_ref") if command else None
        if not shipment_ref:
            return cancellation
        verdict, external = self._cancellation_read_back(merchant_id, shipment_ref)
        return self._resolve_cancellation_uncertainty(merchant_id, cancellation, order, command, verdict, external, from_statuses={"mutation_uncertain"}, auto_retry=True)
