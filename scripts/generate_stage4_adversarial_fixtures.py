#!/usr/bin/env python3
"""Generates the Stage 4 Adversarial Merchant Corpus fixtures:
- adversarial_catalog.xlsx (merged cells, formulas, cached values, error formulas, hidden sheet)
- catalog_revision_b.xlsx (variant lifecycle: added, changed SKU, missing variant marked STALE)
- malformed_rows.csv (diverse encodings, jagged rows, Indian & European formats, missing units)
- colliding_barcodes.csv (barcode collision across distinct product styles)
- multi_product_spec.pdf (multi-product specifications in a single PDF)
- ballast_corrupt.bin & .DS_Store (ballast files to prove fault isolation)
"""

from pathlib import Path
import openpyxl
from openpyxl.styles import PatternFill, Font


def create_adversarial_pack(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. adversarial_catalog.xlsx
    wb = openpyxl.Workbook()
    # Sheet 1: Active Catalogue
    ws = wb.active
    ws.title = "Catalogue"
    headers = [
        "Parent SKU", "Title", "Product Type", "Category", "Variant SKU",
        "Color", "Size", "Price Formula", "Barcode", "Weight", "Dimensions"
    ]
    ws.append(headers)

    # Row 2-4: Style STYLE-KAFTAN-101 with merged parent cells
    ws.append([
        "STYLE-KAFTAN-101", "Embroidered Silk Kaftan", "Apparel", "Kaftans",
        "KFTN-SLK-BLU-S", "Navy Blue", "S", "=1200*1.18", "8901234567801", "350g", "20x15x3 cm"
    ])
    ws.append([
        None, None, None, None,
        "KFTN-SLK-BLU-M", "Navy Blue", "M", "=1200*1.18", "8901234567802", "370g", "20x15x3 cm"
    ])
    ws.append([
        None, None, None, None,
        "KFTN-SLK-BLU-L", "Navy Blue", "L", "=1200*1.18", "8901234567803", "390g", "20x15x3 cm"
    ])

    # Merge parent columns across rows 2 to 4
    ws.merge_cells("A2:A4")
    ws.merge_cells("B2:B4")
    ws.merge_cells("C2:C4")
    ws.merge_cells("D2:D4")

    # Row 5: Standalone product with broken formula
    ws.append([
        "STYLE-LINEN-202", "Linen Summer Tunic", "Apparel", "Tunics",
        "TNC-LIN-WHT-M", "White", "M", "=D5/0", "8901234567804", "250g", "15x10x2 cm"
    ])

    # Sheet 2: Hidden sheet
    ws_hidden = wb.create_sheet(title="Internal_Markup_Notes")
    ws_hidden.sheet_state = "hidden"
    ws_hidden.append(["Style", "Internal Margin", "Supplier Cost"])
    ws_hidden.append(["STYLE-KAFTAN-101", "45%", "650.00"])

    wb_path = target_dir / "adversarial_catalog.xlsx"
    wb.save(wb_path)

    # Patch sheet1.xml inside the xlsx zip to simulate realistic Excel cached values and error codes
    import zipfile
    import shutil

    temp_zip = target_dir / "temp_adv.zip"
    shutil.copyfile(wb_path, temp_zip)
    with zipfile.ZipFile(temp_zip, "r") as zin, zipfile.ZipFile(wb_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                text = content.decode("utf-8")
                # H2, H3, H4 have cached value 1416.0
                text = text.replace('<c r="H2"><f>1200*1.18</f><v></v></c>', '<c r="H2"><f>1200*1.18</f><v>1416.0</v></c>')
                text = text.replace('<c r="H3"><f>1200*1.18</f><v></v></c>', '<c r="H3"><f>1200*1.18</f><v>1416.0</v></c>')
                text = text.replace('<c r="H4"><f>1200*1.18</f><v></v></c>', '<c r="H4"><f>1200*1.18</f><v>1416.0</v></c>')
                # H5 has error formula #DIV/0!
                text = text.replace('<c r="H5"><f>D5/0</f><v></v></c>', '<c r="H5" t="e"><f>D5/0</f><v>#DIV/0!</v></c>')
                content = text.encode("utf-8")
            zout.writestr(item, content)
    temp_zip.unlink()

    # 2. catalog_revision_b.xlsx (revision B of STYLE-KAFTAN-101)
    wb_b = openpyxl.Workbook()
    ws_b = wb_b.active
    ws_b.title = "Catalogue"
    ws_b.append(headers)
    # Row 2: S remains
    ws_b.append([
        "STYLE-KAFTAN-101", "Embroidered Silk Kaftan", "Apparel", "Kaftans",
        "KFTN-SLK-BLU-S", "Navy Blue", "S", "1416.00", "8901234567801", "350g", "20x15x3 cm"
    ])
    # Row 3: M has SKU changed to KFTN-SLK-BLU-M-V2
    ws_b.append([
        "STYLE-KAFTAN-101", "Embroidered Silk Kaftan", "Apparel", "Kaftans",
        "KFTN-SLK-BLU-M-V2", "Navy Blue", "M", "1416.00", "8901234567802", "370g", "20x15x3 cm"
    ])
    # Note: L is REMOVED (absent) from revision B!
    # Row 4: NEW XL variant added
    ws_b.append([
        "STYLE-KAFTAN-101", "Embroidered Silk Kaftan", "Apparel", "Kaftans",
        "KFTN-SLK-BLU-XL", "Navy Blue", "XL", "1499.00", "8901234567805", "410g", "20x15x3 cm"
    ])
    wb_b_path = target_dir / "catalog_revision_b.xlsx"
    wb_b.save(wb_b_path)

    # 3. malformed_rows.csv
    # Exercises Indian format (₹1,49,999.00), European format (1.499,00 €), jagged columns, missing units,
    # and title-only draft without authoritative identifier (to verify fuzzy candidate boundary).
    csv_content = """sku,title,price,currency,product_type,weight,dimensions,colour,size
IND-JEWEL-001,Handcrafted Kundan Choker,₹1,49,999.00,INR,Jewelry,450,15x10x5,Gold,One Size
EUR-JACKET-002,Alpine Wool Coat,"1.499,00 €",EUR,Apparel,1.2 kg,40x30x10 cm,Charcoal,M
JAGGED-ROW-003,Jagged Row Item,2500,INR
,Handmade Silk Stole,1200,INR,Accessories,150g,100x50 cm,Navy,One Size
"""
    (target_dir / "malformed_rows.csv").write_text(csv_content, encoding="utf-8-sig")

    # 4. colliding_barcodes.csv
    # Exercises duplicate barcode 8909999999999 assigned to two completely distinct product styles
    barcode_collision_csv = """parent_sku,sku,title,price,currency,product_type,barcode
STYLE-SHIRT-501,SHIRT-COT-BLU-M,Classic Cotton Formal Shirt,189900,INR,Apparel,8909999999999
STYLE-PANTS-701,PANTS-CHINO-KHK-32,Slim Fit Chino Trousers,249900,INR,Apparel,8909999999999
"""
    (target_dir / "colliding_barcodes.csv").write_text(barcode_collision_csv, encoding="utf-8")

    # 5. multi_product_spec.pdf
    # 5. multi_product_spec.pdf (generated via pymupdf)
    import pymupdf
    pdf_doc = pymupdf.open()
    page = pdf_doc.new_page(width=612, height=792)
    pdf_text = """# Specification Catalog: Handcrafted Decor

| SKU | Title | Price | Product Type | Material | Dimensions |
| SPEC-PDF-001 | Artisanal Ceramic Vase | 2499.00 | Decor | Clay Ceramic | 12x12x25 cm |
| SPEC-PDF-002 | Handmade Brass Planter | 3999.00 | Decor | Solid Brass | 18x18x15 cm |
"""
    page.insert_text((50, 50), pdf_text, fontsize=11)
    pdf_path = target_dir / "multi_product_spec.pdf"
    pdf_doc.save(pdf_path)
    pdf_doc.close()

    # 6. Ballast / corrupt files to prove fault isolation
    (target_dir / "ballast_corrupt.bin").write_bytes(b"\x00\xff\xfe\x00CORRUPT_BALLAST_PAYLOAD\x00\x00")
    (target_dir / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1\x00\x00\x10\x00")

    print(f"Generated adversarial merchant pack in {target_dir}")


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "phase11_merchant" / "adversarial_pack"
    create_adversarial_pack(out_dir)
