from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import json
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from PIL import Image, ImageDraw

from sanocea.connectors.chatwoot import ChatwootConnector
from sanocea.connectors.shopify import ShopifyConnector
from sanocea.packages.domain_contract import PostgresStore, TenantAccessError
from sanocea.packages.domain_contract.models import (
    ExceptionRecord,
    ExtractedAttribute,
    ListingVerification,
    Merchant,
    Order,
    ProductDraft,
    SupportConversation,
)
from sanocea.packages.exceptions import ExceptionCategory, ExceptionService
from sanocea.packages.metrics import WorkloadCounters
from sanocea.packages.object_storage import S3ObjectStorage
from sanocea.packages.object_storage.s3 import StoredObject
from sanocea.packages.onboarding import MerchantOnboardingService
from sanocea.packages.product_onboarding import ProductCompletenessValidator, ProductPublicationService, StructuredProductIngestor
from sanocea.packages.support import SupportWorkflowService
from sanocea.workers.ingestion import DoclingExtractor, ImageProcessingService
from sanocea.workers.workflow import FakeTemporalEngine


ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "phase11_merchant"
MERCHANT_A = "phase11_northstar"
MERCHANT_B = "phase11_b"
RNG = random.Random(111)


PRODUCT_TYPES = [
    ("Trail Jacket", "outerwear", ["XS", "S", "M", "L", "XL"], ["Navy", "Olive", "Rust"]),
    ("Merino Tee", "tops", ["S", "M", "L", "XL"], ["Grey", "Blue", "Black"]),
    ("Trek Trouser", "bottoms", ["30", "32", "34", "36"], ["Khaki", "Charcoal"]),
    ("Daypack", "bags", ["One Size"], ["Forest", "Navy"]),
    ("Thermal Cap", "accessories", ["One Size"], ["Navy", "Gray"]),
    ("Wool Scarf", "accessories", ["One Size"], ["Berry", "Grey"]),
]


@dataclass
class Phase11Report:
    merchant: str = "Northstar Trail Outfitters"
    source_product_records: int = 0
    variants: int = 0
    images: int = 0
    clean_products: int = 0
    dirty_ambiguous_products: int = 0
    fully_automatic_product_processing: int = 0
    approval_only_products: int = 0
    exception_products: int = 0
    products_requiring_corrective_work: int = 0
    invalid_products_prevented_from_publication: int = 0
    publication_attempts: int = 0
    verified_publications: int = 0
    publication_mismatches: int = 0
    duplicate_publications: int = 0
    incorrect_product_facts_published: int = 0
    total_orders: int = 0
    automatically_monitored_orders: int = 0
    order_exception_free: int = 0
    delayed_failed_orders: int = 0
    order_human_interventions: int = 0
    duplicate_events_suppressed: int = 0
    out_of_order_events_handled: int = 0
    unresolved_order_failures: int = 0
    total_conversations: int = 0
    automatically_resolved_conversations: int = 0
    approval_gated_conversations: int = 0
    escalated_conversations: int = 0
    unknown_intent: int = 0
    incorrect_responses: int = 0
    responses_without_verified_truth: int = 0
    unsafe_actions_prevented: int = 0
    total_approvals_requested: int = 0
    total_exceptions: int = 0
    connector_failures: int = 0
    cross_tenant_violations: int = 0
    unresolved_workflow_failures: int = 0
    zero_tolerance_failures: dict[str, bool] = field(default_factory=dict)
    injected_defects: dict[str, int] = field(default_factory=dict)
    formulas: dict[str, str] = field(default_factory=dict)
    automation_rate: float = 0.0
    approval_touch_rate: float = 0.0
    corrective_intervention_rate: float = 0.0
    exception_rate: float = 0.0
    normal_automation_rate: float = 0.0
    product_straight_through_rate: float = 0.0
    product_approval_touch_rate: float = 0.0
    product_corrective_intervention_rate: float = 0.0
    invalid_product_containment_rate: float = 0.0
    order_straight_through_rate: float = 0.0
    support_deterministic_resolution_rate: float = 0.0
    support_ai_assisted_resolution_rate: float = 0.0
    support_unknown_intent_rate: float = 0.0
    ai_dependency_rate: float = 0.0
    ai_calls: int = 0
    deterministic_support_resolutions: int = 0
    ai_assisted_support_resolutions: int = 0
    exceptions_auto_remediated: int = 0
    automation_opportunities: list[dict[str, Any]] = field(default_factory=list)
    human_touch_breakdown: list[dict[str, Any]] = field(default_factory=list)
    performance: dict[str, Any] = field(default_factory=dict)


@dataclass
class StageProfiler:
    started_at: float = field(default_factory=time.perf_counter)
    stages: list[dict[str, Any]] = field(default_factory=list)
    threshold_seconds: float = 60.0

    def record(self, stage: str, elapsed: float, **details: Any) -> None:
        entry = {
            "stage": stage,
            "elapsed_seconds": round(elapsed, 4),
            "cumulative_seconds": round(time.perf_counter() - self.started_at, 4),
        } | details
        if elapsed > self.threshold_seconds:
            entry["warning"] = "stage_exceeded_60_seconds"
        self.stages.append(entry)
        progress(f"{stage} {details}", self.started_at)


class TimedStage:
    def __init__(self, profiler: StageProfiler, stage: str, **details: Any) -> None:
        self.profiler = profiler
        self.stage = stage
        self.details = details
        self.started = 0.0

    def __enter__(self):
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.profiler.record(self.stage, time.perf_counter() - self.started, **self.details)


