from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import time

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import Approval, Product
from sanocea.packages.domain_contract.store import Phase0Store
from sanocea.packages.object_storage import S3ObjectStorage


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    evidence_uri: str
    extractor: str = "docling"
    checksum: str | None = None
    elapsed_ms: int = 0
    cached: bool = False


class DoclingExtractor:
    _cache: dict[str, ExtractedDocument] = {}

    def __init__(self, min_text_chars: int = 120) -> None:
        self.min_text_chars = min_text_chars

    def extract(self, path: Path) -> ExtractedDocument:
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        cached = self._cache.get(checksum)
        if cached:
            return ExtractedDocument(
                text=cached.text,
                evidence_uri=cached.evidence_uri,
                extractor=cached.extractor,
                checksum=checksum,
                elapsed_ms=0,
                cached=True,
            )
        started = time.perf_counter()
        if path.suffix.lower() == ".pdf":
            text = self._extract_pdf_text_layer(content)
            if len(text) >= self.min_text_chars:
                extracted = ExtractedDocument(
                    text=text,
                    evidence_uri=str(path),
                    extractor="pdf_text_layer",
                    checksum=checksum,
                    elapsed_ms=int((time.perf_counter() - started) * 1000),
                )
                self._cache[checksum] = extracted
                return extracted
        from docling.document_converter import DocumentConverter

        result = DocumentConverter().convert(path)
        document = result.document
        try:
            text = document.export_to_markdown()
        except AttributeError:
            text = str(document)
        extracted = ExtractedDocument(
            text=text,
            evidence_uri=str(path),
            extractor="docling",
            checksum=checksum,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
        self._cache[checksum] = extracted
        return extracted

    def _extract_pdf_text_layer(self, content: bytes) -> str:
        try:
            import pymupdf
            doc = pymupdf.open(stream=content, filetype="pdf")
            lines = []
            for page in doc:
                t = page.get_text()
                if t.strip():
                    lines.append(t.strip())
            if lines:
                return "\n".join(lines)
        except Exception:
            pass
        raw = content.decode("latin-1", errors="ignore")
        lines = []
        for match in re.finditer(r"\((.*?)\)\s*Tj", raw, flags=re.DOTALL):
            text = match.group(1)
            text = text.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
            if text.strip():
                lines.append(text.strip())
        return "\n".join(lines)


class DoclingIngestionService:
    def __init__(self, store: Phase0Store, storage: S3ObjectStorage, extractor: DoclingExtractor | None = None) -> None:
        self.store = store
        self.storage = storage
        self.extractor = extractor or DoclingExtractor()
        self.audit = AuditLedger(store)

    def ingest(self, merchant_id: str, path: Path, content_type: str) -> tuple[Product, Approval]:
        content = path.read_bytes()
        stored = self.storage.put(
            merchant_id=merchant_id,
            key=f"supplier/{path.name}",
            content=content,
            content_type=content_type,
        )
        extracted = self.extractor.extract(path)
        title = self._first_meaningful_line(extracted.text)
        product = Product(
            merchant_id=merchant_id,
            title=title,
            attributes={
                "extracted_title": {
                    "value": title,
                    "confidence": 0.65,
                    "verified": False,
                    "evidence": stored.uri,
                }
            },
            evidence_refs=[stored.uri],
        )
        self.store.put(product)
        approval = Approval(
            merchant_id=merchant_id,
            action="approve_product_draft",
            object_id=product.id,
            requested_by="docling_ingestion",
        )
        self.store.put(approval)
        self.audit.record(
            merchant_id=merchant_id,
            actor="ingestion",
            source="docling",
            action="supplier_document_extracted",
            object_type="Product",
            object_id=product.id,
            evidence_ref=stored.uri,
            result="draft_requires_approval",
        )
        return product, approval

    def _first_meaningful_line(self, text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip("#* \t")
            if cleaned:
                return cleaned[:200]
        return "Untitled supplier draft"
