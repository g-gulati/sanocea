from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Literal

try:
    from sanocea.packages.domain_contract.models import (
        IdentityDecision,
        ProductDraft,
        new_id,
        now_utc,
    )
except ImportError:
    from packages.domain_contract.models import (
        IdentityDecision,
        ProductDraft,
        new_id,
        now_utc,
    )


def compute_normalized_similarity(text_a: str | None, text_b: str | None) -> float:
    """Computes normalized text similarity ratio between two titles or descriptions."""
    if not text_a or not text_b:
        return 0.0
    norm_a = re.sub(r"[^\w\s]", " ", text_a.lower())
    norm_a = re.sub(r"\s+", " ", norm_a).strip()
    norm_b = re.sub(r"[^\w\s]", " ", text_b.lower())
    norm_b = re.sub(r"\s+", " ", norm_b).strip()
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


class IdentityDecisionService:
    """Durable, merchant-scoped human identity decision management.
    Preserves operator SAME/DIFFERENT decisions. Scoped strictly to merchant_id
    to prevent cross-tenant identity leakage (Stage 4 Amendment 4).
    """

    def __init__(self, store) -> None:
        self.store = store

    def record_decision(
        self,
        merchant_id: str,
        source_identifier_a: str,
        source_identifier_b: str,
        decision: Literal["SAME", "DIFFERENT"],
        canonical_id: str | None = None,
        decided_by: str = "operator",
        notes: str | None = None,
    ) -> IdentityDecision:
        record = IdentityDecision(
            merchant_id=merchant_id,
            source_identifier_a=source_identifier_a.strip(),
            source_identifier_b=source_identifier_b.strip(),
            decision=decision,
            canonical_id=canonical_id,
            decided_by=decided_by,
            notes=notes,
        )
        self.store.put(record)
        return record

    def get_decision(
        self,
        merchant_id: str,
        id_a: str,
        id_b: str,
    ) -> IdentityDecision | None:
        """Finds any prior decision between two identifiers (order-independent) for this merchant."""
        norm_a = id_a.strip()
        norm_b = id_b.strip()
        decisions = self.store.list(IdentityDecision, merchant_id)
        for d in reversed(decisions):
            if (d.source_identifier_a == norm_a and d.source_identifier_b == norm_b) or (
                d.source_identifier_a == norm_b and d.source_identifier_b == norm_a
            ):
                return d
        return None

    def are_same(self, merchant_id: str, id_a: str, id_b: str) -> bool:
        d = self.get_decision(merchant_id, id_a, id_b)
        return d is not None and d.decision == "SAME"

    def are_different(self, merchant_id: str, id_a: str, id_b: str) -> bool:
        d = self.get_decision(merchant_id, id_a, id_b)
        return d is not None and d.decision == "DIFFERENT"


