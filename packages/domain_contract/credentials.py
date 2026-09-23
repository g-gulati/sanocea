from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg2.extras import RealDictCursor

"""Step P0.1 - the production credential-storage boundary.

The pre-existing `EnvCredentialProvider` (this module, moved from postgres_store.py where it originated
- re-exported there for backward compatibility) is an explicitly-labeled DEVELOPMENT placeholder: it
stores the secret's VALUE in os.environ at write time, so a process restart loses every credential set
since the process started, and nothing is encrypted at rest. `DurableEncryptedCredentialProvider` below
is its production replacement, behind the EXACT SAME abstraction (`CredentialProvider` formalizes what
was previously an implicit, half-written contract - `PostgresStore.set_credential_ref`/
`get_credential_ref` used to hardcode env-var-locator construction directly rather than delegating to
the provider for writes at all; that logic has moved into `EnvCredentialProvider.store()` so both
providers are now symmetric and swappable with zero change to any connector or connector-factory code).

Isolation model: every credential is identified by (merchant_id, ref) - the SAME identity
`credential_references` already used. No separate "channel identifier" column is needed: every existing
connector-factory credential ref name already embeds the channel it belongs to (e.g.
"shopify_webhook_secret", "flipkart_partner_client_id", "meesho_client_id") - a merchant with two
channels has two distinct refs under the SAME merchant_id, already fully isolated by ref-name difference.
Adding a redundant channel column would duplicate information already encoded in `ref`.
"""


class CredentialProvider(Protocol):
    """Formalizes the contract every credential-storage backend must satisfy. `store`/`resolve` were
    already the two operations `PostgresStore` needed; `delete` and `health` are added here because
    Step P0.1 needs revocation and a reality-label distinguishing "this is production-safe storage" from
    "this is not" - see DurableEncryptedCredentialProvider.health() vs EnvCredentialProvider.health()."""

    def store(self, merchant_id: str, ref: str, secret: str) -> str:
        """Persists `secret` and returns an opaque locator - the ONLY thing `credential_references.locator`
        ever stores. The locator must be sufficient, on its own, for a LATER call to resolve()/delete() to
        find this exact credential again - callers never need to know its internal shape."""
        ...

    def resolve(self, locator: str) -> str:
        """Returns the plaintext secret. Must fail closed (raise, never return a guessed/empty value) if
        the locator is unknown, revoked, or cannot be decrypted."""
        ...

    def delete(self, locator: str) -> None:
        """Revokes the credential - resolve() must raise for this locator afterward. Never raises an
        exception that includes the secret value itself."""
        ...

    def health(self) -> dict[str, Any]:
        """A reality label - never mistake one provider's output for another's. Every implementation
        must include at least {"provider": <name>, "durable": bool, "encrypted": bool}."""
        ...


class EnvCredentialProvider:
    """Local development credential boundary - NOT production-safe. Secrets live in the process
    environment only: they do not survive a restart and are never encrypted at rest. Production must use
    DurableEncryptedCredentialProvider instead - see build_production_credential_provider() and
    apps/api/app.py's fail-closed selection logic, which never falls back to this provider silently."""

    def store(self, merchant_id: str, ref: str, secret: str) -> str:
        locator = f"SANOCEA_CRED_{merchant_id.upper()}_{ref.upper()}".replace("-", "_")
        os.environ[locator] = secret
        return locator

    def resolve(self, locator: str) -> str:
        value = os.environ.get(locator)
        if value is None:
            raise KeyError(f"credential locator not available: {locator}")
        return value

    def delete(self, locator: str) -> None:
        os.environ.pop(locator, None)

    def health(self) -> dict[str, Any]:
        return {"provider": "env", "durable": False, "encrypted": False}


class MissingMasterKeyError(RuntimeError):
    """Raised at startup selection time (see build_production_credential_provider), never at request
    time - a production process must refuse to start rather than silently fall back to a non-durable
    provider."""


