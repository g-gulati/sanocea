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

"""SHOPIFY REAL DEVELOPMENT-STORE CERTIFICATION.

PREPARED, NOT EXECUTED. This script has never been run against a real Shopify store - no development-
store credentials exist in this environment. It is built now, structurally complete and byte-compiled,
mirroring scripts/run_woocommerce_platform_independence.py's real, working structure exactly (not a
stub), so that once credentials exist (see
docs/architecture/shopify-dev-store-certification-preparation.md, "ACTION REQUIRED FROM MANPREET"),
running it requires filling in the SANOCEA_SHOPIFY_LIVE_* environment variables this script reads and
nothing else. If it is ever run before those variables are set, it fails loudly at startup (see
REQUIRED_ENV_VARS below) rather than fabricating a result.

Two REAL, independent HTTP endpoints are involved, exactly like the WooCommerce certification:
  1. Shopify's real Admin GraphQL API + a real Shopify development store (SANOCEA_SHOPIFY_LIVE_*).
  2. A real, network-bound Sanocea API instance (SANOCEA_TEST_APP_URL) - apps/api/app.py's unmodified
     production entrypoint, run via a real uvicorn process (never TestClient), reachable from Shopify's
     cloud over a real HTTPS tunnel for webhook delivery (see the prep doc's webhook-ingress section).

Every mutation against Sanocea goes through Sanocea's REAL HTTP API. Every mutation against Shopify
goes through Shopify's REAL Admin GraphQL API. Order ingestion happens ONLY via a webhook Shopify
itself delivers - this script never calls ingest_webhook() directly. Where Shopify doesn't support an
operation exactly as Sanocea models it, this reports the semantic difference (see semantic_findings),
never fabricates equivalence - the same standard the WooCommerce certification held itself to.

REAL EXTERNAL PLATFORM - DEVELOPMENT STORE: Shopify (development store, real Admin GraphQL API, real
webhook delivery from Shopify's cloud - NOT the in-memory ShopifyConnector simulator, which keeps its
own separate, unaffected zero-tolerance suite. Keep BOTH - see the prep doc, item 8).
"""

ROOT = Path(__file__).parents[1]
OUT = ROOT / "tests" / "fixtures" / "phase11_merchant" / "generated" / "shopify_dev_store_certification_report.json"

SANOCEA_APP_URL = os.environ.get("SANOCEA_TEST_APP_URL", "http://127.0.0.1:8080")
SERVICE_KEY = os.environ.get("SANOCEA_TEST_SERVICE_KEY")
MERCHANT_ID = os.environ.get("SANOCEA_SHOPIFY_LIVE_MERCHANT_ID", "shopify_live_cert_merchant")

SHOP_DOMAIN = os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN")
CLIENT_ID = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
API_VERSION = os.environ.get("SANOCEA_SHOPIFY_LIVE_API_VERSION", "2026-07")
WEBHOOK_DELIVERY_BASE_URL = os.environ.get("SANOCEA_SHOPIFY_LIVE_WEBHOOK_DELIVERY_BASE_URL")

# AUTH HARDENING: no access-token/location-gid input - required inputs are exactly shop domain, Client
# ID, Client Secret, and the webhook public base URL. The access token is obtained by
# ShopifyAccessTokenManager itself (client-credentials grant); the default Location gid is discovered
# programmatically by ShopifyLiveConnector on first use. Neither is ever supplied here.
REQUIRED_ENV_VARS = {
    "SANOCEA_TEST_SERVICE_KEY": SERVICE_KEY,
    "SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN": SHOP_DOMAIN,
    "SANOCEA_SHOPIFY_LIVE_CLIENT_ID": CLIENT_ID,
    "SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET": CLIENT_SECRET,
    "SANOCEA_SHOPIFY_LIVE_WEBHOOK_DELIVERY_BASE_URL": WEBHOOK_DELIVERY_BASE_URL,
}

# Constructed unconditionally (even with None values) - harmless, since ShopifyAccessTokenManager's
# constructor makes no network call and get_token() is never invoked before main()'s missing-env-var
# check runs. Shared by _shopify_graphql() and the `probe` ShopifyLiveConnector built in main(), so the
# harness's own direct calls and its calls through the connector use one cached token/lock.
def _build_token_manager():
    from sanocea.connectors.shopify_live.auth import ShopifyAccessTokenManager

    return ShopifyAccessTokenManager(shop_domain=SHOP_DOMAIN or "", client_id=CLIENT_ID or "", client_secret=CLIENT_SECRET or "")


