from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import Channel, Merchant


DEFAULT_PHASE1_CONFIG = {
    "enabled_modules": {"catalogue": True, "orders": True, "support": True},
    "currency": "INR",
    "timezone": "Asia/Kolkata",
    "product_rules": {
        "required": ["sku", "title", "price", "currency", "product_type"],
        "category_profiles": {"apparel": ["size", "material", "colour"], "jewelry": ["material", "brand"]},
    },
    "publication": {"require_approval": True},
    "support": {"auto_response": {"order_status": True, "shipment_status": True}},
    "policy": {"refund": {"automatic_limit": 1000, "above_limit": "REQUIRE_APPROVAL"}},
    "returns": {"mode": "REQUIRE_APPROVAL"},
    "cancellations": {"before_fulfilment": "REQUIRE_APPROVAL"},
    "sla_thresholds": {"order_unfulfilled_hours": 24, "shipment_not_created_hours": 24, "tracking_stale_hours": 48},
}

# Phase 4.5: the config sections the consolidation audit found were NEVER set by onboarding - every
# Phase 3/3.1/4/4.1 workload configured these ad-hoc, directly in Python, because there was no onboarding
# path for them. This is the fix: "merchant onboarding = configuration + credentials + mappings, not
# application-code changes" now genuinely covers finance and procurement, not just catalogue/orders/support.
DEFAULT_FINANCE_CONFIG = {
    "tolerances": {"default": 0},
    "expected_charges": {},
}
DEFAULT_PROCUREMENT_CONFIG = {
    "spending": {"auto_approve_limit": 0, "above_limit": "REQUIRE_APPROVAL"},
    "cost_tolerance": {"pct": 0.0, "absolute": 0, "above_tolerance": "REQUIRE_APPROVAL"},
    "supplier_reliability_threshold": 0.0,
    "supplier_priority": ["preferred", "cost", "lead_time_days"],
    "velocity_lookback_days": 30,
    "default_lead_time_days": 7,
    "replenishment": {"default": {"safety_stock": 0}},
}
DEFAULT_LOGISTICS_CONFIG: dict[str, Any] = {"providers": [], "sla_hours": {}}


@dataclass
class OnboardingResult:
    merchant_id: str
    config_sections_set: list[str]
    channels_created: list[str]
    credentials_set: list[str]
    suppliers_created: int
    supplier_offers_created: int
    operator_api_key_id: str
    operator_api_key: str  # returned exactly once - never persisted or logged in the clear
    validation_warnings: list[str] = field(default_factory=list)


class ConfigValidationError(ValueError):
    pass


