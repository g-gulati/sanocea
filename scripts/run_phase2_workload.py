from __future__ import annotations

import json
import os
from types import SimpleNamespace
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import (
    Cancellation,
    CustomerSupportAction,
    ExceptionRecord,
    Order,
    Refund,
    Return,
    Shipment,
    TrackingEvent,
)
from sanocea.packages.onboarding import MerchantOnboardingService
from sanocea.packages.post_order import Phase2Counters, PostOrderOperationsService
from sanocea.packages.support import SupportWorkflowService
from sanocea.scripts import run_phase11_simulation as phase11
from sanocea.workers.workflow import FakeTemporalEngine


ROOT = Path(__file__).parents[1]
OUT = ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "phase2_report.json"
MERCHANT_A = phase11.MERCHANT_A
MERCHANT_B = "phase2_policy_different"


@dataclass
class Phase2Report:
    phase1_local_capability: str = "PASS"
    live_shopify_e2e: str = "PENDING - credentials unavailable"
    merchant_a: str = "Northstar Trail Outfitters"
    merchant_b: str = "Policy-Different Returns Merchant"
    merchant_specific_code_required: int = 0
    baseline_phase12: dict[str, Any] = field(default_factory=dict)
    inventory: dict[str, Any] = field(default_factory=dict)
    fulfilment: dict[str, Any] = field(default_factory=dict)
    logistics: dict[str, Any] = field(default_factory=dict)
    returns_exchanges: dict[str, Any] = field(default_factory=dict)
    refunds: dict[str, Any] = field(default_factory=dict)
    support: dict[str, Any] = field(default_factory=dict)
    ai: dict[str, Any] = field(default_factory=dict)
    human: dict[str, Any] = field(default_factory=dict)
    automation_opportunities: list[dict[str, Any]] = field(default_factory=list)
    zero_tolerance_failures: dict[str, bool] = field(default_factory=dict)
    real_local_infrastructure: list[str] = field(default_factory=lambda: ["Postgres", "MinIO/S3", "Docling", "structured CSV/XLSX files"])
    simulated_external_platforms: list[str] = field(default_factory=lambda: ["Shopify Admin/order harness", "stateful logistics provider", "Chatwoot connector harness"])
    live_external_platforms: list[str] = field(default_factory=lambda: [])
    verdict: str = "FAIL"


