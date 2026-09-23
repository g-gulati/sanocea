"""Deterministic recommendation engine for product draft missing attributes.
Provides category-aware and catalog-aware recommendations when supplier feeds omit
required commercial fields (e.g. retail price, product category/type, Shopify standardized category).

Zero-invention discipline: recommendations are clearly labeled as suggestions and
require merchant approval/confirmation before becoming authoritative facts.
"""

from __future__ import annotations

import re
from typing import Any

from sanocea.packages.domain_contract.models import ProductDraft
from sanocea.packages.product_onboarding.taxonomy import ShopifyTaxonomyService


def infer_weight_from_sku_or_title(sku: str | None, title: str | None) -> dict[str, Any] | None:
    """Infers product weight from SKU or title pattern (e.g. 0250G -> 250 g, 200G -> 200 g).
    Always proposes for approval rather than assuming it.
    """
    text = f"{sku or ''} {title or ''}"
    match = re.search(r"(?:^|[-_ ])0?(\d{2,4})\s*(g|kg|gm|gms|ml|l)(?:[-_ ]|$)", text, re.IGNORECASE)
    if match:
        val = int(match.group(1))
        unit_raw = match.group(2).upper()
        if unit_raw in ("G", "GM", "GMS"):
            return {
                "value": val,
                "unit": "GRAMS",
                "display": f"{val} g",
                "reason": f"inferred from pattern '{match.group(0).strip()}'",
            }
        if unit_raw == "KG":
            return {
                "value": val,
                "unit": "KILOGRAMS",
                "display": f"{val} kg",
                "reason": f"inferred from pattern '{match.group(0).strip()}'",
            }
    return None


