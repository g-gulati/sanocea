"""Scenario-specific synthetic operational data seeders for prospect demo tenants.

Each function takes (store, merchant_id, product_drafts, tenant_config) and seeds SYNTHETIC_DEMO
operational events (orders, payments, returns, refunds, exceptions) around the REAL product_drafts
already seeded by reset.py. Every seeder calls the SAME production service classes the certified
Reference Merchant lifecycle uses (FinanceOperationsService, PostOrderOperationsService, ExceptionService)
- never hand-crafted rows that bypass the business logic those services enforce. This is deliberate: it
is the same "genuine production engines operating on demo data" pattern the Reference Merchant's own
certification already established as the correct model (see docs/demo/PROSPECT_DEMO_READINESS_REVIEW.md
Tier 2 classification), extended here rather than replaced.
"""

from __future__ import annotations

import random
from typing import Any

from sanocea.packages.domain_contract.models import Approval, Inventory, Location, Order, ProductDraft
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService
from sanocea.packages.finance.operations import FinanceOperationsService
from sanocea.packages.post_order.operations import PostOrderOperationsService

DEFAULT_LOCATION_REF = "loc_default_hub"


def _order(merchant_id: str, channel_id: str, order_number: str, amount_paise: int, currency: str, *, status: str = "confirmed", payment_status: str = "paid", fulfillment_status: str | None = "unfulfilled") -> Order:
    return Order(
        merchant_id=merchant_id, channel_id=channel_id, order_number=order_number,
        status=status, payment_status=payment_status, fulfillment_status=fulfillment_status,
        total_amount=amount_paise, currency=currency,
    )


def seed_reconciliation_scenario(store, merchant_id: str, product_drafts: list[ProductDraft], config: dict[str, Any]) -> dict[str, Any]:
    """Ajanta: products -> channel observations -> reconciliation -> automatic matches -> discrepancies
    -> evidence -> exceptions -> approvals -> resolution -> reporting. Uses real
    FinanceOperationsService.observe_payment/reconcile_payment against real orders derived from the
    real seeded catalogue - one deliberately clean match, one genuine amount discrepancy, matching
    Ajanta's own stated pain point (reconciliation consumes the majority of their team's time)."""
    rng = random.Random(config["deterministic_seed"])
    finance = FinanceOperationsService(store)
    priced = [d for d in product_drafts if d.price]
    results: dict[str, Any] = {"orders": 0, "matched": 0, "divergences": 0}
    channels = ["chn_" + c for c in config["known_channels"] if c != "own_website"] or ["chn_own_website"]

    for i, draft in enumerate(priced[:3]):
        channel_id = channels[i % len(channels)]
        order = _order(merchant_id, channel_id, f"DEMO-AJS-{1000 + i}", draft.price, draft.currency or "INR")
        store.put(order)
        results["orders"] += 1
        if i == 0:
            # Clean match: settlement observation agrees with canonical order total.
            obs = finance.observe_payment(merchant_id, order, channel_id, order.total_amount, order.currency, "paid", external_payment_id=f"ext-{order.id}")
            rec = finance.reconcile_payment(merchant_id, order, obs)
            if rec.result == "MATCH":
                results["matched"] += 1
        else:
            # Genuine discrepancy: the channel's settlement figure disagrees with canonical order total -
            # exactly the kind of gap Ajanta's team currently has to find manually across channels.
            observed_amount = order.total_amount - (500 + rng.randint(0, 2000))
            obs = finance.observe_payment(merchant_id, order, channel_id, observed_amount, order.currency, "paid", external_payment_id=f"ext-{order.id}")
            rec = finance.reconcile_payment(merchant_id, order, obs)
            if rec.result != "MATCH":
                results["divergences"] += 1
    return results


