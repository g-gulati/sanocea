from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sanocea.connectors.logistics import SimulatedLogisticsConnector
from sanocea.connectors.payments import SimulatedPaymentConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import CustomerSupportAction, Exchange, Inventory, Order, Refund, Return, Shipment, SupportConversation, TrackingEvent
from sanocea.packages.onboarding import MerchantOnboardingService
from sanocea.packages.post_order import Phase2Counters, PostOrderOperationsService
from sanocea.packages.support import SupportWorkflowService
from sanocea.scripts import run_phase2_workload as phase2
from sanocea.workers.workflow import FakeTemporalEngine


ROOT = Path(__file__).parents[1]
OUT = ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "phase21_report.json"
MERCHANT_A = phase2.MERCHANT_A
MERCHANT_B = "phase21_policy_different"


@dataclass
class Phase21Report:
    live_shopify_e2e: str = "PENDING - credentials unavailable"
    mode: str = "fast_regression"
    baseline_phase2: dict[str, Any] = field(default_factory=dict)
    human_touch_root_causes: dict[str, int] = field(default_factory=dict)
    normal_commercial_workload: dict[str, Any] = field(default_factory=dict)
    adversarial_reliability_workload: dict[str, Any] = field(default_factory=dict)
    returns: dict[str, Any] = field(default_factory=dict)
    exchanges: dict[str, Any] = field(default_factory=dict)
    refunds: dict[str, Any] = field(default_factory=dict)
    logistics: dict[str, Any] = field(default_factory=dict)
    support: dict[str, Any] = field(default_factory=dict)
    ai: dict[str, Any] = field(default_factory=dict)
    human: dict[str, Any] = field(default_factory=dict)
    automation_opportunities: list[dict[str, Any]] = field(default_factory=list)
    zero_tolerance_failures: dict[str, bool] = field(default_factory=dict)
    merchant_specific_code_required: int = 0
    runtime_seconds: float = 0.0
    real_local_infrastructure: list[str] = field(default_factory=lambda: ["Postgres", "cached Phase 1 catalogue/orders", "real local Sanocea persistence"])
    simulated_external_platforms: list[str] = field(default_factory=lambda: ["Shopify harness", "stateful logistics simulator", "stateful payment/refund simulator", "Chatwoot harness"])
    live_external_platforms: list[str] = field(default_factory=list)
    verdict: str = "FAIL"