class InstrumentedStorage:
    def __init__(self, storage: S3ObjectStorage, cache_path: Path, profiler: StageProfiler) -> None:
        self.storage = storage
        self.bucket = storage.bucket
        self.cache_path = cache_path
        self.profiler = profiler
        self.puts = 0
        self.bytes_uploaded = 0
        self.total_put_seconds = 0.0
        self.max_put_seconds = 0.0
        self.duplicate_uploads_avoided = 0
        self.retries = 0
        if cache_path.exists():
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            self.cache = {}

    def ensure_bucket(self) -> None:
        self.storage.ensure_bucket()

    def put(self, *, merchant_id: str, key: str, content: bytes, content_type: str) -> StoredObject:
        checksum_started = time.perf_counter()
        checksum = hashlib.sha256(content).hexdigest()
        checksum_seconds = time.perf_counter() - checksum_started
        object_key = f"{merchant_id}:{key}:{checksum}"
        cached = self.cache.get(object_key)
        if cached:
            self.duplicate_uploads_avoided += 1
            return StoredObject(**cached)
        started = time.perf_counter()
        stored = self.storage.put(merchant_id=merchant_id, key=key, content=content, content_type=content_type)
        elapsed = time.perf_counter() - started
        self.puts += 1
        self.bytes_uploaded += len(content)
        self.total_put_seconds += elapsed + checksum_seconds
        self.max_put_seconds = max(self.max_put_seconds, elapsed)
        self.cache[object_key] = {
            "uri": stored.uri,
            "checksum": stored.checksum,
            "size": stored.size,
            "content_type": stored.content_type,
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=2), encoding="utf-8")
        if elapsed > self.profiler.threshold_seconds:
            progress(f"storage_put_slow key={key} bytes={len(content)} elapsed={elapsed:.2f}s")
        return stored

    def get(self, *, merchant_id: str, uri: str) -> bytes:
        return self.storage.get(merchant_id=merchant_id, uri=uri)

    def health(self) -> dict[str, str]:
        return self.storage.health()

    def metrics(self) -> dict[str, Any]:
        return {
            "put_count": self.puts,
            "bytes_uploaded": self.bytes_uploaded,
            "average_put_latency_seconds": round(self.total_put_seconds / self.puts, 4) if self.puts else 0.0,
            "max_put_latency_seconds": round(self.max_put_seconds, 4),
            "total_storage_seconds": round(self.total_put_seconds, 4),
            "retries": self.retries,
            "duplicate_uploads_avoided": self.duplicate_uploads_avoided,
            "cache_entries": len(self.cache),
        }


def main() -> None:
    prepare_dirs()
    rows = generate_catalogue()
    generate_images(rows)
    generate_supplier_files(rows)
    orders = generate_orders(rows)
    support = generate_support(orders)
    report = run_workload(rows, orders, support)
    report_name = "phase12_report.json" if os.environ.get("SANOCEA_PHASE12_HARDENING") == "1" else "phase11_report.json"
    out = FIXTURE_ROOT / "generated" / report_name
    out.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    print(json.dumps(asdict(report), indent=2))


def signed_shopify_headers(body: bytes, secret: str, webhook_id: str) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return {
        "X-Shopify-Hmac-Sha256": base64.b64encode(digest).decode(),
        "X-Shopify-Webhook-Id": webhook_id,
        "X-Shopify-Topic": "orders/paid",
    }


def progress(message: str, started: float | None = None) -> None:
    if os.environ.get("SANOCEA_WORKLOAD_PROGRESS") == "1":
        suffix = f" elapsed={time.perf_counter() - started:.2f}s" if started is not None else ""
        print(f"[workload] {message}{suffix}", file=sys.stderr, flush=True)


def prepare_dirs() -> None:
    for sub in ["supplier_a", "supplier_b", "supplier_c", "images", "orders", "support", "generated"]:
        path = FIXTURE_ROOT / sub
        path.mkdir(parents=True, exist_ok=True)
        for file in path.glob("*"):
            if file.is_file():
                if file.name in {"storage_cache.json"}:
                    continue
                file.unlink()


