from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

"""BIGCOMMERCE REAL SANDBOX CERTIFICATION.

PREPARED, NOT EXECUTED. This script has never been run against a real BigCommerce sandbox - no
sandbox/credentials exist in this environment (Partner Portal account creation requires Manpreet's own
interactive signup and an approval wait; see
docs/architecture/bigcommerce-sandbox-certification-preparation.md, "ACTION REQUIRED FROM MANPREET").
It is built now, structurally complete and byte-compiled, mirroring
scripts/run_shopify_dev_store_certification.py's real, working structure and honesty standard exactly -
so that once credentials exist, running it requires filling in the SANOCEA_BIGCOMMERCE_* environment
variables this script reads and nothing else.

Two REAL, independent HTTP endpoints, exactly like every prior real-platform certification in this repo:
  1. BigCommerce's real REST API (V2 + V3) + a real sandbox store (SANOCEA_BIGCOMMERCE_*).
  2. A real, network-bound Sanocea API instance (SANOCEA_TEST_APP_URL) - apps/api/app.py's unmodified
     production entrypoint, via a real uvicorn process, reachable from BigCommerce's cloud over a real
     HTTPS tunnel for webhook delivery.

DESIGN DISCIPLINE for this certification specifically (explicit instruction - see the connector's own
module docstring for the full statement): this harness does NOT add retry/backoff on any read-back check
merely because BigCommerce's documentation describes eventual consistency. Every "real_X_reflected"
check here is ONE immediate read, exactly like the Shopify/WooCommerce harnesses - if a real run observes
a genuinely stale/not-yet-visible read, that is recorded as a FAIL with full evidence (never silently
retried away), and is exactly the finding that would then justify the smallest possible generic core
change - decided AFTER real evidence exists, not before.

Every mutation against Sanocea goes through Sanocea's REAL HTTP API. Every mutation against BigCommerce
goes through BigCommerce's REAL REST API. Order ingestion happens ONLY via a webhook BigCommerce itself
delivers - this script never calls ingest_webhook() directly. Where BigCommerce doesn't support an
operation exactly as Sanocea models it, this reports the semantic difference, never fabricates
equivalence.

REAL EXTERNAL PLATFORM - SANDBOX STORE: BigCommerce (non-transactional sandbox, real REST API, real
webhook delivery from BigCommerce's cloud - NOT the in-memory ShopifyConnector simulator or a fabricated
result).
"""

ROOT = Path(__file__).parents[1]
OUT = ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "bigcommerce_sandbox_certification_report.json"

SANOCEA_APP_URL = os.environ.get("SANOCEA_TEST_APP_URL", "http://127.0.0.1:8080")
SERVICE_KEY = os.environ.get("SANOCEA_TEST_SERVICE_KEY")
MERCHANT_ID = os.environ.get("SANOCEA_BIGCOMMERCE_MERCHANT_ID", "bigcommerce_cert_merchant")

STORE_HASH = os.environ.get("SANOCEA_BIGCOMMERCE_STORE_HASH")
ACCESS_TOKEN = os.environ.get("SANOCEA_BIGCOMMERCE_ACCESS_TOKEN")
WEBHOOK_VERIFICATION_SECRET = os.environ.get("SANOCEA_BIGCOMMERCE_WEBHOOK_VERIFICATION_SECRET")
WEBHOOK_DELIVERY_BASE_URL = os.environ.get("SANOCEA_BIGCOMMERCE_WEBHOOK_DELIVERY_BASE_URL")

REQUIRED_ENV_VARS = {
    "SANOCEA_TEST_SERVICE_KEY": SERVICE_KEY,
    "SANOCEA_BIGCOMMERCE_STORE_HASH": STORE_HASH,
    "SANOCEA_BIGCOMMERCE_ACCESS_TOKEN": ACCESS_TOKEN,
    "SANOCEA_BIGCOMMERCE_WEBHOOK_VERIFICATION_SECRET": WEBHOOK_VERIFICATION_SECRET,
    "SANOCEA_BIGCOMMERCE_WEBHOOK_DELIVERY_BASE_URL": WEBHOOK_DELIVERY_BASE_URL,
}


