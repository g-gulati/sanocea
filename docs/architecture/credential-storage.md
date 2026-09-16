# Production credential storage — Step P0.1

## What existed before this step

`packages/domain_contract/postgres_store.py::EnvCredentialProvider` — an explicitly-labeled development
placeholder. `PostgresStore.set_credential_ref` wrote the secret directly into `os.environ` at write
time and separately upserted a `credential_references(merchant_id, ref, provider, locator)` row;
`get_credential_ref` looked up that row and called `credential_provider.resolve(locator)`. Two real
gaps: secrets did not survive a process restart (they only ever existed in that one process's
environment), and nothing was encrypted at rest — the read path was provider-abstracted, but the write
path was not (`set_credential_ref` hardcoded env-var construction directly, bypassing the provider
entirely for writes).

## What this step implemented

**`packages/domain_contract/credentials.py`** — new module, the credential-storage boundary:

- **`CredentialProvider`** (Protocol) — formalizes `store(merchant_id, ref, secret) -> locator`,
  `resolve(locator) -> secret`, `delete(locator) -> None`, `health() -> dict`. `EnvCredentialProvider`
  moved here (re-exported from `postgres_store.py` for backward compatibility) and gained `store()`/
  `delete()`/`health()` to match the same shape.
- **`DurableEncryptedCredentialProvider`** — the production implementation. AES-256-GCM (authenticated
  encryption — confidentiality AND integrity, via the `cryptography` package, pyca/cryptography; no
  custom cryptography was written) with a fresh random 96-bit nonce per encryption. Storage is a new
  Postgres table, `encrypted_credentials` — the same production database Sanocea already runs, no new
  infrastructure dependency.
- **`load_master_keys_from_env`** / **`build_production_credential_provider`** — the master key is
  supplied externally via environment variables (`SANOCEA_CRED_MASTER_KEY_CURRENT=<version>`,
  `SANOCEA_CRED_MASTER_KEY_<VERSION>=<base64 32-byte key>`), never stored in Postgres, never committed to
  the repository. `build_production_credential_provider` is the one, explicit, fail-closed entry point:
  it raises `MissingMasterKeyError` immediately if the key configuration is absent or invalid, rather
  than deferring the failure to the first credential lookup.

`PostgresStore.set_credential_ref`/`get_credential_ref` now delegate BOTH the write and read path
through `self.credential_provider` symmetrically (previously only reads were provider-abstracted). A new
`delete_credential_ref` method revokes a credential. **No connector or connector-factory code changed
at all** — every existing `store.get_credential_ref(merchant_id, ref)` call site continues to work
unchanged; only what happens *inside* that call changed.

`apps/api/app.py::_build_store()` — the real (non-in-memory) production path now **always** constructs
`DurableEncryptedCredentialProvider` via `build_production_credential_provider(dsn)`. There is no
configuration flag to opt back into `EnvCredentialProvider` here — a production process either starts
with a valid master key or does not start at all.

## Encryption boundary

- **Algorithm:** AES-256-GCM. A unique 96-bit nonce is generated (`os.urandom(12)`) for every single
  encryption operation — GCM's security guarantee depends on never reusing a nonce under the same key,
  and a fresh random nonce per call makes reuse practically impossible even across a very large number
  of writes.
- **Authentication:** GCM's built-in authentication tag means a tampered ciphertext, or one decrypted
  with the wrong key, raises `cryptography.exceptions.InvalidTag` — caught and re-raised as a plain
  `ValueError` that never includes the ciphertext or key material. This is the "fail closed" behavior:
  decryption either succeeds with the exact original plaintext, or raises — it never returns garbage.
- **Key versioning:** every stored row records `key_version`. Rotating the master key going forward
  means introducing a new version (a new `SANOCEA_CRED_MASTER_KEY_<VERSION>` + updating
  `SANOCEA_CRED_MASTER_KEY_CURRENT`) and letting NEW writes use it; existing rows remain decryptable as
  long as their own key version's key is still supplied to the provider. A bulk re-encryption service
  (migrating every existing row to a new key version) is explicitly deferred — the schema already
  carries enough metadata to build that later without another migration.

