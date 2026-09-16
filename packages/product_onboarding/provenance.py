from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sanocea.packages.domain_contract.models import (
    CommercialFact,
    ExtractedAttribute,
    ProductDraft,
    ProvenanceClassification,
    now_utc,
)

# Commercial facts where ABSENCE OF EVIDENCE MUST NEVER RESULT IN AI INFERENCE.
PROTECTED_COMMERCIAL_FACTS: set[str] = {
    "sku",
    "barcode",
    "gtin",
    "title",
    "brand",
    "price",
    "compare_at_price",
    "cost_price",
    "gst_rate",
    "tax_rate",
    "hsn",
    "hsn_code",
    "country_of_origin",
    "material",
    "composition",
    "weight",
    "weight_grams",
    "package_weight",
    "dimensions",
    "length",
    "width",
    "height",
    "inventory_quantity",
    "compliance_claims",
    "manufacturer",
    "importer",
    "expiry_date",
    "shelf_life",
}

# Fields where creative AI enrichment or taxonomy suggestions are permitted
AI_PERMITTED_FIELDS: set[str] = {
    "description",
    "bullet_points",
    "seo_title",
    "seo_description",
    "tags",
    "product_type",
    "category_suggestion",
}


class ZeroInventionViolationError(ValueError):
    """Raised when an automated system, heuristic, or AI model attempts to invent, infer,
    or guess a protected commercial fact in the absence of authoritative source evidence."""
    pass


class ConflictResolutionError(ValueError):
    """Raised when attempting to resolve a conflict with invalid or unauthorized input."""
    pass


def normalize_commercial_fact_value(name: str, value: Any) -> Any:
    """Deterministically normalizes a commercial fact value for comparison and canonical representation.
    Preserves exact provenance while eliminating trivial formatting differences (e.g. casing, units, whitespace).
    """
    if value is None:
        return None

    name_lower = name.strip().lower()

    # Price normalization: "$499.00", "499.00", "₹499", "1,49,999.00", "1.499,00 €" -> int cents
    if name_lower in {"price", "compare_at_price", "cost_price", "retail_price"}:
        if isinstance(value, (int, float)):
            return int(round(float(value) * 100)) if float(value) < 100000 and not isinstance(value, int) else int(value)
        val_str = str(value).strip()
        # Detect European formatting (dot thousands separator, comma decimal separator)
        if re.search(r"\d+\.\d{3},\d{1,2}", val_str) or ("," in val_str and "." not in val_str and re.search(r",\d{1,2}$", val_str)):
            val_str = val_str.replace(".", "").replace(",", ".")
        else:
            # US / Indian formatting: strip commas (e.g. 1,49,999.00 -> 149999.00)
            val_str = val_str.replace(",", "")
        cleaned = re.sub(r"[^\d.]", "", val_str)
        if not cleaned:
            return None
        return int(round(float(cleaned) * 100))

    # Weight normalization: "850 g", "0.85 kg", "850" -> grams as float
    if name_lower in {"weight", "weight_grams", "package_weight"}:
        if isinstance(value, (int, float)):
            return float(value)
        val_str = str(value).strip().lower()
        if "kg" in val_str:
            num = re.sub(r"[^\d.]", "", val_str)
            return float(num) * 1000 if num else None
        if "g" in val_str or "gm" in val_str:
            num = re.sub(r"[^\d.]", "", val_str)
            return float(num) if num else None
        num = re.sub(r"[^\d.]", "", val_str)
        return float(num) if num else None

    # Dimensions normalization: "10x20x30 cm", "10 x 20 x 30" (missing unit)
    if name_lower in {"dimensions", "dimension"}:
        if isinstance(value, dict):
            return {k.lower(): float(v) if isinstance(v, (int, float)) else str(v) for k, v in value.items()}
        val_str = str(value).strip().lower()
        m = re.match(r"([\d.]+)\s*[xX*]\s*([\d.]+)\s*[xX*]\s*([\d.]+)\s*([a-zA-Z]*)", val_str)
        if m:
            l, w, h, unit = m.groups()
            return {"length": float(l), "width": float(w), "height": float(h), "unit": unit.strip() if unit.strip() else None}
        return val_str

    # Colour normalization
    if name_lower in {"colour", "color"}:
        val_str = str(value).strip().lower()
        aliases = {
            "navy blue": "Navy",
            "navy": "Navy",
            "blue": "Blue",
            "grey": "Grey",
            "gray": "Grey",
            "charcoal grey": "Charcoal",
            "black": "Black",
            "white": "White",
            "red": "Red",
        }
        return aliases.get(val_str, val_str.title())

    # Size normalization
    if name_lower in {"size", "size_label"}:
        val_str = str(value).strip().lower()
        aliases = {
            "extra large": "XL",
            "x-large": "XL",
            "one size": "One Size",
            "onesize": "One Size",
            "small": "S",
            "medium": "M",
            "large": "L",
        }
        return aliases.get(val_str, val_str.upper() if val_str in {"xs", "s", "m", "l", "xl", "xxl"} else val_str.title())

    # HSN code normalization
    if name_lower in {"hsn", "hsn_code"}:
        val_str = re.sub(r"[^\d]", "", str(value).strip())
        return val_str if val_str else None

    # Tax / GST rate normalization: "18%", "0.18", 18 -> 18.0
    if name_lower in {"gst_rate", "tax_rate"}:
        if isinstance(value, (int, float)):
            return float(value) * 100 if 0 < float(value) < 1 else float(value)
        val_str = str(value).strip().replace("%", "")
        if not val_str:
            return None
        f = float(val_str)
        return f * 100 if 0 < f < 1 else f

    if isinstance(value, str):
        return value.strip()

    return value


