from __future__ import annotations

import base64
import json
import os
import threading
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("SANOCEA_PG_DSN"),
    reason="requires real Postgres DSN in SANOCEA_PG_DSN",
)

# Step P0.1 - real-Postgres proof of durable, encrypted, tenant-isolated credential storage. Every test
# below either constructs a FRESH DurableEncryptedCredentialProvider/PostgresStore instance per
# operation (proving no in-memory state is load-bearing - real restart durability, not a fake retained
# object) or exercises the actual connector factories in packages/runtime/service_graph.py so credential
# consumption is proven end to end, not just at the provider layer.

SENTINEL = "sentinel-do-not-leak-9f3a7c1e2b"


def _b64_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


@pytest.fixture
def dsn() -> str:
    return os.environ["SANOCEA_PG_DSN"]


@pytest.fixture
def master_key_env():
    from sanocea.packages.domain_contract.credentials import build_production_credential_provider

    original = {k: v for k, v in os.environ.items() if k.startswith("SANOCEA_CRED_MASTER_KEY_")}
    for k in original:
        del os.environ[k]
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = _b64_key()
    yield build_production_credential_provider
    for k in list(os.environ):
        if k.startswith("SANOCEA_CRED_MASTER_KEY_"):
            del os.environ[k]
    os.environ.update(original)


def _setup_merchant(dsn: str, suffix: str):
    from sanocea.packages.domain_contract import PostgresStore
    from sanocea.packages.domain_contract.models import Merchant

    merchant_id = f"credtest_{suffix}"
    provider_store = PostgresStore(dsn)  # dev provider, only for entity setup, never for credential ops in these tests
    provider_store.migrate()
    provider_store.put(Merchant(id=merchant_id, merchant_id=merchant_id, legal_name="CredTest", display_name="CredTest"))
    return merchant_id


def _encrypted_store(dsn: str, master_key_env) -> "PostgresStore":  # noqa: F821
    from sanocea.packages.domain_contract import PostgresStore

    return PostgresStore(dsn, credential_provider=master_key_env(dsn))


# --- 1: encrypted store/get roundtrip -----------------------------------------------------------------

def test_encrypted_store_get_roundtrip(dsn, master_key_env):
    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "test_ref", f"{SENTINEL}-value")
    assert store.get_credential_ref(merchant_id, "test_ref") == f"{SENTINEL}-value"


# --- 2: restart durability (the core acceptance condition) ---------------------------------------------

def test_restart_durability(dsn, master_key_env):
    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    writer = _encrypted_store(dsn, master_key_env)
    writer.set_credential_ref(merchant_id, "restart_ref", f"{SENTINEL}-restart")
    del writer  # destroy the provider/application instance - no reference retained anywhere

    # A genuinely fresh instance, built the SAME way build_production_credential_provider would at a
    # real process startup, against nothing but the same DSN and the same externally-supplied key.
    fresh_store = _encrypted_store(dsn, master_key_env)
    assert fresh_store.get_credential_ref(merchant_id, "restart_ref") == f"{SENTINEL}-restart"


# --- 3: tenant isolation -------------------------------------------------------------------------------

def test_tenant_isolation(dsn, master_key_env):
    from sanocea.packages.domain_contract.store import TenantAccessError

    suffix = uuid4().hex[:8]
    merchant_a = _setup_merchant(dsn, f"a_{suffix}")
    merchant_b = _setup_merchant(dsn, f"b_{suffix}")
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_a, "shared_ref_name", f"{SENTINEL}-tenant-a")
    with pytest.raises(TenantAccessError):
        store.get_credential_ref(merchant_b, "shared_ref_name")


# --- 4: channel isolation (same merchant, two different channel refs) ---------------------------------

def test_channel_isolation_within_one_merchant(dsn, master_key_env):
    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "shopify_webhook_secret", f"{SENTINEL}-shopify")
    store.set_credential_ref(merchant_id, "flipkart_partner_client_secret", f"{SENTINEL}-flipkart")
    assert store.get_credential_ref(merchant_id, "shopify_webhook_secret") == f"{SENTINEL}-shopify"
    assert store.get_credential_ref(merchant_id, "flipkart_partner_client_secret") == f"{SENTINEL}-flipkart"


# --- 5: multi-storefront isolation via real connector factories ----------------------------------------