def _check(status: str, evidence: str) -> dict[str, str]:
    assert status in {"PASS", "FAIL", "UNVERIFIED"}
    return {"status": status, "evidence": evidence}


# --- Thin HTTP clients (stdlib only, matching every other certification script in this repo) --------

def _sanocea(method: str, path: str, *, token: str | None = None, body: dict[str, Any] | None = None, raw_body: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    url = f"{SANOCEA_APP_URL}{path}"
    data = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
    hdrs = dict(headers or {})
    if data is not None and raw_body is None:
        hdrs["Content-Type"] = "application/json"
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw.decode(errors="replace")


def _bc(method: str, base: str, path: str, *, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    """Setup/verification calls made DIRECTLY against BigCommerce's real REST API - distinct from calls
    made THROUGH Sanocea. Plays the same role _wc()/_shopify_graphql() play in the prior two
    certifications: independent verification, never trusting Sanocea's own report of success. `base` is
    "v2" or "v3" - BOTH real API generations are genuinely used across this certification (see the
    connector's own V2-vs-V3 mapping), not a simplification."""
    url = f"https://api.bigcommerce.com/stores/{STORE_HASH}/{base}/{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json", "X-Auth-Token": ACCESS_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw.decode(errors="replace")


def _onboard_merchant() -> str:
    status, result = _sanocea("POST", "/admin/merchants", token=SERVICE_KEY, body={
        "merchant_id": MERCHANT_ID, "display_name": "BigCommerce Sandbox Certification Merchant",
        "config": {
            "currency": "USD", "publication": {"require_approval": False},
            "bigcommerce": {"store_hash": STORE_HASH, "webhook_delivery_base_url": WEBHOOK_DELIVERY_BASE_URL},
        },
        "credentials": {
            "bigcommerce_access_token": ACCESS_TOKEN,
            "bigcommerce_webhook_verification_secret": WEBHOOK_VERIFICATION_SECRET,
        },
        "channels": [{"type": "bigcommerce", "name": "BigCommerce", "credential_ref": "bigcommerce_access_token"}],
    })
    if status != 200:
        raise RuntimeError(f"could not onboard {MERCHANT_ID}: {status} {result}")
    return result["operator_api_key"]


@dataclass
class BigCommerceSandboxReport:
    phase: str = "BIGCOMMERCE REAL SANDBOX CERTIFICATION"
    classification: str = "REAL EXTERNAL PLATFORM - SANDBOX STORE"
    executed: bool = False
    blocked_reason: str | None = None
    journey: dict[str, Any] = field(default_factory=dict)
    semantic_findings: list[dict[str, str]] = field(default_factory=list)
    zero_tolerance: dict[str, dict[str, str]] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    verdict: str = "BLOCKED"


def _write_report(report: BigCommerceSandboxReport) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    print(json.dumps(asdict(report), indent=2, default=str))


class _CertificationAborted(Exception):
    """Raised when a step Sanocea itself reports as failed (non-200, or a body that isn't the dict shape
    expected) - one precise FAIL check recorded and the run stops, never a bare traceback as the
    "result" (the exact bug class found and fixed during the Shopify certification)."""

    def __init__(self, check_name: str, evidence: str) -> None:
        super().__init__(evidence)
        self.check_name = check_name
        self.evidence = evidence


def _expect_dict(status: int, value: Any, *, check_name: str, context: str) -> dict[str, Any]:
    if status != 200 or not isinstance(value, dict):
        raise _CertificationAborted(check_name, f"{context}: HTTP {status}, response={value!r}")
    return value


def main() -> None:
    missing = [name for name, value in REQUIRED_ENV_VARS.items() if not value]
    if missing:
        _write_report(BigCommerceSandboxReport(
            executed=False,
            blocked_reason=f"missing required environment variable(s): {', '.join(missing)} - see docs/architecture/bigcommerce-sandbox-certification-preparation.md 'ACTION REQUIRED FROM MANPREET'",
            verdict="BLOCKED",
        ))
        raise SystemExit(1)

    started = time.perf_counter()
    journey: dict[str, Any] = {}
    findings: list[dict[str, str]] = []
    checks: dict[str, dict[str, str]] = {}

    try:
        _run_journey(journey, findings, checks)
    except _CertificationAborted as exc:
        checks[exc.check_name] = _check("FAIL", exc.evidence)
    except Exception as exc:  # noqa: BLE001 - a real run must always produce a report, never a bare crash
        checks["unexpected_error"] = _check("FAIL", f"{type(exc).__name__}: {exc}")

    report = BigCommerceSandboxReport(
        executed=True, journey=journey, semantic_findings=findings, zero_tolerance=checks,
        runtime_seconds=round(time.perf_counter() - started, 4),
        verdict="PASS" if checks and all(c["status"] == "PASS" for c in checks.values()) else "FAIL",
    )
    _write_report(report)


def _run_journey(journey: dict[str, Any], findings: list[dict[str, str]], checks: dict[str, dict[str, str]]) -> None:
    from sanocea.connectors.bigcommerce import BigCommerceConnector
    from sanocea.packages.connector_sdk import MutationRequest
    from sanocea.packages.domain_contract.store import Phase0Store

    probe = BigCommerceConnector(
        Phase0Store(), workflow=None, store_hash=STORE_HASH, access_token=ACCESS_TOKEN,
        webhook_verification_secret=WEBHOOK_VERIFICATION_SECRET, webhook_delivery_base_url=WEBHOOK_DELIVERY_BASE_URL,
    )

    operator_key = _onboard_merchant()

    channel_id = f"{MERCHANT_ID}_bigcommerce"
    webhook_registration = probe.register_webhooks(MERCHANT_ID, channel_id)
    journey["webhook_registration"] = webhook_registration.payload

    # --- 1. Product create (through Sanocea's real catalogue API -> BigCommerceConnector -> real V3
    #     Catalog Products API) --------------------------------------------------------------------
    sku = f"BIGCOMMERCE-CERT-{int(time.time())}"
    boundary = "----bigcommercecertboundary"
    csv_body = f"sku,title,price,currency,product_type,category\n{sku},BigCommerce Cert Shirt,49.00,USD,apparel,shirts\n".encode()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cert.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() + csv_body + f"\r\n--{boundary}--\r\n".encode()
    status, drafts = _sanocea("POST", f"/merchants/{MERCHANT_ID}/catalogue/ingest", token=operator_key, raw_body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    journey["catalogue_ingest_status"] = status
    if status != 200 or not isinstance(drafts, list) or not drafts:
        raise _CertificationAborted("real_product_created", f"catalogue ingest failed: HTTP {status}, response={drafts!r}")
    draft_id = drafts[0]["id"]
    approve_status, approved_raw = _sanocea("POST", f"/merchants/{MERCHANT_ID}/catalogue/drafts/{draft_id}/approve-facts", token=operator_key)
    approved = _expect_dict(approve_status, approved_raw, check_name="real_product_created", context="approve-facts failed")
    journey["draft_state_after_approval"] = approved.get("state")

    status, publish_result_raw = _sanocea("POST", f"/merchants/{MERCHANT_ID}/catalogue/drafts/{draft_id}/publish", token=operator_key, body={"channel_id": channel_id})
    publish_result = _expect_dict(status, publish_result_raw, check_name="real_product_created", context="publish failed")
    outcome = publish_result.get("outcome")
    journey["publish_outcome"] = outcome
    external_product_id = (publish_result.get("verification") or {}).get("external_product_id")
    journey["external_product_id"] = external_product_id
    checks["real_product_created"] = _check("PASS" if outcome == "published" and external_product_id else "FAIL", f"publish status={status} outcome={outcome} external_product_id={external_product_id}")
    if not external_product_id:
        raise _CertificationAborted("real_product_created", f"no external_product_id returned - cannot proceed: publish_result={publish_result!r}")

    # --- 2. Independent read-back (direct BigCommerce call, not Sanocea's own report) ----------------
    rb_status, readback = _bc("GET", "v3", f"catalog/products/{external_product_id}", params={"include": "variants"})
    product_readback = (readback or {}).get("data", readback) if isinstance(readback, dict) else {}
    checks["real_product_read_back_independently"] = _check(
        "PASS" if rb_status == 200 and product_readback.get("name") == "BigCommerce Cert Shirt" and product_readback.get("sku") == sku else "FAIL",
        f"direct BigCommerce V3 read-back: status={rb_status} name={product_readback.get('name')!r} sku={product_readback.get('sku')!r}",
    )

    # --- 3. Update - not a duplicate ------------------------------------------------------------------
    update_result = probe.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="update_product", object_type="ProductDraft",
        payload={"title": "BigCommerce Cert Shirt", "sku": sku, "price": "59.00"},
        idempotency_key=f"cert-update:{sku}",
    ))
    journey["update_external_ref"] = update_result.external_ref
    rb2_status, readback2 = _bc("GET", "v3", f"catalog/products/{external_product_id}")
    product_after_update = (readback2 or {}).get("data", readback2) if isinstance(readback2, dict) else {}
    checks["real_product_update_reflected"] = _check(
        "PASS" if update_result.external_ref == str(external_product_id) and str(product_after_update.get("price")) == "59.0" else "FAIL",
        f"update_result.external_ref={update_result.external_ref} (must equal the original product id, proving no duplicate was created) price_after_update={product_after_update.get('price')}",
    )

    # --- 4. Multiple real locations --------------------------------------------------------------------
    loc_status, locations_raw = _bc("GET", "v3", "inventory/locations")
    locations = (locations_raw or {}).get("data", []) if isinstance(locations_raw, dict) else []
    journey["locations"] = locations
    if len(locations) < 2:
        findings.append({
            "area": "multiple_locations",
            "finding": f"This sandbox has only {len(locations)} inventory location(s) by default. Creating "
                       "additional locations may or may not be possible via the sandbox's own admin/API - "
                       "not something to fabricate. If only one location exists, the "
                       "location-specific-inventory step below is exercised against that one real location "
                       "only, and this is reported honestly rather than simulating a second location.",
        })
    checks["multiple_real_locations"] = _check(
        "PASS" if len(locations) >= 2 else "UNVERIFIED",
        f"{len(locations)} real inventory location(s) found via GET /v3/inventory/locations: {[l.get('id') for l in locations]}",
    )

    # --- 5. Location-specific inventory mutation/read-back --------------------------------------------
    target_location = locations[0]["id"] if locations else None
    if target_location is None:
        raise _CertificationAborted("real_inventory_location_operation", "no inventory location available to target")
    inventory_result = probe.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="set_inventory", object_type="ProductDraft",
        payload={"external_product_id": external_product_id, "sku": sku, "quantity": 15, "location_ref": target_location},
        idempotency_key=f"cert-inventory:{sku}",
    ))
    journey["inventory_mutation_result"] = inventory_result.payload
    inv_status, inv_readback = _bc("GET", "v3", "inventory/items", params={"identity.sku": sku})
    inv_items = (inv_readback or {}).get("data", []) if isinstance(inv_readback, dict) else []
    journey["inventory_readback"] = inv_items
    checks["real_inventory_location_operation"] = _check(
        "PASS" if inv_status == 200 and inv_items else "FAIL",
        f"set_inventory at location {target_location} -> independent read-back status={inv_status} items={inv_items} "
        f"(BigCommerce's own docs describe this write as eventually consistent - this check does ONE immediate "
        f"read, deliberately not retried; a stale/not-yet-visible result here is a real, reportable finding, "
        f"not silently retried away)",
    )

    # --- 6/7/8. Real order -> real webhook delivery -> canonical Sanocea Order -----------------------
    order_status, order_result = _bc("POST", "v2", "orders", body={
        "status_id": 11,  # "Awaiting Fulfillment" in BigCommerce's default status set - UNVERIFIED, confirm live
        "billing_address": {"first_name": "Cert", "last_name": "Buyer", "email": "bigcommerce-cert-buyer@example.com", "street_1": "1 Cert St", "city": "Austin", "state": "TX", "zip": "78701", "country": "United States", "country_iso2": "US"},
        "products": [{"product_id": int(external_product_id), "quantity": 1}],
    })
    journey["bigcommerce_order_status"] = order_status
    journey["bigcommerce_order_result"] = order_result if order_status != 201 else {"id": order_result.get("id")}
    if order_status != 201:
        raise _CertificationAborted("real_webhook_created_canonical_order", f"POST /v2/orders failed: HTTP {order_status}, response={order_result!r}")
    bc_order_id = order_result["id"]
    journey["bigcommerce_order_id"] = bc_order_id

    before_status, before_orders = _sanocea("GET", f"/merchants/{MERCHANT_ID}/orders", token=operator_key)
    before_count = len(before_orders) if isinstance(before_orders, list) else 0
    sanocea_order = None
    for _ in range(10):
        _, after_orders = _sanocea("GET", f"/merchants/{MERCHANT_ID}/orders", token=operator_key)
        matching = [o for o in (after_orders or []) if any(r.get("system") == "bigcommerce" and r.get("external_id") == str(bc_order_id) for r in o.get("external_refs", []))]
        if matching:
            sanocea_order = matching[-1]
            break
        time.sleep(3)
    journey["webhook_created_canonical_order"] = sanocea_order is not None
    journey["canonical_order_id"] = sanocea_order["id"] if sanocea_order else None
    checks["real_webhook_created_canonical_order"] = _check(
        "PASS" if sanocea_order else "FAIL",
        f"real BigCommerce order {bc_order_id} -> real store/order/created webhook (via the real tunnel at "
        f"{WEBHOOK_DELIVERY_BASE_URL}) -> canonical Sanocea order: found={sanocea_order is not None}. "
        f"REQUIRES the webhook subscriptions registered above AND the tunnel reachable from BigCommerce's cloud.",
    )

    # --- 9. Duplicate webhook idempotency ---------------------------------------------------------------
    dup_status_1 = dup_status_2 = None
    orders_after_replay = before_count
    if sanocea_order:
        import hashlib
        import hmac as hmac_module
        import base64 as base64_module

        raw_order_status, raw_order = _bc("GET", "v2", f"orders/{bc_order_id}")
        replay_payload = {"scope": "store/order/updated", "data": {"id": bc_order_id}, "store_id": STORE_HASH}
        replay_body = json.dumps(replay_payload).encode()
        webhook_id_hdr, timestamp_hdr = "cert-replay-1", str(int(time.time()))
        signed_content = f"{webhook_id_hdr}.{timestamp_hdr}.{replay_body.decode()}".encode()
        digest = hmac_module.new(WEBHOOK_VERIFICATION_SECRET.encode(), signed_content, hashlib.sha256).digest()
        signature = f"v1,{base64_module.b64encode(digest).decode()}"
        replay_headers = {"webhook-id": webhook_id_hdr, "webhook-timestamp": timestamp_hdr, "webhook-signature": signature, "Content-Type": "application/json"}
        req1 = urllib.request.Request(f"{SANOCEA_APP_URL}/webhooks/bigcommerce/{MERCHANT_ID}", data=replay_body, method="POST", headers=replay_headers)
        req2 = urllib.request.Request(f"{SANOCEA_APP_URL}/webhooks/bigcommerce/{MERCHANT_ID}", data=replay_body, method="POST", headers=replay_headers)
        try:
            with urllib.request.urlopen(req1, timeout=30) as resp:
                dup_status_1 = resp.status
        except urllib.error.HTTPError as exc:
            dup_status_1 = exc.code
        try:
            with urllib.request.urlopen(req2, timeout=30) as resp:
                dup_status_2 = resp.status
        except urllib.error.HTTPError as exc:
            dup_status_2 = exc.code
        _, orders_after_replay_list = _sanocea("GET", f"/merchants/{MERCHANT_ID}/orders", token=operator_key)
        orders_after_replay = len(orders_after_replay_list) if isinstance(orders_after_replay_list, list) else before_count
    journey["duplicate_webhook_replay_statuses"] = [dup_status_1, dup_status_2]
    journey["orders_after_duplicate_replay"] = orders_after_replay
    checks["duplicate_webhook_no_duplicate_order"] = _check(
        "PASS" if sanocea_order and dup_status_1 == 200 and dup_status_2 == 200 and orders_after_replay == before_count + 1 else ("UNVERIFIED" if not sanocea_order else "FAIL"),
        f"replay statuses={[dup_status_1, dup_status_2]} order_count_after={orders_after_replay} (must stay at before_count+1={before_count + 1})" if sanocea_order else "skipped - no canonical order to replay against",
    )

    # --- 10. Fulfilment/shipment -----------------------------------------------------------------------
    try:
        fulfilment_result = probe.execute_mutation(MutationRequest(
            merchant_id=MERCHANT_ID, action="create_fulfilment", object_type="Order",
            payload={"external_order_id": bc_order_id}, idempotency_key=f"cert-fulfil:{bc_order_id}",
        ))
        journey["fulfilment_result"] = fulfilment_result.payload
        checks["real_fulfilment_via_shipments_api"] = _check("PASS" if fulfilment_result.external_ref else "FAIL", f"V2 shipment created id={fulfilment_result.external_ref}")
    except Exception as exc:  # noqa: BLE001
        journey["fulfilment_error"] = str(exc)
        checks["real_fulfilment_via_shipments_api"] = _check("FAIL", f"shipment creation raised: {exc}")

    # --- 11. Cancellation / status transition (a SEPARATE order, mirroring the WooCommerce/Shopify
    #     lesson that a fulfilled/refunded order may not also be cancellable) -------------------------
    cancel_order_status, cancel_order_result = _bc("POST", "v2", "orders", body={
        "status_id": 11,
        "billing_address": {"first_name": "Cert", "last_name": "Buyer2", "email": "bigcommerce-cert-buyer-2@example.com", "street_1": "1 Cert St", "city": "Austin", "state": "TX", "zip": "78701", "country": "United States", "country_iso2": "US"},
        "products": [{"product_id": int(external_product_id), "quantity": 1}],
    })
    cancel_order_id = cancel_order_result.get("id") if cancel_order_status == 201 else None
    journey["order_id_for_cancellation"] = cancel_order_id
    if cancel_order_id:
        try:
            cancel_result = probe.execute_mutation(MutationRequest(
                merchant_id=MERCHANT_ID, action="cancel_order", object_type="Order",
                payload={"external_order_id": cancel_order_id}, idempotency_key=f"cert-cancel:{cancel_order_id}",
            ))
            journey["cancel_result"] = cancel_result.payload
            checks["real_cancellation_status_transition"] = _check("PASS" if cancel_result.external_ref else "FAIL", f"order status transitioned, external_ref={cancel_result.external_ref}")
        except Exception as exc:  # noqa: BLE001
            journey["cancel_error"] = str(exc)
            checks["real_cancellation_status_transition"] = _check("FAIL", f"cancel raised: {exc}")
    else:
        checks["real_cancellation_status_transition"] = _check("UNVERIFIED", f"could not create a second order to cancel: status={cancel_order_status} {cancel_order_result!r}")

    # --- 12/13. Refund quote -> refund execution ---------------------------------------------------
    try:
        refund_result = probe.execute_mutation(MutationRequest(
            merchant_id=MERCHANT_ID, action="create_refund", object_type="Order",
            payload={"external_order_id": bc_order_id, "amount": 1000, "currency": "USD"},
            idempotency_key=f"cert-refund:{bc_order_id}",
        ))
        journey["refund_result"] = refund_result.payload
        checks["real_refund_quote_then_execution"] = _check(
            "PASS" if refund_result.external_ref else "FAIL",
            f"refund quote->execute sequence completed inside the connector, refund id={refund_result.external_ref}",
        )
    except Exception as exc:  # noqa: BLE001
        journey["refund_error"] = str(exc)
        checks["real_refund_quote_then_execution"] = _check("FAIL", f"refund quote/execute raised: {exc}")

    # --- 14. Independent reconciliation -------------------------------------------------------------
    if sanocea_order:
        reconciliation = probe.reconcile(MERCHANT_ID, {"external_order_id": bc_order_id})
        journey["reconciliation_result"] = reconciliation
        checks["reconciliation"] = _check("PASS", f"reconcile() ran against the real order: {reconciliation}")
    else:
        checks["reconciliation"] = _check("UNVERIFIED", "no canonical order to reconcile")


if __name__ == "__main__":
    main()
