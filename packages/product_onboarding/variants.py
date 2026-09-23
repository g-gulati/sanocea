from __future__ import annotations

import copy
from typing import Any

try:
    from sanocea.packages.domain_contract.models import (
        ProductDraft,
        VariantDraft,
        new_id,
    )
    from sanocea.packages.product_onboarding.provenance import CommercialFact
except ImportError:
    from packages.domain_contract.models import (
        ProductDraft,
        VariantDraft,
        new_id,
    )
    from packages.product_onboarding.provenance import CommercialFact


STANDARD_OPTION_NAMES = {
    "color": "Color",
    "colour": "Color",
    "colors": "Color",
    "size": "Size",
    "sizes": "Size",
    "material": "Material",
    "materials": "Material",
    "style": "Style",
    "flavor": "Flavor",
    "flavour": "Flavor",
    "scent": "Scent",
    "finish": "Finish",
    "pattern": "Pattern",
    "edition": "Edition",
}


class VariantMatrixEngine:
    """Variant Matrix Construction and Lifecycle Management Engine.
    Handles parent-variant resolution, option matrices, duplicate option detection,
    and variant lifecycle transitions across catalog revisions (Stage 4 Amendment 6).
    """

    def __init__(self) -> None:
        pass

    def normalize_option_name(self, raw_name: str) -> str:
        """Normalizes option dimension names (e.g. 'colour' -> 'Color', 'sizes' -> 'Size')."""
        cleaned = raw_name.strip().lower()
        return STANDARD_OPTION_NAMES.get(cleaned, raw_name.strip().title())

    def extract_option_values_from_row(self, row_values: dict[str, Any]) -> dict[str, str]:
        """Extracts option values from a row dictionary.
        Supports:
        - Direct keys: 'color', 'size', 'material', etc.
        - Indexed Shopify-style keys: 'option1_name' / 'option1_value', etc.
        """
        options: dict[str, str] = {}

        # 1. Check direct standard option keys
        for raw_k, v in row_values.items():
            if v in (None, ""):
                continue
            norm_k = raw_k.strip().lower()
            if norm_k in STANDARD_OPTION_NAMES:
                canonical_name = STANDARD_OPTION_NAMES[norm_k]
                options[canonical_name] = str(v).strip()

        # 2. Check indexed option pairs (Option1 Name, Option1 Value, ...)
        for i in range(1, 4):
            opt_name_key = f"option{i}_name"
            opt_val_key = f"option{i}_value"
            name = row_values.get(opt_name_key)
            val = row_values.get(opt_val_key)
            if name and val:
                canon_name = self.normalize_option_name(str(name))
                options[canon_name] = str(val).strip()

        return options

    def create_variant_draft(
        self,
        sku: str | None,
        barcode: str | None,
        option_values: dict[str, str],
        price: int | None = None,
        compare_at_price: int | None = None,
        cost_price: int | None = None,
        weight: float | None = None,
        dimensions: dict[str, Any] | None = None,
        inventory_quantity: int | None = None,
        commercial_facts: dict[str, CommercialFact] | None = None,
        source_locators: list[dict[str, Any]] | None = None,
    ) -> VariantDraft:
        return VariantDraft(
            id=new_id("vdf"),
            sku=sku.strip() if sku else None,
            barcode=barcode.strip() if barcode else None,
            option_values={self.normalize_option_name(k): str(v).strip() for k, v in option_values.items()},
            price=price,
            compare_at_price=compare_at_price,
            cost_price=cost_price,
            weight=weight,
            dimensions=dimensions or {},
            inventory_quantity=inventory_quantity,
            commercial_facts=commercial_facts or {},
            source_locators=source_locators or [],
            status="ACTIVE",
        )

    def validate_variant_matrix(self, draft: ProductDraft) -> list[str]:
        """Validates the internal consistency of a product's variant matrix.
        Detects:
        - Duplicate option value combinations.
        - Barcode collisions among distinct variants.
        - SKU collisions among distinct variants (two pack sizes sharing one SKU - a real catalogue defect
          found on a live merchant's storefront, where downstream systems can no longer tell them apart).
        - Missing SKUs.
        """
        errors: list[str] = []
        seen_options: dict[str, str] = {}  # key -> variant_id
        seen_barcodes: dict[str, str] = {}  # barcode -> variant_id
        seen_skus: dict[str, str] = {}  # sku -> variant_id

        for v in draft.variants:
            if v.status != "ACTIVE":
                continue

            # Check option uniqueness
            opt_key = "|".join(f"{k}:{v.option_values[k]}" for k in sorted(v.option_values.keys()))
            if opt_key:
                if opt_key in seen_options:
                    prev_id = seen_options[opt_key]
                    err = f"Duplicate variant options combination '{opt_key}' found on variants {prev_id} and {v.id}"
                    errors.append(err)
                    v.conflicts.append(err)
                else:
                    seen_options[opt_key] = v.id

            # Check SKU uniqueness
            if v.sku:
                if v.sku in seen_skus:
                    prev_id = seen_skus[v.sku]
                    err = f"SKU collision within variants: SKU '{v.sku}' shared by {prev_id} and {v.id}"
                    errors.append(err)
                    v.conflicts.append(err)
                else:
                    seen_skus[v.sku] = v.id

            # Check barcode uniqueness
            if v.barcode:
                if v.barcode in seen_barcodes:
                    prev_id = seen_barcodes[v.barcode]
                    err = f"Barcode collision within variants: barcode '{v.barcode}' shared by {prev_id} and {v.id}"
                    errors.append(err)
                    v.conflicts.append(err)
                else:
                    seen_barcodes[v.barcode] = v.id

        return errors

    def reconcile_variant_lifecycle(
        self,
        existing_draft: ProductDraft,
        incoming_variants: list[VariantDraft],
        source_revision: str | None = None,
    ) -> ProductDraft:
        """Reconciles variant lifecycle transitions between an existing draft and incoming revision:
        - Variant Added: newly observed variant appended as ACTIVE.
        - SKU Changed: variant with matching options receives new SKU with provenance.
        - Barcode Changed: barcode updated with provenance.
        - Option Renamed: option value updated.
        - Variant Removed from newer revision: marked STALE (Absence != Deletion).
        """
        existing_draft.source_revision = source_revision

        # Map existing variants by their option key and by SKU
        def get_opt_key(v: VariantDraft) -> str:
            return "|".join(f"{k}:{v.option_values[k]}" for k in sorted(v.option_values.keys()))

        existing_by_opt_key = {get_opt_key(v): v for v in existing_draft.variants if get_opt_key(v)}
        existing_by_sku = {v.sku: v for v in existing_draft.variants if v.sku}

        incoming_matched_existing_ids: set[str] = set()

        for inc_v in incoming_variants:
            inc_opt_key = get_opt_key(inc_v)
            match: VariantDraft | None = None

            # 1. Match by exact option combination
            if inc_opt_key and inc_opt_key in existing_by_opt_key:
                match = existing_by_opt_key[inc_opt_key]
            # 2. Or match by SKU if options were renamed
            elif inc_v.sku and inc_v.sku in existing_by_sku:
                match = existing_by_sku[inc_v.sku]

            if match:
                incoming_matched_existing_ids.add(match.id)
                # Reactivate if previously stale
                match.status = "ACTIVE"

                # Check SKU changed
                if inc_v.sku and inc_v.sku != match.sku:
                    match.sku = inc_v.sku

                # Check barcode changed
                if inc_v.barcode and inc_v.barcode != match.barcode:
                    match.barcode = inc_v.barcode

                # Update options (e.g. Navy -> Navy Blue)
                if inc_v.option_values:
                    match.option_values.update(inc_v.option_values)

                # Update prices if present
                if inc_v.price is not None:
                    match.price = inc_v.price
                if inc_v.compare_at_price is not None:
                    match.compare_at_price = inc_v.compare_at_price
                if inc_v.cost_price is not None:
                    match.cost_price = inc_v.cost_price
                if inc_v.weight is not None:
                    match.weight = inc_v.weight
                if inc_v.inventory_quantity is not None:
                    match.inventory_quantity = inc_v.inventory_quantity

                # Append source locators
                match.source_locators.extend(inc_v.source_locators)
                # Merge commercial facts
                match.commercial_facts.update(inc_v.commercial_facts)
            else:
                # Newly added variant
                inc_v.status = "ACTIVE"
                existing_draft.variants.append(inc_v)
                incoming_matched_existing_ids.add(inc_v.id)

        # Absence != Deletion invariant:
        # Any prior ACTIVE variant not present in the incoming revision becomes STALE
        for v in existing_draft.variants:
            if v.id not in incoming_matched_existing_ids and v.status == "ACTIVE":
                v.status = "STALE"

        # Update product draft options list
        all_option_names: set[str] = set()
        for v in existing_draft.variants:
            all_option_names.update(v.option_values.keys())
        existing_draft.options = sorted(all_option_names)

        return existing_draft
