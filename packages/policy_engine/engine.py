from __future__ import annotations

from enum import Enum
from typing import Any


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyEngine:
    def evaluate_with_reason(self, policy: dict[str, Any], action: str, context: dict[str, Any]) -> tuple[Decision, str, dict[str, Any]]:
        """Authoritative deterministic policy evaluation.
        Returns: (Decision, reason_string, structured_evidence_dict)
        """
        rules = policy.get(action, {})
        if not rules:
            return Decision.DENY, f"No policy configured for action '{action}'", {"action": action, "configured_rules": list(policy.keys())}

        if action == "refund":
            amount = int(context.get("amount", 0))
            automatic_limit = int(rules.get("automatic_limit", 0))
            order_total = int(context.get("order_total", 0))
            max_order_percent = float(rules.get("max_order_percent", 100.0))

            if order_total > 0 and (amount / order_total) * 100 > max_order_percent:
                reason = f"Refund amount ₹{amount/100:.2f} is {(amount/order_total)*100:.1f}% of order total, exceeding allowed {max_order_percent:.1f}%"
                evidence = {"amount": amount, "order_total": order_total, "percent": (amount/order_total)*100, "threshold_percent": max_order_percent}
                return Decision(rules.get("above_limit", Decision.REQUIRE_APPROVAL)), reason, evidence

            if amount <= automatic_limit:
                return Decision.ALLOW, f"Refund amount ₹{amount/100:.2f} is within automatic limit ₹{automatic_limit/100:.2f}", {"amount": amount, "limit": automatic_limit}
            
            reason = f"Refund amount ₹{amount/100:.2f} exceeds automatic limit ₹{automatic_limit/100:.2f}"
            evidence = {"amount": amount, "limit": automatic_limit, "threshold_rule": "refund.automatic_limit"}
            return Decision(rules.get("above_limit", Decision.REQUIRE_APPROVAL)), reason, evidence

        if action in ("price_change", "channel_price_correction"):
            old_price = float(context.get("old_price", 0))
            new_price = float(context.get("new_price", 0))
            if old_price > 0 and new_price > 0:
                delta_percent = abs((new_price - old_price) / old_price) * 100
            else:
                delta_percent = abs(float(context.get("delta_percent", 0)))

            automatic_limit_percent = float(rules.get("automatic_limit_percent", 10.0))
            is_live = bool(context.get("is_published", False))

            if is_live and rules.get("require_approval_for_live", False):
                reason = f"Price change on live published product requires operator approval"
                evidence = {"old_price": old_price, "new_price": new_price, "delta_percent": delta_percent, "is_published": True}
                return Decision.REQUIRE_APPROVAL, reason, evidence

            if delta_percent <= automatic_limit_percent:
                return Decision.ALLOW, f"Price delta {delta_percent:.1f}% is within automatic limit {automatic_limit_percent:.1f}%", {"delta_percent": delta_percent, "limit": automatic_limit_percent}

            reason = f"Price change delta {delta_percent:.1f}% exceeds automatic threshold {automatic_limit_percent:.1f}%"
            evidence = {"old_price": old_price, "new_price": new_price, "delta_percent": delta_percent, "limit": automatic_limit_percent}
            return Decision(rules.get("above_limit", Decision.REQUIRE_APPROVAL)), reason, evidence

        if action == "catalog_unpublish":
            if rules.get("require_approval", True):
                reason = f"Catalog unpublishing for product {context.get('product_id', 'unknown')} on channel {context.get('channel', 'all')} requires explicit approval"
                evidence = {"product_id": context.get("product_id"), "channel": context.get("channel"), "policy_rule": "catalog_unpublish.require_approval"}
                return Decision.REQUIRE_APPROVAL, reason, evidence
            return Decision.ALLOW, "Catalog unpublish allowed by policy", {"action": action}

        if action == "inventory_writeoff":
            qty = int(context.get("quantity", 0))
            max_auto_qty = int(rules.get("max_automatic_quantity", 0))
            if qty <= max_auto_qty:
                return Decision.ALLOW, f"Write-off quantity {qty} is within automatic limit {max_auto_qty}", {"quantity": qty, "limit": max_auto_qty}
            reason = f"Inventory write-off quantity {qty} exceeds automatic threshold {max_auto_qty}"
            evidence = {"quantity": qty, "limit": max_auto_qty, "sku": context.get("sku")}
            return Decision(rules.get("above_limit", Decision.REQUIRE_APPROVAL)), reason, evidence

        mode = rules.get("mode")
        if mode in Decision._value2member_map_:
            return Decision(mode), f"Policy evaluated by static mode '{mode}'", {"mode": mode}
        return Decision.DENY, f"Default deny for action '{action}'", {"action": action}

    def decide(self, policy: dict[str, Any], action: str, context: dict[str, Any]) -> Decision:
        decision, _, _ = self.evaluate_with_reason(policy, action, context)
        return decision

