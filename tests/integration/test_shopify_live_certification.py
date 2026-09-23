from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import psycopg2
import pytest

from sanocea.connectors.shopify_live import ShopifyAccessTokenManager, ShopifyLiveConnector
from sanocea.packages.connector_sdk import MutationRequest
from sanocea.packages.domain_contract import PostgresStore
from sanocea.packages.domain_contract.credentials import build_production_credential_provider

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN")
        and os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID")
        and os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET")
        and os.environ.get("SANOCEA_PG_DSN")
    ),
    reason="Requires live Shopify dev store credentials and Postgres DSN",
)

SHOP_DOMAIN = os.environ.get("SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN", "")
CLIENT_ID = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET", "")
API_VERSION = os.environ.get("SANOCEA_SHOPIFY_LIVE_API_VERSION", "2026-07")
WEBHOOK_DELIVERY_BASE_URL = os.environ.get("SANOCEA_SHOPIFY_LIVE_WEBHOOK_DELIVERY_BASE_URL", "")
PG_DSN = os.environ.get("SANOCEA_PG_DSN", "postgresql://sanocea@127.0.0.1:55432/sanocea_phase05")
SANOCEA_APP_URL = os.environ.get("SANOCEA_TEST_APP_URL", "http://127.0.0.1:8080")
SERVICE_KEY = os.environ.get("SANOCEA_TEST_SERVICE_KEY", "")
MERCHANT_ID = "shopify_live_cert_merchant"


@pytest.fixture(scope="module")
def token_manager():
    return ShopifyAccessTokenManager(shop_domain=SHOP_DOMAIN, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)


@pytest.fixture(scope="module")
def store():
    return PostgresStore(PG_DSN, credential_provider=build_production_credential_provider(PG_DSN))


@pytest.fixture(scope="module")
def connector(store, token_manager):
    return ShopifyLiveConnector(
        store,
        workflow=None,
        shop_domain=SHOP_DOMAIN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        api_version=API_VERSION,
        token_manager=token_manager,
        webhook_delivery_base_url=WEBHOOK_DELIVERY_BASE_URL,
    )


def _shopify_graphql(token_manager, query: str, variables: dict):
    token = token_manager.get_token()
    url = f"https://{SHOP_DOMAIN}/admin/api/{API_VERSION}/graphql.json"
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        parsed = json.loads(resp.read())
    if parsed.get("errors"):
        raise RuntimeError(f"Shopify GraphQL errors: {parsed['errors']}")
    return parsed.get("data") or {}


def _api_call(method: str, path: str, *, token: str | None = None, body: dict | None = None, raw_body: bytes | None = None, headers: dict | None = None):
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
        except Exception:
            return exc.code, raw.decode(errors="replace")


# 1. Authentication & Store Discovery
def test_1_authentication_and_store_discovery(token_manager, connector):
    token = token_manager.get_token()
    assert token and isinstance(token, str) and not token.startswith("shpss_")
    data = _shopify_graphql(token_manager, "query { shop { name currencyCode primaryDomain { host } } }", {})
    shop = data.get("shop") or {}
    assert shop.get("name") is not None
    assert shop.get("currencyCode") in ("USD", "INR", "EUR", "GBP")

    location_gid = connector._ensure_location_gid()
    assert location_gid.startswith("gid://shopify/Location/")