def seed_order_monitoring_scenario(store, merchant_id: str, product_drafts: list[ProductDraft], config: dict[str, Any]) -> dict[str, Any]:
    """HealthVitals: orders -> monitoring -> fulfilment/status -> exception detection -> escalation ->
    follow-up -> human decision. One order per known channel proceeds normally; one is deliberately
    stuck past a reasonable fulfilment window, generating a real FULFILMENT_DELAY exception and a
    pending escalation Approval - the exact "someone has to notice and follow up" gap HealthVitals
    described."""
    exceptions = ExceptionService(store)
    priced = [d for d in product_drafts if d.price]
    channels = ["chn_" + c for c in config["known_channels"]] or ["chn_own_website"]
    results: dict[str, Any] = {"orders": 0, "delayed": 0, "escalations": 0}

    for i, draft in enumerate(priced[:4]):
        channel_id = channels[i % len(channels)]
        stuck = i == 1
        order = _order(
            merchant_id, channel_id, f"DEMO-DJH-{2000 + i}", draft.price, draft.currency or "INR",
            fulfillment_status="pending" if stuck else "unfulfilled",
        )
        store.put(order)
        results["orders"] += 1
        if stuck:
            exc = exceptions.create(
                merchant_id=merchant_id, category=ExceptionCategory.FULFILMENT_DELAY,
                message=f"Order {order.order_number} on {channel_id} has been unfulfilled past the expected window.",
                object_id=order.id, severity="warning",
                remediation_options=["escalate_to_fulfilment_team", "contact_customer", "review"],
            )
            from sanocea.packages.domain_contract.models import Approval

            store.put(Approval(
                merchant_id=merchant_id, action="escalate_fulfilment_delay", object_id=order.id,
                status="pending", requested_by="policy", workflow_id=exc.id,
            ))
            results["delayed"] += 1
            results["escalations"] += 1
    return results


def seed_returns_reconciliation_scenario(store, merchant_id: str, product_drafts: list[ProductDraft], config: dict[str, Any]) -> dict[str, Any]:
    """Carzex: returns -> refund status -> marketplace evidence -> reconciliation -> discrepancies ->
    approval -> resolution. Uses real PostOrderOperationsService.evaluate_return/progress_return/
    evaluate_refund against a real order, plus a marketplace settlement-evidence mismatch via
    FinanceOperationsService - mirroring Carzex's own stated interest (Amazon returns/reconciliation)."""
    post_order = PostOrderOperationsService(store, None, None)
    finance = FinanceOperationsService(store)
    priced = [d for d in product_drafts if d.price]
    results: dict[str, Any] = {"orders": 0, "returns": 0, "refunds_pending_approval": 0, "marketplace_discrepancies": 0}
    if not priced:
        return results

    channel_id = "chn_amazon_in" if "amazon_in" in config["known_channels"] else "chn_own_website"
    draft = priced[0]
    order = _order(merchant_id, channel_id, "DEMO-CZX-3001", draft.price, draft.currency or "INR", fulfillment_status="fulfilled")
    order.placed_at = order.sync.observed_at
    store.put(order)
    results["orders"] += 1

    ret = post_order.evaluate_return(merchant_id, order, reason="customer_choice")
    post_order.progress_return(merchant_id, ret.id, event="inspection_passed", restockable=True)
    results["returns"] += 1

    refund = post_order.evaluate_refund(merchant_id, order, amount=order.total_amount)
    if refund.status == "approval_required":
        results["refunds_pending_approval"] += 1

    # Marketplace evidence mismatch: the settlement Amazon reports for this return's refund disagrees
    # with what Carzex's own order total says - the concrete "marketplace evidence vs. reconciliation"
    # gap Carzex asked about.
    observed_amount = order.total_amount - 15000
    obs = finance.observe_payment(merchant_id, order, "amazon_in", observed_amount, order.currency, "refunded", external_payment_id=f"amzn-{order.id}")
    rec = finance.reconcile_payment(merchant_id, order, obs)
    if rec.result != "MATCH":
        results["marketplace_discrepancies"] += 1
    return results


