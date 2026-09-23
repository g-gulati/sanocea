from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

try:
    from sanocea.packages.audit import AuditLedger
    from sanocea.packages.domain_contract.models import ExtractedAttribute, ProductDraft, ProvenanceClassification
    from sanocea.packages.object_storage import S3ObjectStorage
    from sanocea.packages.product_onboarding.identity import ProductIdentityResolver
    from sanocea.packages.product_onboarding.provenance import (
        CommercialFact,
        detect_and_merge_fact,
        normalize_commercial_fact_value,
        sync_facts_to_extracted_attributes,
    )
    from sanocea.packages.product_onboarding.variants import VariantMatrixEngine
    from sanocea.workers.ingestion import DoclingExtractor, ImageProcessingService
except ImportError:
    from packages.audit import AuditLedger
    from packages.domain_contract.models import ExtractedAttribute, ProductDraft, ProvenanceClassification
    from packages.object_storage import S3ObjectStorage
    from packages.product_onboarding.identity import ProductIdentityResolver
    from packages.product_onboarding.provenance import (
        CommercialFact,
        detect_and_merge_fact,
        normalize_commercial_fact_value,
        sync_facts_to_extracted_attributes,
    )
    from packages.product_onboarding.variants import VariantMatrixEngine
    from workers.ingestion import DoclingExtractor, ImageProcessingService