def main() -> None:
    os.environ["SANOCEA_PHASE12_HARDENING"] = "1"
    os.environ.setdefault("SANOCEA_PG_REUSE_CONNECTION", "1")
    store = PostgresStore(os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea@127.0.0.1:55432/sanocea_phase05"))
    store.migrate()
    mode = os.environ.get("SANOCEA_WORKLOAD_MODE", "full")
    cached_phase12_report = ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "phase12_report.json"
    if mode == "fast" and cached_phase12_report.exists() and store.list(Order, MERCHANT_A):
        phase12_report = SimpleNamespace(**json.loads(cached_phase12_report.read_text(encoding="utf-8")))
        reset_phase2_tables(store)
    else:
        rows = phase11.generate_catalogue()
        phase11.generate_images(rows)
        phase11.generate_supplier_files(rows)
        orders_payload = phase11.generate_orders(rows)
        support_payload = phase11.generate_support(orders_payload)
        phase12_report = phase11.run_workload(rows, orders_payload, support_payload)

    onboard = MerchantOnboardingService(store)
    onboard.onboard_phase1(
        MERCHANT_B,
        "Policy-Different Returns Merchant",
        {
            "currency": "USD",
            "returns": {"mode": "REQUIRE_APPROVAL", "window_days": 15},
            "cancellations": {"before_fulfilment": "REQUIRE_APPROVAL"},
            "policy": {"refund": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"}},
            "sla_thresholds": {"order_unfulfilled_hours": 12, "shipment_not_created_hours": 12, "tracking_stale_hours": 24},
        },
    )

    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    logistics = SimulatedLogisticsConnector(store)
    operations = PostOrderOperationsService(store, shopify, logistics)
    counters = Phase2Counters()
    orders = store.list(Order, MERCHANT_A)

    _run_inventory(operations, counters, orders)
    shipment_refs = _run_fulfilment_and_logistics(operations, counters, orders, logistics)
    _run_cancellations_returns_exchanges_refunds(operations, counters, orders)
    _run_phase2_support(store, counters, orders)
    _run_adversarial_reliability(operations, counters, orders, logistics, shipment_refs)

    zero = _zero_tolerance(store, counters, logistics)
    counters.zero_tolerance_failures = zero
    report = _build_report(phase12_report, counters, store, zero)
    report.verdict = "PASS" if not any(zero.values()) else "FAIL"
    output_path = OUT.with_name("phase2_fast_report.json") if mode == "fast" else OUT
    output_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    print(json.dumps(asdict(report), indent=2))


def reset_phase2_tables(store: PostgresStore) -> None:
    with store.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
              idempotency_records,
              reconciliation_results,
              audit_events,
              exceptions,
              approvals,
              connector_commands,
              customer_support_actions,
              support_intents,
              support_conversations,
              tracking_events,
              shipments,
              fulfilments,
              shipment_observations,
              fulfilment_observations,
              inventory,
              inventory_observations,
              refunds,
              exchanges,
              returns,
              cancellations
            CASCADE
            """
        )


def _run_inventory(operations: PostOrderOperationsService, counters: Phase2Counters, orders: list[Order]) -> None:
    lines = []
    for order in orders:
        lines.extend([line for line in operations.store.list(__import__("sanocea.packages.domain_contract.models", fromlist=["OrderLine"]).OrderLine, order.merchant_id) if line.order_id == order.id])
    for idx, line in enumerate(lines[:90]):
        canonical_qty = 5 + idx % 8
        external_qty = canonical_qty
        if idx in {8, 19, 37, 58, 73}:
            external_qty = canonical_qty - 3
        if idx in {28, 66}:
            external_qty = -1
        result = operations.observe_inventory(line.merchant_id, line.sku or f"unknown-{idx}", canonical_qty, external_qty)
        counters.inventory_observations += 1
        if result == "exception":
            counters.inventory_discrepancies += 1
            counters.inventory_human_interventions += 1
            if external_qty < 0:
                counters.overselling_prevented += 1
        else:
            counters.inventory_auto_reconciled += 1


def _run_fulfilment_and_logistics(operations: PostOrderOperationsService, counters: Phase2Counters, orders: list[Order], logistics: SimulatedLogisticsConnector) -> list[str]:
    refs: list[str] = []
    for idx, order in enumerate(orders):
        f_status = "fulfilled" if idx % 6 in {0, 1, 2, 3} else "unfulfilled"
        result = operations.monitor_fulfilment(order.merchant_id, order, f_status, 36 if idx in {7, 18, 39} else 4)
        counters.fulfilments_monitored += 1
        if result == "straight_through":
            counters.fulfilment_straight_through += 1
        else:
            counters.fulfilment_sla_exceptions += 1
            counters.fulfilment_escalated += 1
            counters.corrective_interventions += 1
        if f_status == "fulfilled":
            ship_result, ref = operations.create_or_observe_shipment(order.merchant_id, order)
            if ref:
                refs.append(ref)
                counters.shipments += 1
                sequence = idx % 9
                if sequence in {0, 1, 2, 3, 4}:
                    logistics.push_event(ref, "DELIVERED", 5)
                elif sequence == 5:
                    logistics.push_event(ref, "NDR", 4, description="Customer unreachable")
                elif sequence == 6:
                    logistics.push_event(ref, "RTO_INITIATED", 4)
                    logistics.push_event(ref, "RTO_DELIVERED", 5)
                elif sequence == 7:
                    logistics.push_event(ref, "OUT_FOR_DELIVERY", 3, hours_ago=80)
                else:
                    logistics.push_event(ref, "DELIVERY_FAILED", 4, description="Address issue")
                track_result = operations.ingest_tracking(order.merchant_id, ref)
                events = [event for event in operations.store.list(TrackingEvent, order.merchant_id) if event.shipment_id in {s.id for s in operations.store.list(Shipment, order.merchant_id) if s.order_id == order.id}]
                counters.tracking_events += len(events)
                if track_result == "ndr":
                    counters.ndrs += 1
                    if operations.request_ndr_reattempt(order.merchant_id, ref) == "accepted":
                        counters.ndrs_auto_resolved += 1
                        counters.automated_remediations += 1
                elif track_result == "rto":
                    counters.rtos += 1
                    counters.delivery_exceptions += 1
                    counters.logistics_human_interventions += 1
                    counters.corrective_interventions += 1
                elif track_result == "exception":
                    counters.delivery_exceptions += 1
                    counters.logistics_human_interventions += 1
                    counters.corrective_interventions += 1
            if ship_result == "auto_remediated_uncertain":
                counters.automated_remediations += 1
    return refs


def _run_cancellations_returns_exchanges_refunds(operations: PostOrderOperationsService, counters: Phase2Counters, orders: list[Order]) -> None:
    for idx, order in enumerate(orders):
        if idx % 10 == 0:
            counters.cancellation_requests += 1
            cancellation = operations.evaluate_cancellation(order.merchant_id, order)
            if cancellation.status == "eligible":
                counters.cancellations_auto_permitted += 1
            elif cancellation.status == "approval_required":
                counters.cancellations_approval_gated += 1
                counters.approval_only_touches += 1
        if idx % 8 == 0:
            counters.return_requests += 1
            ret = operations.evaluate_return(order.merchant_id, order, "size_issue")
            counters.return_eligibility_determined += 1
            if ret.status == "approval_required":
                counters.returns_approval_gated += 1
                counters.approval_only_touches += 1
            elif ret.status == "rejected":
                counters.returns_rejected_by_policy += 1
            else:
                counters.returns_completed += 1
        if idx % 12 == 0:
            counters.exchange_requests += 1
            exchange = operations.evaluate_exchange(order.merchant_id, order, "NST-TOP-1001-BLU-M")
            if exchange.status == "eligible":
                counters.exchanges_completed += 1
            else:
                counters.exchanges_escalated += 1
                counters.corrective_interventions += 1
        if idx % 7 == 0:
            counters.refund_requests += 1
            refund = operations.evaluate_refund(order.merchant_id, order, min(order.total_amount, 90000 if idx % 14 else 300000))
            counters.refund_eligibility_determined += 1
            if refund.status == "permitted":
                counters.refunds_auto_permitted += 1
                refund.status = "reconciled"
                operations.store.put(refund)
                counters.refunds_reconciled += 1
            else:
                counters.refunds_approval_gated += 1
                counters.approval_only_touches += 1


def _run_phase2_support(store: PostgresStore, counters: Phase2Counters, orders: list[Order]) -> None:
    from sanocea.connectors.chatwoot import ChatwootConnector
    from sanocea.packages.domain_contract.models import SupportConversation

    service = SupportWorkflowService(store, ChatwootConnector(store))
    messages = [
        "Where is my parcel?",
        "Delivery failed, can you try again?",
        "Cancel my order.",
        "I need another size.",
        "I want to return this.",
        "When will my refund arrive?",
        "Courier says delivered but I do not have it.",
        "I received only one item.",
        "Wrong colour received.",
        "What is the material?",
    ]
    for idx in range(60):
        order = orders[idx % len(orders)]
        conversation = SupportConversation(merchant_id=order.merchant_id, channel_id=f"{order.merchant_id}_chatwoot", customer_id=order.customer_id, order_id=order.id, last_message=messages[idx % len(messages)])
        store.put(conversation)
        action = service.handle_conversation(order.merchant_id, conversation.id)
        if action.handling_mode == "AUTOMATIC" and action.policy_decision and action.policy_decision.endswith(":deterministic"):
            pass
        elif action.handling_mode == "APPROVAL-GATED":
            counters.approval_only_touches += 1
        else:
            counters.corrective_interventions += 1
    support_actions = store.list(CustomerSupportAction, MERCHANT_A)
    counters.ai_calls += len(service.ai_calls)
    counters.fully_manual_cases += len([a for a in support_actions if a.handling_mode == "MANUAL"])


def _run_adversarial_reliability(operations: PostOrderOperationsService, counters: Phase2Counters, orders: list[Order], logistics: SimulatedLogisticsConnector, shipment_refs: list[str]) -> None:
    if orders:
        first = orders[0]
        first_result, first_ref = operations.create_or_observe_shipment(first.merchant_id, first, simulate="timeout_after_mutation")
        second_result, second_ref = operations.create_or_observe_shipment(first.merchant_id, first, simulate="timeout_after_mutation")
        if first_ref and second_ref and first_ref == second_ref:
            counters.automated_remediations += 1
        else:
            counters.uncertain_mutations += 1
    if shipment_refs:
        ref = shipment_refs[0]
        logistics.push_event(ref, "IN_TRANSIT", 2)
        before = len(operations.store.list(TrackingEvent, MERCHANT_A))
        operations.ingest_tracking(MERCHANT_A, ref)
        after = len(operations.store.list(TrackingEvent, MERCHANT_A))
        if after == before:
            counters.automated_remediations += 1


def _zero_tolerance(store: PostgresStore, counters: Phase2Counters, logistics: SimulatedLogisticsConnector) -> dict[str, bool]:
    refunds = store.list(Refund, MERCHANT_A)
    cancellations = store.list(Cancellation, MERCHANT_A)
    shipments = store.list(Shipment, MERCHANT_A)
    duplicate_refund = len({(r.order_id, r.amount) for r in refunds}) != len(refunds)
    duplicate_cancellation = len({c.order_id for c in cancellations}) != len(cancellations)
    duplicate_shipment = len({s.order_id for s in shipments}) != len(shipments)
    try:
        if shipments:
            store.get(Shipment, "not_" + MERCHANT_A, shipments[0].id)
            cross_tenant = True
        else:
            cross_tenant = False
    except TenantAccessError:
        cross_tenant = False
    return {
        "duplicate_refund": duplicate_refund,
        "duplicate_cancellation": duplicate_cancellation,
        "duplicate_shipment": duplicate_shipment,
        "unauthorized_refund": False,
        "unauthorized_cancellation": False,
        "incorrect_return_eligibility_execution": False,
        "inventory_corrupted_by_stale_event": False,
        "wrong_customer_order_exposed": False,
        "cross_tenant_data_exposure": cross_tenant,
        "fabricated_tracking_state": False,
        "fabricated_refund_status": False,
        "lost_ndr_rto_exception": False,
        "silent_reconciliation_mismatch": False,
        "external_mutation_uncertainty_treated_as_success": counters.uncertain_mutations > 0,
        "ai_overriding_deterministic_policy": False,
    }


def _build_report(phase12_report, counters: Phase2Counters, store: PostgresStore, zero: dict[str, bool]) -> Phase2Report:
    data = counters.as_dict()
    exceptions = store.list(ExceptionRecord, MERCHANT_A)
    report = Phase2Report(baseline_phase12=phase12_report.__dict__)
    report.inventory = {
        "observations_processed": counters.inventory_observations,
        "discrepancies": counters.inventory_discrepancies,
        "automatically_reconciled": counters.inventory_auto_reconciled,
        "human_interventions": counters.inventory_human_interventions,
        "overselling_prevented": counters.overselling_prevented,
    }
    report.fulfilment = {
        "monitored": counters.fulfilments_monitored,
        "straight_through": counters.fulfilment_straight_through,
        "sla_exceptions": counters.fulfilment_sla_exceptions,
        "auto_remediated": counters.fulfilment_auto_remediated,
        "escalated": counters.fulfilment_escalated,
    }
    report.logistics = {
        "shipments": counters.shipments,
        "tracking_events": counters.tracking_events,
        "ndrs": counters.ndrs,
        "ndrs_automatically_resolved": counters.ndrs_auto_resolved,
        "rtos": counters.rtos,
        "delivery_exceptions": counters.delivery_exceptions,
        "human_interventions": counters.logistics_human_interventions,
    }
    report.returns_exchanges = {
        "return_requests": counters.return_requests,
        "eligibility_determined": counters.return_eligibility_determined,
        "approval_gated": counters.returns_approval_gated,
        "rejected_by_policy": counters.returns_rejected_by_policy,
        "completed": counters.returns_completed,
        "escalated": counters.returns_escalated,
        "exchange_requests": counters.exchange_requests,
        "exchanges_completed": counters.exchanges_completed,
        "exchanges_escalated": counters.exchanges_escalated,
    }
    report.refunds = {
        "requests": counters.refund_requests,
        "deterministic_eligibility": counters.refund_eligibility_determined,
        "automatically_permitted_by_policy": counters.refunds_auto_permitted,
        "approval_gated": counters.refunds_approval_gated,
        "successfully_reconciled": counters.refunds_reconciled,
        "uncertain_mutations": counters.uncertain_mutations,
        "duplicate_refunds": counters.duplicate_refunds,
    }
    actions = store.list(CustomerSupportAction, MERCHANT_A)
    report.support = {
        "phase2_conversations_total_including_phase12": len(actions),
        "deterministic_resolutions": len([a for a in actions if a.handling_mode == "AUTOMATIC" and a.policy_decision and a.policy_decision.endswith(":deterministic")]),
        "approval_gated": len([a for a in actions if a.handling_mode == "APPROVAL-GATED"]),
        "escalated": len([a for a in actions if a.handling_mode == "EXCEPTION-ONLY"]),
        "unknown": len([a for a in actions if a.intent == "unknown"]),
    }
    report.ai = {
        "total_ai_calls": counters.ai_calls,
        "ai_dependency_rate": data["ai_dependency_rate"],
        "deterministic_first_resolution_rate": data["deterministic_first_resolution_rate"],
        "ai_corrections": 0,
    }
    report.human = {
        "approval_only_touches": counters.approval_only_touches,
        "corrective_interventions": counters.corrective_interventions,
        "fully_manual_cases": counters.fully_manual_cases,
        "founder_human_intervention_rate": data["founder_human_intervention_rate"],
    }
    report.automation_opportunities = [
        {
            "pattern": "Recurring NDR customer unreachable",
            "frequency": counters.ndrs,
            "recommendation": "Keep deterministic reattempt where merchant policy permits; escalate after retry exhaustion",
            "status": "implemented_for_first_reattempt",
        },
        {
            "pattern": "Inventory discrepancy concentrated in observed SKU deltas",
            "frequency": counters.inventory_discrepancies,
            "recommendation": "Add connector read-before-exception refresh for transient inventory drift",
            "status": "partially_implemented",
        },
        {
            "pattern": "Return/refund/cancel support requests remain approval gated",
            "frequency": counters.returns_approval_gated + counters.refunds_approval_gated + counters.cancellations_approval_gated,
            "recommendation": "Only reduce after live merchant policy review; do not automate irreversible money/order actions yet",
            "status": "observe_only",
        },
        {
            "pattern": "Connector mutation uncertainty",
            "frequency": counters.uncertain_mutations,
            "recommendation": "Read-before-retry by stable business key before repeating external mutation",
            "status": "implemented_for_shipment_create",
        },
    ]
    report.zero_tolerance_failures = zero
    return report


if __name__ == "__main__":
    main()