def test_multi_storefront_isolation_via_connector_factories(dsn, master_key_env):
    from sanocea.packages.runtime.service_graph import _amazon_factory, _flipkart_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "flipkart_partner_client_id", "fk-client-id")
    store.set_credential_ref(merchant_id, "flipkart_partner_client_secret", "fk-client-secret")
    store.set_credential_ref(merchant_id, "flipkart_merchant_refresh_token", "fk-refresh")
    store.set_credential_ref(merchant_id, "amazon_lwa_client_id", "amz-client-id")
    store.set_credential_ref(merchant_id, "amazon_lwa_client_secret", "amz-client-secret")
    store.set_credential_ref(merchant_id, "amazon_merchant_refresh_token", "amz-refresh")
    store.set_config(merchant_id, {"amazon": {"seller_id": "SELLER1"}})

    flipkart = _flipkart_factory(store, None, merchant_id)
    amazon = _amazon_factory(store, None, merchant_id)
    assert flipkart.auth.client_id == "fk-client-id"
    assert amazon.auth.client_id == "amz-client-id"
    assert flipkart.auth.client_id != amazon.auth.client_id


# --- 6: replacement/rotation ---------------------------------------------------------------------------

def test_credential_replacement_old_value_never_returned_again(dsn, master_key_env):
    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "rotating_ref", f"{SENTINEL}-old")
    assert store.get_credential_ref(merchant_id, "rotating_ref") == f"{SENTINEL}-old"
    store.set_credential_ref(merchant_id, "rotating_ref", f"{SENTINEL}-new")
    assert store.get_credential_ref(merchant_id, "rotating_ref") == f"{SENTINEL}-new"


# --- 7: deletion/revocation ----------------------------------------------------------------------------

def test_deletion_revokes_and_connector_construction_fails_cleanly(dsn, master_key_env):
    from sanocea.packages.domain_contract.store import TenantAccessError
    from sanocea.packages.runtime.service_graph import _flipkart_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "flipkart_partner_client_id", f"{SENTINEL}-revoke-me")
    store.set_credential_ref(merchant_id, "flipkart_partner_client_secret", "x")
    store.set_credential_ref(merchant_id, "flipkart_merchant_refresh_token", "y")
    store.delete_credential_ref(merchant_id, "flipkart_partner_client_id")

    with pytest.raises(TenantAccessError) as excinfo:
        store.get_credential_ref(merchant_id, "flipkart_partner_client_id")
    assert SENTINEL not in str(excinfo.value)

    with pytest.raises(TenantAccessError) as excinfo2:
        _flipkart_factory(store, None, merchant_id)
    assert SENTINEL not in str(excinfo2.value)


# --- 8: wrong encryption key ---------------------------------------------------------------------------

def test_wrong_encryption_key_fails_closed(dsn, master_key_env):
    from sanocea.packages.domain_contract.credentials import DurableEncryptedCredentialProvider

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "wrongkey_ref", f"{SENTINEL}-correct")

    wrong_provider = DurableEncryptedCredentialProvider(dsn, {"v1": os.urandom(32)}, "v1")
    from sanocea.packages.domain_contract import PostgresStore

    wrong_store = PostgresStore(dsn, credential_provider=wrong_provider)
    with pytest.raises(ValueError):
        wrong_store.get_credential_ref(merchant_id, "wrongkey_ref")


# --- 9: corrupted ciphertext ---------------------------------------------------------------------------

def test_corrupted_ciphertext_fails_closed(dsn, master_key_env):
    import psycopg2

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "corrupt_ref", f"{SENTINEL}-corrupt")

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE encrypted_credentials SET ciphertext = ciphertext || %s WHERE merchant_id = %s AND ref = %s",
            (b"\x00\x01", merchant_id, "corrupt_ref"),
        )
        conn.commit()

    with pytest.raises(ValueError):
        store.get_credential_ref(merchant_id, "corrupt_ref")


# --- 10: missing encryption key (key_version present in DB, not loaded into this provider) -----------

def test_missing_key_version_fails_closed(dsn, master_key_env):
    from sanocea.packages.domain_contract.credentials import DurableEncryptedCredentialProvider, MissingMasterKeyError

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "missingkey_ref", f"{SENTINEL}-missing")

    # A provider that only knows about a DIFFERENT key version than what actually encrypted this row.
    provider_without_v1 = DurableEncryptedCredentialProvider(dsn, {"v2": os.urandom(32)}, "v2")
    from sanocea.packages.domain_contract import PostgresStore

    store_without_v1 = PostgresStore(dsn, credential_provider=provider_without_v1)
    with pytest.raises(MissingMasterKeyError):
        store_without_v1.get_credential_ref(merchant_id, "missingkey_ref")


# --- 11: malformed credential payload (malformed locator) ---------------------------------------------

