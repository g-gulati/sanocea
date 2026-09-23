from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sanocea.packages.domain_contract.models import ProductDraft, ProvenanceClassification, now_utc
from sanocea.packages.product_onboarding.provenance import (
    PROTECTED_COMMERCIAL_FACTS,
    ZeroInventionPolicy,
    normalize_commercial_fact_value,
    sync_facts_to_extracted_attributes,
)
try:
    from sanocea.packages.product_onboarding.variants import VariantMatrixEngine
except ImportError:
    from packages.product_onboarding.variants import VariantMatrixEngine



@dataclass(frozen=True)
class PublicationDecision:
    outcome: str
    reasons: list[str]


class ProductCompletenessValidator:
    def __init__(self, store) -> None:
        self.store = store

    def validate(self, draft: ProductDraft) -> ProductDraft:
        existing_errors = [
            error for error in draft.validation_errors
            if not error.startswith("missing_required_attribute:") and not error.startswith("zero_invention_violation:")
        ]
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
                fact = draft.commercial_facts.get(field)
                if fact and fact.value not in (None, ""):
                    if field == "price":
                        val = normalize_commercial_fact_value("price", fact.value)
                        if val is not None and val > 0:
                            draft.price = val
                            value = val
                        else:
                            missing.append(field)
                    else:
                        value = fact.value
                        if hasattr(draft, field):
                            setattr(draft, field, value)
                        else:
                            draft.attributes[field] = value
                else:
                    missing.append(field)
                    if field not in draft.commercial_facts:
                        draft.commercial_facts[field] = ZeroInventionPolicy.create_missing_fact(field)
                    else:
                        draft.commercial_facts[field].classification = ProvenanceClassification.MISSING.value
                        draft.commercial_facts[field].value = None

        # Physical product inventory publication requirements
        is_physical = draft.attributes.get("requires_shipping", True) is not False and not draft.attributes.get("is_digital")
        enforce_inv = product_rules.get("enforce_physical_inventory") or "inventory_quantity" in required or draft.merchant_id.startswith("prospect_")

        if is_physical and enforce_inv:
            # If merchant explicitly chose track_inventory=False, that is an allowed deliberate policy choice
            if draft.attributes.get("track_inventory") is False:
                draft.commercial_facts.pop("inventory_quantity", None)
                draft.commercial_facts.pop("inventory_location", None)
            elif draft.attributes.get("inventory_quantity") is not None and draft.attributes.get("inventory_location") is not None:
                draft.attributes["inventory_confirmed"] = True
            elif not draft.attributes.get("inventory_confirmed"):
                if draft.attributes.get("inventory_quantity") is None:
                    missing.append("inventory_quantity")
                    if "inventory_quantity" not in draft.commercial_facts:
                        draft.commercial_facts["inventory_quantity"] = ZeroInventionPolicy.create_missing_fact("inventory_quantity")
                if not draft.attributes.get("inventory_location"):
                    missing.append("inventory_location")
                    if "inventory_location" not in draft.commercial_facts:
                        draft.commercial_facts["inventory_location"] = ZeroInventionPolicy.create_missing_fact("inventory_location")

        # Enforce Zero-Invention Policy on protected commercial facts
        zero_invention_errors = []
        for name, fact in draft.commercial_facts.items():
            if name in PROTECTED_COMMERCIAL_FACTS:
                if fact.classification in (ProvenanceClassification.AI_ENRICHED.value, ProvenanceClassification.AI_SUGGESTED.value):
                    zero_invention_errors.append(f"zero_invention_violation:{name}")

        # Identity fallback: If identity_status is UNRESOLVED but deterministic authoritative identifiers exist, mark RESOLVED
        if draft.identity_status == "UNRESOLVED":
            if draft.sku or draft.product_id:
                draft.identity_status = "RESOLVED"
                draft.identity_key = f"sku:{draft.sku}" if draft.sku else f"product_id:{draft.product_id}"

        # Stage 4 Amendment 6: Validate variant matrix if variants are present
        if draft.variants:
            variant_engine = VariantMatrixEngine()
            variant_conflicts = variant_engine.validate_variant_matrix(draft)
            if variant_conflicts:
                draft.conflicts = list(set(draft.conflicts + variant_conflicts))

        conflicts = self._detect_conflicts(draft)
        draft.validation_errors = existing_errors + [f"missing_required_attribute:{field}" for field in missing] + zero_invention_errors
        draft.conflicts = conflicts
        if any(error == "invalid_price" for error in draft.validation_errors) or zero_invention_errors:
            draft.state = "INVALID"
        elif conflicts:
            draft.state = "CONFLICTED"
        elif missing:
            draft.state = "INCOMPLETE"
        elif any(not attr.approved and not attr.verified for attr in draft.extracted_attributes) or any(not fact.approved and not fact.verified for fact in draft.commercial_facts.values()):
            draft.state = "NEEDS_APPROVAL"
        else:
            draft.state = "READY"
        if draft.state == "NEEDS_APPROVAL" and self._trusted_evidence_can_be_verified(draft):
            for attr in draft.extracted_attributes:
                attr.verified = True
            for fact in draft.commercial_facts.values():
                fact.verified = True
            draft.state = "READY"
        sync_facts_to_extracted_attributes(draft)
        self.store.put(draft)
        return draft

    def apply_publication_policy(self, draft: ProductDraft) -> PublicationDecision:
        config = self.store.get_config(draft.merchant_id)
        publication = config.get("publication", {})
        exceptions: list[str] = []
        # Stage 4 Amendment 2: Strict orthogonal check on identity_status
        if draft.identity_status != "RESOLVED":
            exceptions.append(f"unresolved_product_identity:{draft.identity_status}")
            if draft.identity_conflict_reason:
                exceptions.append(draft.identity_conflict_reason)
        if draft.state != "READY":
            exceptions.append(f"draft_state:{draft.state}")
        if draft.validation_errors or draft.conflicts:
            exceptions.extend(draft.validation_errors + draft.conflicts)
        if any(fact.conflicted for fact in draft.commercial_facts.values()):
            exceptions.append("unresolved_commercial_fact_conflicts")
        for name, fact in draft.commercial_facts.items():
            if name in PROTECTED_COMMERCIAL_FACTS:
                if fact.classification in (ProvenanceClassification.AI_ENRICHED.value, ProvenanceClassification.AI_SUGGESTED.value):
                    exceptions.append(f"zero_invention_violation:{name}")
                if fact.classification == ProvenanceClassification.MISSING.value:
                    if name in ("inventory_quantity", "inventory_location") and draft.attributes.get("track_inventory") is False:
                        continue
                    exceptions.append(f"missing_protected_fact:{name}")
        if not draft.sku:
            exceptions.append("missing_sku")
        if not self._unique_sku(draft):
            exceptions.append("duplicate_sku")
        if draft.price is None or draft.price <= 0:
            exceptions.append("invalid_price")
        if not draft.currency:
            exceptions.append("missing_currency")
        if "internal_only_field" in draft.attributes:
            exceptions.append("internal_only_field")

        is_physical = draft.attributes.get("requires_shipping", True) is not False and not draft.attributes.get("is_digital")
        product_rules = config.get("product_rules", {})
        enforce_inv = product_rules.get("enforce_physical_inventory") or draft.merchant_id.startswith("prospect_")
        if is_physical and enforce_inv and draft.attributes.get("track_inventory") is not False:
            if not draft.attributes.get("inventory_confirmed") or draft.attributes.get("inventory_quantity") is None:
                exceptions.append("unconfirmed_inventory_policy")

        if exceptions:
            return PublicationDecision("EXCEPTION", exceptions)

        if publication.get("require_approval", True):
            return PublicationDecision("REQUIRE_APPROVAL", ["merchant_requires_publication_approval"])
        auto_categories = set(publication.get("auto_publish_categories") or [])
        if auto_categories and (draft.category or draft.product_type) not in auto_categories:
            return PublicationDecision("REQUIRE_APPROVAL", ["category_not_auto_publishable"])
        max_price = publication.get("auto_publish_max_price")
        if max_price is not None and draft.price > int(max_price):
            return PublicationDecision("REQUIRE_APPROVAL", ["price_above_auto_publish_threshold"])
        if any(not attr.approved and not attr.verified for attr in draft.extracted_attributes) or any(not fact.approved and not fact.verified for fact in draft.commercial_facts.values()):
            return PublicationDecision("REQUIRE_APPROVAL", ["unapproved_extracted_facts"])
        draft.approved_for_publication = True
        self.store.put(draft)
        return PublicationDecision("AUTO_PUBLISH", ["clean_verified_product"])

    def approve_extracted_facts(self, draft: ProductDraft, actor: str) -> ProductDraft:
        for attr in draft.extracted_attributes:
            attr.approved = True
        for fact in draft.commercial_facts.values():
            if not fact.conflicted:
                fact.approved = True
                fact.approved_by = actor
                fact.approved_at = now_utc()
        draft.approved_by = actor
        draft.approved_at = now_utc()
        return self.validate(draft)

    def approve_publication(self, draft: ProductDraft, actor: str) -> ProductDraft:
        if draft.identity_status != "RESOLVED":
            raise ValueError(
                f"Cannot approve product draft {draft.id} for publication: identity is {draft.identity_status} "
                f"({draft.identity_conflict_reason or 'unresolved'})"
            )
        for attr in draft.extracted_attributes:
            attr.approved = True
        for fact in draft.commercial_facts.values():
            if not fact.conflicted:
                fact.approved = True
                fact.approved_by = actor
                fact.approved_at = now_utc()
        draft.state = "READY"
        draft.approved_for_publication = True
        draft.approved_by = actor
        draft.approved_at = now_utc()
        self.store.put(draft)
        return draft

    def _detect_conflicts(self, draft: ProductDraft) -> list[str]:
        conflicts = set()
        for c in draft.conflicts:
            conflicts.add(c)
        for fact_name, fact in draft.commercial_facts.items():
            if fact.conflicted:
                conflicts.add(f"conflicting_product_evidence:{fact_name}")
        values = defaultdict(set)
        for attr in draft.extracted_attributes:
            if attr.value not in (None, ""):
                fact = draft.commercial_facts.get(attr.name)
                if fact and not fact.conflicted and fact.approved:
                    continue
                values[attr.name].add(self._normalize_value(attr.name, attr.value))
        for name, observed in values.items():
            if len(observed) > 1:
                conflicts.add(f"conflicting_product_evidence:{name}")
        return sorted(list(conflicts))

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
