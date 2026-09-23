from __future__ import annotations

import base64
import os

import pytest

from sanocea.packages.domain_contract.credentials import (
    EnvCredentialProvider,
    MissingMasterKeyError,
    _make_locator,
    _parse_locator,
    build_production_credential_provider,
    load_master_keys_from_env,
)

# Step P0.1 - pure unit tests for the encryption/key-loading/locator machinery that does not require a
# real database. Restart durability, tenant/channel isolation, rotation, revocation, raw-DB inspection,
# and connector-consumption proofs live in tests/integration/test_credential_storage_real_infra.py
# (real Postgres required).


def _clear_master_key_env():
    for name in list(os.environ):
        if name.startswith("SANOCEA_CRED_MASTER_KEY_"):
            del os.environ[name]


@pytest.fixture(autouse=True)
def _isolated_master_key_env():
    _clear_master_key_env()
    yield
    _clear_master_key_env()


def _b64_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


# --- key loading -----------------------------------------------------------------------------------

def test_load_master_keys_from_env_reads_versions_and_current():
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = _b64_key()
    os.environ["SANOCEA_CRED_MASTER_KEY_V2"] = _b64_key()
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v2"
    keys, current = load_master_keys_from_env()
    assert set(keys) == {"v1", "v2"}
    assert current == "v2"
    assert len(keys["v1"]) == 32 and len(keys["v2"]) == 32


def test_load_master_keys_from_env_no_current_returns_none():
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = _b64_key()
    keys, current = load_master_keys_from_env()
    assert current is None
    assert "v1" in keys


def test_load_master_keys_rejects_wrong_length():
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = base64.b64encode(os.urandom(16)).decode()
    with pytest.raises(MissingMasterKeyError):
        load_master_keys_from_env()


def test_load_master_keys_rejects_invalid_base64():
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = "not-valid-base64!!!"
    with pytest.raises(MissingMasterKeyError):
        load_master_keys_from_env()


# --- fail-closed startup selection -----------------------------------------------------------------

def test_build_production_provider_fails_closed_with_no_key_configured():
    with pytest.raises(MissingMasterKeyError):
        build_production_credential_provider("postgresql://irrelevant/irrelevant")


def test_build_production_provider_fails_closed_when_current_points_to_missing_key():
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v9"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = _b64_key()
    with pytest.raises(MissingMasterKeyError):
        build_production_credential_provider("postgresql://irrelevant/irrelevant")


def test_build_production_provider_succeeds_with_valid_configuration():
    os.environ["SANOCEA_CRED_MASTER_KEY_CURRENT"] = "v1"
    os.environ["SANOCEA_CRED_MASTER_KEY_V1"] = _b64_key()
    provider = build_production_credential_provider("postgresql://irrelevant/irrelevant")
    health = provider.health()
    assert health == {"provider": "encrypted_postgres", "durable": True, "encrypted": True, "current_key_version": "v1", "known_key_versions": ["v1"]}


# --- locator encoding ----------------------------------------------------------------------------

def test_locator_roundtrip():
    locator = _make_locator("abc123", "mer_A", "shopify_webhook_secret")
    credential_id, merchant_id, ref = _parse_locator(locator)
    assert (credential_id, merchant_id, ref) == ("abc123", "mer_A", "shopify_webhook_secret")


def test_malformed_locator_raises_value_error():
    with pytest.raises(ValueError):
        _parse_locator("not json at all")
    with pytest.raises(ValueError):
        _parse_locator('{"id": "x"}')  # missing merchant_id/ref


# --- EnvCredentialProvider reality label ------------------------------------------------------------

def test_env_provider_health_labels_itself_as_non_durable_non_encrypted():
    provider = EnvCredentialProvider()
    assert provider.health() == {"provider": "env", "durable": False, "encrypted": False}


def test_env_provider_store_resolve_delete_roundtrip():
    provider = EnvCredentialProvider()
    locator = provider.store("mer_A", "test_ref", "super-secret-value")
    assert provider.resolve(locator) == "super-secret-value"
    provider.delete(locator)
    with pytest.raises(KeyError):
        provider.resolve(locator)