def load_master_keys_from_env(prefix: str = "SANOCEA_CRED_MASTER_KEY_") -> tuple[dict[str, bytes], str | None]:
    """Reads AES-256 master keys from environment variables shaped `{prefix}V1`, `{prefix}V2`, ... (each
    a base64-encoded 32-byte value) plus `{prefix}CURRENT` naming which version new writes should use.
    The master key itself is NEVER stored in Postgres and NEVER committed to the repository - it is
    supplied externally (an env var here; a real KMS/Vault later - see
    docs/architecture/credential-storage.md for the migration path). Returns ({version: key_bytes},
    current_version) - current_version is None if `{prefix}CURRENT` is unset, letting the caller decide
    whether that's fatal (production) or acceptable (a caller that only needs to decrypt, not encrypt).
    """
    keys: dict[str, bytes] = {}
    for name, value in os.environ.items():
        if not name.startswith(prefix) or name == f"{prefix}CURRENT":
            continue
        version = name[len(prefix):].lower()
        try:
            decoded = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise MissingMasterKeyError(f"master key {name} is not valid base64: {exc}") from exc
        if len(decoded) != 32:
            raise MissingMasterKeyError(f"master key {name} must decode to exactly 32 bytes (AES-256), got {len(decoded)}")
        keys[version] = decoded
    current = os.environ.get(f"{prefix}CURRENT")
    return keys, (current.lower() if current else None)