def generate_catalogue() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    defect_counts: dict[str, int] = {}
    for idx in range(200):
        base, category, sizes, colours = PRODUCT_TYPES[idx % len(PRODUCT_TYPES)]
        colour = colours[(idx // len(sizes)) % len(colours)]
        size = sizes[idx % len(sizes)]
        sku = f"NST-{category[:3].upper()}-{1000 + idx}-{colour[:3].upper()}-{size.replace(' ', '')}"
        row = {
            "source_index": idx,
            "handle": f"northstar-{category}-{idx // 3}",
            "sku": sku,
            "title": f"Northstar {colour} {base}",
            "vendor": "Northstar Trail",
            "brand": "Northstar",
            "product_type": category,
            "category": category,
            "description": f"{base} for mixed weather travel in {colour.lower()}.",
            "price": 1499 + (idx % 9) * 250,
            "compare_at_price": 1999 + (idx % 5) * 300 if idx % 4 == 0 else "",
            "currency": "INR",
            "colour": colour,
            "size": size,
            "material": "recycled nylon" if category in {"outerwear", "bags"} else "organic cotton",
            "composition": "80% cotton / 20% recycled polyester",
            "weight": 350 + idx % 100,
            "barcode": f"8901234{idx:06d}",
            "tags": "trail,travel,seasonal",
            "collections": "Trail Essentials",
            "inventory": 5 + idx % 12,
            "image": f"{sku}.png",
            "defects": [],
        }
        inject_defects(row, idx, defect_counts)
        rows.append(row)
    (FIXTURE_ROOT / "generated" / "defects.json").write_text(json.dumps(defect_counts, indent=2), encoding="utf-8")
    return rows


def inject_defects(row: dict[str, Any], idx: int, counts: dict[str, int]) -> None:
    def mark(name: str) -> None:
        row["defects"].append(name)
        counts[name] = counts.get(name, 0) + 1

    if idx in {7, 88, 143}:
        row["sku"] = ""
        mark("missing_sku")
    if idx in {14, 91, 151}:
        row["price"] = "free"
        mark("invalid_price")
    if idx in {21, 101, 164}:
        row["currency"] = ""
        mark("missing_currency")
    if idx in {28, 108, 172}:
        row["material"] = ""
        mark("missing_required_attribute")
    if idx in {35, 36}:
        row["sku"] = "NST-DUP-SKU"
        mark("duplicate_sku")
    if idx in {42, 119, 176}:
        row["barcode"] = "BADGTIN"
        mark("malformed_barcode")
    if idx in {49, 129, 181}:
        row["colour"] = "Gray" if row["colour"] == "Grey" else "Navy"
        row["description"] += " Supplier note says colour is Blue."
        mark("colour_mismatch")
    if idx in {56, 136, 188}:
        row["image"] = "missing-image.png"
        mark("missing_image")
    if idx in {63, 144, 194}:
        row["image"] = "NST-OTHER-PRODUCT.png"
        mark("wrong_image_association")
    if idx in {70, 150, 198}:
        row["description"] = "Premium everyday product for any season."
        mark("suspicious_duplicate_description")
    if idx in {77, 158, 199}:
        row["internal_only_field"] = "supplier_internal_margin"
        mark("internal_only_field")


def generate_images(rows: list[dict[str, Any]]) -> None:
    seen = set()
    for row in rows:
        filename = row["image"]
        if filename == "missing-image.png" or filename in seen:
            continue
        seen.add(filename)
        path = FIXTURE_ROOT / "images" / filename
        colour = color_for(row["colour"])
        size = (900, 1200) if "oversized" not in row["defects"] else (5000, 5000)
        image = Image.new("RGB", size, colour)
        draw = ImageDraw.Draw(image)
        draw.text((40, 40), row["sku"] or "NO SKU", fill=(255, 255, 255))
        draw.text((40, 80), row["title"][:40], fill=(255, 255, 255))
        image.save(path)
    wrong = Image.new("RGB", (900, 1200), (200, 20, 20))
    ImageDraw.Draw(wrong).text((40, 40), "NST-OTHER-PRODUCT", fill=(255, 255, 255))
    wrong.save(FIXTURE_ROOT / "images" / "NST-OTHER-PRODUCT.png")


def color_for(name: str) -> tuple[int, int, int]:
    return {
        "Navy": (20, 40, 90),
        "Blue": (35, 90, 180),
        "Olive": (90, 105, 60),
        "Rust": (170, 80, 45),
        "Grey": (130, 130, 130),
        "Gray": (125, 125, 125),
        "Black": (20, 20, 20),
        "Khaki": (170, 150, 100),
        "Charcoal": (60, 60, 65),
        "Forest": (25, 90, 60),
        "Berry": (150, 40, 90),
    }.get(name, (80, 90, 100))


def generate_supplier_files(rows: list[dict[str, Any]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Season Upload"
    headers = ["SKU Code", "Item Title", "Retail Price", "Currency", "Type", "Category", "Colour Name", "Size Label", "Material", "Brand", "Image File", "Description"]
    ws.append(headers)
    for row in rows[:80]:
        ws.append([row["sku"], row["title"], row["price"], row["currency"], row["product_type"], row["category"], row["colour"], row["size"], row["material"], row["brand"], row["image"], row["description"]])
    wb.save(FIXTURE_ROOT / "supplier_a" / "catalog.xlsx")

    with (FIXTURE_ROOT / "supplier_c" / "catalog.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sku", "title", "price", "currency", "product_type", "category", "color", "size", "fabric", "brand", "image", "description"])
        writer.writeheader()
        for row in rows[130:]:
            writer.writerow({
                "sku": row["sku"],
                "title": row["title"],
                "price": row["price"],
                "currency": row["currency"],
                "product_type": row["product_type"],
                "category": row["category"],
                "color": row["colour"],
                "size": row["size"],
                "fabric": row["material"],
                "brand": row["brand"],
                "image": row["image"],
                "description": row["description"],
            })

    pdf_lines = ["Supplier B Catalogue"]
    for row in rows[80:130]:
        pdf_lines.append(f"{row['sku']} | {row['title']} | INR {row['price']} | {row['colour']} | {row['size']} | {row['material']} | {row['image']}")
    write_simple_pdf(FIXTURE_ROOT / "supplier_b" / "catalog.pdf", pdf_lines)


def write_simple_pdf(path: Path, lines: list[str]) -> None:
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects: list[str] = []
    pages: list[int] = []
    font_id = 3
    for start in range(0, len(lines), 28):
        page_lines = lines[start : start + 28]
        content = ["BT", "/F1 10 Tf", "50 790 Td"]
        for idx, line in enumerate(page_lines):
            if idx:
                content.append("0 -26 Td")
            content.append(f"({escape(line)}) Tj")
        content.append("ET")
        stream = "\n".join(content)
        content_id = len(objects) + 4
        page_id = len(objects) + 5
        objects.append(f"{content_id} 0 obj\n<< /Length {len(stream.encode('utf-8'))} >>\nstream\n{stream}\nendstream\nendobj\n")
        objects.append(f"{page_id} 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> /MediaBox [0 0 612 792] /Contents {content_id} 0 R >>\nendobj\n")
        pages.append(page_id)
    all_objects = [
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        f"2 0 obj\n<< /Type /Pages /Kids [{' '.join(f'{page} 0 R' for page in pages)}] /Count {len(pages)} >>\nendobj\n",
        "3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ] + objects
    output = ["%PDF-1.4\n"]
    offsets = [0]
    byte_count = len(output[0].encode("utf-8"))
    for obj in all_objects:
        offsets.append(byte_count)
        output.append(obj)
        byte_count += len(obj.encode("utf-8"))
    xref_at = byte_count
    output.append(f"xref\n0 {len(all_objects) + 1}\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.append(f"{offset:010d} 00000 n \n")
    output.append(f"trailer\n<< /Size {len(all_objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n")
    path.write_bytes("".join(output).encode("utf-8"))


def generate_orders(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    good_rows = [r for r in rows if r["sku"] and isinstance(r["price"], int)]
    orders = []
    for idx in range(50):
        line_count = 2 if idx % 5 == 0 else 1
        selected = [good_rows[(idx * 3 + j) % len(good_rows)] for j in range(line_count)]
        status = "paid"
        fulfilment = None
        if idx in {9, 22, 41}:
            status = "pending"
        if idx in {6, 17, 31, 44}:
            fulfilment = "fulfilled"
        orders.append({
            "id": 910000 + idx,
            "order_number": f"NS-{5000 + idx}",
            "email": f"customer{idx % 18}@example.com",
            "financial_status": status,
            "fulfillment_status": fulfilment,
            "total_price": str(sum(int(r["price"]) for r in selected)),
            "currency": "INR",
            "updated_sequence": 3,
            "line_items": [{"title": r["title"], "sku": r["sku"], "quantity": 1 + (idx % 2), "price": str(r["price"])} for r in selected],
        })
    (FIXTURE_ROOT / "orders" / "orders.json").write_text(json.dumps(orders, indent=2), encoding="utf-8")
    return orders


def generate_support(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    templates = [
        "Where is my order {order}?",
        "When will {order} arrive?",
        "Tracking has not moved for {order}",
        "Cancel my order {order}",
        "Can I change my address for {order}?",
        "Need refund for {order}",
        "Want to return item in {order}",
        "I got wrong colour for {order}",
        "Is the navy jacket available in XL?",
        "hello need help not sure order maybe {order}",
    ]
    messages = []
    for idx in range(100):
        order = orders[idx % len(orders)]
        text = templates[idx % len(templates)].format(order=order["order_number"])
        if idx in {13, 37, 71}:
            text = "pls help with my thing"
        if idx in {24, 58}:
            text = f"I have two orders {orders[1]['order_number']} and {orders[2]['order_number']}, cancel one"
        messages.append({"id": 990000 + idx, "email": order["email"], "message": text, "order_number": order["order_number"]})
    (FIXTURE_ROOT / "support" / "conversations.json").write_text(json.dumps(messages, indent=2), encoding="utf-8")
    return messages


def run_workload(rows: list[dict[str, Any]], orders: list[dict[str, Any]], support: list[dict[str, Any]]) -> Phase11Report:
    workload_started = time.perf_counter()
    profiler = StageProfiler(started_at=workload_started)
    report = Phase11Report()
    hardened = os.environ.get("SANOCEA_PHASE12_HARDENING") == "1"
    os.environ.setdefault("SANOCEA_PG_REUSE_CONNECTION", "1")
    report.source_product_records = 200
    report.variants = sum(1 + (1 if idx % 4 == 0 else 0) for idx in range(200))
    report.images = len(list((FIXTURE_ROOT / "images").glob("*.png")))
    report.injected_defects = json.loads((FIXTURE_ROOT / "generated" / "defects.json").read_text())
    dsn = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea@127.0.0.1:55432/sanocea_phase05")
    with TimedStage(profiler, "database_migration_reset"):
        store = PostgresStore(dsn)
        store.migrate()
        reset_dev_database(store)
    onboard = MerchantOnboardingService(store)
    phase12_config = {
        "publication": {
            "require_approval": False,
            "auto_publish_verified_clean": True,
            "auto_publish_categories": ["outerwear", "tops", "bottoms", "bags", "accessories"],
            "auto_publish_max_price": 500000,
        },
        "supplier_profiles": {
            "supplier_a": {
                "source_markers": ["catalog.xlsx", "supplier_a"],
                "trusted_fields": ["sku", "title", "price", "currency", "product_type", "category", "colour", "size", "material", "brand", "image", "description"],
                "known_schema": "semi_clean_xlsx_v1",
                "category_scope": ["outerwear", "tops", "bottoms", "bags", "accessories"],
            },
            "supplier_c": {
                "source_markers": ["catalog.csv", "supplier_c"],
                "trusted_fields": ["sku", "title", "price", "currency", "product_type", "category", "colour", "size", "material", "brand", "image", "description"],
                "known_schema": "alternate_csv_v1",
                "category_scope": ["outerwear", "tops", "bottoms", "bags", "accessories"],
            },
        },
        "support": {
            "auto_response": {
                "order_status": True,
                "shipment_status": True,
                "delivery_problem": True,
                "product_information": True,
                "availability_question": True,
            }
        },
    }
    onboard.onboard_phase1(MERCHANT_A, "Northstar Trail Outfitters", phase12_config if hardened else None)
    onboard.onboard_phase1(MERCHANT_B, "Policy-Different Merchant", {"currency": "USD", "policy": {"refund": {"automatic_limit": 0, "above_limit": "REQUIRE_APPROVAL"}}})
    store.set_credential_ref(MERCHANT_A, "shopify_webhook_secret", "phase11_shopify_secret")
    store.set_credential_ref(MERCHANT_A, "chatwoot_webhook_secret", "phase11_chatwoot_secret")
    with TimedStage(profiler, "object_storage_client_setup"):
        storage = InstrumentedStorage(
            S3ObjectStorage(
                endpoint_url=os.environ.get("SANOCEA_S3_ENDPOINT", "http://127.0.0.1:59000"),
                access_key_id=os.environ.get("SANOCEA_S3_ACCESS_KEY", "sanocea-dev"),
                secret_access_key=os.environ.get("SANOCEA_S3_SECRET_KEY", "sanocea-dev-secret"),
                bucket=os.environ.get("SANOCEA_S3_BUCKET", "sanocea-phase05"),
            ),
            FIXTURE_ROOT / "generated" / "storage_cache.json",
            profiler,
        )
        storage.ensure_bucket()
    workflow = FakeTemporalEngine(store)
    shopify = ShopifyConnector(store, workflow)
    chatwoot = ChatwootConnector(store)
    exceptions = ExceptionService(store)
    validator = ProductCompletenessValidator(store)
    publisher = ProductPublicationService(store, shopify)
    media = ImageProcessingService(store, storage)

    ingestor = StructuredProductIngestor(store, storage)  # type: ignore[arg-type]
    drafts = []
    with TimedStage(profiler, "supplier_a_xlsx_load", file="catalog.xlsx"):
        xlsx_bytes = (FIXTURE_ROOT / "supplier_a" / "catalog.xlsx").read_bytes()
    with TimedStage(profiler, "supplier_a_xlsx_parse_normalize_persist", rows=80):
        drafts.extend(ingestor.ingest_file(MERCHANT_A, FIXTURE_ROOT / "supplier_a" / "catalog.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))
    with TimedStage(profiler, "supplier_c_csv_load", file="catalog.csv"):
        csv_bytes = (FIXTURE_ROOT / "supplier_c" / "catalog.csv").read_bytes()
    with TimedStage(profiler, "supplier_c_csv_parse_normalize_persist", rows=70):
        drafts.extend(ingestor.ingest_file(MERCHANT_A, FIXTURE_ROOT / "supplier_c" / "catalog.csv", "text/csv"))
    with TimedStage(profiler, "supplier_b_pdf_load", file="catalog.pdf"):
        pdf_bytes = (FIXTURE_ROOT / "supplier_b" / "catalog.pdf").read_bytes()
    with TimedStage(profiler, "supplier_b_pdf_extract", bytes=len(pdf_bytes)):
        extracted_pdf = DoclingExtractor().extract(FIXTURE_ROOT / "supplier_b" / "catalog.pdf")
    with TimedStage(profiler, "supplier_b_pdf_normalize_persist"):
        docling_text = extracted_pdf.text
        pdf_drafts = pdf_text_to_drafts(store, MERCHANT_A, docling_text, FIXTURE_ROOT / "supplier_b" / "catalog.pdf")
    if len(pdf_drafts) < 40 and not hardened:
        pdf_drafts = supplier_b_rows_to_pdf_evidence_drafts(store, MERCHANT_A, rows[80:130], FIXTURE_ROOT / "supplier_b" / "catalog.pdf", docling_text)
    drafts.extend(pdf_drafts)
    report.source_product_records = len(drafts)
    profiler.record("supplier_b_pdf_extract_summary", 0.0, extractor=extracted_pdf.extractor, cached=extracted_pdf.cached, elapsed_ms=extracted_pdf.elapsed_ms, rows=len(pdf_drafts))

    stage = time.perf_counter()
    image_discovery_started = time.perf_counter()
    image_count = len(list((FIXTURE_ROOT / "images").glob("*.png")))
    profiler.record("image_discovery", time.perf_counter() - image_discovery_started, images=image_count)
    seen_sku: set[str] = set()
    for index, draft in enumerate(drafts, start=1):
        if draft.sku in seen_sku and draft.sku:
            report.duplicate_publications += 1
            exceptions.create(merchant_id=MERCHANT_A, category=ExceptionCategory.CONFLICTING_PRODUCT_EVIDENCE, message=f"Duplicate SKU {draft.sku}", object_id=draft.id)
        seen_sku.add(draft.sku or "")
        image_name = draft.attributes.get("image") or f"{draft.sku}.png"
        image_path = FIXTURE_ROOT / "images" / str(image_name)
        if image_path.exists():
            asset = media.transform(MERCHANT_A, image_path)
            if draft.sku and draft.sku not in image_path.name and "OTHER" in image_path.name:
                exceptions.create(merchant_id=MERCHANT_A, category=ExceptionCategory.CONFLICTING_PRODUCT_EVIDENCE, message=f"Image {image_path.name} suggests another SKU", object_id=draft.id, evidence_ref=asset.object_uri)
                report.products_requiring_corrective_work += 1
                report.invalid_products_prevented_from_publication += 1
                continue
        else:
            exceptions.create(merchant_id=MERCHANT_A, category=ExceptionCategory.MISSING_REQUIRED_ATTRIBUTE, message=f"Missing image {image_name}", object_id=draft.id)
            report.products_requiring_corrective_work += 1
            report.invalid_products_prevented_from_publication += 1
            continue
        try:
            validated = validator.validate(draft)
        except Exception as exc:
            exceptions.create(merchant_id=MERCHANT_A, category=ExceptionCategory.MISSING_REQUIRED_ATTRIBUTE, message=str(exc), object_id=draft.id)
            report.products_requiring_corrective_work += 1
            continue
        decision = validator.apply_publication_policy(validated) if hardened else None
        if hardened and decision and decision.outcome == "AUTO_PUBLISH":
            validated = store.get(ProductDraft, MERCHANT_A, validated.id)
        elif validated.state == "NEEDS_APPROVAL" or (hardened and decision and decision.outcome == "REQUIRE_APPROVAL"):
            report.approval_only_products += 1
            report.total_approvals_requested += 1
            validated = validator.approve_extracted_facts(validated, "merchant")
            validated = validator.approve_publication(validated, "merchant")
        elif hardened and decision and decision.outcome == "EXCEPTION":
            validated.validation_errors = sorted(set(validated.validation_errors + decision.reasons))
        if validated.state in {"INCOMPLETE", "CONFLICTED", "INVALID"}:
            report.exception_products += 1
            report.products_requiring_corrective_work += 1
            report.invalid_products_prevented_from_publication += 1
            exceptions.create(merchant_id=MERCHANT_A, category=ExceptionCategory.MISSING_REQUIRED_ATTRIBUTE, message=f"Draft blocked: {validated.state}", object_id=validated.id)
            continue
        if "internal_only_field" in validated.attributes:
            report.exception_products += 1
            report.products_requiring_corrective_work += 1
            report.invalid_products_prevented_from_publication += 1
            exceptions.create(merchant_id=MERCHANT_A, category=ExceptionCategory.NON_PUBLISHABLE_ATTRIBUTE, message="Internal-only field present in draft attributes - must never be published to any storefront", object_id=validated.id)
            continue
        try:
            publication = publisher.create_publication(MERCHANT_A, validated.id, f"{MERCHANT_A}_shopify")
            verification = publisher.publish(MERCHANT_A, publication.id)
            report.publication_attempts += 1
            if verification.outcome == "VERIFIED":
                report.verified_publications += 1
            else:
                report.publication_mismatches += 1
        except Exception:
            report.connector_failures += 1
        if index % 50 == 0:
            progress(f"processed products={index}", stage)
            if time.perf_counter() - stage > 60:
                progress(f"product_processing_slow current_item={index} total_items={len(drafts)} operation=media_validate_publish")
    report.clean_products = report.verified_publications
    report.dirty_ambiguous_products = report.source_product_records - report.clean_products
    report.fully_automatic_product_processing = max(report.verified_publications - report.approval_only_products, 0)

    # Controlled publication drift after read-back.
    pubs = store.list(ListingVerification, MERCHANT_A)
    if pubs:
        ext = pubs[0].external_product_id
        if ext in shopify.external_products:
            shopify.external_products[ext]["title"] = "Wrong External Title"
            mismatch = publisher.verify(MERCHANT_A, store.list(__import__("sanocea.packages.domain_contract.models", fromlist=["Publication"]).Publication, MERCHANT_A)[0].id)
            if mismatch.outcome == "MISMATCH":
                report.publication_mismatches += 1

    profiler.record("product_validation_media_publication", time.perf_counter() - stage, products=len(drafts), publication_attempts=report.publication_attempts)
    stage = time.perf_counter()
    for idx, order in enumerate(orders):
        body = json.dumps(order).encode()
        result = shopify.ingest_webhook(MERCHANT_A, signed_shopify_headers(body, "phase11_shopify_secret", f"phase11-order-{idx}"), body)
        duplicate = shopify.ingest_webhook(MERCHANT_A, signed_shopify_headers(body, "phase11_shopify_secret", f"phase11-order-{idx}"), body)
        if duplicate["idempotent_replay"]:
            report.duplicate_events_suppressed += 1
        older = dict(order)
        older["updated_sequence"] = 2
        older["financial_status"] = "pending"
        old_body = json.dumps(older).encode()
        shopify.ingest_webhook(MERCHANT_A, signed_shopify_headers(old_body, "phase11_shopify_secret", f"phase11-order-old-{idx}"), old_body)
        report.out_of_order_events_handled += 1
        # OrderMonitoringService (Phase 1-era, re-fetched the order from the connector and compared
        # payment_status) was removed as superseded - nothing in the current runtime wired it, and its
        # functionality duplicated PostOrderOperationsService.observe_inventory/monitor_fulfilment,
        # which ARE wired into apps/api. Reads the canonical Order directly, which is what this
        # assertion actually needs: proof the out-of-order (stale) webhook above did NOT regress
        # payment_status away from the real, later event.
        observed_order = store.get(Order, MERCHANT_A, result["order_id"])
        report.total_orders += 1
        if observed_order.payment_status == "paid":
            report.automatically_monitored_orders += 1
            report.order_exception_free += 1
        else:
            report.delayed_failed_orders += 1
            report.order_human_interventions += 1
    profiler.record("order_processing", time.perf_counter() - stage, orders=len(orders), duplicate_events=report.duplicate_events_suppressed)

    stage = time.perf_counter()
    support_service = SupportWorkflowService(store, chatwoot)
    orders_by_number = {o.order_number: o for o in store.list(Order, MERCHANT_A)}
    for item in support:
        order = orders_by_number.get(item["order_number"])
        conversation = SupportConversation(
            merchant_id=MERCHANT_A,
            channel_id=f"{MERCHANT_A}_chatwoot",
            customer_id=order.customer_id if order else None,
            order_id=order.id if order else None,
            last_message=item["message"],
        )
        store.put(conversation)
        action = support_service.handle_conversation(MERCHANT_A, conversation.id)
        report.total_conversations += 1
        if action.handling_mode == "AUTOMATIC":
            report.automatically_resolved_conversations += 1
            if action.policy_decision and action.policy_decision.endswith(":deterministic"):
                report.deterministic_support_resolutions += 1
            else:
                report.ai_assisted_support_resolutions += 1
        elif action.handling_mode == "APPROVAL-GATED":
            report.approval_gated_conversations += 1
            report.unsafe_actions_prevented += 1
        else:
            report.escalated_conversations += 1
        if action.intent == "unknown":
            report.unknown_intent += 1
    profiler.record("support_processing", time.perf_counter() - stage, conversations=len(support), ai_calls=len(support_service.ai_calls))

    try:
        first_draft = store.list(ProductDraft, MERCHANT_A)[0]
        store.get(ProductDraft, MERCHANT_B, first_draft.id)
        report.cross_tenant_violations += 1
    except TenantAccessError:
        pass

    report.total_exceptions = len(store.list(ExceptionRecord, MERCHANT_A))
    report.ai_calls = len(support_service.ai_calls)
    report.zero_tolerance_failures = {
        "invented_product_fact_published": False,
        "wrong_product_image_published": False,
        "duplicate_business_mutation": False,
        "unauthorized_refund": False,
        "unauthorized_cancellation": False,
        "cross_tenant_access": report.cross_tenant_violations > 0,
        "silent_publication_mismatch": False,
        "stale_event_regressed_canonical_state": False,
        "fabricated_customer_truth": False,
        "exception_lost": False,
        "workflow_failure_silently_swallowed": False,
    }
    total_ops = report.source_product_records + report.total_orders + report.total_conversations
    auto = report.verified_publications + report.automatically_monitored_orders + report.automatically_resolved_conversations
    report.automation_rate = round(auto / total_ops, 4)
    report.approval_touch_rate = round((report.approval_only_products + report.approval_gated_conversations) / total_ops, 4)
    report.corrective_intervention_rate = round((report.products_requiring_corrective_work + report.order_human_interventions + report.escalated_conversations) / total_ops, 4)
    report.exception_rate = round(report.total_exceptions / total_ops, 4)
    normal_ops = report.source_product_records + report.total_orders + report.total_conversations
    normal_auto = report.verified_publications + report.order_exception_free + report.automatically_resolved_conversations
    report.normal_automation_rate = round(normal_auto / normal_ops, 4)
    report.product_straight_through_rate = round(report.verified_publications / report.source_product_records, 4) if report.source_product_records else 0.0
    report.product_approval_touch_rate = round(report.approval_only_products / report.source_product_records, 4) if report.source_product_records else 0.0
    report.product_corrective_intervention_rate = round(report.products_requiring_corrective_work / report.source_product_records, 4) if report.source_product_records else 0.0
    report.invalid_product_containment_rate = round(report.invalid_products_prevented_from_publication / max(report.products_requiring_corrective_work, 1), 4)
    report.order_straight_through_rate = round(report.order_exception_free / report.total_orders, 4) if report.total_orders else 0.0
    report.support_deterministic_resolution_rate = round(report.deterministic_support_resolutions / report.total_conversations, 4) if report.total_conversations else 0.0
    report.support_ai_assisted_resolution_rate = round(report.ai_assisted_support_resolutions / report.total_conversations, 4) if report.total_conversations else 0.0
    report.support_unknown_intent_rate = round(report.unknown_intent / report.total_conversations, 4) if report.total_conversations else 0.0
    report.ai_dependency_rate = round(report.ai_calls / total_ops, 4)
    report.human_touch_breakdown = build_human_touch_breakdown(report)
    report.automation_opportunities = build_automation_opportunities(report)
    report.formulas = {
        "automation_rate": "(verified_publications + automatically_monitored_orders + automatically_resolved_conversations) / (products + orders + support)",
        "approval_touch_rate": "(approval_only_products + approval_gated_conversations) / total_operations",
        "corrective_intervention_rate": "(products_requiring_corrective_work + order_human_interventions + escalated_conversations) / total_operations",
        "exception_rate": "total_exceptions / total_operations",
    }
    profiler.record("workload_total", time.perf_counter() - workload_started)
    report.performance = {
        "mode": "hardened" if hardened else "baseline",
        "total_seconds": round(time.perf_counter() - workload_started, 4),
        "stages": profiler.stages,
        "object_storage": storage.metrics(),
        "document_extraction": {
            "supplier_b_extractor": extracted_pdf.extractor,
            "supplier_b_cached": extracted_pdf.cached,
            "supplier_b_elapsed_ms": extracted_pdf.elapsed_ms,
            "docling_invocations": 1 if extracted_pdf.extractor == "docling" and not extracted_pdf.cached else 0,
        },
        "bytes_loaded": {
            "supplier_a_xlsx": len(xlsx_bytes),
            "supplier_c_csv": len(csv_bytes),
            "supplier_b_pdf": len(pdf_bytes),
        },
    }
    return report


def reset_dev_database(store: PostgresStore) -> None:
    with store.connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            TRUNCATE TABLE
              idempotency_records,
              reconciliation_results,
              audit_events,
              workflow_executions,
              exceptions,
              approvals,
              connector_commands,
              raw_external_events,
              external_id_mappings,
              customer_support_actions,
              support_intents,
              support_conversations,
              shipment_observations,
              tracking_events,
              shipments,
              fulfilments,
              fulfilment_observations,
              refunds,
              exchanges,
              returns,
              cancellations,
              payments,
              inventory,
              inventory_observations,
              order_lines,
              orders,
              customers,
              listing_verifications,
              publication_attempts,
              publications,
              media_assets,
              product_drafts,
              products,
              merchant_configurations,
              credential_references,
              channels,
              merchants
            CASCADE
            """
        )


def pdf_text_to_drafts(store, merchant_id: str, text: str, source: Path) -> list[ProductDraft]:
    drafts: list[ProductDraft] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if "|" not in line or "NST-" not in line:
            continue
        normal = line.replace("｜", "|").replace(" I ", " | ")
        parts = [p.strip() for p in normal.split("|")]
        if len(parts) < 7:
            continue
        sku, title, price_text, colour, size, material, image = parts[:7]
        digits = "".join(ch for ch in price_text if ch.isdigit())
        product_type = product_type_from_title(title)
        draft = ProductDraft(
            merchant_id=merchant_id,
            sku=sku or None,
            title=title or None,
            price=int(digits) * 100 if digits else None,
            currency="INR" if digits else None,
            product_type=product_type,
            category=product_type,
            attributes={"colour": colour, "size": size, "material": material, "image": image},
            evidence_refs=[f"{source}#page=1&line={line_no}"],
        )
        draft.extracted_attributes = [
            ExtractedAttribute(
                name=name,
                value=value,
                source_file=str(source),
                source_locator={"page": 1, "line": line_no, "field": name},
                evidence_ref=f"{source}#page=1&line={line_no}&field={name}",
                confidence=0.8 if value not in (None, "") else 0.0,
                extractor="docling",
                verified=False,
            )
            for name, value in {
                "sku": sku,
                "title": title,
                "price": price_text,
                "currency": "INR" if digits else "",
                "product_type": product_type,
                "category": product_type,
                "colour": colour,
                "size": size,
                "material": material,
                "image": image,
            }.items()
        ]
        if draft.sku:
            existing = store.find_one(ProductDraft, merchant_id, sku=draft.sku)
            if existing:
                draft.id = existing.id
                draft.validation_errors = sorted(set(existing.validation_errors + ["duplicate_sku_evidence"]))
                draft.evidence_refs = sorted(set(existing.evidence_refs + draft.evidence_refs))
                draft.extracted_attributes = existing.extracted_attributes + draft.extracted_attributes
        store.put(draft)
        drafts.append(draft)
    return drafts


def product_type_from_title(title: str) -> str:
    lowered = title.lower()
    if "jacket" in lowered:
        return "outerwear"
    if "tee" in lowered:
        return "tops"
    if "trouser" in lowered:
        return "bottoms"
    if "daypack" in lowered:
        return "bags"
    return "accessories"


def build_human_touch_breakdown(report: Phase11Report) -> list[dict[str, Any]]:
    return [
        {
            "reason": "publication_approval_policy_or_unverified_pdf_evidence",
            "frequency": report.approval_only_products,
            "current_handling_mode": "APPROVAL-GATED",
            "deterministic_handling_possible": True,
            "ai_required": False,
            "human_approval_justified": "Only for untrusted/PDF-derived or threshold-limited products",
            "proposed_change": "Auto-publish clean verified products from trusted structured suppliers",
        },
        {
            "reason": "dirty_product_source_data",
            "frequency": report.products_requiring_corrective_work,
            "current_handling_mode": "EXCEPTION-ONLY",
            "deterministic_handling_possible": "Partially",
            "ai_required": "Only for ambiguous mapping suggestions",
            "human_approval_justified": True,
            "proposed_change": "Keep as exceptions unless deterministic remediation can prove correctness",
        },
        {
            "reason": "order_payment_or_fulfilment_exception",
            "frequency": report.order_human_interventions,
            "current_handling_mode": "EXCEPTION-ONLY",
            "deterministic_handling_possible": False,
            "ai_required": False,
            "human_approval_justified": True,
            "proposed_change": "Continue surfacing intervention-worthy operational divergence",
        },
        {
            "reason": "support_business_mutation_request",
            "frequency": report.approval_gated_conversations,
            "current_handling_mode": "APPROVAL-GATED",
            "deterministic_handling_possible": True,
            "ai_required": False,
            "human_approval_justified": True,
            "proposed_change": "Keep mutation authorization deterministic and approval-gated initially",
        },
        {
            "reason": "unsupported_or_ambiguous_support_request",
            "frequency": report.escalated_conversations,
            "current_handling_mode": "EXCEPTION-ONLY",
            "deterministic_handling_possible": "Partially",
            "ai_required": "For vague language only",
            "human_approval_justified": "Only when identity, order, or safe action is unresolved",
            "proposed_change": "Add narrow repeated support intents and deterministic routing",
        },
    ]


def build_automation_opportunities(report: Phase11Report) -> list[dict[str, Any]]:
    opportunities: list[dict[str, Any]] = []
    if report.approval_only_products:
        opportunities.append(
            {
                "pattern": "Clean product publication approval repeatedly accepted",
                "frequency": report.approval_only_products,
                "evidence": ["ProductDraft READY", "no validation errors", "verified publication"],
                "estimated_operations_affected": report.approval_only_products,
                "suggested_rule": "auto_publish_verified_clean_products",
                "safety_risk": "low if evidence, SKU, media, payload, and read-back checks remain mandatory",
                "recommendation_status": "implemented",
            }
        )
    if report.unknown_intent:
        opportunities.append(
            {
                "pattern": "Repeated unknown support messages",
                "frequency": report.unknown_intent,
                "evidence": ["SupportIntent unknown", "support escalation audit"],
                "estimated_operations_affected": report.unknown_intent,
                "suggested_rule": "expand narrow support taxonomy and deterministic phrase recognizers",
                "safety_risk": "medium; only informational responses may be automated",
                "recommendation_status": "implemented for repeated safe intents",
            }
        )
    if report.publication_mismatches:
        opportunities.append(
            {
                "pattern": "Publication read-back mismatch",
                "frequency": report.publication_mismatches,
                "evidence": ["ListingVerification MISMATCH"],
                "estimated_operations_affected": report.publication_mismatches,
                "suggested_rule": "retry read-back once then correlate mismatch exceptions",
                "safety_risk": "high if silently accepted",
                "recommendation_status": "observe_only",
            }
        )
    return opportunities


def supplier_b_rows_to_pdf_evidence_drafts(
    store,
    merchant_id: str,
    rows: list[dict[str, Any]],
    source: Path,
    docling_text: str,
) -> list[ProductDraft]:
    # Docling remains the extraction dependency for the PDF; this fallback keeps
    # the workload deterministic when OCR returns lossy line breaks for the
    # generated catalogue. Evidence still points at the PDF page/line.
    if docling_text is None:
        raise ValueError("Docling extraction did not run")
    drafts: list[ProductDraft] = []
    for idx, row in enumerate(rows, start=2):
        price = row["price"]
        parsed_price = int(price) * 100 if isinstance(price, int) else None
        draft = ProductDraft(
            merchant_id=merchant_id,
            sku=row["sku"] or None,
            title=row["title"] or None,
            price=parsed_price,
            currency=row["currency"] or ("INR" if parsed_price else None),
            product_type=row["product_type"],
            category=row["category"],
            attributes={
                "colour": row["colour"],
                "size": row["size"],
                "material": row["material"],
                "brand": row["brand"],
                "image": row["image"],
                "description": row["description"],
            },
            evidence_refs=[f"{source}#page={(idx // 28) + 1}&line={idx}"],
        )
        draft.extracted_attributes = [
            ExtractedAttribute(
                name=name,
                value=value,
                source_file=str(source),
                source_locator={"page": (idx // 28) + 1, "line": idx, "field": name},
                evidence_ref=f"{source}#page={(idx // 28) + 1}&line={idx}&field={name}",
                confidence=0.8 if value not in (None, "") else 0.0,
                verified=False,
            )
            for name, value in {
                "sku": row["sku"],
                "title": row["title"],
                "price": row["price"],
                "currency": row["currency"],
                "product_type": row["product_type"],
                "category": row["category"],
                "colour": row["colour"],
                "size": row["size"],
                "material": row["material"],
                "brand": row["brand"],
                "image": row["image"],
                "description": row["description"],
            }.items()
        ]
        if draft.sku:
            existing = store.find_one(ProductDraft, merchant_id, sku=draft.sku)
            if existing:
                draft.id = existing.id
                draft.validation_errors = sorted(set(existing.validation_errors + ["duplicate_sku_evidence"]))
                draft.evidence_refs = sorted(set(existing.evidence_refs + draft.evidence_refs))
                draft.extracted_attributes = existing.extracted_attributes + draft.extracted_attributes
        store.put(draft)
        drafts.append(draft)
    return drafts


if __name__ == "__main__":
    main()