class ZeroInventionPolicy:
    """Enforces that protected commercial facts cannot be synthesized, inferred, or hallucinated."""

    @staticmethod
    def validate_fact_origin(name: str, value: Any, classification: str, extractor: str) -> None:
        name_clean = name.strip().lower()
        if name_clean in PROTECTED_COMMERCIAL_FACTS:
            if classification in (ProvenanceClassification.AI_ENRICHED, ProvenanceClassification.AI_SUGGESTED):
                raise ZeroInventionViolationError(
                    f"Zero-Invention Violation: Protected commercial fact '{name}' cannot be generated or enriched by AI."
                )
            if extractor.lower() in ("ai", "llm", "inferred", "gpt", "gemini", "claude"):
                raise ZeroInventionViolationError(
                    f"Zero-Invention Violation: Protected commercial fact '{name}' cannot be produced by extractor '{extractor}'."
                )

    @staticmethod
    def create_missing_fact(name: str, reason: str = "Absent from all merchant sources") -> CommercialFact:
        return CommercialFact(
            name=name,
            value=None,
            source="system:policy",
            locator={"status": "not_found"},
            evidence_ref="",
            classification=ProvenanceClassification.MISSING.value,
            confidence=0.0,
            metadata={"missing_reason": reason, "required_action": "MERCHANT_INPUT"},
        )


class CommercialAIEnricher:
    """Provides bounded AI enrichment for approved marketing/copy fields only.
    Strictly forbids generating or overriding protected commercial facts.
    """

    def enrich_field(self, draft: ProductDraft, field_name: str, enriched_value: Any, model_id: str = "mock-llm-enricher") -> CommercialFact:
        field_clean = field_name.strip().lower()
        if field_clean in PROTECTED_COMMERCIAL_FACTS:
            raise ZeroInventionViolationError(
                f"AI Enrichment Prohibited: Field '{field_name}' is a protected commercial fact and cannot be AI-enriched."
            )
        if field_clean not in AI_PERMITTED_FIELDS and not field_clean.startswith("seo_"):
            raise ZeroInventionViolationError(
                f"AI Enrichment Not Permitted: Field '{field_name}' is not in the approved AI enrichment catalog."
            )

        fact = CommercialFact(
            name=field_name,
            value=enriched_value,
            source=f"ai:{model_id}",
            locator={"model": model_id, "prompt": f"enrich_{field_name}", "timestamp": datetime.now(timezone.utc).isoformat()},
            evidence_ref=f"ai://{model_id}/{field_name}",
            classification=ProvenanceClassification.AI_ENRICHED.value,
            confidence=0.85,
            metadata={"ai_model": model_id, "requires_approval": True},
        )
        draft.commercial_facts[field_name] = fact
        draft.attributes[field_name] = enriched_value

        # Mirror into extracted_attributes for backward compatibility
        draft.extracted_attributes.append(
            ExtractedAttribute(
                name=field_name,
                value=enriched_value,
                source_file=fact.source,
                source_locator=fact.locator,
                evidence_ref=fact.evidence_ref,
                confidence=fact.confidence,
                extractor="ai_enricher",
                verified=False,
                approved=False,
            )
        )
        return fact


