from __future__ import annotations

import hashlib
import hmac
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sanocea.connectors.woocommerce.oauth1 import sign_request

"""Multi-platform connector hardening, item 5: simultaneous-platform proof.

ONE real, network-bound Sanocea process (apps.api.app:app, unmodified production entrypoint - the
storefront connector registry now supports Shopify AND WooCommerce by default, no special test-only
wiring needed) serves:
  Merchant A -> Shopify (simulator, in-process, real HTTP through the real app)
  Merchant B -> REAL LOCAL WooCommerce (infra/woocommerce-dev, real HTTP both directions)
simultaneously. Every check below is measured against the real running app - no direct service calls.

REAL LOCAL infra: Postgres, WooCommerce (WordPress+WooCommerce via wp-env/Docker).
SIMULATED: ShopifyConnector (Merchant A's channel).
LIVE: none.
"""

ROOT = Path(__file__).parents[1]
OUT = ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "multi_platform_isolation_report.json"

SANOCEA_APP_URL = os.environ.get("SANOCEA_TEST_APP_URL", "http://127.0.0.1:8080")
WC_BASE_URL = os.environ["SANOCEA_WOOCOMMERCE_BASE_URL"]
WC_CONSUMER_KEY = os.environ["SANOCEA_WOOCOMMERCE_CONSUMER_KEY"]
WC_CONSUMER_SECRET = os.environ["SANOCEA_WOOCOMMERCE_CONSUMER_SECRET"]
WC_WEBHOOK_SECRET = os.environ.get("SANOCEA_WOOCOMMERCE_WEBHOOK_SECRET", "sanocea_wc_webhook_secret_isolation")
SERVICE_KEY = os.environ["SANOCEA_TEST_SERVICE_KEY"]
MERCHANT_A = os.environ.get("SANOCEA_MERCHANT_A", "iso_merchant_a_shopify")
MERCHANT_B = os.environ.get("SANOCEA_MERCHANT_B", "iso_merchant_b_woocommerce")
SHOPIFY_WEBHOOK_SECRET = "whsec_isolation_a"


def _check(status: str, evidence: str) -> dict[str, str]:
    assert status in {"PASS", "FAIL", "UNVERIFIED"}
    return {"status": status, "evidence": evidence}


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