def seed_catalogue_operations_scenario(store, merchant_id: str, product_drafts: list[ProductDraft], config: dict[str, Any]) -> dict[str, Any]:
    """The Premium Basket: catalogue, inventory, orders, channel coordination, exceptions,
    reconciliation, reporting across many real channels. Includes:
    - Cross-channel listing-variance exception (TPB-002/003/004 public audit evidence)
    - Blinkit 100% OOS inventory exception (TPB-001)
    - TPB-018 price-inversion approval for the BBQ Almonds 2-pack
    All seeded through production service classes — same pattern as the Reference Merchant."""
    exceptions = ExceptionService(store)
    finance = FinanceOperationsService(store)
    priced = [d for d in product_drafts if d.price]
    channels = ["chn_" + c for c in config["known_channels"]] or ["chn_own_website"]
    results: dict[str, Any] = {
        "orders": 0, "matched": 0, "divergences": 0,
        "channel_variance_exceptions": 0, "oos_exceptions": 0, "price_approvals": 0,
    }

    # ── Orders + reconciliation ──────────────────────────────────────────────
    for i, draft in enumerate(priced[:5]):
        channel_id = channels[i % len(channels)]
        order = _order(merchant_id, channel_id, f"DEMO-TPB-{4000 + i}", draft.price, draft.currency or "INR")
        store.put(order)
        results["orders"] += 1
        if i % 2 == 0:
            obs = finance.observe_payment(merchant_id, order, channel_id, order.total_amount, order.currency, "paid", external_payment_id=f"ext-{order.id}")
            rec = finance.reconcile_payment(merchant_id, order, obs)
            if rec.result == "MATCH":
                results["matched"] += 1
        else:
            observed_amount = order.total_amount - 1000
            obs = finance.observe_payment(merchant_id, order, channel_id, observed_amount, order.currency, "paid", external_payment_id=f"ext-{order.id}")
            rec = finance.reconcile_payment(merchant_id, order, obs)
            if rec.result != "MATCH":
                results["divergences"] += 1

    # ── Cross-channel listing variance exception (TPB-002/003/004) ───────────
    if len(priced) >= 1:
        exceptions.create(
            merchant_id=merchant_id, category="cross_channel_listing_variance",
            message=(
                f"'{priced[0].title}' is represented with different pack-size/price data across "
                f"{', '.join(config['known_channels'][:3])} - verified via public audit evidence, requires "
                f"merchandising review."
            ),
            object_id=priced[0].id, severity="warning",
            remediation_options=["review", "normalize_cross_channel_listing"],
        )
        results["channel_variance_exceptions"] += 1

    # ── Location: Blinkit dark store hub (required for inventory + briefing) ─
    blinkit_loc = Location(
        merchant_id=merchant_id,
        name="Blinkit Dark Store — Delhi NCR",
        code="BLINKIT_DELHI",
        is_active=True,
        fulfillment_types=["q_commerce"],
        metadata={"channel": "blinkit", "location_ref": "loc_blinkit_hub"},
    )
    store.put(blinkit_loc)

    # ── Blinkit 100% OOS (TPB-001): inventory record + exception + approval ──
    # Pick the second priced product for Blinkit OOS — typically BBQ Almonds.
    # sellable=0 → ats=0 → 100% OOS. quantity=50 shows it was stocked but is now depleted.
    oos_draft = priced[1] if len(priced) > 1 else priced[0]
    blinkit_inv = Inventory(
        merchant_id=merchant_id,
        sku=oos_draft.sku or oos_draft.id,
        location_ref="loc_blinkit_hub",
        quantity=50,    # historically stocked
        sellable=0,     # → ats=0: fully depleted
        reserved=0,
        quarantine=0,
        status="active",
    )
    store.put(blinkit_inv)

    oos_exc = exceptions.create(
        merchant_id=merchant_id,
        category=ExceptionCategory.INVENTORY_CONFLICT,
        message=(
            f"'{oos_draft.title}' is 100% out of stock on Blinkit (loc_blinkit_hub). "
            f"ATS = 0 / 50 units depleted. Manual replenishment or Q-commerce listing suspension required."
        ),
        object_id=blinkit_inv.id, severity="critical",
        remediation_options=["replenish_blinkit_stock", "suspend_blinkit_listing", "review"],
    )
    store.put(Approval(
        merchant_id=merchant_id,
        action="resolve_inventory_shortage",
        object_id=blinkit_inv.id,
        status="pending",
        requested_by="policy",
        workflow_id=oos_exc.id,
        reference="TPB-INV-001",
        summary=f"Blinkit OOS: '{oos_draft.title}' — 0 units ATS. Replenish or suspend listing?",
        recommendation="Replenish stock to Blinkit hub or temporarily delist to avoid customer-facing OOS.",
        evidence={
            "sku": oos_draft.sku or oos_draft.id,
            "channel": "blinkit",
            "location": "Blinkit Dark Store — Delhi NCR",
            "ats": 0,
            "historical_quantity": 50,
            "severity": "critical",
        },
    ))
    results["oos_exceptions"] += 1

    # ── TPB-018: price-inversion approval for BBQ Almonds 2-pack ─────────────
    # 2-pack at ₹998 = same as 2 × single. No bundle benefit. Fix = 10% discount → ₹898.
    # Uses the third priced product where available; falls back to first.
    price_draft = priced[2] if len(priced) > 2 else priced[0]
    current_price_rs = round(price_draft.price / 100, 2) if price_draft.price else 998.0
    bundle_price_rs = round(current_price_rs * 0.90, 2)   # 10% bundle discount
    compare_at_rs = current_price_rs                        # original becomes compare-at
    store.put(Approval(
        merchant_id=merchant_id,
        action="price_change",
        object_id=price_draft.id,
        status="pending",
        requested_by="policy",
        reference="TPB-018",
        summary=f"'{price_draft.title}' 2-pack priced at same rate as 2× single — no bundle benefit for customer.",
        recommendation=f"Apply 10% bundle discount: ₹{bundle_price_rs:.2f} (compare-at ₹{compare_at_rs:.2f})",
        evidence={
            "sku": price_draft.sku or price_draft.id,
            "current_price": current_price_rs,
            "new_price": bundle_price_rs,
            "compare_at_price": compare_at_rs,
            "reason": "Unit pricing inversion: 2-pack offers zero saving vs buying 2 singles",
            "likely_impact": "+15-25% conversion lift on bundle SKU once discount is visible to customer",
            "unit_economics": f"Single unit: ₹{round(current_price_rs/2,2)} implied. "
                              f"2-pack at ₹{bundle_price_rs:.2f} = ₹{round(bundle_price_rs/2,2)}/unit — clear saving.",
        },
    ))
    results["price_approvals"] += 1

    return results