class MerchantOnboardingService:
    def __init__(self, store) -> None:
        self.store = store
        self.audit = AuditLedger(store)

    # --- Legacy Phase 1 entry point - kept for backward compatibility with existing workload scripts.

    def onboard_phase1(self, merchant_id: str, display_name: str, config: dict | None = None) -> int:
        merged = DEFAULT_PHASE1_CONFIG | (config or {})
        self.store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name=display_name, display_name=display_name))
        self.store.set_config(merchant_id, merged)
        self.store.put(Channel(id=f"{merchant_id}_shopify", merchant_id=merchant_id, type="shopify", name="Shopify", credential_ref="shopify_webhook_secret"))
        self.store.put(Channel(id=f"{merchant_id}_chatwoot", merchant_id=merchant_id, type="chatwoot", name="Chatwoot", credential_ref="chatwoot_webhook_secret"))
        self.audit.record(merchant_id=merchant_id, actor="operator", source="onboarding", action="merchant_onboarded_phase1", object_type="Merchant", object_id=merchant_id, result="configured")
        return self._count_values(merged) + 4

    # --- Phase 4.5: full onboarding - config + credentials + mappings, no application code changes ---

    def onboard(
        self,
        merchant_id: str,
        display_name: str,
        *,
        config: dict[str, Any],
        credentials: dict[str, str] | None = None,
        channels: list[dict[str, str]] | None = None,
        suppliers: list[dict[str, Any]] | None = None,
        procurement_service=None,
    ) -> OnboardingResult:
        """`config` must at minimum be able to supply `finance` and `procurement` sections (merged over
        the deterministic defaults above) alongside the Phase 1 sections (catalogue/support/returns/
        cancellations/refund policy/SLA). Configuration is VALIDATED before the merchant is activated -
        an invalid config raises ConfigValidationError and nothing is persisted.
        `suppliers`: [{"name": ..., "default_lead_time_days": ..., "offers": [{"sku":..., "supplier_sku":...,
        "cost":..., "currency":..., "moq":..., "pack_quantity":..., "lead_time_days":..., "preferred":...}]}]
        """
        merged = {
            **DEFAULT_PHASE1_CONFIG,
            **config,
            "finance": DEFAULT_FINANCE_CONFIG | config.get("finance", {}),
            "procurement": DEFAULT_PROCUREMENT_CONFIG | config.get("procurement", {}),
            "logistics": DEFAULT_LOGISTICS_CONFIG | config.get("logistics", {}),
        }
        warnings = self._validate_config(merged)
        errors = [w for w in warnings if w.startswith("ERROR:")]
        if errors:
            raise ConfigValidationError("; ".join(errors))

        self.store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name=display_name, display_name=display_name))
        self.store.set_config(merchant_id, merged)

        channels_created = []
        for ch in channels or [
            {"type": "shopify", "name": "Shopify", "credential_ref": "shopify_webhook_secret"},
            {"type": "chatwoot", "name": "Chatwoot", "credential_ref": "chatwoot_webhook_secret"},
        ]:
            channel_id = f"{merchant_id}_{ch['type']}"
            self.store.put(Channel(id=channel_id, merchant_id=merchant_id, type=ch["type"], name=ch["name"], credential_ref=ch.get("credential_ref")))
            channels_created.append(channel_id)

        credentials_set = []
        for ref, secret in (credentials or {}).items():
            self.store.set_credential_ref(merchant_id, ref, secret)
            credentials_set.append(ref)

        suppliers_created = 0
        offers_created = 0
        if suppliers and procurement_service is not None:
            for supplier_cfg in suppliers:
                supplier = procurement_service.upsert_supplier(
                    merchant_id, supplier_cfg["name"],
                    default_lead_time_days=int(supplier_cfg.get("default_lead_time_days", 7)),
                )
                suppliers_created += 1
                for offer in supplier_cfg.get("offers", []):
                    procurement_service.ingest_supplier_offer(
                        merchant_id, supplier.id,
                        sku=offer["sku"], supplier_sku=offer["supplier_sku"], cost=int(offer["cost"]),
                        currency=offer["currency"], moq=int(offer["moq"]), pack_quantity=int(offer["pack_quantity"]),
                        lead_time_days=int(offer["lead_time_days"]), preferred=bool(offer.get("preferred", False)),
                        evidence_ref=f"onboarding:{merchant_id}",
                    )
                    offers_created += 1

        key_id, raw_key = self.store.create_api_key(merchant_id=merchant_id, role="operator", label=f"{merchant_id}-onboarding")

        self.audit.record(
            merchant_id=merchant_id, actor="operator", source="onboarding", action="merchant_onboarded_v2",
            object_type="Merchant", object_id=merchant_id, result="activated",
        )
        return OnboardingResult(
            merchant_id=merchant_id,
            config_sections_set=sorted(merged.keys()),
            channels_created=channels_created,
            credentials_set=credentials_set,
            suppliers_created=suppliers_created,
            supplier_offers_created=offers_created,
            operator_api_key_id=key_id,
            operator_api_key=raw_key,
            validation_warnings=[w for w in warnings if not w.startswith("ERROR:")],
        )

    def _validate_config(self, config: dict[str, Any]) -> list[str]:
        """Deliberately not a full JSON-schema validator - checks the shapes that would otherwise
        silently break a running merchant (wrong type on a threshold, missing currency, an invalid
        Decision literal), returning ERROR-prefixed strings for anything that must block activation and
        plain warnings for anything merely worth flagging."""
        issues: list[str] = []

        currency = config.get("currency")
        if not isinstance(currency, str) or len(currency) != 3:
            issues.append(f"ERROR: currency must be a 3-letter ISO code, got {currency!r}")

        refund_policy = config.get("policy", {}).get("refund", {})
        if not isinstance(refund_policy.get("automatic_limit", 0), int):
            issues.append("ERROR: policy.refund.automatic_limit must be an int (minor currency units)")
        if refund_policy.get("above_limit") not in {None, "ALLOW", "REQUIRE_APPROVAL", "DENY"}:
            issues.append(f"ERROR: policy.refund.above_limit must be a valid Decision, got {refund_policy.get('above_limit')!r}")

        finance = config.get("finance", {})
        if not isinstance(finance.get("tolerances", {}), dict):
            issues.append("ERROR: finance.tolerances must be an object")
        if not isinstance(finance.get("expected_charges", {}), dict):
            issues.append("ERROR: finance.expected_charges must be an object")

        procurement = config.get("procurement", {})
        spending = procurement.get("spending", {})
        if not isinstance(spending.get("auto_approve_limit", 0), int):
            issues.append("ERROR: procurement.spending.auto_approve_limit must be an int")
        if spending.get("above_limit") not in {None, "ALLOW", "REQUIRE_APPROVAL", "DENY"}:
            issues.append(f"ERROR: procurement.spending.above_limit must be a valid Decision, got {spending.get('above_limit')!r}")
        priority = procurement.get("supplier_priority", [])
        valid_priority_terms = {"preferred", "cost", "lead_time_days", "lead_time", "moq", "reliability"}
        unknown_terms = [p for p in priority if p not in valid_priority_terms]
        if unknown_terms:
            issues.append(f"ERROR: procurement.supplier_priority contains unknown term(s) {unknown_terms}")
        threshold = procurement.get("supplier_reliability_threshold", 0.0)
        if not isinstance(threshold, (int, float)) or not (0.0 <= float(threshold) <= 1.0):
            issues.append(f"ERROR: procurement.supplier_reliability_threshold must be between 0.0 and 1.0, got {threshold!r}")

        if not config.get("enabled_modules", {}).get("orders"):
            issues.append("WARNING: orders module disabled - webhook ingestion will persist orders with no downstream processing")

        return issues

    def _count_values(self, value) -> int:
        if isinstance(value, dict):
            return sum(self._count_values(v) for v in value.values())
        if isinstance(value, list):
            return len(value)
        return 1