class ProductIdentityResolver:
    """Product Identity Resolution Engine.
    Strictly adheres to Stage 4 Amendment 1:
    - Fuzzy evidence (brand + normalized title, Levenshtein/semantic similarity)
      generates identity_candidates ONLY, NEVER automatically marks RESOLVED.
    - Automatic resolution requires merchant-scoped deterministic authoritative
      identifiers (style_code/parent_sku, unique barcode/GTIN, deterministic SKU)
      or prior durable human SAME decisions.
    - Ambiguities and collisions (duplicate barcodes across distinct styles)
      fail closed into AMBIGUOUS or CONFLICT status.
    """

    def __init__(self, store, decision_service: IdentityDecisionService | None = None) -> None:
        self.store = store
        self.decision_service = decision_service or IdentityDecisionService(store)

    def extract_identifiers(self, draft: ProductDraft) -> dict[str, str]:
        """Extracts all authoritative identifiers from a product draft."""
        identifiers: dict[str, str] = {}
        if draft.sku:
            identifiers["sku"] = draft.sku.strip()
        if draft.product_id:
            identifiers["product_id"] = draft.product_id.strip()

        # Check attributes and commercial facts
        for key in ("style_id", "style_code", "parent_sku", "model_number", "barcode", "upc", "ean", "gtin"):
            val = draft.attributes.get(key)
            if val is None and key in draft.commercial_facts:
                val = draft.commercial_facts[key].value
            if val is not None and str(val).strip():
                identifiers[key] = str(val).strip()

        return identifiers

    def resolve_draft(
        self,
        draft: ProductDraft,
        existing_drafts: list[ProductDraft],
    ) -> ProductDraft:
        """Resolves identity for a single draft against existing drafts for the same merchant."""
        merchant_id = draft.merchant_id
        identifiers = self.extract_identifiers(draft)
        primary_sku = identifiers.get("sku")
        barcode = identifiers.get("barcode") or identifiers.get("upc") or identifiers.get("ean") or identifiers.get("gtin")
        style_code = identifiers.get("style_id") or identifiers.get("style_code") or identifiers.get("parent_sku") or identifiers.get("model_number")

        # 1. Check prior durable human decisions
        for existing in existing_drafts:
            if existing.id == draft.id:
                continue
            existing_ids = self.extract_identifiers(existing)
            # Check pairwise identifier decisions
            for id_type_a, id_val_a in identifiers.items():
                for id_type_b, id_val_b in existing_ids.items():
                    decision = self.decision_service.get_decision(merchant_id, id_val_a, id_val_b)
                    if decision:
                        if decision.decision == "SAME":
                            draft.identity_status = "RESOLVED"
                            draft.identity_key = f"decision:{decision.id}"
                            draft.product_id = decision.canonical_id or existing.product_id or existing.id
                            return draft
                        elif decision.decision == "DIFFERENT":
                            # Explicitly recorded different - forbid merging on this pair
                            pass

        # 2. Check Barcode Collision Invariant
        # If barcode is present, verify it is not already used by a DIFFERENT product/style
        if barcode:
            for existing in existing_drafts:
                if existing.id == draft.id:
                    continue
                exist_ids = self.extract_identifiers(existing)
                exist_barcode = exist_ids.get("barcode") or exist_ids.get("upc") or exist_ids.get("ean") or exist_ids.get("gtin")
                if exist_barcode == barcode:
                    # Barcode matches! Is it genuinely the same style or a conflicting product?
                    exist_style = exist_ids.get("style_id") or exist_ids.get("style_code") or exist_ids.get("parent_sku")
                    if style_code and exist_style and style_code != exist_style:
                        draft.identity_status = "CONFLICT"
                        draft.identity_conflict_reason = (
                            f"Barcode collision: barcode '{barcode}' is already associated with "
                            f"distinct style '{exist_style}' (draft {existing.id})"
                        )
                        return draft
                    # Check if human marked them DIFFERENT
                    if primary_sku and exist_ids.get("sku") and self.decision_service.are_different(merchant_id, primary_sku, exist_ids["sku"]):
                        draft.identity_status = "CONFLICT"
                        draft.identity_conflict_reason = (
                            f"Barcode collision: barcode '{barcode}' matches draft {existing.id} "
                            f"which was explicitly marked DIFFERENT by human decision"
                        )
                        return draft

        # 3. Deterministic Authoritative Resolution
        if style_code:
            # Check for conflicting human decision
            is_blocked = False
            for existing in existing_drafts:
                if existing.id == draft.id:
                    continue
                exist_ids = self.extract_identifiers(existing)
                if exist_ids.get("style_code") == style_code or exist_ids.get("style_id") == style_code:
                    if primary_sku and exist_ids.get("sku") and self.decision_service.are_different(merchant_id, primary_sku, exist_ids["sku"]):
                        is_blocked = True
                        break
            if not is_blocked:
                draft.identity_status = "RESOLVED"
                draft.identity_key = f"style:{style_code}"
                draft.product_id = draft.product_id or style_code
                return draft
            else:
                draft.identity_status = "CONFLICT"
                draft.identity_conflict_reason = f"Style code '{style_code}' blocked by prior DIFFERENT decision"
                return draft

        if barcode:
            draft.identity_status = "RESOLVED"
            draft.identity_key = f"barcode:{barcode}"
            draft.product_id = draft.product_id or f"prod_barcode_{barcode}"
            return draft

        if primary_sku:
            # Check if SKU matches an existing draft
            matching_existing = [
                e for e in existing_drafts
                if e.id != draft.id and e.sku == primary_sku
            ]
            if matching_existing:
                # Same SKU
                exist = matching_existing[0]
                if self.decision_service.are_different(merchant_id, primary_sku, exist.id):
                    draft.identity_status = "CONFLICT"
                    draft.identity_conflict_reason = f"SKU '{primary_sku}' blocked by prior DIFFERENT decision"
                    return draft
                draft.identity_status = "RESOLVED"
                draft.identity_key = f"sku:{primary_sku}"
                draft.product_id = exist.product_id or exist.id
                return draft
            else:
                draft.identity_status = "RESOLVED"
                draft.identity_key = f"sku:{primary_sku}"
                draft.product_id = draft.product_id or f"prod_sku_{primary_sku}"
                return draft

        # 4. No authoritative identifier present - generate Fuzzy Candidates ONLY (Amendment 1)
        candidates: list[dict[str, Any]] = []
        if draft.title:
            for existing in existing_drafts:
                if existing.id == draft.id or not existing.title:
                    continue
                # Check if prior human decision marked DIFFERENT
                exist_id = existing.sku or existing.id
                draft_id = draft.sku or draft.id
                if self.decision_service.are_different(merchant_id, draft_id, exist_id):
                    continue

                sim = compute_normalized_similarity(draft.title, existing.title)
                if sim >= 0.70:
                    candidates.append({
                        "candidate_id": existing.id,
                        "candidate_sku": existing.sku,
                        "candidate_title": existing.title,
                        "confidence": round(sim, 3),
                        "reason": "fuzzy_title_similarity",
                    })

        # Sort candidates descending by confidence
        candidates.sort(key=lambda c: c["confidence"], reverse=True)
        draft.identity_candidates = candidates

        if candidates:
            # Stage 4 Amendment 1: Never automatically resolve on fuzzy similarity!
            draft.identity_status = "AMBIGUOUS"
            draft.identity_conflict_reason = (
                f"No authoritative identifier present; found {len(candidates)} fuzzy candidate(s) "
                f"with title similarity >= 0.70. Requires operator decision."
            )
        else:
            draft.identity_status = "UNRESOLVED"
            draft.identity_conflict_reason = "No authoritative identifier (SKU, barcode, or style ID) found in source."

        return draft