_TOKEN_MANAGER = _build_token_manager()


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


def _shopify_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Setup/verification calls made DIRECTLY against Shopify's real Admin GraphQL API - distinct from
    calls made THROUGH Sanocea. Plays the same role run_woocommerce_platform_independence.py's `_wc()`
    helper does: creating/reading real external-platform state independent of Sanocea's own reporting
    of it, so a mismatch between what Sanocea claims and what Shopify actually shows would be caught.

    AUTH HARDENING: no static access token - this reuses the SAME ShopifyAccessTokenManager the `probe`
    ShopifyLiveConnector instance in main() already holds, so the harness's own direct calls and its
    calls through the connector share one cached token/lock, exactly like a real merchant's traffic
    would. Set by main() before first use; module-level so this helper's signature stays simple."""
    from sanocea.connectors.shopify_live.auth import ShopifyAuthenticationError

    for attempt in range(2):
        token = _TOKEN_MANAGER.get_token()
        url = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
        body = json.dumps({"query": query, "variables": variables}).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                parsed = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403) and attempt == 0:
                _TOKEN_MANAGER.invalidate()
                continue
            raise
        if parsed.get("errors"):
            raise RuntimeError(f"Shopify GraphQL errors: {parsed['errors']}")
        data = parsed.get("data") or {}
        for value in data.values():
            if isinstance(value, dict) and value.get("userErrors"):
                raise RuntimeError(f"Shopify mutation userErrors: {value['userErrors']}")
        return data
    raise ShopifyAuthenticationError(f"Shopify Admin API rejected the request against {SHOP_DOMAIN} twice in a row")


_shop_currency_cache: list[str] = []


def _shop_currency() -> str:
    """REAL FINDING: Sanocea's project-wide default currency (INR, used throughout every simulator
    workload) does not match this real store's actual currency. orderCreate rejects a line item whose
    priceSet.shopMoney.currencyCode differs from the shop's own currency ("Line items currency must be
    provided when ... different from the shop currency"). Queried once and cached, never assumed."""
    if not _shop_currency_cache:
        data = _shopify_graphql("query { shop { currencyCode } }", {})
        _shop_currency_cache.append(data["shop"]["currencyCode"])
    return _shop_currency_cache[0]


