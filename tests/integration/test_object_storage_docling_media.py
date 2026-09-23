from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from sanocea.packages.domain_contract import Phase0Store
from sanocea.packages.domain_contract.models import Merchant
from sanocea.packages.object_storage import S3ObjectStorage
from sanocea.workers.ingestion import DoclingIngestionService, ImageProcessingService


pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_S3_BUCKET"),
    reason="requires S3/MinIO settings in SANOCEA_S3_*",
)


def storage() -> S3ObjectStorage:
    s = S3ObjectStorage(
        endpoint_url=os.environ.get("SANOCEA_S3_ENDPOINT"),
        access_key_id=os.environ["SANOCEA_S3_ACCESS_KEY"],
        secret_access_key=os.environ["SANOCEA_S3_SECRET_KEY"],
        bucket=os.environ["SANOCEA_S3_BUCKET"],
    )
    s.ensure_bucket()
    return s


def test_s3_object_storage_docling_and_media():
    store = Phase0Store()
    store.put(Merchant(id="s3_mer_A", merchant_id="s3_mer_A", legal_name="A", display_name="A"))
    s3 = storage()
    workdir = Path("sanocea/tests/fixtures/phase11_merchant/generated/integration_object_storage")
    workdir.mkdir(parents=True, exist_ok=True)
    fixture = workdir / "supplier.csv"
    fixture.write_text("Diamond Ring\nmetal,gold\nmissing_size,\n", encoding="utf-8")
    product, approval = DoclingIngestionService(store, s3).ingest("s3_mer_A", fixture, "text/csv")
    assert product.status == "draft"
    assert product.attributes["extracted_title"]["verified"] is False
    assert approval.status == "pending"
    assert s3.get(merchant_id="s3_mer_A", uri=product.evidence_refs[0])
    with pytest.raises(PermissionError):
        s3.get(merchant_id="s3_mer_B", uri=product.evidence_refs[0])

    image_path = workdir / "source.png"
    Image.new("RGB", (640, 480), "red").save(image_path)
    asset = ImageProcessingService(store, s3).transform("s3_mer_A", image_path)
    assert asset.mime_type == "image/webp"
    assert asset.checksum


def test_docling_pdf_dirty_product_keeps_unverified_provenance():
    store = Phase0Store()
    store.put(Merchant(id="pdf_mer_A", merchant_id="pdf_mer_A", legal_name="A", display_name="A"))
    workdir = Path("sanocea/tests/fixtures/phase11_merchant/generated/integration_docling")
    workdir.mkdir(parents=True, exist_ok=True)
    pdf_path = workdir / "dirty-product.pdf"
    pdf_path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 92 >> stream\nBT /F1 18 Tf 72 720 Td (Supplier Ring PDF) Tj 0 -24 Td (Material: unclear; Size missing) Tj ET\nendstream endobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000241 00000 n \n0000000384 00000 n \n"
        b"trailer << /Root 1 0 R /Size 6 >>\nstartxref\n454\n%%EOF\n"
    )
    product, approval = DoclingIngestionService(store, storage()).ingest("pdf_mer_A", pdf_path, "application/pdf")
    assert product.status == "draft"
    assert product.evidence_refs[0].startswith("s3://")
    assert product.attributes["extracted_title"]["verified"] is False
    assert approval.status == "pending"