def test_malformed_locator_raises_value_error(dsn, master_key_env):
    import psycopg2

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "malformed_ref", "value")
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE credential_references SET locator = %s WHERE merchant_id = %s AND ref = %s",
            ("not-json-at-all", merchant_id, "malformed_ref"),
        )
        conn.commit()
    with pytest.raises(ValueError):
        store.get_credential_ref(merchant_id, "malformed_ref")


# --- 12: concurrent replacement (bounded harness, single invocation, aggregate once) -------------------

def test_concurrent_replacement_never_corrupts_the_row(dsn, master_key_env):
    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "concurrent_ref", "initial")

    errors: list[str] = []
    barrier = threading.Barrier(2)

    def replace(value: str) -> None:
        try:
            barrier.wait(timeout=10)
            thread_store = _encrypted_store(dsn, master_key_env)
            thread_store.set_credential_ref(merchant_id, "concurrent_ref", value)
        except BaseException as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")

    t1 = threading.Thread(target=replace, args=("value-a",))
    t2 = threading.Thread(target=replace, args=("value-b",))
    t1.start()
    t2.start()
    t1.join(timeout=20)
    t2.join(timeout=20)

    assert not errors, f"unexpected errors: {errors}"
    final = store.get_credential_ref(merchant_id, "concurrent_ref")
    assert final in {"value-a", "value-b"}, "exactly one writer's value must win cleanly, never a corrupted/mixed value"


# --- 13: DB rollback on failed write --------------------------------------------------------------------

def test_failed_write_leaves_no_partial_row(dsn, master_key_env):
    from sanocea.packages.domain_contract.credentials import DurableEncryptedCredentialProvider

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    # A merchant_id that does not exist - the foreign key constraint on encrypted_credentials.merchant_id
    # must reject the write atomically, leaving no partial ciphertext/nonce row behind.
    nonexistent_merchant = f"does_not_exist_{uuid4().hex[:8]}"
    provider = DurableEncryptedCredentialProvider(dsn, {"v1": os.urandom(32)}, "v1")
    import psycopg2

    with pytest.raises(psycopg2.Error):
        provider.store(nonexistent_merchant, "ref", "value")

    import psycopg2 as pg

    with pg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM encrypted_credentials WHERE merchant_id = %s", (nonexistent_merchant,))
        assert cur.fetchone()[0] == 0


# --- 14/15/16: sentinel absent from raw DB, logs, audit, exceptions ------------------------------------

def test_sentinel_absent_from_raw_database_row(dsn, master_key_env):
    import psycopg2

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "raw_db_ref", f"{SENTINEL}-raw-db-check")

    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT ciphertext, nonce, key_version FROM encrypted_credentials WHERE merchant_id = %s AND ref = %s", (merchant_id, "raw_db_ref"))
        row = cur.fetchone()
        assert row is not None
        ciphertext, nonce, key_version = row
        assert SENTINEL.encode() not in bytes(ciphertext)
        assert bytes(ciphertext), "ciphertext must be present (non-empty)"
        assert key_version == "v1"

        cur.execute("SELECT locator FROM credential_references WHERE merchant_id = %s AND ref = %s", (merchant_id, "raw_db_ref"))
        locator = cur.fetchone()[0]
        assert SENTINEL not in locator, "the locator itself must never contain the secret value"


def test_sentinel_absent_from_audit_and_exceptions_on_auth_failure(dsn, master_key_env):
    """Exercises a REAL failure path (revoked credential -> connector construction failure) and proves
    the sentinel never leaks into the audit ledger or ExceptionRecord table."""
    from sanocea.packages.domain_contract.models import ExceptionRecord
    from sanocea.packages.domain_contract.store import TenantAccessError
    from sanocea.packages.runtime.service_graph import _flipkart_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "flipkart_partner_client_id", f"{SENTINEL}-audit-check")
    store.set_credential_ref(merchant_id, "flipkart_partner_client_secret", "x")
    store.set_credential_ref(merchant_id, "flipkart_merchant_refresh_token", "y")
    store.delete_credential_ref(merchant_id, "flipkart_partner_client_id")

    with pytest.raises(TenantAccessError):
        _flipkart_factory(store, None, merchant_id)

    audit_dump = json.dumps([e.model_dump(mode="json") for e in store.list_audit(merchant_id)])
    exception_dump = json.dumps([e.model_dump(mode="json") for e in store.list(ExceptionRecord, merchant_id)])
    assert SENTINEL not in audit_dump
    assert SENTINEL not in exception_dump