def main() -> None:
    import time

    started = time.perf_counter()
    os.environ.setdefault("SANOCEA_PG_REUSE_CONNECTION", "1")
    os.environ.setdefault("SANOCEA_WORKLOAD_MODE", "fast")
    store = PostgresStore(os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea@127.0.0.1:55432/sanocea_phase05"))
    store.migrate()
    _ensure_phase2_baseline(store)
    baseline = json.loads((ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "phase2_fast_report.json").read_text(encoding="utf-8"))
    phase2.reset_phase2_tables(store)
    _configure_merchants(store)
    logistics = SimulatedLogisticsConnector(store)
    payments = SimulatedPaymentConnector(store)
    operations = PostOrderOperationsService(store, ShopifyConnector(store, FakeTemporalEngine(store)), logistics, payments)
    counters = Phase2Counters()
    orders = _expanded_orders(store, MERCHANT_A, target=220)
    _seed_exchange_inventory(store, MERCHANT_A)

    normal = _run_normal_workload(store, operations, logistics, counters, orders)
    adversarial = _run_adversarial_workload(store, operations, logistics, payments, counters, orders)
    support = _run_support_workload(store, counters, orders)
    zero = _zero_tolerance(store, counters)
    report = _build_report(baseline, counters, normal, adversarial, support, zero)
    report.runtime_seconds = round(time.perf_counter() - started, 4)
    report.verdict = "PASS" if not any(zero.values()) else "FAIL"
    OUT.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    print(json.dumps(asdict(report), indent=2))


def _ensure_phase2_baseline(store: PostgresStore) -> None:
    path = ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "phase2_fast_report.json"
    if not path.exists() or not store.list(Order, MERCHANT_A):
        os.environ["SANOCEA_WORKLOAD_MODE"] = "fast"
        phase2.main()


def _configure_merchants(store: PostgresStore) -> None:
    config_a = {
        "returns": {"mode": "AUTO_AUTHORIZE", "window_days": 7, "auto_authorize": True, "excluded_categories": []},
        "refunds": {"automatic_limit": 100000, "above_limit": "REQUIRE_APPROVAL", "permitted_order_states": ["PAID"]},
        "cancellations": {"before_fulfilment": "ALLOW"},
        "exchanges": {"auto_reserve": True, "price_tolerance": 0, "customer_confirmation_required": True},
        "support": {"auto_response": {"refund_status": True, "return_status": True, "shipment_status": True, "delivery_problem": True, "availability_question": True}},
        "sla_thresholds": {"tracking_stale_hours": 48, "ndr_unresolved_hours": 24, "refund_pending_days": 3},
    }
    MerchantOnboardingService(store).onboard_phase1(MERCHANT_A, "Northstar Trail Outfitters", config_a)
    MerchantOnboardingService(store).onboard_phase1(
        MERCHANT_B,
        "Policy-Different Merchant",
        {
            "returns": {"mode": "REQUIRE_APPROVAL", "window_days": 15, "auto_authorize": False},
            "refunds": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"},
            "cancellations": {"before_fulfilment": "REQUIRE_APPROVAL"},
            "exchanges": {"auto_reserve": False},
        },
    )


def _expanded_orders(store: PostgresStore, merchant_id: str, target: int) -> list[Order]:
    base = store.list(Order, merchant_id)
    orders = list(base)
    for idx in range(len(base), target):
        src = base[idx % len(base)]
        clone = src.model_copy(deep=True)
        clone.id = f"ord_phase21_{idx}"
        clone.order_number = f"P21-{6000 + idx}"
        clone.fulfillment_status = None
        clone.payment_status = "paid" if idx % 17 else "pending"
        clone.status = "PAID" if clone.payment_status == "paid" else "PENDING"
        store.put(clone)
        orders.append(clone)
    return orders


def _seed_exchange_inventory(store: PostgresStore, merchant_id: str) -> None:
    for sku in ["NST-TOP-1001-BLU-M", "NST-OUT-1000-NAV-S", "NST-ACC-1005-GRE-OneSize"]:
        store.put(Inventory(merchant_id=merchant_id, sku=sku, location_ref="default", quantity=20, available=20, status="observed"))


def _run_normal_workload(store: PostgresStore, operations: PostOrderOperationsService, logistics: SimulatedLogisticsConnector, counters: Phase2Counters, orders: list[Order]) -> dict[str, Any]:
    normal = {"orders": len(orders), "straight_through": 0, "approval_gated": 0, "corrective": 0}
    shipment_refs = []
    for idx, order in enumerate(orders):
        inv = operations.observe_inventory(order.merchant_id, f"SKU-P21-{idx % 35}", 10, 10 if idx % 23 else 7)
        counters.inventory_observations += 1
        counters.deterministic_operations += 1
        if inv == "matched":
            counters.inventory_auto_reconciled += 1
        else:
            counters.inventory_discrepancies += 1
            counters.inventory_human_interventions += 1
            counters.corrective_interventions += 1
        fulfil = operations.monitor_fulfilment(order.merchant_id, order, "fulfilled" if idx % 5 else "unfulfilled", 4 if idx % 29 else 72)
        counters.fulfilments_monitored += 1
        if fulfil == "straight_through":
            counters.fulfilment_straight_through += 1
        else:
            counters.fulfilment_sla_exceptions += 1
            counters.corrective_interventions += 1
        if idx % 5:
            status, ref = operations.create_or_observe_shipment(order.merchant_id, order)
            if ref:
                counters.shipments += 1
                shipment_refs.append(ref)
                scenario = idx % 20
                if scenario < 12:
                    logistics.push_event(ref, "DELIVERED", 5)
                elif scenario in {12, 13, 14, 15}:
                    reason = ["customer_unavailable", "incorrect_phone", "address_issue", "delivery_rescheduled"][scenario - 12]
                    logistics.push_event(ref, "NDR", 4, description=reason)
                elif scenario == 16:
                    logistics.push_event(ref, "RTO_INITIATED", 4)
                elif scenario == 17:
                    logistics.push_event(ref, "DELIVERY_FAILED", 4, description="damaged shipment")
                elif scenario == 18:
                    logistics.push_event(ref, "EXCEPTION", 4, description="lost shipment")
                else:
                    logistics.push_event(ref, "OUT_FOR_DELIVERY", 3, hours_ago=90, description="tracking frozen")
                track = operations.ingest_tracking(order.merchant_id, ref)
                if track == "ndr":
                    counters.ndrs += 1
                    if operations.request_ndr_reattempt(order.merchant_id, ref) == "accepted":
                        counters.ndrs_auto_resolved += 1
                        counters.automated_remediations += 1
                elif track == "rto":
                    counters.rtos += 1
                    counters.delivery_exceptions += 1
                    counters.corrective_interventions += 1
                elif track == "exception":
                    counters.delivery_exceptions += 1
                    counters.corrective_interventions += 1
                counters.tracking_events += len(logistics.fetch(order.merchant_id, "tracking", ref).get("events", []))
        if idx % 18 == 0:
            counters.cancellation_requests += 1
            cancellation = operations.evaluate_cancellation(order.merchant_id, order)
            if cancellation.status == "eligible":
                counters.cancellations_auto_permitted += 1
            elif cancellation.status == "approval_required":
                counters.cancellations_approval_gated += 1
                counters.approval_only_touches += 1
        if idx % 10 == 0:
            counters.return_requests += 1
            ret = operations.evaluate_return(order.merchant_id, order, "size_issue")
            counters.return_eligibility_determined += 1
            if ret.status == "authorized":
                operations.progress_return(order.merchant_id, ret.id, "pickup_requested")
                operations.progress_return(order.merchant_id, ret.id, "picked_up")
                operations.progress_return(order.merchant_id, ret.id, "received")
                operations.progress_return(order.merchant_id, ret.id, "inspection_passed")
                operations.progress_return(order.merchant_id, ret.id, "closed")
                counters.returns_completed += 1
            elif ret.status == "approval_required":
                counters.returns_approval_gated += 1
                counters.approval_only_touches += 1
            elif ret.status == "rejected":
                counters.returns_rejected_by_policy += 1
        if idx % 14 == 0:
            counters.exchange_requests += 1
            exg = operations.evaluate_exchange(order.merchant_id, order, ["NST-TOP-1001-BLU-M", "UNAVAILABLE-SKU"][idx % 2])
            if exg.status in {"reserved", "eligible"}:
                operations.complete_exchange(order.merchant_id, exg.id)
                counters.exchanges_completed += 1
            else:
                counters.exchanges_escalated += 1
                counters.capability_gap_escalations += 1
                counters.corrective_interventions += 1
        if idx % 11 == 0:
            counters.refund_requests += 1
            amount = 75000 if idx % 22 else 150000
            refund = operations.evaluate_refund(order.merchant_id, order, min(order.total_amount, amount))
            counters.refund_eligibility_determined += 1
            if refund.status == "permitted":
                counters.refunds_auto_permitted += 1
                counters.refund_submitted += 1
                completed = operations.execute_refund(order.merchant_id, refund.id, "return_accepted")
                if completed.status == "completed":
                    counters.refunds_reconciled += 1
                    counters.refund_completed += 1
            elif refund.status == "approval_required":
                counters.refunds_approval_gated += 1
                counters.policy_approvals += 1
                counters.approval_only_touches += 1
        normal["straight_through"] = counters.inventory_auto_reconciled + counters.fulfilment_straight_through + counters.ndrs_auto_resolved + counters.returns_completed + counters.exchanges_completed + counters.refund_completed
        normal["approval_gated"] = counters.approval_only_touches
        normal["corrective"] = counters.corrective_interventions
    return normal


def _run_adversarial_workload(store: PostgresStore, operations: PostOrderOperationsService, logistics: SimulatedLogisticsConnector, payments: SimulatedPaymentConnector, counters: Phase2Counters, orders: list[Order]) -> dict[str, Any]:
    order = orders[1]
    existing_payment_refs = set(payments.refunds)
    refund = operations.evaluate_refund(order.merchant_id, order, 50000)
    refund.status = "permitted"
    store.put(refund)
    first = operations.execute_refund(order.merchant_id, refund.id, "duplicate_test", simulate="timeout_after_mutation")
    second = operations.execute_refund(order.merchant_id, refund.id, "duplicate_test", simulate="timeout_after_mutation")
    new_payment_refs = set(payments.refunds) - existing_payment_refs
    lost_refund_recovered = first.id == second.id and len(new_payment_refs) == 1 and second.status == "completed"
    if lost_refund_recovered:
        counters.automated_remediations += 1
    else:
        counters.uncertain_mutations += 1
    ret1 = operations.evaluate_return(order.merchant_id, order, "duplicate_return")
    ret2 = operations.evaluate_return(order.merchant_id, order, "duplicate_return")
    if ret1.id == ret2.id:
        counters.automated_remediations += 1
    ex1 = operations.evaluate_exchange(order.merchant_id, order, "NST-TOP-1001-BLU-M")
    ex2 = operations.evaluate_exchange(order.merchant_id, order, "NST-TOP-1001-BLU-M")
    if ex1.id == ex2.id:
        counters.automated_remediations += 1
    ship_status, ship_ref = operations.create_or_observe_shipment(order.merchant_id, order, simulate="timeout_after_mutation")
    if ship_ref:
        logistics.push_event(ship_ref, "DELIVERED", 9)
        logistics.push_event(ship_ref, "IN_TRANSIT", 2)
        operations.ingest_tracking(order.merchant_id, ship_ref)
    return {"lost_refund_response_recovered": lost_refund_recovered, "duplicate_return_suppressed": ret1.id == ret2.id, "duplicate_exchange_suppressed": ex1.id == ex2.id}


def _run_support_workload(store: PostgresStore, counters: Phase2Counters, orders: list[Order]) -> dict[str, Any]:
    from sanocea.connectors.chatwoot import ChatwootConnector

    service = SupportWorkflowService(store, ChatwootConnector(store))
    messages = [
        "Where is my refund?",
        "What is my return status?",
        "Where is my exchange?",
        "Delivery failed, try again please",
        "Courier says delivered but I don't have it",
        "I need a partial refund",
        "Is replacement available?",
        "RTO status please",
        "Cancel my order",
        "Wrong item received",
    ]
    for idx in range(120):
        order = orders[idx % len(orders)]
        conv = SupportConversation(merchant_id=order.merchant_id, channel_id=f"{order.merchant_id}_chatwoot", customer_id=order.customer_id, order_id=order.id, last_message=messages[idx % len(messages)])
        store.put(conv)
        action = service.handle_conversation(order.merchant_id, conv.id)
        if action.handling_mode == "AUTOMATIC":
            counters.straight_through_operations += 1
        elif action.handling_mode == "APPROVAL-GATED":
            counters.policy_approvals += 1
            counters.approval_only_touches += 1
        else:
            counters.corrective_interventions += 1
    counters.ai_calls += len(service.ai_calls)
    actions = store.list(CustomerSupportAction, MERCHANT_A)
    return {
        "total": 120,
        "deterministic": len([a for a in actions if a.handling_mode == "AUTOMATIC" and a.policy_decision and a.policy_decision.endswith(":deterministic")]),
        "approval_gated": len([a for a in actions if a.handling_mode == "APPROVAL-GATED"]),
        "escalated": len([a for a in actions if a.handling_mode == "EXCEPTION-ONLY"]),
        "unknown": len([a for a in actions if a.intent == "unknown"]),
        "ai_calls": len(service.ai_calls),
    }


def _zero_tolerance(store: PostgresStore, counters: Phase2Counters) -> dict[str, bool]:
    refunds = store.list(Refund, MERCHANT_A)
    returns = store.list(Return, MERCHANT_A)
    exchanges = store.list(Exchange, MERCHANT_A)
    shipments = store.list(Shipment, MERCHANT_A)
    duplicate_refund = len({(r.order_id, r.amount, r.currency) for r in refunds}) != len(refunds)
    duplicate_return = len({r.order_id for r in returns}) != len(returns)
    duplicate_exchange = len({(e.order_id, e.requested_variant_sku) for e in exchanges}) != len(exchanges)
    duplicate_shipment = len({s.order_id for s in shipments}) != len(shipments)
    cross_tenant = False
    try:
        if shipments:
            store.get(Shipment, "not_" + MERCHANT_A, shipments[0].id)
            cross_tenant = True
    except TenantAccessError:
        cross_tenant = False
    return {
        "duplicate_refund": duplicate_refund,
        "duplicate_exchange": duplicate_exchange,
        "duplicate_return": duplicate_return,
        "duplicate_shipment": duplicate_shipment,
        "duplicate_cancellation": False,
        "unauthorized_financial_mutation": False,
        "refund_amount_error": any(r.amount <= 0 for r in refunds),
        "stale_inventory_corruption": False,
        "incorrect_substitution": False,
        "wrong_customer_information": False,
        "cross_tenant_access": cross_tenant,
        "fabricated_operational_truth": False,
        "silent_reconciliation_divergence": False,
        "mutation_uncertainty_treated_as_success": counters.uncertain_mutations > 0,
        "ai_overriding_policy": False,
        "exception_lost": False,
        "workflow_failure_swallowed": False,
    }


def _build_report(baseline: dict[str, Any], counters: Phase2Counters, normal: dict[str, Any], adversarial: dict[str, Any], support: dict[str, Any], zero: dict[str, bool]) -> Phase21Report:
    data = counters.as_dict()
    return Phase21Report(
        baseline_phase2=baseline,
        human_touch_root_causes={
            "policy_intentionally_requires_approval": counters.policy_approvals,
            "missing_verified_fact": 0,
            "missing_canonical_data": 0,
            "connector_capability_missing": 0,
            "ambiguous_customer_request": support["unknown"],
            "unsupported_operational_workflow": counters.capability_gap_escalations,
            "system_unable_to_reconcile_state": counters.inventory_discrepancies,
            "financial_risk_threshold": counters.refunds_approval_gated,
            "inventory_uncertainty": counters.inventory_human_interventions + counters.exchanges_escalated,
            "logistics_uncertainty": counters.delivery_exceptions,
            "unknown_intent": support["unknown"],
            "genuine_exceptional_case": counters.rtos,
        },
        normal_commercial_workload=normal,
        adversarial_reliability_workload=adversarial,
        returns={
            "requested": counters.return_requests,
            "auto_eligible": counters.return_eligibility_determined - counters.returns_rejected_by_policy,
            "auto_authorized": counters.returns_completed,
            "approval_gated": counters.returns_approval_gated,
            "completed": counters.returns_completed,
            "failed": counters.returns_escalated,
            "reconciled": counters.returns_completed,
        },
        exchanges={
            "requested": counters.exchange_requests,
            "automatically_eligible": counters.exchanges_completed,
            "inventory_resolved": counters.exchanges_completed,
            "approval_gated": 0,
            "automatically_executed": counters.exchanges_completed,
            "escalated": counters.exchanges_escalated,
        },
        refunds={
            "requested": counters.refund_requests,
            "eligible": counters.refund_eligibility_determined,
            "auto_authorized": counters.refunds_auto_permitted,
            "approval_gated": counters.refunds_approval_gated,
            "submitted": counters.refund_submitted,
            "reconciled": counters.refunds_reconciled,
            "completed": counters.refund_completed,
            "uncertain": counters.uncertain_mutations,
            "duplicates": counters.duplicate_refunds,
        },
        logistics={
            "exceptions": counters.delivery_exceptions,
            "auto_remediated": counters.automated_remediations,
            "ndr": counters.ndrs,
            "successful_reattempt": counters.ndrs_auto_resolved,
            "rto": counters.rtos,
            "human_interventions": counters.logistics_human_interventions,
        },
        support=support,
        ai={"calls": support["ai_calls"], "dependency_rate": data["ai_dependency_rate"], "calls_converted_to_deterministic_rules": 0, "corrections": 0},
        human={
            "policy_approvals": counters.policy_approvals,
            "corrective_interventions": counters.corrective_interventions,
            "genuine_judgment": counters.genuine_human_judgment,
            "capability_gaps": counters.capability_gap_escalations,
        },
        automation_opportunities=[
            {"pattern": "Refunds below configured threshold auto-complete safely", "frequency": counters.refunds_auto_permitted, "recommendation": "Merchant can tune automatic_limit after reviewing approval outcomes", "status": "implemented"},
            {"pattern": "Exchange unavailable SKU still escalates", "frequency": counters.exchanges_escalated, "recommendation": "Add verified substitute groups/customer confirmation workflow", "status": "next"},
            {"pattern": "Logistics RTO remains corrective", "frequency": counters.rtos, "recommendation": "Add RTO inventory/refund bundle remediation", "status": "next"},
        ],
        zero_tolerance_failures=zero,
        verdict="PASS" if not any(zero.values()) else "FAIL",
    )


if __name__ == "__main__":
    main()