## Master-key responsibility

The master key is **the operator's** responsibility, not the application's:
- Generate it once per version: 32 random bytes, base64-encoded (e.g. `python -c "import os,
  base64; print(base64.b64encode(os.urandom(32)).decode())"`).
- Set it as an environment variable on the production host/process — never in a config file committed
  to the repository, never in `merchant config JSON`, never logged.
- Losing the master key means every credential encrypted under it becomes permanently unrecoverable
  (this is the correct, intended behavior of authenticated encryption — there is no backdoor). Back up
  the master key itself through whatever secure channel the operator already trusts (a password manager,
  a sealed physical copy, etc.) — this document deliberately does not prescribe one, since that is an
  operational choice outside this step's scope.

## Startup configuration

| Environment variable | Required for | Behavior if missing/invalid |
|---|---|---|
| `SANOCEA_PG_DSN` | Real (non-in-memory) mode | `RuntimeError` at `_build_store()` (pre-existing behavior, unchanged) |
| `SANOCEA_CRED_MASTER_KEY_CURRENT` | Real mode | `MissingMasterKeyError` at `_build_store()` — the process never starts |
| `SANOCEA_CRED_MASTER_KEY_<VERSION>` (matching `CURRENT`) | Real mode | Same — `MissingMasterKeyError` |
| `SANOCEA_USE_IN_MEMORY_STORE=1` | Unit-test harnesses only | Bypasses all of the above; never valid for a real deployment |

## Backup implications

`encrypted_credentials` is an ordinary table in the same Postgres database everything else lives in —
it is backed up by whatever backup procedure covers the rest of the database (see the P0.5 database-
backup item in `docs/architecture/core-roadmap-after-9q.md`, not yet implemented). **The master key is
NOT in that database and must be backed up separately** — a database backup alone is insufficient to
recover credentials; the master key must survive independently for the backup to be useful.

## Credential rotation

Calling `store.set_credential_ref(merchant_id, ref, new_secret)` again for an existing `(merchant_id,
ref)` is a safe, in-place replacement: the same database row is updated (its `id` is preserved), the
credential is re-encrypted under whatever key version is currently active, and any previously-issued
locator continues to resolve to the NEW value — there is no ambiguous half-rotated state, because the
whole replacement happens in one atomic `INSERT ... ON CONFLICT ... DO UPDATE` statement.

## Credential revocation

`store.delete_credential_ref(merchant_id, ref)` sets `revoked_at` on the row (never a hard delete —
consistent with this codebase's append-only audit philosophy elsewhere). After revocation,
`get_credential_ref` raises `TenantAccessError` for that `(merchant_id, ref)` — the SAME exception a
never-configured credential raises, so callers do not need to distinguish "never set" from "revoked."
Any connector instance already holding a resolved value from before the revocation is unaffected until
its own next credential lookup — this is a disclosed limitation, not a gap: none of Sanocea's connectors
currently re-resolve credentials mid-session, so a revoked credential's practical effect is "no NEW
connector construction/authentication for this ref," not an instant kill switch on in-flight connections.

## Future KMS/Vault migration path

`DurableEncryptedCredentialProvider`'s constructor already separates "where the master key comes from"
(`master_keys: dict[str, bytes]`, currently loaded from environment variables) from "how credentials are
encrypted/stored" (AES-GCM + Postgres). Migrating to a real KMS/Vault later means replacing
`load_master_keys_from_env()` with a call to that service's own key-retrieval API — the encryption logic,
the `encrypted_credentials` schema, and every connector/connector-factory call site remain unchanged.

## What operators must NEVER put into config/logs

- The master key itself, in any form, anywhere in the repository, merchant config JSON, or logs.
- Raw credential values in merchant config JSON — credentials belong in `set_credential_ref`, never in
  `store.set_config(...)`'s config dict, which is stored in plaintext (`merchant_configurations.config`)
  and is not encrypted by this step.
- Raw credential values in log statements, audit records, or exception messages — every connector's
  `connector_health()` method is designed to report only non-secret state (authenticated: bool, key
  version, etc.); do not extend any `connector_health()` implementation to include a token/secret value.