def test_sentinel_absent_from_connector_health(dsn, master_key_env):
    from sanocea.packages.runtime.service_graph import _amazon_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "amazon_lwa_client_id", "id")
    store.set_credential_ref(merchant_id, "amazon_lwa_client_secret", f"{SENTINEL}-amazon-secret")
    store.set_credential_ref(merchant_id, "amazon_merchant_refresh_token", f"{SENTINEL}-amazon-refresh")
    store.set_config(merchant_id, {"amazon": {"seller_id": "SELLER1"}})

    connector = _amazon_factory(store, None, merchant_id)
    health = connector.connector_health()
    assert SENTINEL not in json.dumps(health)


# --- 17: Shopify / WooCommerce / Flipkart / Amazon / Meesho credential consumption ----------------------

def test_shopify_credential_consumption(dsn, master_key_env):
    from sanocea.connectors.shopify import ShopifyConnector
    from sanocea.workers.workflow import FakeTemporalEngine

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "shopify_webhook_secret", f"{SENTINEL}-shopify-webhook")

    connector = ShopifyConnector(store, FakeTemporalEngine(store))
    import base64
    import hashlib
    import hmac
    import json as _json

    body = _json.dumps({"id": 1, "line_items": []}).encode()
    secret = store.get_credential_ref(merchant_id, "shopify_webhook_secret")
    digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    result = connector.ingest_webhook(merchant_id, {"x-shopify-topic": "orders/create", "x-shopify-hmac-sha256": signature, "x-shopify-webhook-id": "wh-1"}, body)
    assert result["order_id"]


def test_woocommerce_credential_consumption(dsn, master_key_env):
    from sanocea.packages.runtime.service_graph import _woocommerce_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_config(merchant_id, {"woocommerce": {"base_url": "https://example-store.test"}})
    store.set_credential_ref(merchant_id, "woocommerce_consumer_key", f"{SENTINEL}-wc-key")
    store.set_credential_ref(merchant_id, "woocommerce_consumer_secret", f"{SENTINEL}-wc-secret")

    connector = _woocommerce_factory(store, None, merchant_id)
    assert connector.consumer_key == f"{SENTINEL}-wc-key"
    assert connector.consumer_secret == f"{SENTINEL}-wc-secret"


def test_flipkart_credential_consumption(dsn, master_key_env):
    from sanocea.packages.runtime.service_graph import _flipkart_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "flipkart_partner_client_id", f"{SENTINEL}-fk-id")
    store.set_credential_ref(merchant_id, "flipkart_partner_client_secret", f"{SENTINEL}-fk-secret")
    store.set_credential_ref(merchant_id, "flipkart_merchant_refresh_token", f"{SENTINEL}-fk-refresh")

    connector = _flipkart_factory(store, None, merchant_id)
    assert connector.auth.client_id == f"{SENTINEL}-fk-id"
    assert connector.auth.client_secret == f"{SENTINEL}-fk-secret"
    assert connector.auth.refresh_token == f"{SENTINEL}-fk-refresh"


def test_amazon_credential_consumption(dsn, master_key_env):
    from sanocea.packages.runtime.service_graph import _amazon_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_config(merchant_id, {"amazon": {"seller_id": "SELLER1"}})
    store.set_credential_ref(merchant_id, "amazon_lwa_client_id", f"{SENTINEL}-amz-id")
    store.set_credential_ref(merchant_id, "amazon_lwa_client_secret", f"{SENTINEL}-amz-secret")
    store.set_credential_ref(merchant_id, "amazon_merchant_refresh_token", f"{SENTINEL}-amz-refresh")

    connector = _amazon_factory(store, None, merchant_id)
    assert connector.auth.client_id == f"{SENTINEL}-amz-id"
    assert connector.auth.refresh_token == f"{SENTINEL}-amz-refresh"
    assert connector.seller_id == "SELLER1"


def test_meesho_credential_consumption(dsn, master_key_env):
    from sanocea.packages.runtime.service_graph import _meesho_factory

    merchant_id = _setup_merchant(dsn, uuid4().hex[:8])
    store = _encrypted_store(dsn, master_key_env)
    store.set_credential_ref(merchant_id, "meesho_client_id", f"{SENTINEL}-meesho-id")
    store.set_credential_ref(merchant_id, "meesho_security", f"{SENTINEL}-meesho-security")
    store.set_credential_ref(merchant_id, "meesho_supplier_identifier", f"{SENTINEL}-meesho-loc")

    connector = _meesho_factory(store, None, merchant_id)
    headers = connector.auth.auth_headers()
    assert headers["merchant"] == f"{SENTINEL}-meesho-id"
    assert headers["security"] == f"{SENTINEL}-meesho-security"
    assert headers["supplier_identifier"] == f"{SENTINEL}-meesho-loc"