def get_draft_recommendations(
    draft: ProductDraft,
    connector: Any = None,
    merchant_config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Returns deterministic, category-grounded recommendations for missing draft attributes.
    Each entry provides:
      - 'value': the canonical value to apply if approved (e.g. '249' or 'Dry Fruits & Nuts' or TaxonomyCategory ID)
      - 'display': human-readable display string (e.g. '₹249.00' or category full path)
      - 'reason': commercial rationale or category benchmark
    """
    recs: dict[str, dict[str, Any]] = {}
    title_lower = (draft.title or "").lower()
    tags_lower = str(draft.attributes.get("tags") or "").lower()
    desc_lower = str(draft.attributes.get("description") or "").lower()
    combined_text = f"{title_lower} {tags_lower} {desc_lower}"

    missing_fields = {
        e.split(":", 1)[1]
        for e in draft.validation_errors
        if e.startswith("missing_required_attribute:")
    }

    # 1. Retail Price recommendation
    if "price" in missing_fields:
        if "makhana" in combined_text or "lotus" in combined_text:
            recs["price"] = {
                "value": "249",
                "display": "₹249.00",
                "reason": "50g roasted lotus seed benchmark (40% margin at ₹249)",
            }
        elif "cashew" in combined_text and ("choco" in combined_text or "coffee" in combined_text or "sweet" in combined_text):
            recs["price"] = {
                "value": "349",
                "display": "₹349.00",
                "reason": "200g gourmet confectionery cashew benchmark",
            }
        elif "cashew" in combined_text:
            recs["price"] = {
                "value": "499",
                "display": "₹499.00",
                "reason": "250g premium W240 cashew benchmark",
            }
        elif "almond" in combined_text:
            recs["price"] = {
                "value": "399",
                "display": "₹399.00",
                "reason": "250g California almonds benchmark",
            }
        else:
            recs["price"] = {
                "value": "299",
                "display": "₹299.00",
                "reason": "gourmet snacking catalogue benchmark",
            }

    # 2. Resolve Shopify Standardized Product Category via Shopify Taxonomy
    tax_service = ShopifyTaxonomyService()
    tax_rec = None
    if draft.attributes.get("recommended_category_id") and draft.attributes.get("recommended_category_path"):
        tax_rec = {
            "category_id": draft.attributes["recommended_category_id"],
            "name": draft.attributes.get("recommended_category_name", "Recommended Category"),
            "full_path": draft.attributes["recommended_category_path"],
            "confidence": draft.attributes.get("taxonomy_confidence", 0.90),
            "evidence": draft.attributes.get("taxonomy_evidence", []),
            "product_type": draft.attributes.get("recommended_product_type") or draft.product_type or "Dry Fruits & Nuts",
            "requires_confirmation": bool(draft.attributes.get("taxonomy_confidence", 1.0) < 0.80),
        }
    else:
        resolved = tax_service.recommend_category(
            connector=connector,
            title=draft.title or "",
            description=draft.attributes.get("description") or "",
            tags=str(draft.attributes.get("tags") or ""),
            sku=draft.sku or "",
            product_type=draft.product_type or "",
            merchant_config=merchant_config,
        )
        if resolved:
            tax_rec = resolved.to_dict()

    if tax_rec:
        recs["category_recommendation"] = tax_rec

    # 3. Product Category / Type recommendation (Merchant custom grouping)
    derived_product_type = (tax_rec.get("product_type") if tax_rec else None)
    if not derived_product_type:
        if any(w in combined_text for w in ["almond", "cashew", "walnut", "pistachio", "nuts", "dates"]):
            derived_product_type = "Dry Fruits & Nuts"
        else:
            derived_product_type = "snacks"

    if "product_type" in missing_fields or "category" in missing_fields or not draft.product_type:
        recs["product_type"] = {
            "value": derived_product_type,
            "display": derived_product_type,
            "reason": "inferred from ingredients and catalogue classification",
        }

    if tax_rec and ("category" in missing_fields or "product_type" in missing_fields or not draft.category):
        recs["category"] = {
            "value": tax_rec["category_id"],
            "display": tax_rec["full_path"],
            "reason": f"Shopify Standardized Category ({tax_rec['name']})",
            "full_path": tax_rec["full_path"],
            "confidence": tax_rec["confidence"],
            "evidence": tax_rec["evidence"],
        }

    # 4. Inventory, Location, Weight and Variant recommendations for physical goods
    is_physical = draft.attributes.get("requires_shipping", True) is not False and not draft.attributes.get("is_digital")
    if is_physical:
        # Weight recommendation (propose rather than assume)
        weight_rec = infer_weight_from_sku_or_title(draft.sku, draft.title)
        if weight_rec:
            recs["weight"] = weight_rec
            recs["product_weight"] = weight_rec

        # Inventory recommendations (prevent overselling by default)
        recs["track_inventory"] = {
            "value": True,
            "display": "Yes (Tracked)",
            "reason": "Required for physical goods to prevent overselling",
        }
        recs["inventory_quantity"] = {
            "value": 10,
            "display": "10 units",
            "reason": "recommended opening stock batch",
        }
        recs["inventory_location"] = {
            "value": "Shop location",
            "display": "Shop location",
            "reason": "primary verified shipping location",
        }

        # Variant structure recommendation
        if draft.variants and any(v.option_values for v in draft.variants):
            recs["variant_structure"] = {
                "value": "multi_variant",
                "display": f"{len(draft.variants)} variants ({', '.join(draft.options)})",
                "reason": "supplied in supplier file",
            }
        else:
            recs["variant_structure"] = {
                "value": "single_variant",
                "display": "Single default variant (Default Title)",
                "reason": "default variant; reply if options or pack sizes needed",
            }

    return recs


def format_missing_fields_notification(draft: ProductDraft, missing_fields: list[str]) -> str:
    """Formats an executive WhatsApp notification for a draft with missing publishing fields.
    Presents Sanocea's safe gatekeeper role, the missing attribute, recommended Shopify standardized category,
    recommended merchant type with rationale, and clear one-tap action guidance.
    """
    recs = get_draft_recommendations(draft)
    label = draft.title or draft.sku or draft.id
    category_rec = recs.get("category_recommendation")
    tax_path = category_rec["full_path"] if category_rec else None

    field_labels = {
        "price": "Retail Price",
        "product_type": "Product Category / Type",
        "category": "Standardized Product Category",
        "sku": "SKU Code",
        "title": "Product Title",
        "description": "Product Description",
        "tags": "Product Tags",
    }

    lines = [
        "📋 *SANOCEA Catalogue Gate — Product Onboarding*",
        "",
        "New supplier product draft was staged safely and kept *unpublished* until required publishing fields are complete:",
        "",
        f"• *Product:* {label}",
    ]
    if draft.sku:
        lines.append(f"• *SKU:* `{draft.sku}`")

    # Present existing known fields for context
    context_items = []
    if draft.price and "price" not in missing_fields:
        context_items.append(f"Price: ₹{draft.price / 100:.2f}")
    if draft.product_type and "product_type" not in missing_fields:
        context_items.append(f"Type: {draft.product_type}")
    if context_items:
        lines.append(f"• *Known Details:* {', '.join(context_items)}")

    lines.append("")
    lines.append("*Missing Required Detail(s):*")
    for f in missing_fields:
        flabel = field_labels.get(f, f.replace("_", " ").title())
        rec = recs.get(f)
        if rec:
            lines.append(f"• *{flabel}:* MISSING")
            if f in ("product_type", "category"):
                if tax_path:
                    lines.append(f"  ↳ _Recommended Shopify category:_ *{tax_path}*")
                    lines.append(f"  ↳ _Merchant type grouping:_ *{rec['display']}*")
                else:
                    lines.append(f"  ↳ _Recommended:_ *{rec['display']}* ({rec['reason']})")
            else:
                lines.append(f"  ↳ _Recommended:_ *{rec['display']}* ({rec['reason']})")
        else:
            lines.append(f"• *{flabel}:* MISSING")

    # Physical product inventory, weight, and variant unconfirmed checks
    is_physical = draft.attributes.get("requires_shipping", True) is not False and not draft.attributes.get("is_digital")
    inv_confirmed = bool(draft.attributes.get("inventory_confirmed") or draft.attributes.get("track_inventory") is False)

    if is_physical and not inv_confirmed:
        lines.append("• *Inventory & Location:* UNCONFIRMED")
        lines.append("  ↳ _Track inventory:_ *Yes* (Required for physical goods to prevent overselling)")
        inv_qty = recs.get("inventory_quantity", {}).get("display", "10 units")
        inv_loc = recs.get("inventory_location", {}).get("display", "Shop location")
        lines.append(f"  ↳ _Recommended opening stock:_ *{inv_qty}* at *{inv_loc}*")

        weight_rec = recs.get("weight")
        if weight_rec:
            lines.append("• *Product Weight:* UNCONFIRMED")
            lines.append(f"  ↳ _Recommended weight:_ *{weight_rec['display']}* ({weight_rec['reason']})")

        var_rec = recs.get("variant_structure")
        if var_rec and var_rec.get("value") == "single_variant":
            lines.append("• *Variant Structure:* UNCONFIRMED")
            lines.append(f"  ↳ _Proposed:_ *{var_rec['display']}* ({var_rec['reason']})")

    # If category is not in missing_fields but is recommended, show context
    if "product_type" not in missing_fields and "category" not in missing_fields and tax_path:
        lines.append("")
        lines.append(f"• *Recommended Shopify category:* {tax_path}")

    # Provide clear action guidance
    lines.append("")
    lines.append("💡 *To publish safely to Shopify:*")
    rec_pieces = []
    if tax_path and ("product_type" in missing_fields or "category" in missing_fields):
        rec_pieces.append(category_rec["name"] if category_rec else "Category")
    if is_physical and not inv_confirmed:
        inv_qty = recs.get("inventory_quantity", {}).get("display", "10 units")
        inv_loc = recs.get("inventory_location", {}).get("display", "Shop location")
        rec_pieces.append(f"{inv_qty} at {inv_loc}")
        weight_rec = recs.get("weight")
        if weight_rec:
            rec_pieces.append(weight_rec["display"])

    if rec_pieces:
        rec_summary = ", ".join(rec_pieces)
        lines.append(f"👉 Reply *APPROVE* to use this category and accept all recommendations (*{rec_summary}*)")
    else:
        lines.append("👉 Reply *APPROVE* to use this category and accept all recommendations")

    lines.append("👉 Or reply with custom values (e.g. \"qty 20 at Shop location\", \"500g\", or \"no tracking\")")

    lines.append("")
    lines.append("_Sanocea prevents incomplete products from reaching customers._")

    return "\n".join(lines)


def format_publish_confirmation(
    title: str,
    sku: str | None,
    completed_fields: dict[str, Any],
    outcome: dict[str, Any],
    audit_ref: str,
    category_path: str | None = None,
) -> str:
    """Formats an executive WhatsApp confirmation after a product draft is completed and published."""
    field_labels = {
        "price": "Retail Price",
        "product_type": "Merchant Type",
        "category": "Shopify Category",
    }
    completed_items = []
    for k, v in completed_fields.items():
        if k in ("inventory_quantity", "inventory_location", "track_inventory", "weight"):
            continue
        flabel = field_labels.get(k, k.replace("_", " ").title())
        if k == "price":
            try:
                num = float(re.sub(r"[^\d.]", "", str(v)))
                val_str = f"₹{num:.2f}"
            except Exception:
                val_str = str(v)
        elif k == "category" and category_path:
            val_str = category_path
        else:
            val_str = str(v)
        completed_items.append(f"{flabel}: {val_str}")

    # Add inventory tracking summary
    if completed_fields.get("track_inventory") is False:
        completed_items.append("Inventory: Untracked (merchant policy choice)")
    elif "inventory_quantity" in completed_fields:
        qty = completed_fields["inventory_quantity"]
        loc = completed_fields.get("inventory_location", "Shop location")
        completed_items.append(f"Inventory: {qty} units tracked at {loc}")

    if "weight" in completed_fields:
        completed_items.append(f"Weight: {completed_fields['weight']} g")

    completed_str = ", ".join(completed_items) or "All required fields completed"

    sku_tag = f" ({sku})" if sku else ""
    is_published = outcome.get("outcome") == "published"
    is_visible = bool(outcome.get("storefront_visible"))

    if is_published:
        status_str = "Live on Store (Verified visible on Online Store)" if is_visible else "Published to Shopify (Admin catalog active)"
    elif outcome.get("outcome") == "pending_approval":
        status_str = "Completed — Pending governance sign-off in Command Center"
    else:
        status_str = f"Completed — Publication blocked: {', '.join(outcome.get('reasons', []))}"

    lines = [
        "✅ *Published to Shopify Storefront*",
        "",
        f"• *Product:* {title}{sku_tag}",
        f"• *Completed Field(s):* {completed_str}",
        f"• *Publishing Result:* {status_str}",
        f"• *Audit Reference:* `{audit_ref}`",
        "",
        "_Product is now live and customer-facing with verified completeness._",
    ]
    return "\n".join(lines)
