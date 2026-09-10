from __future__ import annotations

from enum import Enum
from typing import Any


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class PolicyEngine:
    def decide(self, policy: dict[str, Any], action: str, context: dict[str, Any]) -> Decision:
        rules = policy.get(action, {})
        if not rules:
            return Decision.DENY
        if action == "refund":
            amount = int(context.get("amount", 0))
            automatic_limit = int(rules.get("automatic_limit", 0))
            if amount <= automatic_limit:
                return Decision.ALLOW
            return Decision(rules.get("above_limit", Decision.REQUIRE_APPROVAL))
        mode = rules.get("mode")
        if mode in Decision._value2member_map_:
            return Decision(mode)
        return Decision.DENY

