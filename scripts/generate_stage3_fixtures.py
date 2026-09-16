from pathlib import Path
from PIL import Image, ImageDraw
import pymupdf

def generate_fixtures():
    pack_dir = Path("tests/fixtures/phase11_merchant/messy_merchant_pack")
    pack_dir.mkdir(parents=True, exist_ok=True)

    # 1. Messy Catalog CSV
    csv_content = (
        "SKU,Item_Name,Retail_Price,Currency,Type,Fabric,Gross_Weight,HSN_Code,Origin_Country,Inventory_Quantity\n"
        "SKU-CLEAN-001,Silk Evening Kurti,149.99,USD,Apparel,100% Mulberry Silk,350 g,6204,India,50\n"
        "SKU-MISSING-002,Linen Summer Tunic,89.00,USD,Apparel,,,,India,25\n"
        "SKU-CONFLICT-003,Merino Wool Shawl,120.00,USD,Apparel,Merino Wool,450 g,6214,India,30\n"
        "SKU-INVALID-004,Defective Sample,N/A,USD,Apparel,Cotton,200 g,6204,India,10\n"
    )
    csv_path = pack_dir / "messy_catalog.csv"
    csv_path.write_text(csv_content, encoding="utf-8")
    print(f"Generated {csv_path}")

    # 2. Supplier Spec PDF (conflicts with SKU-CONFLICT-003 on weight: 650g vs 450g)
    doc = pymupdf.open()
    page = doc.new_page()
    pdf_text = """
Supplier Technical Specification Sheet
SKU: SKU-CONFLICT-003
Title: Merino Wool Shawl
Price: 120.00
Currency: USD
Product Type: Apparel
Material: Merino Wool
Weight: 650 g
Country of Origin: India
HSN: 6214
"""
    page.insert_text((50, 72), pdf_text)
    pdf_path = pack_dir / "supplier_spec.pdf"
    doc.save(pdf_path)
    doc.close()
    print(f"Generated {pdf_path}")

    # 3. Product Photo PNG for SKU-CLEAN-001
    img = Image.new("RGB", (400, 400), color=(240, 240, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([50, 50, 350, 350], fill=(200, 220, 240), outline=(100, 100, 150), width=4)
    img_path = pack_dir / "SKU-CLEAN-001-main.png"
    img.save(img_path)
    print(f"Generated {img_path}")

if __name__ == "__main__":
    generate_fixtures()