# 2. Product Creation, 3. Read-back & 4. Publication Verification
def test_2_to_4_product_creation_readback_and_verification(token_manager, connector):
    # Ensure merchant onboarded
    status, res = _api_call("POST", "/admin/merchants", token=SERVICE_KEY, body={
        "merchant_id": MERCHANT_ID,
        "display_name": "Shopify Dev-Store Cert Merchant",
        "config": {
            "currency": "INR", "publication": {"require_approval": False},
            "shopify_live": {"shop_domain": SHOP_DOMAIN, "api_version": API_VERSION, "webhook_delivery_base_url": WEBHOOK_DELIVERY_BASE_URL},
        },
        "credentials": {"shopify_live_client_id": CLIENT_ID, "shopify_live_client_secret": CLIENT_SECRET},
        "channels": [{"type": "shopify_live", "name": "Shopify (dev store)", "credential_ref": "shopify_live_client_id"}],
    })
    operator_key = res["operator_api_key"] if status == 200 else None
    assert operator_key is not None

    sku = f"SHOPIFY-CERT-PYTEST-{int(time.time())}"
    boundary = "----shopifypytestboundary"
    csv_body = f"sku,title,price,currency,product_type,category\n{sku},Pytest Cert Shirt,499.00,INR,apparel,shirts\n".encode()
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"cert.csv\"\r\nContent-Type: text/csv\r\n\r\n").encode() + csv_body + f"\r\n--{boundary}--\r\n".encode()
    status, drafts = _api_call("POST", f"/merchants/{MERCHANT_ID}/catalogue/ingest", token=operator_key, raw_body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    assert status == 200 and drafts
    draft_id = drafts[0]["id"]

    status, approved = _api_call("POST", f"/merchants/{MERCHANT_ID}/catalogue/drafts/{draft_id}/approve-facts", token=operator_key)
    assert status == 200 and approved.get("state") == "READY"

    channel_id = f"{MERCHANT_ID}_shopify_live"
    status, publish_res = _api_call("POST", f"/merchants/{MERCHANT_ID}/catalogue/drafts/{draft_id}/publish", token=operator_key, body={"channel_id": channel_id})
    assert status == 200
    assert publish_res.get("outcome") == "published"
    product_gid = (publish_res.get("verification") or {}).get("external_product_id")
    assert product_gid and product_gid.startswith("gid://shopify/Product/")

    # 3. Independent Read-back
    readback = _shopify_graphql(token_manager, "query($id: ID!) { product(id: $id) { title status variants(first: 1) { nodes { sku price } } } }", {"id": product_gid})
    product_data = readback.get("product") or {}
    assert product_data.get("title") == "Pytest Cert Shirt"
    variant = product_data.get("variants", {}).get("nodes", [{}])[0]
    assert variant.get("sku") == sku
    assert variant.get("price") == "499.00"

    # 4. Publication Verification
    assert product_data.get("status") == "ACTIVE"
    verification = publish_res.get("verification") or {}
    assert verification.get("outcome") == "VERIFIED"


# 5. Duplicate / Replay Protection
def test_5_duplicate_replay_protection(token_manager, connector):
    sku = f"SHOPIFY-CERT-DUP-{int(time.time())}"
    # Mutate 1
    res1 = connector.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="create_product", object_type="ProductDraft",
        payload={"title": "Duplicate Protection Shirt", "sku": sku, "price": "399.00"},
        idempotency_key=f"cert-dup-test:{sku}",
    ))
    product_gid = res1.external_ref
    assert product_gid is not None

    # Mutate 2 with same idempotency key
    res2 = connector.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="create_product", object_type="ProductDraft",
        payload={"title": "Duplicate Protection Shirt", "sku": sku, "price": "399.00"},
        idempotency_key=f"cert-dup-test:{sku}",
    ))
    assert res2.external_ref == product_gid

    # Query Shopify for variants with this SKU
    sku_data = _shopify_graphql(token_manager, "query($q: String!) { productVariants(first: 5, query: $q) { nodes { id product { id } } } }", {"q": f"sku:{sku}"})
    variants = sku_data.get("productVariants", {}).get("nodes") or []
    assert len(variants) == 1, f"Expected exactly 1 variant on Shopify for SKU {sku}, found {len(variants)}"


# 6. Timeout-After-Mutation Recovery
def test_6_timeout_after_mutation_recovery(token_manager, connector):
    sku = f"SHOPIFY-CERT-TIMEOUT-{int(time.time())}"
    # Create product
    res = connector.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="create_product", object_type="ProductDraft",
        payload={"title": "Timeout Recovery Shirt", "sku": sku, "price": "499.00"},
        idempotency_key=f"cert-timeout-create:{sku}",
    ))
    product_gid = res.external_ref

    # Execute update directly on Shopify to simulate a mutation that succeeded externally but whose client response timed out
    _shopify_graphql(token_manager, """mutation($input: ProductSetInput!, $identifier: ProductSetIdentifiers, $synchronous: Boolean) {
        productSet(input: $input, identifier: $identifier, synchronous: $synchronous) {
            product { id title }
            userErrors { field message }
        }
    }""", {
        "input": {
            "title": "Timeout Recovery Shirt",
            "productOptions": [{"name": "Title", "values": [{"name": "Default Title"}]}],
            "variants": [{"price": "599.00", "sku": sku, "optionValues": [{"optionName": "Title", "name": "Default Title"}]}],
        },
        "identifier": {"id": product_gid},
        "synchronous": True,
    })

    # Recovery worker performs authoritative read-back by SKU
    recovered_gid = connector._find_product_gid_by_sku(sku)
    assert recovered_gid == product_gid

    rb = _shopify_graphql(token_manager, "query($id: ID!) { product(id: $id) { variants(first: 1) { nodes { price } } } }", {"id": recovered_gid})
    recovered_price = rb.get("product", {}).get("variants", {}).get("nodes", [{}])[0].get("price")
    assert recovered_price == "599.00", "Authoritative read-back must confirm external price 599.00 without repeating mutation"