class UnifiedProductIngestor:
    """Unified Merchant Ingestion Service (Harden Stage 4).
    Accepts CSV, XLSX, PDF (via Docling), product images, and mixed-source packages through one
    coherent ingestion boundary.
    Extracts commercial facts with exact source file, line/sheet/row/column/cell locators.
    Honors Stage 4 Amendments:
    1. Strict Non-Fuzzy Identity Resolution (authoritative identifiers only, fuzzy generates candidates).
    2. Orthogonal Identity Status (RESOLVED, AMBIGUOUS, UNRESOLVED, CONFLICT).
    3. Honest XLSX Formula Handling (extracts formula text, cached value, cell locator separately; fails closed).
    4. Durable, merchant-scoped Identity Decisions integration.
    5. Parent-variant matrix resolution & variant lifecycle (absence != deletion; mark STALE).
    6. Fault isolation: quarantines corrupt or ballast files (.DS_Store, corrupt binary) without crashing package.
    """

    def __init__(self, store, storage: S3ObjectStorage | None = None) -> None:
        self.store = store
        self.storage = storage
        self.audit = AuditLedger(store)
        self.docling_extractor = DoclingExtractor()
        self.image_service = ImageProcessingService(store, storage) if storage else None
        self.identity_resolver = ProductIdentityResolver(store)
        self.variant_engine = VariantMatrixEngine()

    def ingest_file(self, merchant_id: str, path: Path, content_type: str | None = None) -> list[ProductDraft]:
        evidence_uri = f"file://{path.resolve()}"
        suffix = path.suffix.lower()

        # Fault isolation: quarantine unsupported or ballast files
        supported_suffixes = {".csv", ".xlsx", ".xlsm", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}
        if suffix not in supported_suffixes or path.name.startswith("."):
            self.audit.record(
                merchant_id=merchant_id,
                actor="ingestion",
                source="unified_ingestor",
                action="file_quarantined",
                object_type="File",
                object_id=path.name,
                evidence_ref=evidence_uri,
                result="quarantined_unsupported_ballast",
            )
            return []

        try:
            content = path.read_bytes()
        except Exception as exc:
            self.audit.record(
                merchant_id=merchant_id,
                actor="ingestion",
                source="unified_ingestor",
                action="file_quarantined",
                object_type="File",
                object_id=path.name,
                evidence_ref=evidence_uri,
                result=f"read_error:{exc}",
            )
            return []

        if self.storage is not None:
            stored = self.storage.put(
                merchant_id=merchant_id,
                key=f"stage3/supplier/{path.name}",
                content=content,
                content_type=content_type or "application/octet-stream",
            )
            evidence_uri = stored.uri

        drafts: list[ProductDraft] = []
        try:
            if suffix == ".csv":
                rows = self._read_csv(path)
                drafts = self._rows_to_drafts(merchant_id, rows, evidence_uri, path.name)
            elif suffix in (".xlsx", ".xlsm"):
                rows = self._read_xlsx(path)
                drafts = self._rows_to_drafts(merchant_id, rows, evidence_uri, path.name)
            elif suffix == ".pdf":
                drafts = self._read_pdf(merchant_id, path, evidence_uri)
            elif suffix in (".png", ".jpg", ".jpeg", ".webp"):
                drafts = self._read_image(merchant_id, path, evidence_uri)
        except Exception as exc:
            self.audit.record(
                merchant_id=merchant_id,
                actor="ingestion",
                source="unified_ingestor",
                action="file_quarantined",
                object_type="File",
                object_id=path.name,
                evidence_ref=evidence_uri,
                result=f"parse_error:{exc}",
            )
            return []

        existing_drafts = self.store.list(ProductDraft, merchant_id)
        persisted_drafts = []

        for draft in drafts:
            # Resolve product identity (Authoritative vs Fuzzy Candidates)
            resolved = self.identity_resolver.resolve_draft(draft, existing_drafts)

            # Match against existing drafts in catalog
            matched_existing: ProductDraft | None = None
            if resolved.identity_status == "RESOLVED" and resolved.identity_key:
                for exist in existing_drafts:
                    if exist.identity_key == resolved.identity_key or (exist.sku and resolved.sku and exist.sku == resolved.sku):
                        matched_existing = exist
                        break
            elif resolved.sku:
                for exist in existing_drafts:
                    if exist.sku == resolved.sku:
                        matched_existing = exist
                        break

            if matched_existing:
                # Merge incoming facts into existing draft
                for fact in resolved.commercial_facts.values():
                    detect_and_merge_fact(matched_existing, fact)

                # Reconcile variant lifecycle transitions (Added, Changed SKU/Barcode, Option Renamed, Stale)
                if resolved.variants:
                    self.variant_engine.reconcile_variant_lifecycle(
                        matched_existing,
                        resolved.variants,
                        source_revision=path.name,
                    )

                if evidence_uri not in matched_existing.evidence_refs:
                    matched_existing.evidence_refs.append(evidence_uri)

                matched_existing.identity_status = resolved.identity_status
                matched_existing.identity_key = resolved.identity_key or matched_existing.identity_key
                sync_facts_to_extracted_attributes(matched_existing)
                self.store.put(matched_existing)
                persisted_drafts.append(matched_existing)
            else:
                sync_facts_to_extracted_attributes(resolved)
                self.store.put(resolved)
                persisted_drafts.append(resolved)
                existing_drafts.append(resolved)

            self.audit.record(
                merchant_id=merchant_id,
                actor="ingestion",
                source="unified_ingestor",
                action="product_draft_created",
                object_type="ProductDraft",
                object_id=persisted_drafts[-1].id,
                evidence_ref=evidence_uri,
                result=persisted_drafts[-1].state,
            )

        return persisted_drafts

    def ingest_package(self, merchant_id: str, paths: list[Path]) -> list[ProductDraft]:
        """Ingests a mixed package of merchant source files.
        Processes all valid files while safely isolating and quarantining corrupt/ballast files.
        """
        all_drafts: list[ProductDraft] = []
        for path in paths:
            file_drafts = self.ingest_file(merchant_id, path)
            all_drafts.extend(file_drafts)

        # Return de-duplicated list by id
        seen: set[str] = set()
        deduped: list[ProductDraft] = []
        for d in all_drafts:
            if d.id not in seen:
                seen.add(d.id)
                deduped.append(d)
        return deduped

    # --- CSV & Excel extraction -------------------------------------------------------------

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        raw = path.read_bytes()
        text: str = ""
        for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")

        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample)
            delim = str(getattr(dialect, "delimiter", ""))
            if len(delim) != 1 or delim in ("\r", "\n", ""):
                dialect = csv.excel
        except Exception:
            dialect = csv.excel

        reader = csv.reader(io.StringIO(text), dialect=dialect)
        rows: list[dict[str, Any]] = []
        headers: list[str] = []

        for idx, line in enumerate(reader, start=1):
            if not line or not any(c.strip() for c in line):
                continue
            if not headers:
                headers = [str(h).strip() for h in line]
                continue
            # Handle jagged rows (pad with None if short, slice if long)
            vals = line[:len(headers)]
            if len(vals) < len(headers):
                vals.extend([None] * (len(headers) - len(vals)))

            row_values = {headers[i]: vals[i] for i in range(len(headers)) if headers[i]}
            rows.append({
                "row_number": idx,
                "sheet": None,
                "values": row_values,
                "formula_metadata": {},
            })

        return rows

    def _read_xlsx(self, path: Path) -> list[dict[str, Any]]:
        """Reads XLSX workbook with formula text and cached values separated.
        Unrolls merged cells and detects hidden sheets (Stage 4 Amendment 3).
        """
        wb_formulas = load_workbook(path, data_only=False)
        wb_values = load_workbook(path, data_only=True)
        rows: list[dict[str, Any]] = []

        for sheet_name in wb_values.sheetnames:
            sheet_val = wb_values[sheet_name]
            sheet_form = wb_formulas[sheet_name]
            is_hidden = getattr(sheet_val, "sheet_state", "visible") in ("hidden", "veryHidden")
            if is_hidden:
                # Stage 4: Hidden sheets in merchant workbooks contain internal notes/costing, skip public row extraction
                continue

            # Build merged cells lookup (read-only, does not mutate openpyxl MergedCell)
            merged_val_lookup: dict[tuple[int, int], Any] = {}
            merged_form_lookup: dict[tuple[int, int], Any] = {}
            for m_range in sheet_val.merged_cells.ranges:
                top_val = sheet_val.cell(m_range.min_row, m_range.min_col).value
                top_form = sheet_form.cell(m_range.min_row, m_range.min_col).value
                for r in range(m_range.min_row, m_range.max_row + 1):
                    for c in range(m_range.min_col, m_range.max_col + 1):
                        merged_val_lookup[(r, c)] = top_val
                        merged_form_lookup[(r, c)] = top_form

            # Determine headers from first row
            header_row_idx = 1
            headers: list[str] = []
            for col_idx in range(1, sheet_val.max_column + 1):
                val = sheet_val.cell(row=header_row_idx, column=col_idx).value
                headers.append(str(val).strip() if val is not None else f"col_{col_idx}")

            for row_idx in range(header_row_idx + 1, sheet_val.max_row + 1):
                row_vals: dict[str, Any] = {}
                row_formula_meta: dict[str, Any] = {}
                has_any_val = False

                for col_idx in range(1, min(len(headers) + 1, sheet_val.max_column + 1)):
                    from openpyxl.utils import get_column_letter
                    header = headers[col_idx - 1]
                    cell_val = merged_val_lookup.get((row_idx, col_idx), sheet_val.cell(row=row_idx, column=col_idx).value)
                    cell_form = merged_form_lookup.get((row_idx, col_idx), sheet_form.cell(row=row_idx, column=col_idx).value)
                    col_letter = get_column_letter(col_idx)
                    cell_ref = f"{col_letter}{row_idx}"

                    if cell_val is not None:
                        has_any_val = True

                    # Formula detection
                    if isinstance(cell_form, str) and cell_form.startswith("="):
                        formula_text = cell_form
                        cached_value = cell_val
                        # Fail closed if cached value is missing or an Excel error code
                        if cached_value is None or (isinstance(cached_value, str) and cached_value.startswith("#")):
                            actual_val = None
                            untrustworthy = True
                        else:
                            actual_val = cached_value
                            untrustworthy = False

                        row_vals[header] = actual_val
                        row_formula_meta[header] = {
                            "formula_text": formula_text,
                            "cached_value": cached_value,
                            "cell": cell_ref,
                            "formula_evaluated": False,
                            "untrustworthy": untrustworthy,
                            "sheet_hidden": is_hidden,
                        }
                    else:
                        row_vals[header] = cell_val

                if has_any_val:
                    rows.append({
                        "row_number": row_idx,
                        "sheet": sheet_name,
                        "values": row_vals,
                        "formula_metadata": row_formula_meta,
                        "is_hidden": is_hidden,
                    })

        return rows

    def _rows_to_drafts(
        self,
        merchant_id: str,
        rows: list[dict[str, Any]],
        evidence_uri: str,
        source_revision: str | None = None,
    ) -> list[ProductDraft]:
        """Converts structured rows into canonical ProductDrafts with parent-variant grouping."""
        # 1. Group rows by parent identifier (parent_sku / style_code / style_id) if present
        parent_groups: dict[str, list[dict[str, Any]]] = {}
        standalone_rows: list[dict[str, Any]] = []

        for row in rows:
            raw_vals = {self._canonical_header(str(k)): v for k, v in row["values"].items()}
            parent_id = (
                raw_vals.get("parent_sku")
                or raw_vals.get("style_code")
                or raw_vals.get("style_id")
                or raw_vals.get("product_id")
            )
            if parent_id and str(parent_id).strip():
                p_key = str(parent_id).strip()
                parent_groups.setdefault(p_key, []).append(row)
            else:
                standalone_rows.append(row)

        drafts: list[ProductDraft] = []

        # 2. Build multi-variant parent drafts
        for parent_id, group_rows in parent_groups.items():
            first_row = group_rows[0]
            first_raw = {self._canonical_header(str(k)): v for k, v in first_row["values"].items()}

            title = str(first_raw.get("title") or first_raw.get("product_name") or f"Style {parent_id}").strip()
            # A blank product type must stay blank (so it is flagged as missing), not become the literal text
            # "default" - which used to make an incomplete row look complete and publish with type "default".
            product_type = str(first_raw.get("product_type") or "").strip() or None
            category = str(first_raw.get("category") or "default").strip()
            currency = str(first_raw.get("currency") or "INR").strip().upper()

            # Build variants for this parent
            variants: list[Any] = []
            min_price: int | None = None

            for r in group_rows:
                r_vals = {self._canonical_header(str(k)): v for k, v in r["values"].items()}
                v_sku = str(r_vals.get("sku") or r_vals.get("variant_sku") or "").strip() or None
                v_barcode = str(r_vals.get("barcode") or r_vals.get("variant_barcode") or r_vals.get("upc") or r_vals.get("ean") or "").strip() or None
                v_price_raw = r_vals.get("price") or r_vals.get("variant_price") or r_vals.get("price_formula")
                v_price = normalize_commercial_fact_value("price", v_price_raw) if v_price_raw else None
                v_weight = normalize_commercial_fact_value("weight", r_vals.get("weight"))
                v_dim = normalize_commercial_fact_value("dimensions", r_vals.get("dimensions"))
                v_stock = int(r_vals.get("inventory_quantity") or r_vals.get("qty") or 0) if r_vals.get("inventory_quantity") or r_vals.get("qty") else None

                options = self.variant_engine.extract_option_values_from_row(r_vals)

                if v_price and (min_price is None or v_price < min_price):
                    min_price = v_price

                locator = {"sheet": r.get("sheet"), "row": r["row_number"], "source_revision": source_revision}
                v_draft = self.variant_engine.create_variant_draft(
                    sku=v_sku,
                    barcode=v_barcode,
                    option_values=options,
                    price=v_price,
                    weight=v_weight,
                    dimensions=v_dim if isinstance(v_dim, dict) else None,
                    inventory_quantity=v_stock,
                    source_locators=[locator],
                )
                variants.append(v_draft)

            # Build parent commercial facts from first row
            parent_facts, parent_attrs, invalid_price = self._build_commercial_facts_and_attrs(
                first_row, evidence_uri
            )

            all_option_dimensions = sorted({k for v in variants for k in v.option_values.keys()})

            draft = ProductDraft(
                merchant_id=merchant_id,
                sku=parent_id,
                product_id=parent_id,
                title=title,
                price=min_price or first_raw.get("price"),
                currency=currency,
                product_type=product_type,
                category=category,
                attributes={"style_code": parent_id, **first_raw},
                commercial_facts=parent_facts,
                extracted_attributes=parent_attrs,
                evidence_refs=[evidence_uri],
                options=all_option_dimensions,
                variants=variants,
                source_revision=source_revision,
                state="READY" if (min_price and not invalid_price) else "INCOMPLETE",
            )
            drafts.append(draft)

        # 3. Build standalone drafts
        for row in standalone_rows:
            draft = self._row_to_draft(merchant_id, row, evidence_uri, source_revision)
            drafts.append(draft)

        return drafts

    def _build_commercial_facts_and_attrs(
        self,
        row: dict[str, Any],
        evidence_uri: str,
    ) -> tuple[dict[str, CommercialFact], list[ExtractedAttribute], bool]:
        raw_values = {self._canonical_header(str(k)): v for k, v in row["values"].items()}
        formula_meta = {self._canonical_header(str(k)): v for k, v in row.get("formula_metadata", {}).items()}
        commercial_facts: dict[str, CommercialFact] = {}
        extracted: list[ExtractedAttribute] = []
        invalid_price = False

        for key, value in raw_values.items():
            locator = {"sheet": row.get("sheet"), "row": row["row_number"], "column": key}
            meta = formula_meta.get(key, {})
            if meta.get("cell"):
                locator["cell"] = meta["cell"]
            if meta.get("sheet_hidden"):
                locator["sheet_hidden"] = True

            is_empty = value in (None, "")
            classification = (
                ProvenanceClassification.MISSING.value
                if is_empty
                else ProvenanceClassification.SOURCE_FACT.value
            )

            fact_metadata: dict[str, Any] = {"extractor": "structured_spreadsheet"}
            if meta.get("formula_text"):
                fact_metadata["formula_text"] = meta["formula_text"]
                fact_metadata["cached_value"] = meta.get("cached_value")
                fact_metadata["formula_evaluated"] = False
                if meta.get("untrustworthy"):
                    fact_metadata["untrustworthy_formula"] = True

            fact = CommercialFact(
                name=key,
                value=None if is_empty else value,
                source=evidence_uri,
                locator=locator,
                evidence_ref=f"{evidence_uri}#row={row['row_number']}&column={key}",
                classification=classification,
                confidence=0.0 if is_empty else 1.0,
                metadata=fact_metadata,
            )
            commercial_facts[key] = fact
            extracted.append(
                ExtractedAttribute(
                    name=key,
                    value=value,
                    source_file=evidence_uri,
                    source_locator=locator,
                    evidence_ref=fact.evidence_ref,
                    confidence=fact.confidence,
                    extractor="structured",
                )
            )

        price_raw = raw_values.get("price")
        if price_raw not in (None, ""):
            parsed_price = normalize_commercial_fact_value("price", price_raw)
            if parsed_price is None or parsed_price <= 0:
                invalid_price = True

        return commercial_facts, extracted, invalid_price

    def _row_to_draft(
        self,
        merchant_id: str,
        row: dict[str, Any],
        evidence_uri: str,
        source_revision: str | None = None,
    ) -> ProductDraft:
        raw_values = {self._canonical_header(str(k)): v for k, v in row["values"].items()}
        commercial_facts, extracted, invalid_price = self._build_commercial_facts_and_attrs(row, evidence_uri)

        price_raw = raw_values.get("price")
        parsed_price: int | None = None
        if price_raw not in (None, ""):
            parsed_price = normalize_commercial_fact_value("price", price_raw)

        sku = str(raw_values.get("sku")).strip() if raw_values.get("sku") not in (None, "") else None
        title = str(raw_values.get("title")).strip() if raw_values.get("title") not in (None, "") else None
        currency = str(raw_values.get("currency")).strip().upper() if raw_values.get("currency") not in (None, "") else None
        product_type = str(raw_values.get("product_type")).strip() if raw_values.get("product_type") not in (None, "") else None
        category = str(raw_values.get("category")).strip() if raw_values.get("category") not in (None, "") else None

        core_attributes = {
            k: v for k, v in raw_values.items()
            if k not in {"sku", "title", "price", "currency", "product_type", "category"}
        }

        # Check if row defines single variant options
        options_dict = self.variant_engine.extract_option_values_from_row(raw_values)
        variants = []
        if options_dict:
            v_draft = self.variant_engine.create_variant_draft(
                sku=sku,
                barcode=str(raw_values.get("barcode") or "").strip() or None,
                option_values=options_dict,
                price=parsed_price,
                source_locators=[{"sheet": row.get("sheet"), "row": row["row_number"]}],
            )
            variants.append(v_draft)

        state = "INVALID" if invalid_price else ("READY" if (parsed_price and sku and title) else "INCOMPLETE")

        return ProductDraft(
            merchant_id=merchant_id,
            sku=sku,
            title=title,
            price=parsed_price,
            currency=currency,
            product_type=product_type,
            category=category,
            attributes=core_attributes,
            commercial_facts=commercial_facts,
            extracted_attributes=extracted,
            evidence_refs=[evidence_uri],
            options=sorted(options_dict.keys()),
            variants=variants,
            source_revision=source_revision,
            validation_errors=["invalid_price"] if invalid_price else [],
            state=state,
        )

    # --- PDF extraction (Docling) -----------------------------------------------------------

    def _read_pdf(self, merchant_id: str, path: Path, evidence_uri: str) -> list[ProductDraft]:
        extracted_doc = self.docling_extractor.extract(path)
        text = extracted_doc.text

        # 1. Multi-product PDF detection via markdown tables
        table_rows = self._extract_markdown_tables(text)
        if table_rows:
            return self._rows_to_drafts(merchant_id, table_rows, evidence_uri, path.name)

        # 2. Multi-section specification detection (e.g. sections separated by "### Product" or "---")
        sections = re.split(r"\n(?=#{1,3}\s+[A-Za-z0-9])", text)
        if len(sections) > 1:
            drafts = []
            for sec in sections:
                d = self._parse_specification_section(merchant_id, sec, evidence_uri, extracted_doc.extractor)
                if d:
                    drafts.append(d)
            if drafts:
                return drafts

        # 3. Single product specification fallback
        single_draft = self._parse_specification_section(merchant_id, text, evidence_uri, extracted_doc.extractor)
        return [single_draft] if single_draft else []

    def _parse_specification_section(
        self,
        merchant_id: str,
        section_text: str,
        evidence_uri: str,
        extractor: str,
    ) -> ProductDraft | None:
        facts_extracted: dict[str, tuple[Any, int]] = {}
        for line_idx, line in enumerate(section_text.splitlines(), start=1):
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#"):
                continue
            m = re.match(r"^([\w\s]+)[:=\-]\s*(.+)$", cleaned)
            if m:
                k, v = m.groups()
                canon_key = self._canonical_header(k.strip())
                if canon_key and canon_key not in facts_extracted:
                    facts_extracted[canon_key] = (v.strip(), line_idx)

        if not facts_extracted:
            return None

        sku = facts_extracted.get("sku", (None, 0))[0]
        title = facts_extracted.get("title", (self._first_meaningful_line(section_text), 1))[0]
        price_raw = facts_extracted.get("price", (None, 0))[0]
        parsed_price = normalize_commercial_fact_value("price", price_raw) if price_raw else None

        commercial_facts: dict[str, CommercialFact] = {}
        extracted_attrs: list[ExtractedAttribute] = []
        for key, (val, line_idx) in facts_extracted.items():
            locator = {"page": 1, "line": line_idx, "extractor": extractor}
            fact = CommercialFact(
                name=key,
                value=val,
                source=evidence_uri,
                locator=locator,
                evidence_ref=f"{evidence_uri}#line={line_idx}",
                classification=ProvenanceClassification.SOURCE_FACT.value,
                confidence=0.90,
                metadata={"extractor": extractor},
            )
            commercial_facts[key] = fact
            extracted_attrs.append(
                ExtractedAttribute(
                    name=key,
                    value=val,
                    source_file=evidence_uri,
                    source_locator=locator,
                    evidence_ref=fact.evidence_ref,
                    confidence=fact.confidence,
                    extractor=extractor,
                )
            )

        return ProductDraft(
            merchant_id=merchant_id,
            sku=str(sku).strip() if sku else None,
            title=str(title).strip() if title else "Untitled Product",
            price=parsed_price,
            currency=facts_extracted.get("currency", ("INR", 0))[0],
            product_type=facts_extracted.get("product_type", ("apparel", 0))[0],
            category=facts_extracted.get("category", ("default", 0))[0],
            attributes={
                k: v[0] for k, v in facts_extracted.items()
                if k not in {"sku", "title", "price", "currency", "product_type", "category"}
            },
            commercial_facts=commercial_facts,
            extracted_attributes=extracted_attrs,
            evidence_refs=[evidence_uri],
            state="INCOMPLETE",
        )

    def _extract_markdown_tables(self, text: str) -> list[dict[str, Any]]:
        """Parses ALL markdown tables generated by Docling into structured row dictionaries."""
        lines = text.splitlines()
        rows: list[dict[str, Any]] = []
        headers: list[str] = []
        in_table = False

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                if not in_table or not headers:
                    headers = [self._canonical_header(c) for c in cells]
                    in_table = True
                    continue
                if all(re.match(r"^:?-+:?$", c) for c in cells):
                    # Separator line
                    continue
                if len(cells) == len(headers):
                    row_dict = {headers[i]: cells[i] for i in range(len(headers)) if headers[i]}
                    rows.append({"row_number": idx, "sheet": "pdf_table", "values": row_dict})
            else:
                # End of current table, reset to detect subsequent tables
                if in_table:
                    headers = []
                    in_table = False

        return rows

    # --- Image extraction -------------------------------------------------------------------

    def _read_image(self, merchant_id: str, path: Path, evidence_uri: str) -> list[ProductDraft]:
        from PIL import Image

        img = Image.open(path)
        dimensions = f"{img.width}x{img.height}"
        locator = {"filename": path.name, "dimensions": dimensions, "format": img.format}

        media_id = None
        if self.image_service:
            asset = self.image_service.transform(merchant_id, path)
            media_id = asset.id

        fact = CommercialFact(
            name="image",
            value=evidence_uri,
            source=evidence_uri,
            locator=locator,
            evidence_ref=evidence_uri,
            classification=ProvenanceClassification.SOURCE_FACT.value,
            confidence=1.0,
            metadata={"media_asset_id": media_id, "dimensions": dimensions},
        )

        sku_guess = None
        existing_drafts = self.store.list(ProductDraft, merchant_id)
        for d in existing_drafts:
            if d.sku and (d.sku.lower() in path.stem.lower() or path.stem.lower().startswith(d.sku.lower())):
                sku_guess = d.sku
                break
        if not sku_guess:
            sku_guess = re.sub(r"[-_](main|front|back|detail|\d+)$", "", path.stem, flags=re.IGNORECASE)

        draft = ProductDraft(
            merchant_id=merchant_id,
            sku=sku_guess,
            title=f"Product Photo {path.stem}",
            attributes={"image_uri": evidence_uri, "image_dimensions": dimensions},
            commercial_facts={"image": fact},
            extracted_attributes=[
                ExtractedAttribute(
                    name="image",
                    value=evidence_uri,
                    source_file=evidence_uri,
                    source_locator=locator,
                    evidence_ref=evidence_uri,
                    confidence=1.0,
                    extractor="image_processor",
                )
            ],
            evidence_refs=[evidence_uri],
            state="INCOMPLETE",
        )
        return [draft]

    def _first_meaningful_line(self, text: str) -> str:
        for line in text.splitlines():
            cleaned = line.strip("#* \t")
            if cleaned and len(cleaned) > 3:
                return cleaned[:200]
        return "Untitled Document"

    def _canonical_header(self, header: str) -> str:
        key = header.strip().lower().replace("-", "_").replace(" ", "_").replace(".", "_")
        aliases = {
            "sku_code": "sku",
            "item_code": "sku",
            "item_title": "title",
            "item_name": "title",
            "product_name": "title",
            "product_title": "title",
            "retail_price": "price",
            "mrp": "price",
            "unit_price": "price",
            "price_formula": "price",
            "calculated_price": "price",
            "type": "product_type",
            "colour_name": "colour",
            "color": "colour",
            "size_label": "size",
            "fabric": "material",
            "composition": "material",
            "image_file": "image",
            "hsn_code": "hsn",
            "tax_rate": "gst_rate",
            "origin": "country_of_origin",
            "origin_country": "country_of_origin",
            "gross_weight": "weight",
            "net_weight": "weight",
            "upc": "barcode",
            "ean": "barcode",
            "gtin": "barcode",
            "style": "style_code",
            "style_id": "style_code",
            "model_no": "style_code",
            "model_number": "style_code",
            "parent_id": "parent_sku",
            "parent": "parent_sku",
            "variant_sku": "sku",
            "variant_barcode": "barcode",
            "variant_price": "price",
            "option_sku": "sku",
            "stock": "inventory_quantity",
            "qty": "inventory_quantity",
            "quantity": "inventory_quantity",
        }
        return aliases.get(key, key)


# Backward compatibility alias
StructuredProductIngestor = UnifiedProductIngestor