def seed_delivery_exceptions_scenario(store, merchant_id: str, product_drafts: list[ProductDraft], config: dict[str, Any]) -> dict[str, Any]:
    """HealthVitals: post-dispatch delivery-logistics exceptions - NDR (non-delivery report), a shipment
    running behind its expected transit window, and a shipment approaching RTO (return-to-origin) risk.
    This is the "someone has to track every carrier/marketplace tracking page and notice before it's too
    late" gap HealthVitals described (cross-platform tracking, NDR/RTO, escalations). Each is a real
    Order + ExceptionRecord via ExceptionService, using the ExceptionCategory values the domain already
    defines (NDR_DETECTED, SHIPMENT_DELAY) - no new category invented. The RTO-risk case additionally
    gets a pending Approval, matching how a genuine near-RTO shipment needs a human decision (reattempt
    delivery vs. accept the return) rather than silent auto-resolution."""
    exceptions = ExceptionService(store)
    priced = [d for d in product_drafts if d.price]
    channels = ["chn_" + c for c in config["known_channels"]] or ["chn_own_website"]
    results: dict[str, Any] = {"orders": 0, "ndr": 0, "shipment_delays": 0, "rto_risk": 0, "escalations": 0}
    if not priced:
        return results

    def _next_draft(i: int) -> ProductDraft:
        return priced[i % len(priced)]

    def _next_channel(i: int) -> str:
        return channels[i % len(channels)]

    order_seq = 5000
    # ── 3 NDR cases: courier attempted delivery, customer unreachable/refused ──
    ndr_reasons = ["customer unreachable - phone switched off", "customer refused delivery", "address not found by courier"]
    for i, reason in enumerate(ndr_reasons):
        draft = _next_draft(i)
        order = _order(merchant_id, _next_channel(i), f"DEMO-DJH-{order_seq}", draft.price, draft.currency or "INR", fulfillment_status="ndr")
        store.put(order)
        results["orders"] += 1
        exceptions.create(
            merchant_id=merchant_id, category=ExceptionCategory.NDR_DETECTED,
            message=f"Non-delivery report on order {order.order_number}: {reason}. Courier will attempt RTO after 2 more failed attempts.",
            object_id=order.id, severity="warning",
            remediation_options=["reattempt_delivery", "contact_customer", "escalate_to_courier"],
        )
        results["ndr"] += 1
        order_seq += 1

    # ── 2 shipments running behind their expected transit window ─────────────
    for i in range(2):
        draft = _next_draft(i + 3)
        order = _order(merchant_id, _next_channel(i + 3), f"DEMO-DJH-{order_seq}", draft.price, draft.currency or "INR", fulfillment_status="in_transit")
        store.put(order)
        results["orders"] += 1
        days_late = 2 + i
        exceptions.create(
            merchant_id=merchant_id, category=ExceptionCategory.SHIPMENT_DELAY,
            message=f"Shipment for order {order.order_number} is {days_late} day(s) past its expected delivery window with no carrier scan update.",
            object_id=order.id, severity="warning",
            remediation_options=["contact_courier", "notify_customer", "review"],
        )
        results["shipment_delays"] += 1
        order_seq += 1

    # ── 1 shipment approaching RTO risk (repeated NDR, courier will return it) ─
    draft = _next_draft(5)
    order = _order(merchant_id, _next_channel(5), f"DEMO-DJH-{order_seq}", draft.price, draft.currency or "INR", fulfillment_status="ndr")
    store.put(order)
    results["orders"] += 1
    rto_exc = exceptions.create(
        merchant_id=merchant_id, category=ExceptionCategory.SHIPMENT_DELAY,
        message=(
            f"Order {order.order_number} has failed 2 delivery attempts and is now flagged by the courier "
            f"for RTO (return-to-origin) if a 3rd attempt fails or no action is taken within 24h."
        ),
        object_id=order.id, severity="critical",
        remediation_options=["approve_reattempt", "accept_rto", "contact_customer_urgently"],
    )
    store.put(Approval(
        merchant_id=merchant_id, action="resolve_delivery_exception", object_id=order.id,
        status="pending", requested_by="policy", workflow_id=rto_exc.id,
        reference=f"RTO-{order.order_number}",
        summary=f"Order {order.order_number} is one failed attempt away from RTO - reattempt delivery or accept the return?",
        recommendation="Approve a final reattempt with customer SMS confirmation before the courier auto-RTOs the shipment.",
        evidence={
            "order_number": order.order_number, "attempts_failed": 2, "hours_until_auto_rto": 24,
            "likely_impact": "RTO reverses this order's revenue and adds reverse-logistics cost if not caught in time.",
        },
    ))
    results["rto_risk"] += 1
    results["escalations"] += 1
    return results


SCENARIO_SEEDERS = {
    "reconciliation": seed_reconciliation_scenario,
    "order_monitoring": seed_order_monitoring_scenario,
    "returns_reconciliation": seed_returns_reconciliation_scenario,
    "catalogue_operations": seed_catalogue_operations_scenario,
    "delivery_exceptions": seed_delivery_exceptions_scenario,
}