# 7. Inventory Write & Read-back
def test_7_inventory_write_and_readback(token_manager, connector):
    sku = f"SHOPIFY-CERT-INV-{int(time.time())}"
    res = connector.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="create_product", object_type="ProductDraft",
        payload={"title": "Inventory Test Shirt", "sku": sku, "price": "499.00"},
        idempotency_key=f"cert-inv-create:{sku}",
    ))
    product_gid = res.external_ref

    # Write inventory
    inv_res = connector.execute_mutation(MutationRequest(
        merchant_id=MERCHANT_ID, action="set_inventory", object_type="ProductDraft",
        payload={"external_product_id": product_gid, "quantity": 18},
        idempotency_key=f"cert-inv-set:{sku}",
    ))
    assert inv_res.status == "accepted"

    # Read back inventory
    inv_readback = connector.fetch(MERCHANT_ID, "inventory", product_gid)
    assert inv_readback.get("available") == 18


# 11. Merchant Isolation
def test_11_merchant_isolation():
    # Onboard merchant B
    merchant_b_id = f"iso_mer_b_{int(time.time())}"
    status, res = _api_call("POST", "/admin/merchants", token=SERVICE_KEY, body={
        "merchant_id": merchant_b_id,
        "display_name": "Isolated Merchant B",
        "config": {"currency": "USD"},
        "credentials": {},
        "channels": [],
    })
    assert status == 200
    op_key_b = res.get("operator_api_key")

    # Merchant B tries to read Merchant A's data
    s1, _ = _api_call("GET", f"/merchants/{MERCHANT_ID}/orders", token=op_key_b)
    s2, _ = _api_call("GET", f"/merchants/{MERCHANT_ID}/catalogue/drafts", token=op_key_b)
    assert s1 == 403, f"Expected 403 Forbidden for cross-tenant order read, got {s1}"
    assert s2 == 403, f"Expected 403 Forbidden for cross-tenant draft read, got {s2}"

    # Database isolation check
    with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM encrypted_credentials WHERE merchant_id = %s", (merchant_b_id,))
        count = cur.fetchone()[0]
        assert count == 0


# 12. Process Restart / Recovery
def test_12_process_restart_recovery(token_manager, store):
    token_manager.invalidate()
    fresh_store = PostgresStore(PG_DSN, credential_provider=build_production_credential_provider(PG_DSN))
    cid = fresh_store.get_credential_ref(MERCHANT_ID, "shopify_live_client_id")
    secret = fresh_store.get_credential_ref(MERCHANT_ID, "shopify_live_client_secret")
    assert cid == CLIENT_ID
    assert secret == CLIENT_SECRET

    fresh_connector = ShopifyLiveConnector(
        fresh_store, workflow=None, shop_domain=SHOP_DOMAIN, client_id=cid, client_secret=secret, api_version=API_VERSION,
    )
    loc = fresh_connector._ensure_location_gid()
    assert loc.startswith("gid://shopify/Location/")


# 13. Audit Trail & Secret Redaction
def test_13_audit_trail_and_secret_redaction():
    with psycopg2.connect(PG_DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_events WHERE merchant_id = %s", (MERCHANT_ID,))
        audit_count = cur.fetchone()[0]
        assert audit_count > 0

        cur.execute("SELECT * FROM audit_events WHERE merchant_id = %s", (MERCHANT_ID,))
        all_audit = cur.fetchall()
        cur.execute("SELECT * FROM raw_external_events WHERE merchant_id = %s", (MERCHANT_ID,))
        all_raw = cur.fetchall()

    assert not any(CLIENT_SECRET in str(r) for r in all_audit), "CLIENT_SECRET leaked into audit_events!"
    assert not any(CLIENT_SECRET in str(r) for r in all_raw), "CLIENT_SECRET leaked into raw_external_events!"
    assert not any("shpua_" in str(r) or "shpat_" in str(r) for r in all_audit), "Access token leaked into audit_events!"
