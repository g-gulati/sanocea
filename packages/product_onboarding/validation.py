from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sanocea.packages.domain_contract.models import ProductDraft


@dataclass(frozen=True)
class PublicationDecision:
    outcome: str
    reasons: list[str]


class ProductCompletenessValidator:
    def __init__(self, store) -> None:
        self.store = store

    def validate(self, draft: ProductDraft) -> ProductDraft:
        existing_errors = [error for error in draft.validation_errors if not error.startswith("missing_required_attribute:")]
        self.apply_deterministic_mappings(draft)
        config = self.store.get_config(draft.merchant_id)
        product_rules = config.get("product_rules", {})
        required = list(product_rules.get("required", ["sku", "title", "price", "currency", "product_type"]))
        category = draft.category or draft.product_type or "default"
        required += list(product_rules.get("category_profiles", {}).get(category, []))
        missing: list[str] = []
        for field in required:
            value = getattr(draft, field, None) if hasattr(draft, field) else draft.attributes.get(field)
            if value in (None, ""):
                missing.append(field)
        conflicts = self._detect_conflicts(draft)
        draft.validation_errors = existing_errors + [f"missing_required_attribute:{field}" for field in missing]
        draft.conflicts = conflicts
        if any(error == "invalid_price" for error in draft.validation_errors):
            draft.state = "INVALID"
        elif conflicts:
            draft.state = "CONFLICTED"
        elif missing:
            draft.state = "INCOMPLETE"
        elif any(not attr.approved and not attr.verified for attr in draft.extracted_attributes):
            draft.state = "NEEDS_APPROVAL"
        else:
            draft.state = "READY"
        if draft.state == "NEEDS_APPROVAL" and self._trusted_evidence_can_be_verified(draft):
            for attr in draft.extracted_attributes:
                attr.verified = True
            draft.state = "READY"
        self.store.put(draft)
        return draft

    def apply_publication_policy(self, draft: ProductDraft) -> PublicationDecision:
        config = self.store.get_config(draft.merchant_id)
        publication = config.get("publication", {})
        if publication.get("require_approval", True):
            return PublicationDecision("REQUIRE_APPROVAL", ["merchant_requires_publication_approval"])
        if draft.state != "READY":
            return PublicationDecision("EXCEPTION", [f"draft_state:{draft.state}"])
        if draft.validation_errors or draft.conflicts:
            return PublicationDecision("EXCEPTION", draft.validation_errors + draft.conflicts)
        if not draft.sku:
            return PublicationDecision("EXCEPTION", ["missing_sku"])
        if not self._unique_sku(draft):
            return PublicationDecision("EXCEPTION", ["duplicate_sku"])
        if draft.price is None or draft.price <= 0:
            return PublicationDecision("EXCEPTION", ["invalid_price"])
        if not draft.currency:
            return PublicationDecision("EXCEPTION", ["missing_currency"])
        # A platform-neutral rule: an internal-only field that leaked into extracted attributes (e.g. a
        # supplier's internal margin figure) must never reach ANY storefront, regardless of which
        # connector eventually publishes this draft - not a Shopify-specific constraint. Named
        # "internal_only_field" (not e.g. "unsupported_shopify_field", its pre-multi-platform name) per
        # docs/architecture/multi-platform-connector-hardening.md closure item 2.
        if "internal_only_field" in draft.attributes:
            return PublicationDecision("EXCEPTION", ["internal_only_field"])
        auto_categories = set(publication.get("auto_publish_categories") or [])
        if auto_categories and (draft.category or draft.product_type) not in auto_categories:
            return PublicationDecision("REQUIRE_APPROVAL", ["category_not_auto_publishable"])
        max_price = publication.get("auto_publish_max_price")
        if max_price is not None and draft.price > int(max_price):
            return PublicationDecision("REQUIRE_APPROVAL", ["price_above_auto_publish_threshold"])
        if any(not attr.approved and not attr.verified for attr in draft.extracted_attributes):
            return PublicationDecision("REQUIRE_APPROVAL", ["unapproved_extracted_facts"])
        draft.approved_for_publication = True
        self.store.put(draft)
        return PublicationDecision("AUTO_PUBLISH", ["clean_verified_product"])

    def approve_extracted_facts(self, draft: ProductDraft, actor: str) -> ProductDraft:
        for attr in draft.extracted_attributes:
            attr.approved = True
        draft.approved_by = actor
        from sanocea.packages.domain_contract.models import now_utc

        draft.approved_at = now_utc()
        return self.validate(draft)

    def approve_publication(self, draft: ProductDraft, actor: str) -> ProductDraft:
        draft.approved_for_publication = True
        draft.approved_by = actor
        from sanocea.packages.domain_contract.models import now_utc

        draft.approved_at = now_utc()
        self.store.put(draft)
        return draft

    def _detect_conflicts(self, draft: ProductDraft) -> list[str]:
        values = defaultdict(set)
        for attr in draft.extracted_attributes:
            if attr.value not in (None, ""):
                values[attr.name].add(self._normalize_value(attr.name, attr.value))
        return [f"conflicting_product_evidence:{name}" for name, observed in values.items() if len(observed) > 1]

    def apply_deterministic_mappings(self, draft: ProductDraft) -> ProductDraft:
        for key in ("colour", "color"):
            if key in draft.attributes:
                draft.attributes["colour"] = self._display_colour(draft.attributes.pop(key))
        if "size" in draft.attributes:
            draft.attributes["size"] = self._display_size(draft.attributes["size"])
        for attr in draft.extracted_attributes:
            if attr.name == "color":
                attr.name = "colour"
            if attr.name == "colour":
                attr.value = self._display_colour(attr.value)
            if attr.name == "size":
                attr.value = self._display_size(attr.value)
        return draft

    def _trusted_evidence_can_be_verified(self, draft: ProductDraft) -> bool:
        config = self.store.get_config(draft.merchant_id)
        profiles = config.get("supplier_profiles", {})
        if not profiles:
            return False
        for attr in draft.extracted_attributes:
            if attr.approved or attr.verified:
                continue
            source = attr.source_file.lower()
            matched = [
                profile
                for profile in profiles.values()
                if any(marker.lower() in source for marker in profile.get("source_markers", []))
            ]
            if not matched:
                return False
            if not any(attr.name in set(profile.get("trusted_fields", [])) for profile in matched):
                return False
            if attr.confidence < 1.0:
                return False
        return True

    def _unique_sku(self, draft: ProductDraft) -> bool:
        return "duplicate_sku_evidence" not in draft.validation_errors

    def _normalize_value(self, name: str, value) -> str:
        if name in {"colour", "color"}:
            return self._display_colour(value).lower()
        if name == "size":
            return self._display_size(value).lower()
        return str(value).strip().lower()

    def _display_colour(self, value) -> str:
        raw = str(value).strip()
        aliases = {
            "navy blue": "Navy",
            "navy": "Navy",
            "blue": "Blue",
            "grey": "Grey",
            "gray": "Grey",
            "charcoal grey": "Charcoal",
        }
        return aliases.get(raw.lower(), raw.title())

    def _display_size(self, value) -> str:
        raw = str(value).strip()
        aliases = {"extra large": "XL", "x-large": "XL", "one size": "One Size", "onesize": "One Size"}
        return aliases.get(raw.lower(), raw.upper() if raw.lower() in {"xs", "s", "m", "l", "xl"} else raw)
