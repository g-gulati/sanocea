from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sanocea.packages.domain_contract.models import Approval, Product
from sanocea.packages.domain_contract.store import Phase0Store


@dataclass(frozen=True)
class ExtractedField:
    name: str
    value: Any
    confidence: float
    evidence_ref: str
    verified: bool = False


class ObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, merchant_id: str, name: str, content: bytes) -> str:
        uri = f"memory://{merchant_id}/{name}"
        self.objects[uri] = content
        return uri


class IngestionService:
    def __init__(self, store: Phase0Store, storage: ObjectStorage | None = None) -> None:
        self.store = store
        self.storage = storage or ObjectStorage()

    def ingest_supplier_file(self, merchant_id: str, filename: str, content: bytes) -> tuple[Product, Approval]:
        uri = self.storage.put(merchant_id, filename, content)
        text = content.decode("utf-8", errors="ignore")
        title = text.splitlines()[0].strip() if text.splitlines() else "Untitled supplier draft"
        evidence = f"{uri}#line=1"
        product = Product(
            merchant_id=merchant_id,
            title=title,
            attributes={"extracted_title": {"value": title, "confidence": 0.7, "verified": False}},
            evidence_refs=[evidence],
        )
        self.store.put(product)
        approval = Approval(
            merchant_id=merchant_id,
            action="approve_product_draft",
            object_id=product.id,
            requested_by="ingestion",
        )
        self.store.put(approval)
        return product, approval