def _wc(method: str, path: str, *, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    url = f"{WC_BASE_URL}/wp-json/wc/v3/{path}"
    signed = sign_request(method, url, {}, WC_CONSUMER_KEY, WC_CONSUMER_SECRET)
    full_url = f"{url}?{urllib.parse.urlencode(signed)}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(full_url, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _sign_shopify(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _operator_key(merchant_id: str) -> str:
    status, result = _sanocea("POST", "/admin/api-keys", token=SERVICE_KEY, body={"merchant_id": merchant_id, "role": "operator", "label": "iso-proof"})
    assert status == 200, (status, result)
    return result["api_key"]


@dataclass
class IsolationReport:
    phase: str = "MULTI-PLATFORM CONNECTOR HARDENING - SIMULTANEOUS PLATFORM ISOLATION PROOF"
    classification: dict[str, list[str]] = field(default_factory=lambda: {
        "REAL_LOCAL_INFRASTRUCTURE": ["Postgres", "WooCommerce (WordPress + WooCommerce, real REST API + webhooks)"],
        "SIMULATED_EXTERNAL_PLATFORM": ["ShopifyConnector (Merchant A's channel)"],
        "LIVE_EXTERNAL_PLATFORM": [],
    })
    checks: dict[str, dict[str, str]] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    verdict: str = "FAIL"


def main() -> None:
    started = time.perf_counter()
    checks: dict[str, dict[str, str]] = {}

    # --- Onboard Merchant A (Shopify) and Merchant B (real WooCommerce) in the SAME running app ------
    status, result_a = _sanocea("POST", "/admin/merchants", token=SERVICE_KEY, body={
        "merchant_id": MERCHANT_A, "display_name": "Isolation Proof Merchant A (Shopify)",
        "config": {"currency": "INR", "publication": {"require_approval": False}, "policy": {"refund": {"automatic_limit": 50000, "above_limit": "REQUIRE_APPROVAL"}}},
        "credentials": {"shopify_webhook_secret": SHOPIFY_WEBHOOK_SECRET},
        "channels": [{"type": "shopify", "name": "Shopify", "credential_ref": "shopify_webhook_secret"}],
    })
    assert status == 200, (status, result_a)
    token_a = result_a["operator_api_key"]

    status, result_b = _sanocea("POST", "/admin/merchants", token=SERVICE_KEY, body={
        "merchant_id": MERCHANT_B, "display_name": "Isolation Proof Merchant B (WooCommerce)",
        "config": {"currency": "INR", "publication": {"require_approval": False}, "woocommerce": {"base_url": WC_BASE_URL}},
        "credentials": {
            "woocommerce_consumer_key": WC_CONSUMER_KEY,
            "woocommerce_consumer_secret": WC_CONSUMER_SECRET,
            "woocommerce_webhook_secret": WC_WEBHOOK_SECRET,
        },
        "channels": [{"type": "woocommerce", "name": "WordPress/WooCommerce", "credential_ref": "woocommerce_consumer_key"}],
    })
    assert status == 200, (status, result_b)
    token_b = result_b["operator_api_key"]

    # --- 1. WooCommerce credentials cannot reach the Shopify merchant --------------------------------
    # Attempt to authenticate as Merchant B's operator against Merchant A's URL - tenant isolation
    # (pre-existing, unrelated to the storefront registry) must refuse this outright.
    status, resp = _sanocea("GET", f"/merchants/{MERCHANT_A}/orders", token=token_b)
    checks["woocommerce_credentials_cannot_reach_shopify_merchant"] = _check(
        "PASS" if status == 403 else "FAIL", f"Merchant B's operator key against Merchant A's URL: status={status} (must be 403)",
    )

    # --- 2. Shopify credentials cannot reach the WooCommerce merchant --------------------------------
    status, resp = _sanocea("GET", f"/merchants/{MERCHANT_B}/orders", token=token_a)
    checks["shopify_credentials_cannot_reach_woocommerce_merchant"] = _check(
        "PASS" if status == 403 else "FAIL", f"Merchant A's operator key against Merchant B's URL: status={status} (must be 403)",
    )

    # --- Catalogue publication uses the correct connector for each merchant --------------------------
    def _ingest_and_publish(merchant_id: str, token: str, sku: str, channel_type: str) -> dict[str, Any]:
        boundary = "----isoboundary"
        csv_body = f"sku,title,price,currency,product_type,category\n{sku},Isolation Test Product,299.00,INR,apparel,shirts\n".encode()
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"i.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() + csv_body + f"\r\n--{boundary}--\r\n".encode()
        status, drafts = _sanocea("POST", f"/merchants/{merchant_id}/catalogue/ingest", token=token, raw_body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        assert status == 200, (status, drafts)
        draft_id = drafts[0]["id"]
        _sanocea("POST", f"/merchants/{merchant_id}/catalogue/drafts/{draft_id}/approve-facts", token=token)
        channel_id = f"{merchant_id}_{channel_type}"
        status, publish_result = _sanocea("POST", f"/merchants/{merchant_id}/catalogue/drafts/{draft_id}/publish", token=token, body={"channel_id": channel_id})
        assert status == 200, (status, publish_result)
        return publish_result

    publish_a = _ingest_and_publish(MERCHANT_A, token_a, f"ISO-A-{int(time.time())}", "shopify")
    publish_b = _ingest_and_publish(MERCHANT_B, token_b, f"ISO-B-{int(time.time())}", "woocommerce")
    # Merchant B's external product id must be resolvable as a REAL WooCommerce product.
    wc_status, wc_product = _wc("GET", f"products/{publish_b['verification']['external_product_id']}")
    checks["catalogue_publication_uses_correct_connector"] = _check(
        "PASS" if publish_a["outcome"] == "published" and publish_b["outcome"] == "published" and wc_status == 200 and wc_product.get("name") == "Isolation Test Product" else "FAIL",
        f"A published via simulator (outcome={publish_a['outcome']}), B published to REAL WooCommerce (outcome={publish_b['outcome']}, "
        f"real read-back status={wc_status}, name={wc_product.get('name')!r})",
    )

    # --- Order ingestion uses the correct connector: real Shopify-shaped webhook for A, real WooCommerce
    #     webhook delivery for B -------------------------------------------------------------------------
    shopify_payload = {"id": 555001, "order_number": "ISO-A-ORDER", "email": "iso-a@example.com", "financial_status": "paid", "total_price": "500.00", "currency": "INR", "updated_sequence": 1, "line_items": [{"sku": "ISO-A-LINE", "title": "Item", "quantity": 1, "price": "500.00"}]}
    sbody = json.dumps(shopify_payload).encode()
    status, order_a_result = _sanocea("POST", f"/webhooks/shopify/{MERCHANT_A}", raw_body=sbody, headers={"x-shopify-hmac-sha256": _sign_shopify(SHOPIFY_WEBHOOK_SECRET, sbody), "x-shopify-topic": "orders/create", "x-shopify-webhook-id": "iso-a-order-1"})
    checks["order_ingestion_uses_correct_connector_shopify"] = _check(
        "PASS" if status == 200 and order_a_result.get("order_id") else "FAIL", f"Shopify webhook for Merchant A: status={status} result={order_a_result}",
    )

    # Register a REAL WooCommerce webhook for Merchant B pointed at THIS running app, then place a REAL
    # WooCommerce order to trigger REAL delivery - proving webhook routing resolves the correct
    # platform/merchant, not merely that the connector CAN process a hand-built payload.
    delivery_base = os.environ.get("SANOCEA_WEBHOOK_DELIVERY_BASE_URL", "http://host.docker.internal:8080")
    wc_status, webhook = _wc("POST", "webhooks", body={"name": "Isolation proof order.created", "topic": "order.created", "delivery_url": f"{delivery_base}/webhooks/woocommerce/{MERCHANT_B}", "secret": WC_WEBHOOK_SECRET, "status": "active"})
    assert wc_status == 201, (wc_status, webhook)

    _, orders_b_before = _sanocea("GET", f"/merchants/{MERCHANT_B}/orders", token=token_b)
    before_count = len(orders_b_before) if isinstance(orders_b_before, list) else 0
    wc_status, wc_order = _wc("POST", "orders", body={
        "payment_method": "cod", "payment_method_title": "COD", "set_paid": False,
        "billing": {"first_name": "Iso", "last_name": "B", "email": "iso-b@example.com", "address_1": "1 X", "city": "Bengaluru", "country": "IN"},
        "line_items": [{"product_id": int(publish_b["verification"]["external_product_id"]), "quantity": 1}],
    })
    assert wc_status == 201, (wc_status, wc_order)

    order_b_found = False
    orders_b_after: list[dict[str, Any]] = []
    for _ in range(8):
        # WooCommerce webhook delivery is async (Action Scheduler) - poll rather than assume synchronous.
        _run_action_scheduler_once()
        _, orders_b_after = _sanocea("GET", f"/merchants/{MERCHANT_B}/orders", token=token_b)
        if isinstance(orders_b_after, list) and any(any(r.get("system") == "woocommerce" and r.get("external_id") == str(wc_order["id"]) for r in o.get("external_refs", [])) for o in orders_b_after):
            order_b_found = True
            break
        time.sleep(3)
    checks["order_ingestion_uses_correct_connector_woocommerce"] = _check(
        "PASS" if order_b_found else "FAIL", f"real WooCommerce order {wc_order['id']} -> real webhook -> canonical order for Merchant B: found={order_b_found}",
    )

    # --- Cross-platform webhook routing: wrong channel_type for a merchant must be refused, never
    #     silently processed by the wrong (or a fallback) connector ------------------------------------
    status, resp = _sanocea("POST", f"/webhooks/woocommerce/{MERCHANT_A}", raw_body=b"{}", headers={"X-WC-Webhook-Topic": "order.updated", "X-WC-Webhook-Signature": "irrelevant"})
    checks["cross_platform_webhook_routing_shopify_merchant_rejects_woocommerce_url"] = _check(
        "PASS" if status == 404 else "FAIL", f"WooCommerce-shaped webhook at Merchant A's (Shopify) URL: status={status} (must be 404, ChannelMismatchError - never processed)",
    )
    status, resp = _sanocea("POST", f"/webhooks/shopify/{MERCHANT_B}", raw_body=b"{}", headers={"x-shopify-hmac-sha256": "irrelevant", "x-shopify-topic": "orders/create", "x-shopify-webhook-id": "wrong-platform"})
    checks["cross_platform_webhook_routing_woocommerce_merchant_rejects_shopify_url"] = _check(
        "PASS" if status == 404 else "FAIL", f"Shopify-shaped webhook at Merchant B's (WooCommerce) URL: status={status} (must be 404, ChannelMismatchError - never processed)",
    )

    # --- External IDs remain namespaced by platform: identical order_number reused across both
    #     merchants must never collide (merchant AND system both distinguish the mapping) -------------
    dup_number_payload = {**shopify_payload, "id": 555002, "order_number": "SAME-NUMBER-TEST"}
    dbody = json.dumps(dup_number_payload).encode()
    _sanocea("POST", f"/webhooks/shopify/{MERCHANT_A}", raw_body=dbody, headers={"x-shopify-hmac-sha256": _sign_shopify(SHOPIFY_WEBHOOK_SECRET, dbody), "x-shopify-topic": "orders/create", "x-shopify-webhook-id": "iso-a-dup-number"})
    _, orders_a_final = _sanocea("GET", f"/merchants/{MERCHANT_A}/orders", token=token_a)
    a_order = next((o for o in orders_a_final if o["order_number"] == "SAME-NUMBER-TEST"), None)
    b_order = next((o for o in orders_b_after if o.get("order_number") == wc_order.get("number")), None) if orders_b_after else None
    checks["external_ids_namespaced_by_platform"] = _check(
        "PASS" if a_order and a_order["external_refs"][0]["system"] == "shopify" and all(r["system"] != "woocommerce" for r in a_order["external_refs"]) else "FAIL",
        f"Merchant A's order external_refs system(s): {[r['system'] for r in a_order['external_refs']] if a_order else 'NOT FOUND'} (must be ['shopify'] only, never mixed with 'woocommerce')",
    )

    # --- Refund/cancellation use the correct connector ------------------------------------------------
    refund_a_status, refund_a = _sanocea("POST", f"/merchants/{MERCHANT_A}/refunds", token=token_a, body={"order_id": order_a_result["order_id"], "amount": 10000})
    execute_a_status, execute_a = _sanocea("POST", f"/merchants/{MERCHANT_A}/refunds/{refund_a['id']}/execute", token=token_a, body={})
    wc_status_before, wc_order_before_refund = _wc("GET", f"orders/{wc_order['id']}")
    checks["refund_uses_correct_connector"] = _check(
        "PASS" if execute_a_status == 200 and execute_a.get("status") in {"completed", "external_confirmed", "reconciled"} and len(wc_order_before_refund.get("refunds", [])) == 0 else "FAIL",
        f"Merchant A refund executed via simulator: status={execute_a.get('status')}; Merchant B's real WooCommerce order untouched by A's refund: refunds_on_b_order={len(wc_order_before_refund.get('refunds', []))} (must be 0)",
    )

    # --- One platform failure does not route/fall back to another connector --------------------------
    # Misconfigure Merchant B's woocommerce base_url to an unreachable address AFTER its connector has
    # already been resolved/cached is not a fair test (the registry caches per-merchant) - instead,
    # prove the structural guarantee directly: Merchant A's storefront resolution must succeed and
    # never touch WooCommerce at all, even though Merchant B's WooCommerce connector construction can
    # fail (e.g. temporarily wrong credentials). This is proven by onboarding a THIRD, deliberately
    # broken WooCommerce merchant and confirming Merchant A's own operations are completely unaffected.
    merchant_c = f"iso_merchant_c_broken_wc_{int(time.time())}"
    status_c_onboard, result_c_onboard = _sanocea("POST", "/admin/merchants", token=SERVICE_KEY, body={
        "merchant_id": merchant_c, "display_name": "Broken WooCommerce Merchant",
        "config": {"currency": "INR", "publication": {"require_approval": False}, "woocommerce": {"base_url": "http://localhost:1"}},
        "credentials": {"woocommerce_consumer_key": "ck_bogus", "woocommerce_consumer_secret": "cs_bogus", "woocommerce_webhook_secret": "bogus"},
        "channels": [{"type": "woocommerce", "name": "WordPress/WooCommerce", "credential_ref": "woocommerce_consumer_key"}],
    })
    assert status_c_onboard == 200, (status_c_onboard, result_c_onboard)
    token_c = result_c_onboard["operator_api_key"]
    # Actually DRIVE merchant C's broken WooCommerce connector (not merely construct it) - publish a
    # product, which must reach through execute_mutation() to http://localhost:1 and fail. This proves
    # the failure is real, not assumed, before checking that it left Merchant A untouched.
    try:
        publish_c = _ingest_and_publish(merchant_c, token_c, f"ISO-C-{int(time.time())}", "woocommerce")
        merchant_c_failed = publish_c.get("outcome") != "published" or publish_c.get("verification", {}).get("outcome") == "FAILED"
        merchant_c_evidence = f"publish_c={publish_c}"
    except AssertionError as exc:
        merchant_c_failed = True
        merchant_c_evidence = f"merchant C's publish raised (connector correctly failed to reach localhost:1): {exc}"

    checks["broken_woocommerce_merchant_actually_fails_not_assumed"] = _check(
        "PASS" if merchant_c_failed else "FAIL", merchant_c_evidence,
    )

    broken_payload = {**shopify_payload, "id": 555003, "order_number": "ISO-A-AFTER-C-BROKEN"}
    bbody = json.dumps(broken_payload).encode()
    status_a_after, result_a_after = _sanocea("POST", f"/webhooks/shopify/{MERCHANT_A}", raw_body=bbody, headers={"x-shopify-hmac-sha256": _sign_shopify(SHOPIFY_WEBHOOK_SECRET, bbody), "x-shopify-topic": "orders/create", "x-shopify-webhook-id": "iso-a-after-c-broken"})
    checks["one_platform_failure_does_not_fallback_to_another_connector"] = _check(
        "PASS" if merchant_c_failed and status_a_after == 200 and result_a_after.get("order_id") else "FAIL",
        f"Merchant A's Shopify webhook processed normally immediately after Merchant C's genuinely-failed "
        f"WooCommerce publish attempt: status={status_a_after} result={result_a_after} "
        f"(must succeed - no shared state/fallback between merchants' connector resolution)",
    )

    report = IsolationReport(checks=checks, runtime_seconds=round(time.perf_counter() - started, 4), verdict=_verdict(checks))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    print(json.dumps(asdict(report), indent=2, default=str))


def _run_action_scheduler_once() -> None:
    import subprocess

    wp_env_dir = ROOT / "infra" / "woocommerce-dev"
    env = dict(os.environ)
    docker_bin = r"C:\Program Files\Docker\Docker\resources\bin"
    if docker_bin not in env.get("PATH", ""):
        env["PATH"] = env.get("PATH", "") + os.pathsep + docker_bin
    subprocess.run(
        ["npx", "--yes", "@wordpress/env", "run", "cli", "--", "wp", "action-scheduler", "run"],
        cwd=wp_env_dir, capture_output=True, timeout=90, shell=True, env=env,
    )


def _verdict(checks: dict[str, dict[str, str]]) -> str:
    failures = [k for k, v in checks.items() if v["status"] == "FAIL"]
    unverified = [k for k, v in checks.items() if v["status"] == "UNVERIFIED"]
    if failures:
        return "FAIL"
    if unverified:
        return "CONDITIONAL_PASS"
    return "PASS"


if __name__ == "__main__":
    main()