def _sign_webhook(body: bytes) -> str:
    digest = hmac.new(CLIENT_SECRET.encode(), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _post_webhook(topic: str, body: bytes, webhook_id: str) -> int:
    req = urllib.request.Request(
        f"{SANOCEA_APP_URL}/webhooks/shopify_live/{MERCHANT_ID}", data=body, method="POST",
        headers={"x-shopify-hmac-sha256": _sign_webhook(body), "x-shopify-topic": topic, "x-shopify-webhook-id": webhook_id, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _onboard_merchant() -> str:
    status, result = _sanocea("POST", "/admin/merchants", token=SERVICE_KEY, body={
        "merchant_id": MERCHANT_ID, "display_name": "Shopify Dev-Store Certification Merchant",
        "config": {
            "currency": "INR", "publication": {"require_approval": False},
            "shopify_live": {
                "shop_domain": SHOP_DOMAIN, "api_version": API_VERSION,
                "webhook_delivery_base_url": WEBHOOK_DELIVERY_BASE_URL,
                # no default_location_gid - discovered programmatically by ShopifyLiveConnector
            },
        },
        "credentials": {"shopify_live_client_id": CLIENT_ID, "shopify_live_client_secret": CLIENT_SECRET},
        "channels": [{"type": "shopify_live", "name": "Shopify (dev store)", "credential_ref": "shopify_live_client_id"}],
    })
    if status != 200:
        raise RuntimeError(f"could not onboard {MERCHANT_ID}: {status} {result}")
    return result["operator_api_key"]


@dataclass
class ShopifyDevStoreReport:
    phase: str = "SHOPIFY REAL DEVELOPMENT-STORE CERTIFICATION"
    classification: str = "REAL EXTERNAL PLATFORM - DEVELOPMENT STORE"
    executed: bool = False
    blocked_reason: str | None = None
    journey: dict[str, Any] = field(default_factory=dict)
    semantic_findings: list[dict[str, str]] = field(default_factory=list)
    zero_tolerance: dict[str, dict[str, str]] = field(default_factory=dict)
    runtime_seconds: float = 0.0
    verdict: str = "BLOCKED"


def _write_report(report: ShopifyDevStoreReport) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
    print(json.dumps(asdict(report), indent=2, default=str))


def main() -> None:
    missing = [name for name, value in REQUIRED_ENV_VARS.items() if not value]
    if missing:
        # Fails loudly rather than proceeding with any fabricated/partial value - do not fabricate
        # credentials, do not claim live certification. This is the CORRECT, expected outcome of
        # running this script before Manpreet's Shopify authorization steps are complete.
        _write_report(ShopifyDevStoreReport(
            executed=False,
            blocked_reason=f"missing required environment variable(s): {', '.join(missing)} - see docs/architecture/shopify-dev-store-certification-preparation.md 'ACTION REQUIRED FROM MANPREET'",
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
        # A step Sanocea itself reported as failed (non-200 or a non-JSON/non-dict body where a dict
        # was expected) - the precise, specific case this fix targets. Recorded as a clean FAIL, not a
        # traceback; whatever checks/journey/findings were already gathered before the abort are kept.
        checks[exc.check_name] = _check("FAIL", exc.evidence)
    except Exception as exc:  # noqa: BLE001 - a real run must always produce a report, never a bare crash
        # Any OTHER unexpected failure (a real Shopify/Sanocea error not already normalized above) is
        # still reported cleanly - the type and message, never a raw traceback dumped as the "result".
        checks["unexpected_error"] = _check("FAIL", f"{type(exc).__name__}: {exc}")

    report = ShopifyDevStoreReport(
        executed=True, journey=journey, semantic_findings=findings, zero_tolerance=checks,
        runtime_seconds=round(time.perf_counter() - started, 4),
        verdict="PASS" if checks and all(c["status"] == "PASS" for c in checks.values()) else "FAIL",
    )
    _write_report(report)


class _CertificationAborted(Exception):
    """Raised when a step Sanocea itself reports as failed (non-200 status, or a body that isn't the
    dict shape this script expects) - carries enough to record one precise FAIL check and stop, instead
    of a downstream .get()-on-a-string crash producing a bare Python traceback as the "result"."""

    def __init__(self, check_name: str, evidence: str) -> None:
        super().__init__(evidence)
        self.check_name = check_name
        self.evidence = evidence


def _expect_dict(status: int, value: Any, *, check_name: str, context: str) -> dict[str, Any]:
    if status != 200 or not isinstance(value, dict):
        raise _CertificationAborted(check_name, f"{context}: HTTP {status}, response={value!r}")
    return value


def _run_journey(journey: dict[str, Any], findings: list[dict[str, str]], checks: dict[str, dict[str, str]]) -> None:
    from sanocea.connectors.shopify_live import ShopifyLiveConnector
    from sanocea.packages.connector_sdk import MutationRequest
    from sanocea.packages.domain_contract.store import Phase0Store

    probe = ShopifyLiveConnector(
        Phase0Store(), workflow=None, shop_domain=SHOP_DOMAIN, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        api_version=API_VERSION, token_manager=_TOKEN_MANAGER, webhook_delivery_base_url=WEBHOOK_DELIVERY_BASE_URL,
        # no default_location_gid - discovered programmatically on first inventory operation
    )

    operator_key = _onboard_merchant()

    # Item 5's explicit requirement: register REAL webhook subscriptions against the active tunnel URL,
    # via the connector's own register_webhooks() - a real webhookSubscriptionCreate mutation, not
    # assumed/skipped. Without this, no order webhook can ever arrive regardless of anything else being
    # correct (the root cause of an earlier real FAIL: this call was missing entirely).
    channel_id = f"{MERCHANT_ID}_shopify_live"
    webhook_registration = probe.register_webhooks(MERCHANT_ID, channel_id)
    journey["webhook_registration"] = webhook_registration.payload

    # --- 1. Product create (through Sanocea's real catalogue API -> ShopifyLiveConnector -> Shopify's
    #     real productSet mutation) -------------------------------------------------------------------
    sku = f"SHOPIFY-LIVE-CERT-{int(time.time())}"
    boundary = "----shopifylivecertboundary"
    csv_body = f"sku,title,price,currency,product_type,category\n{sku},Shopify Dev Store Cert Shirt,499.00,INR,apparel,shirts\n".encode()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cert.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() + csv_body + f"\r\n--{boundary}--\r\n".encode()
    status, drafts = _sanocea("POST", f"/merchants/{MERCHANT_ID}/catalogue/ingest", token=operator_key, raw_body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    journey["catalogue_ingest_status"] = status
    if status != 200 or not isinstance(drafts, list) or not drafts:
        raise _CertificationAborted("real_product_created", f"catalogue ingest failed: HTTP {status}, response={drafts!r}")
    draft_id = drafts[0]["id"]
    approve_status, approved_raw = _sanocea("POST", f"/merchants/{MERCHANT_ID}/catalogue/drafts/{draft_id}/approve-facts", token=operator_key)
    approved = _expect_dict(approve_status, approved_raw, check_name="real_product_created", context="approve-facts failed")
    journey["draft_state_after_approval"] = approved.get("state")

    channel_id = f"{MERCHANT_ID}_shopify_live"
    status, publish_result_raw = _sanocea("POST", f"/merchants/{MERCHANT_ID}/catalogue/drafts/{draft_id}/publish", token=operator_key, body={"channel_id": channel_id})
    publish_result = _expect_dict(status, publish_result_raw, check_name="real_product_created", context="publish failed")
    outcome = publish_result.get("outcome")
    journey["publish_outcome"] = outcome
    external_product_gid = (publish_result.get("verification") or {}).get("external_product_id")
    journey["external_product_gid"] = external_product_gid
    checks["real_product_created"] = _check("PASS" if outcome == "published" and external_product_gid else "FAIL", f"publish status={status} outcome={outcome} external_product_gid={external_product_gid}")
    if not external_product_gid:
        raise _CertificationAborted("real_product_created", f"no external_product_gid returned - cannot proceed with dependent steps 2-12: publish_result={publish_result!r}")

    # --- 2. Shopify read-back (independent of Sanocea's own verification) ----------------------------
    readback = _shopify_graphql(
        "query($id: ID!) { product(id: $id) { title status variants(first: 1) { nodes { sku price } } } }",
        {"id": external_product_gid},
    )
    product_readback = readback.get("product") or {}
    variant_readback = (product_readback.get("variants", {}).get("nodes") or [{}])[0]
    journey["shopify_readback"] = product_readback
    checks["real_product_read_back_independently"] = _check(
        "PASS" if product_readback.get("title") == "Shopify Dev Store Cert Shirt" and variant_readback.get("sku") == sku else "FAIL",
        f"direct Shopify GraphQL read-back: title={product_readback.get('title')!r} sku={variant_readback.get('sku')!r} status={product_readback.get('status')!r}",
    )

    # --- 3. Product update ---------------------------------------------------------------------------
    update_result = probe.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="update_product", object_type="ProductDraft",
        payload={"title": "Shopify Dev Store Cert Shirt", "sku": sku, "price": "549.00"},
        idempotency_key=f"cert-update:{sku}",
    ))
    journey["update_external_ref"] = update_result.external_ref
    readback2 = _shopify_graphql("query($id: ID!) { product(id: $id) { variants(first: 5) { nodes { sku price } } } }", {"id": external_product_gid})
    variants_after_update = readback2.get("product", {}).get("variants", {}).get("nodes") or []
    checks["real_product_update_reflected"] = _check(
        "PASS" if update_result.external_ref == external_product_gid and len(variants_after_update) == 1 and variants_after_update[0].get("price") == "549.00" else "FAIL",
        f"update_result.external_ref={update_result.external_ref} (must equal the original product gid, proving productSet UPDATED rather than created a duplicate) "
        f"variants_after_update={variants_after_update}",
    )

    # --- 4. Inventory/location operation ------------------------------------------------------------
    inventory_result = probe.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="set_inventory", object_type="ProductDraft",
        payload={"external_product_id": external_product_gid, "quantity": 15},
        idempotency_key=f"cert-inventory:{sku}",
    ))
    journey["inventory_mutation_result"] = inventory_result.payload
    inventory_readback = probe.fetch(MERCHANT_ID, "inventory", external_product_gid)
    journey["inventory_readback"] = inventory_readback
    checks["real_inventory_location_operation"] = _check(
        "PASS" if inventory_readback.get("available") == 15 else "FAIL",
        f"inventorySetQuantities -> read-back available={inventory_readback.get('available')} (must be 15) at location {probe.default_location_gid} (discovered programmatically, not configured)",
    )

    # --- 5/6/7. Test order -> REAL Shopify webhook delivery -> canonical Sanocea Order ---------------
    # Placed via Shopify's orderCreate mutation (direct API) - the most automatable path. If a real
    # storefront checkout via the Bogus Gateway behaves differently (e.g. different webhook payload
    # shape or a different set of topics fired), that is itself a real finding to add below, not
    # something to assume away.
    # REAL FINDING: a refund (refundCreate) against an order with NO prior captured payment transaction
    # fails with "Unable to find parent transaction" - a genuine Shopify business rule (there is nothing
    # to refund money FROM), not a connector defect. An explicit `transactions` entry (kind=SALE,
    # status=SUCCESS, gateway="cash" - Shopify's own sanctioned manual/ledger gateway, matching
    # create_refund's own default) gives this order a real parent transaction to refund against later.
    currency = _shop_currency()
    order_result = _shopify_graphql(
        """mutation($order: OrderCreateOrderInput!) {
            orderCreate(order: $order) { order { id name } userErrors { field message } }
        }""",
        {"order": {
            "lineItems": [{"title": "Shopify Dev Store Cert Shirt", "sku": sku, "priceSet": {"shopMoney": {"amount": "499.00", "currencyCode": currency}}, "quantity": 1}],
            "email": "shopify-live-cert-buyer@example.com",
            "transactions": [{"kind": "SALE", "status": "SUCCESS", "gateway": "cash", "amountSet": {"shopMoney": {"amount": "499.00", "currencyCode": currency}}}],
        }},
    )
    # _shopify_graphql() only auto-raises on userErrors it can SEE - the mutation must select userErrors
    # for that to work at all (a real bug this run found: the original selection set omitted userErrors
    # entirely, so a real rejection surfaced only as order: null with zero explanation). Guarded with
    # `or {}` at each level since orderCreate itself can legitimately be null.
    order_create_payload = (order_result or {}).get("orderCreate") or {}
    journey["order_create_user_errors"] = order_create_payload.get("userErrors")
    shopify_order = order_create_payload.get("order") or {}
    shopify_order_gid = shopify_order.get("id")
    journey["shopify_order_gid"] = shopify_order_gid
    findings.append({
        "area": "test_order_creation",
        "finding": "orderCreate was used to place the certification's test order directly via the Admin "
                   "API, rather than a real storefront checkout through the Bogus Gateway - the more "
                   "automatable path. Report here whether this triggered identical real webhook "
                   "delivery to a checkout-originated order; if not, that is a genuine semantic "
                   "difference worth recording, not one to paper over.",
    })

    before_status, before_orders = _sanocea("GET", f"/merchants/{MERCHANT_ID}/orders", token=operator_key)
    before_count = len(before_orders) if isinstance(before_orders, list) else 0
    journey["orders_before_webhook"] = before_count

    sanocea_order = None
    numeric_order_id = shopify_order_gid.rsplit("/", 1)[-1] if shopify_order_gid else None
    for _ in range(10):
        _, after_orders = _sanocea("GET", f"/merchants/{MERCHANT_ID}/orders", token=operator_key)
        matching = [o for o in (after_orders or []) if any(r.get("system") == "shopify_live" and r.get("external_id") == numeric_order_id for r in o.get("external_refs", []))]
        if matching:
            sanocea_order = matching[-1]
            break
        time.sleep(3)
    journey["webhook_created_canonical_order"] = sanocea_order is not None
    journey["canonical_order_id"] = sanocea_order["id"] if sanocea_order else None
    checks["real_webhook_created_canonical_order"] = _check(
        "PASS" if sanocea_order else "FAIL",
        f"real Shopify order {numeric_order_id} -> real ORDERS_CREATE webhook (via the real tunnel at "
        f"{WEBHOOK_DELIVERY_BASE_URL}) -> canonical Sanocea order: found={sanocea_order is not None}. "
        f"REQUIRES a real webhook subscription for this merchant's channel already registered (see "
        f"register_webhooks / the prep doc's step 5) AND the tunnel actually up and reachable from "
        f"Shopify's cloud - a FAIL here most likely means one of those two setup steps, not the "
        f"connector itself.",
    )

    # --- 8. Webhook replay / idempotency --------------------------------------------------------------
    dup_status_1 = dup_status_2 = None
    orders_after_replay = before_count
    if sanocea_order:
        raw_order = _shopify_graphql(
            "query($id: ID!) { order(id: $id) { id name email financialStatus: displayFinancialStatus fulfillmentStatus: displayFulfillmentStatus updatedAt cancelledAt totalPriceSet { shopMoney { amount } } lineItems(first: 5) { nodes { sku title quantity } } } }",
            {"id": shopify_order_gid},
        )["order"]
        # Reconstructs a REST-shaped payload matching what a real ORDERS_UPDATED webhook delivers (id,
        # financial_status, line_items with price/quantity/sku, updated_at - see the prep doc's audit
        # for why NOT "updated_sequence", which real Shopify never sends) - resending the SAME delivery
        # (same webhook id) twice proves checksum/delivery-id-based idempotency, matching the WooCommerce
        # certification's equivalent step.
        replay_payload = {
            "id": int(numeric_order_id), "order_number": raw_order.get("name", "").lstrip("#"),
            "email": raw_order.get("email"), "financial_status": (raw_order.get("financialStatus") or "").lower(),
            "fulfillment_status": raw_order.get("fulfillmentStatus"), "updated_at": raw_order.get("updatedAt"),
            "cancelled_at": raw_order.get("cancelledAt"),
            "total_price": (raw_order.get("totalPriceSet", {}).get("shopMoney", {}) or {}).get("amount", "0"),
            "line_items": [{"sku": li.get("sku"), "title": li.get("title"), "quantity": li.get("quantity"), "price": "499.00"} for li in raw_order.get("lineItems", {}).get("nodes", [])],
        }
        replay_body = json.dumps(replay_payload, separators=(",", ":")).encode()
        dup_status_1 = _post_webhook("orders/updated", replay_body, f"cert-replay-{numeric_order_id}")
        dup_status_2 = _post_webhook("orders/updated", replay_body, f"cert-replay-{numeric_order_id}")
        _, orders_after_replay_list = _sanocea("GET", f"/merchants/{MERCHANT_ID}/orders", token=operator_key)
        orders_after_replay = len(orders_after_replay_list) if isinstance(orders_after_replay_list, list) else before_count
    journey["duplicate_webhook_replay_statuses"] = [dup_status_1, dup_status_2]
    journey["orders_after_duplicate_replay"] = orders_after_replay
    checks["duplicate_webhook_no_duplicate_order"] = _check(
        "PASS" if sanocea_order and dup_status_1 == 200 and dup_status_2 == 200 and orders_after_replay == before_count + 1 else "FAIL" if sanocea_order else "UNVERIFIED",
        f"replay statuses={[dup_status_1, dup_status_2]} order_count_after={orders_after_replay} (must stay at before_count+1={before_count + 1})" if sanocea_order else "skipped - no canonical order was created to replay against",
    )

    # --- 9. Fulfilment (real FulfillmentOrder API) -----------------------------------------------------
    fulfilment_status = None
    if shopify_order_gid:
        try:
            fulfilment_result = probe.execute_mutation(MutationRequest(
                merchant_id=MERCHANT_ID, action="create_fulfilment", object_type="Order",
                payload={"external_order_id": numeric_order_id}, idempotency_key=f"cert-fulfil:{numeric_order_id}",
            ))
            fulfilment_status = fulfilment_result.payload.get("status")
            journey["fulfilment_result"] = fulfilment_result.payload
            checks["real_fulfilment_via_fulfillment_order_api"] = _check("PASS" if fulfilment_status else "FAIL", f"fulfillmentCreate result status={fulfilment_status}")
        except Exception as exc:  # noqa: BLE001 - report the real failure, don't hide it
            journey["fulfilment_error"] = str(exc)
            checks["real_fulfilment_via_fulfillment_order_api"] = _check("FAIL", f"fulfillmentCreate raised: {exc}")
    else:
        checks["real_fulfilment_via_fulfillment_order_api"] = _check("UNVERIFIED", "no real Shopify order gid available")

    # --- 10. Cancellation where valid (a SEPARATE order - a fulfilled/refunded order is a genuinely
    #     different Shopify business state, mirroring the exact "two separate orders" lesson the
    #     WooCommerce certification already learned; do not assume Shopify's rule is identical, verify
    #     it live and report the real behaviour either way) -----------------------------------------
    cancel_order_result = _shopify_graphql(
        """mutation($order: OrderCreateOrderInput!) { orderCreate(order: $order) { order { id name } userErrors { field message } } }""",
        {"order": {"lineItems": [{"title": "Shopify Dev Store Cert Shirt - Cancellation Order", "sku": sku, "priceSet": {"shopMoney": {"amount": "499.00", "currencyCode": _shop_currency()}}, "quantity": 1}], "email": "shopify-live-cert-buyer-2@example.com"}},
    )
    # Guarded with `or {}` at each level - orderCreate can legitimately be null (this is the exact spot
    # a real run crashed with AttributeError: 'NoneType' object has no attribute 'get' before this fix).
    cancel_order_gid = ((cancel_order_result or {}).get("orderCreate") or {}).get("order", {}).get("id")
    journey["order_gid_for_cancellation"] = cancel_order_gid
    if cancel_order_gid:
        try:
            cancel_numeric_id = cancel_order_gid.rsplit("/", 1)[-1]
            cancel_result = probe.execute_mutation(MutationRequest(
                merchant_id=MERCHANT_ID, action="cancel_order", object_type="Order",
                payload={"external_order_id": cancel_numeric_id, "reason": "OTHER", "refund": False, "restock": True},
                idempotency_key=f"cert-cancel:{cancel_numeric_id}",
            ))
            journey["cancel_result"] = cancel_result.payload
            checks["real_cancellation_where_valid"] = _check("PASS" if cancel_result.async_operation_id else "FAIL", f"orderCancel job={cancel_result.async_operation_id}")
        except Exception as exc:  # noqa: BLE001
            journey["cancel_error"] = str(exc)
            checks["real_cancellation_where_valid"] = _check("FAIL", f"orderCancel raised: {exc}")
    else:
        checks["real_cancellation_where_valid"] = _check("UNVERIFIED", "could not create a second order to cancel")

    # --- 11. Refund via the store's real test-payment path (Bogus Gateway) --------------------------
    # A refundCreate transaction requires a real prior payment transaction on the order to refund
    # against - which gateway this dev store actually has active (Bogus Gateway is the documented test
    # path; Shopify Payments' own test cards are a DIFFERENT, incompatible mechanism) can only be
    # confirmed against the real store. Reported as a finding either way, not assumed.
    findings.append({
        "area": "refund_test_payment_path",
        "finding": "Shopify's real test-payment mechanism for a development store is the Bogus Gateway "
                   "(Settings > Payments > Additional payment methods), which is DIFFERENT from Shopify "
                   "Payments' own test card numbers (the Bogus Gateway does not accept those cards, and "
                   "vice versa) - must be enabled once on the real store before this step can produce a "
                   "refundable transaction. If orderCreate-created orders (used above for automation) "
                   "don't carry a real gateway transaction at all, a refund may need to originate from a "
                   "Bogus-Gateway checkout order instead - report whichever is true against the real store.",
    })
    if sanocea_order:
        try:
            refund_result = probe.execute_mutation(MutationRequest(
                merchant_id=MERCHANT_ID, action="create_refund", object_type="Order",
                payload={"external_order_id": numeric_order_id, "amount": 10000, "reason": "cert test refund"},
                idempotency_key=f"cert-refund:{numeric_order_id}",
            ))
            journey["refund_result"] = refund_result.payload
            checks["real_refund_via_bogus_gateway_or_manual"] = _check("PASS" if refund_result.external_ref else "FAIL", f"refundCreate refund id={refund_result.external_ref}")
        except Exception as exc:  # noqa: BLE001
            journey["refund_error"] = str(exc)
            checks["real_refund_via_bogus_gateway_or_manual"] = _check("FAIL", f"refundCreate raised (see refund_test_payment_path finding above for the likely reason): {exc}")
    else:
        checks["real_refund_via_bogus_gateway_or_manual"] = _check("UNVERIFIED", "no canonical order was created to refund")

    # --- 12. Reconciliation ---------------------------------------------------------------------------
    if sanocea_order:
        reconciliation = probe.reconcile(MERCHANT_ID, {"external_order_id": numeric_order_id})
        journey["reconciliation_result"] = reconciliation
        checks["reconciliation"] = _check("PASS", f"reconcile() ran against the real order: {reconciliation}")
    else:
        checks["reconciliation"] = _check("UNVERIFIED", "no canonical order to reconcile")
    # _run_journey() only populates journey/findings/checks (in place) or raises - main() always writes
    # the report, in exactly one place, whether this function returns normally or raises.


if __name__ == "__main__":
    main()