class DurableEncryptedCredentialProvider:
    """Production credential storage. AES-256-GCM (authenticated encryption - integrity-protected, not
    just confidentiality-protected; a tampered or wrong-key ciphertext fails closed via
    cryptography.exceptions.InvalidTag, never silently returns garbage) via the `cryptography` package
    (pyca/cryptography - a mature, widely-audited library; no custom cryptography is implemented here).
    A fresh random 96-bit nonce is generated per encryption (AESGCM.encrypt's own contract requires a
    never-reused nonce per key; os.urandom(12) makes reuse practically impossible even across a very
    large number of writes).

    Storage is the SAME production Postgres the rest of Sanocea already uses (a new table,
    `encrypted_credentials` - see migrations/0002_credential_encryption.sql) - no new infrastructure
    dependency. The master key is supplied externally (see load_master_keys_from_env) and is never
    itself persisted to Postgres or committed to the repository.

    Key versioning: every stored row records which key version encrypted it (`key_version`). Rotating
    the master key going forward means introducing a new version and pointing NEW writes at it; existing
    rows remain decryptable as long as their OWN key version's key is still supplied. A full
    re-encryption service (migrating every existing row to a new key version) is explicitly deferred -
    the schema carries enough metadata to do that later without another migration.
    """

    def __init__(self, dsn: str, master_keys: dict[str, bytes], current_key_version: str) -> None:
        if current_key_version not in master_keys:
            raise MissingMasterKeyError(f"current key version {current_key_version!r} has no corresponding master key loaded")
        self.dsn = dsn
        self._master_keys = dict(master_keys)
        self._current_key_version = current_key_version

    def _connect(self):
        import psycopg2

        return psycopg2.connect(self.dsn)

    def store(self, merchant_id: str, ref: str, secret: str) -> str:
        key = self._master_keys[self._current_key_version]
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, secret.encode("utf-8"), None)
        credential_id = secrets.token_hex(16)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO encrypted_credentials (id, merchant_id, ref, ciphertext, nonce, key_version, created_at, updated_at)
                VALUES (%(id)s, %(merchant_id)s, %(ref)s, %(ciphertext)s, %(nonce)s, %(key_version)s, now(), now())
                ON CONFLICT (merchant_id, ref) DO UPDATE SET
                  ciphertext = EXCLUDED.ciphertext, nonce = EXCLUDED.nonce, key_version = EXCLUDED.key_version,
                  updated_at = now(), revoked_at = NULL
                RETURNING id
                """,
                {
                    "id": credential_id, "merchant_id": merchant_id, "ref": ref,
                    "ciphertext": ciphertext, "nonce": nonce, "key_version": self._current_key_version,
                },
            )
            row = cur.fetchone()
            conn.commit()
        # The ON CONFLICT path may have kept the ORIGINAL row's id (a real replace/rotate, not a fresh
        # insert) - the locator must reflect whichever id is actually now current, so it is read back
        # from the statement's own RETURNING clause rather than assumed to be `credential_id`.
        return _make_locator(str(row[0]), merchant_id, ref)

    def resolve(self, locator: str) -> str:
        credential_id, merchant_id, ref = _parse_locator(locator)
        with self._connect() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT ciphertext, nonce, key_version, revoked_at FROM encrypted_credentials WHERE id = %s AND merchant_id = %s AND ref = %s",
                (credential_id, merchant_id, ref),
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"credential locator not found: {locator}")
        if row["revoked_at"] is not None:
            raise KeyError(f"credential has been revoked: {locator}")
        key = self._master_keys.get(row["key_version"])
        if key is None:
            raise MissingMasterKeyError(f"no master key loaded for version {row['key_version']!r} required to decrypt this credential")
        try:
            plaintext = AESGCM(key).decrypt(bytes(row["nonce"]), bytes(row["ciphertext"]), None)
        except InvalidTag as exc:
            # Fail closed - never guess, never return partial/garbage plaintext, never include the
            # ciphertext or key material in the raised error.
            raise ValueError("credential decryption failed - wrong key or corrupted ciphertext") from exc
        return plaintext.decode("utf-8")

    def delete(self, locator: str) -> None:
        credential_id, merchant_id, ref = _parse_locator(locator)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE encrypted_credentials SET revoked_at = now() WHERE id = %s AND merchant_id = %s AND ref = %s",
                (credential_id, merchant_id, ref),
            )
            conn.commit()

    def health(self) -> dict[str, Any]:
        return {
            "provider": "encrypted_postgres", "durable": True, "encrypted": True,
            "current_key_version": self._current_key_version, "known_key_versions": sorted(self._master_keys),
        }


def _make_locator(credential_id: str, merchant_id: str, ref: str) -> str:
    # Self-describing rather than a bare id, so resolve()/delete() need no separate lookup table and so
    # a locator string alone can never be replayed against the wrong (merchant_id, ref) - the row lookup
    # itself is scoped by all three fields, not just the id.
    return json.dumps({"id": credential_id, "merchant_id": merchant_id, "ref": ref})


def _parse_locator(locator: str) -> tuple[str, str, str]:
    try:
        parsed = json.loads(locator)
        return parsed["id"], parsed["merchant_id"], parsed["ref"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"malformed credential locator: {locator!r}") from exc


def build_production_credential_provider(dsn: str) -> DurableEncryptedCredentialProvider:
    """The one, explicit, fail-closed entry point production startup must use - see apps/api/app.py.
    Never returns EnvCredentialProvider; raises MissingMasterKeyError immediately (before any request is
    served) if the master key configuration is absent or invalid, rather than deferring the failure to
    the first credential lookup."""
    keys, current = load_master_keys_from_env()
    if not current:
        raise MissingMasterKeyError(
            "SANOCEA_CRED_MASTER_KEY_CURRENT is not set - production credential storage requires an "
            "explicit current key version. Set SANOCEA_CRED_MASTER_KEY_CURRENT=<version> and "
            "SANOCEA_CRED_MASTER_KEY_<VERSION>=<base64 32-byte key>."
        )
    if current not in keys:
        raise MissingMasterKeyError(
            f"SANOCEA_CRED_MASTER_KEY_CURRENT={current!r} but no matching SANOCEA_CRED_MASTER_KEY_{current.upper()} was found."
        )
    return DurableEncryptedCredentialProvider(dsn, keys, current)
