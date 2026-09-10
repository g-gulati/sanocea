from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from sanocea.packages.audit import AuditLedger
from sanocea.packages.domain_contract.models import ExtractedAttribute, ProductDraft
from sanocea.packages.object_storage import S3ObjectStorage


class StructuredProductIngestor:
    def __init__(self, store, storage: S3ObjectStorage | None = None) -> None:
        self.store = store
        self.storage = storage
        self.audit = AuditLedger(store)

    def ingest_file(self, merchant_id: str, path: Path, content_type: str | None = None) -> list[ProductDraft]:
        content = path.read_bytes()
        evidence_uri = f"file://{path.resolve()}"
        if self.storage is not None:
            stored = self.storage.put(
                merchant_id=merchant_id,
                key=f"phase1/supplier/{path.name}",
                content=content,
                content_type=content_type or "application/octet-stream",
            )
            evidence_uri = stored.uri
        if path.suffix.lower() == ".csv":
            rows = self._read_csv(path)
        elif path.suffix.lower() in (".xlsx", ".xlsm"):
            rows = self._read_xlsx(path)
        else:
            raise ValueError(f"structured ingestion does not support {path.suffix}")
        drafts = [self._row_to_draft(merchant_id, row, evidence_uri) for row in rows]
        existing_by_sku = {
            draft.sku: draft
            for draft in self.store.list(ProductDraft, merchant_id)
            if draft.sku
        }
        for draft in drafts:
            if draft.sku and draft.sku in existing_by_sku:
                draft.id = existing_by_sku[draft.sku].id
            elif draft.sku:
                existing_by_sku[draft.sku] = draft
            self.store.put(draft)
            self.audit.record(
                merchant_id=merchant_id,
                actor="ingestion",
                source="structured_spreadsheet",
                action="product_draft_created",
                object_type="ProductDraft",
                object_id=draft.id,
                evidence_ref=evidence_uri,
                result=draft.state,
            )
        return drafts

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            return [
                {"row_number": i + 2, "sheet": None, "values": dict(row)}
                for i, row in enumerate(reader)
            ]

    def _read_xlsx(self, path: Path) -> list[dict[str, Any]]:
        workbook = load_workbook(path, read_only=True, data_only=True)
        rows: list[dict[str, Any]] = []
        for sheet in workbook.worksheets:
            iterator = sheet.iter_rows(values_only=True)
            headers = [str(h).strip() if h is not None else "" for h in next(iterator)]
            for idx, values in enumerate(iterator, start=2):
                rows.append(
                    {
                        "row_number": idx,
                        "sheet": sheet.title,
                        "values": {headers[i]: values[i] for i in range(len(headers)) if headers[i]},
                    }
                )
        return rows

    def _row_to_draft(self, merchant_id: str, row: dict[str, Any], evidence_uri: str) -> ProductDraft:
        values = {self._canonical_header(str(k)): v for k, v in row["values"].items()}
        extracted = [
            ExtractedAttribute(
                name=key,
                value=value,
                source_file=evidence_uri,
                source_locator={"sheet": row.get("sheet"), "row": row["row_number"], "column": key},
                evidence_ref=f"{evidence_uri}#row={row['row_number']}&column={key}",
                confidence=1.0 if value not in (None, "") else 0.0,
                verified=False,
            )
            for key, value in values.items()
        ]
        price = values.get("price")
        parsed_price: int | None = None
        invalid_price = False
        if price not in (None, ""):
            try:
                parsed_price = int(float(price) * 100)
            except (TypeError, ValueError):
                invalid_price = True
        return ProductDraft(
            merchant_id=merchant_id,
            sku=str(values.get("sku")).strip() if values.get("sku") not in (None, "") else None,
            title=str(values.get("title")).strip() if values.get("title") not in (None, "") else None,
            price=parsed_price,
            currency=str(values.get("currency")).strip() if values.get("currency") not in (None, "") else None,
            product_type=str(values.get("product_type")).strip() if values.get("product_type") not in (None, "") else None,
            category=str(values.get("category")).strip() if values.get("category") not in (None, "") else None,
            attributes={k: v for k, v in values.items() if k not in {"sku", "title", "price", "currency", "product_type", "category"}},
            extracted_attributes=extracted,
            evidence_refs=[evidence_uri],
            validation_errors=["invalid_price"] if invalid_price else [],
            state="INVALID" if invalid_price else "INCOMPLETE",
        )

    def _canonical_header(self, header: str) -> str:
        key = header.strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "sku_code": "sku",
            "item_title": "title",
            "retail_price": "price",
            "type": "product_type",
            "colour_name": "colour",
            "color": "colour",
            "size_label": "size",
            "fabric": "material",
            "image_file": "image",
        }
        return aliases.get(key, key)