def detect_and_merge_fact(
    draft: ProductDraft,
    incoming: CommercialFact,
) -> None:
    """Merges an incoming CommercialFact into the draft. If an existing fact has a different
    normalized value, a CONFLICT is recorded with exact provenance locators from both sources.
    """
    ZeroInventionPolicy.validate_fact_origin(
        incoming.name, incoming.value, incoming.classification, incoming.metadata.get("extractor", "structured")
    )

    name = incoming.name
    norm_incoming = normalize_commercial_fact_value(name, incoming.value)

    if name not in draft.commercial_facts:
        draft.commercial_facts[name] = incoming
        return

    existing = draft.commercial_facts[name]
    norm_existing = normalize_commercial_fact_value(name, existing.value)

    # If existing fact was MISSING, incoming authoritative value supersedes it
    if existing.classification == ProvenanceClassification.MISSING.value and norm_incoming is not None:
        draft.commercial_facts[name] = incoming
        return

    # If incoming value is None or empty, preserve existing fact
    if norm_incoming is None:
        return

    # Compare normalized values
    if norm_existing != norm_incoming:
        # CONFLICT DETECTED
        existing.conflicted = True
        conflict_entry_1 = {
            "source": existing.source,
            "locator": existing.locator,
            "value": existing.value,
            "normalized": norm_existing,
            "evidence_ref": existing.evidence_ref,
        }
        conflict_entry_2 = {
            "source": incoming.source,
            "locator": incoming.locator,
            "value": incoming.value,
            "normalized": norm_incoming,
            "evidence_ref": incoming.evidence_ref,
        }
        if not existing.conflict_sources:
            existing.conflict_sources.append(conflict_entry_1)
        existing.conflict_sources.append(conflict_entry_2)

        conflict_key = f"conflicting_product_evidence:{name}"
        if conflict_key not in draft.conflicts:
            draft.conflicts.append(conflict_key)
        draft.conflict_details[name] = existing.conflict_sources
        draft.state = "CONFLICTED"
    else:
        # Values agree - augment provenance metadata with additional confirming source
        existing.metadata.setdefault("confirming_sources", []).append({
            "source": incoming.source,
            "locator": incoming.locator,
            "evidence_ref": incoming.evidence_ref,
        })


def resolve_fact_conflict(
    draft: ProductDraft,
    fact_name: str,
    chosen_value: Any,
    chosen_source: str,
    actor: str,
    resolution_note: str | None = None,
) -> ProductDraft:
    """Resolves an active fact conflict with explicit human sign-off.
    The decision becomes an immutable part of the commercial fact's provenance history.
    """
    if fact_name not in draft.commercial_facts:
        raise ConflictResolutionError(f"Fact '{fact_name}' does not exist on draft {draft.id}")

    fact = draft.commercial_facts[fact_name]
    if not fact.conflicted and f"conflicting_product_evidence:{fact_name}" not in draft.conflicts:
        raise ConflictResolutionError(f"Fact '{fact_name}' is not in conflict state.")

    # Record resolution
    fact.value = chosen_value
    fact.source = chosen_source
    fact.conflicted = False
    fact.classification = ProvenanceClassification.HUMAN_APPROVED.value
    fact.approved = True
    fact.approved_by = actor
    fact.approved_at = now_utc()
    fact.resolution_note = resolution_note or f"Resolved by {actor} selecting {chosen_source}"

    # Update draft core attribute if applicable
    norm_val = normalize_commercial_fact_value(fact_name, chosen_value)
    if hasattr(draft, fact_name):
        if fact_name == "price" and norm_val is not None:
            setattr(draft, fact_name, norm_val)
        else:
            setattr(draft, fact_name, chosen_value)
    draft.attributes[fact_name] = chosen_value

    # Remove conflict flag
    conflict_key = f"conflicting_product_evidence:{fact_name}"
    if conflict_key in draft.conflicts:
        draft.conflicts.remove(conflict_key)
    draft.conflict_details.pop(fact_name, None)

    # Sync into extracted_attributes
    for attr in draft.extracted_attributes:
        if attr.name == fact_name:
            attr.value = chosen_value
            attr.approved = True

    return draft


def sync_facts_to_extracted_attributes(draft: ProductDraft) -> None:
    """Synchronizes commercial_facts dictionary into extracted_attributes list for 100% backward compatibility."""
    existing_by_name = {attr.name: attr for attr in draft.extracted_attributes}
    for name, fact in draft.commercial_facts.items():
        if name in existing_by_name:
            attr = existing_by_name[name]
            attr.value = fact.value
            attr.approved = fact.approved
            attr.verified = fact.verified
        else:
            draft.extracted_attributes.append(
                ExtractedAttribute(
                    name=name,
                    value=fact.value,
                    source_file=fact.source,
                    source_locator=fact.locator,
                    evidence_ref=fact.evidence_ref,
                    confidence=fact.confidence,
                    extractor=fact.metadata.get("extractor", "structured"),
                    verified=fact.verified,
                    approved=fact.approved,
                )
            )
