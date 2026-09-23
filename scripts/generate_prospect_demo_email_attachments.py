#!/usr/bin/env python3
"""Generates the demo product-master workbooks used for the live email-ingestion demo (PHASE D).

Each workbook mixes REAL, publicly-verified products (from packages/prospect_demo/tenants.py -
PROSPECT_TENANTS) with a small number of new SYNTHETIC_DEMO proposed variants around the same real
product families - clearly new, never misrepresented as publicly verified. A few rows carry genuine,
realistic defects (missing required field, conflicting price for the same parent SKU) that the REAL
SANOCEA validator (packages/product_onboarding/validation.py) actually detects - nothing here fakes an
exception; every "requires attention" row is a real data problem the certified pipeline finds itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
PARENT_DIR = ROOT_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import openpyxl

from sanocea.packages.prospect_demo.tenants import PROSPECT_TENANTS

OUT_DIR = ROOT_DIR / "tests" / "fixtures" / "prospect_demo_email"

HEADERS = ["parent_sku", "sku", "title", "price", "currency", "product_type", "category", "barcode", "weight", "hsn"]

# One new SYNTHETIC_DEMO proposed variant family per prospect, built around their real product line -
# clearly new SKUs, never claimed as publicly verified.
SYNTHETIC_NEW_VARIANTS = {
    "prospect_ajanta_soya": [
        # Clean: a plausible new pack size for the real "Anchal Refined Sunflower Oil" line.
        {"parent_sku": "AJS-NEW-SFO-2L", "sku": "AJS-NEW-SFO-2L", "title": "Anchal Refined Sunflower Oil - 2L Pouch (Proposed)",
         "price": "380.00", "currency": "INR", "product_type": "Cooking Oil", "category": "Cooking Oil", "barcode": "8901234500021", "weight": "2000g", "hsn": "15121000"},
        # Defect 1: missing product_type (mandatory field) -> real MISSING_REQUIRED_ATTRIBUTE exception.
        {"parent_sku": "AJS-NEW-MOI-500", "sku": "AJS-NEW-MOI-500", "title": "Anchal Kachi Ghani Mustard Oil - 500ml Trial Pack (Proposed)",
         "price": "129.00", "currency": "INR", "product_type": "", "category": "Cooking Oil", "barcode": "", "weight": "500g", "hsn": "15142011"},
        # Defect 2: conflicting price for the SAME parent SKU (two rows, same parent_sku, different price).
        {"parent_sku": "AJS-NEW-SOY-1L", "sku": "AJS-NEW-SOY-1L", "title": "Anchal Refined Soyabean Oil - 1L Bottle (Proposed)",
         "price": "165.00", "currency": "INR", "product_type": "Cooking Oil", "category": "Cooking Oil", "barcode": "8901234500038", "weight": "1000g", "hsn": "15071000"},
        {"parent_sku": "AJS-NEW-SOY-1L", "sku": "AJS-NEW-SOY-1L", "title": "Anchal Refined Soyabean Oil - 1L Bottle (Proposed)",
         "price": "179.00", "currency": "INR", "product_type": "Cooking Oil", "category": "Cooking Oil", "barcode": "8901234500038", "weight": "1000g", "hsn": "15071000"},
    ],
    "prospect_healthvitals": [
        {"parent_sku": "DJH-NEW-GBS-45", "sku": "DJH-NEW-GBS-45", "title": "Gut Brain Support - 45 Day Pack (Proposed)",
         "price": "1899.00", "currency": "INR", "product_type": "Gut health supplement", "category": "Supplement", "barcode": "8901234600014", "weight": "150g", "hsn": "21069099"},
        {"parent_sku": "DJH-NEW-PCOS-45", "sku": "DJH-NEW-PCOS-45", "title": "PCOS Hormone Balance - 45 Day Pack (Proposed)",
         "price": "1999.00", "currency": "INR", "product_type": "", "category": "Supplement", "barcode": "", "weight": "150g", "hsn": "21069099"},
        {"parent_sku": "DJH-NEW-WELL-2", "sku": "DJH-NEW-WELL-2", "title": "Complete Wellness Bundle - Pack of 2 (Proposed)",
         "price": "5200.00", "currency": "INR", "product_type": "Bundle", "category": "Bundle", "barcode": "8901234600021", "weight": "500g", "hsn": "21069099"},
        {"parent_sku": "DJH-NEW-WELL-2", "sku": "DJH-NEW-WELL-2", "title": "Complete Wellness Bundle - Pack of 2 (Proposed)",
         "price": "5600.00", "currency": "INR", "product_type": "Bundle", "category": "Bundle", "barcode": "8901234600021", "weight": "500g", "hsn": "21069099"},
    ],
    "prospect_carzex": [
        {"parent_sku": "CZX-NEW-LED-8", "sku": "CZX-NEW-LED-8", "title": "Carzex RGB Underbody Chassis Light - Set of 8 (Proposed)",
         "price": "1199.00", "currency": "INR", "product_type": "Exterior Accessories", "category": "Car Lightings", "barcode": "8901234700018", "weight": "600g", "hsn": "85122010"},
        {"parent_sku": "CZX-NEW-COVER-XL", "sku": "CZX-NEW-COVER-XL", "title": "Carzex Waterproof Body Cover - SUV Size (Proposed)",
         "price": "1499.00", "currency": "INR", "product_type": "", "category": "Car Comfort & Safety", "barcode": "", "weight": "1200g", "hsn": "63062900"},
        {"parent_sku": "CZX-NEW-KEY-5", "sku": "CZX-NEW-KEY-5", "title": "Carzex Car Key Cover - 5 Brand Pack (Proposed)",
         "price": "349.00", "currency": "INR", "product_type": "Interior Accessories", "category": "Interior Accessories", "barcode": "8901234700025", "weight": "80g", "hsn": "39269099"},
        {"parent_sku": "CZX-NEW-KEY-5", "sku": "CZX-NEW-KEY-5", "title": "Carzex Car Key Cover - 5 Brand Pack (Proposed)",
         "price": "399.00", "currency": "INR", "product_type": "Interior Accessories", "category": "Interior Accessories", "barcode": "8901234700025", "weight": "80g", "hsn": "39269099"},
    ],
    "prospect_premium_basket": [
        {"parent_sku": "TPB-NEW-MAK-100", "sku": "TPB-NEW-MAK-100", "title": "Pure Roasted Makhana - 100g Family Pack (Proposed)",
         "price": "449.00", "currency": "INR", "product_type": "Snacks", "category": "Snacks", "barcode": "8901234800012", "weight": "100g", "hsn": "20081990"},
        {"parent_sku": "TPB-NEW-DATE-300", "sku": "TPB-NEW-DATE-300", "title": "Arabian Mabroom Dates - 300g Pack (Proposed)",
         "price": "699.00", "currency": "INR", "product_type": "", "category": "Dry Fruits", "barcode": "", "weight": "300g", "hsn": "08041010"},
        {"parent_sku": "TPB-NEW-NUTS-500", "sku": "TPB-NEW-NUTS-500", "title": "Bountiful Salted Three Mixed Nuts - 500g (Proposed)",
         "price": "1899.00", "currency": "INR", "product_type": "Dry Fruits", "category": "Dry Fruits", "barcode": "8901234800029", "weight": "500g", "hsn": "08029000"},
        {"parent_sku": "TPB-NEW-NUTS-500", "sku": "TPB-NEW-NUTS-500", "title": "Bountiful Salted Three Mixed Nuts - 500g (Proposed)",
         "price": "1999.00", "currency": "INR", "product_type": "Dry Fruits", "category": "Dry Fruits", "barcode": "8901234800029", "weight": "500g", "hsn": "08029000"},
    ],
}

DISPLAY_FILENAME = {
    "prospect_ajanta_soya": "Ajanta_New_Product_Master.xlsx",
    "prospect_healthvitals": "HealthVitals_New_Product_Master.xlsx",
    "prospect_carzex": "Carzex_New_Product_Master.xlsx",
    "prospect_premium_basket": "PremiumBasket_New_Product_Master.xlsx",
}


def build_workbook(merchant_id: str) -> Path:
    config = PROSPECT_TENANTS[merchant_id]
    rows: list[dict[str, str]] = []

    # Real, publicly-verified products first (clean rows) - reusing the exact facts already recorded in
    # PROSPECT_TENANTS, never re-invented here.
    for p in config["public_products"]:
        if p.get("price_paise") is None or not p.get("sku"):
            continue  # only include rows with genuinely known, complete public facts as "clean" rows
        rows.append({
            "parent_sku": "", "sku": p["sku"], "title": p["title"],
            "price": f"{p['price_paise'] / 100:.2f}", "currency": p.get("currency", "INR"),
            "product_type": p.get("category") or "General", "category": p.get("category") or "",
            "barcode": "", "weight": p.get("pack_size") or "", "hsn": "",
        })

    rows.extend(SYNTHETIC_NEW_VARIANTS.get(merchant_id, []))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / DISPLAY_FILENAME[merchant_id]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Product Master"
    ws.append(HEADERS)
    for row in rows:
        ws.append([row.get(h, "") for h in HEADERS])
    wb.save(out_path)
    print(f"[GENERATE] {merchant_id}: {out_path} ({len(rows)} rows: {len(config['public_products'])} real candidates filtered to {sum(1 for p in config['public_products'] if p.get('price_paise') and p.get('sku'))} clean + {len(SYNTHETIC_NEW_VARIANTS.get(merchant_id, []))} synthetic)")
    return out_path


def main() -> None:
    for merchant_id in PROSPECT_TENANTS:
        build_workbook(merchant_id)


if __name__ == "__main__":
    main()
