# Production configuration contract — Step P0.2

No real values appear in this document. Every variable below is either set in the systemd
`EnvironmentFile` (`/opt/sanocea/shared/env/sanocea.env`, see `production-deployment.md`) or, for
merchant/channel credentials, stored through `DurableEncryptedCredentialProvider` (P0.1) — **never** as
a deployment environment variable. This split is deliberate and load-bearing: infrastructure/bootstrap
secrets (how to reach Postgres, the credential-encryption master key) must exist before the application
can even start; merchant credentials (Shopify webhook secrets, Flipkart/Amazon/Meesho keys) are
per-tenant business data that P0.1 already solved durable, encrypted, tenant-isolated storage for — they
must not be duplicated into a second, unencrypted storage location.

## Classification key

- **REQUIRED** — the process fails to start (or fails closed at first use) without this.
- **OPTIONAL** — has a safe default or safely-absent behavior.
- **DEVELOPMENT ONLY** — must never be set in production; exists purely for local/test harnesses.
- **CHANNEL-SPECIFIC** — only needed if a specific certification/live-credential harness script is run; the running application itself never reads these (see below).
- **EXTERNAL SECRET** — the value's source of truth is an external provider, not Sanocea; Sanocea only needs a way to reach it.

## Variables

| Variable | Classification | Purpose | Notes |
|---|---|---|---|
| `SANOCEA_PG_DSN` | REQUIRED | Postgres connection string | `PostgresStore.migrate()` and every store operation depend on this; `_build_store()` raises `RuntimeError` if absent |
| `SANOCEA_CRED_MASTER_KEY_CURRENT` | REQUIRED, EXTERNAL SECRET | Names which key version new credential writes use | `_build_store()` raises `MissingMasterKeyError` if absent — the process does not start |
| `SANOCEA_CRED_MASTER_KEY_<VERSION>` (matching `CURRENT`, e.g. `SANOCEA_CRED_MASTER_KEY_V1`) | REQUIRED, EXTERNAL SECRET | The base64-encoded 32-byte AES-256 master key for that version | Generated once by the operator (see `production-deployment.md`), never committed, never logged. Additional older versions may also be set (comma-free, one var per version) to keep decrypting rows encrypted under them. |
| `SANOCEA_S3_ENDPOINT` | OPTIONAL | S3-compatible endpoint URL | Omit for real AWS S3 (boto3's own default resolution applies); set for a self-hosted S3-compatible provider |
| `SANOCEA_S3_ACCESS_KEY` | REQUIRED (if object storage is used), EXTERNAL SECRET | Object storage access key | Whichever S3-compatible provider is chosen (Part H) — provider selection is an external/config decision, not fixed by this document |
| `SANOCEA_S3_SECRET_KEY` | REQUIRED (if object storage is used), EXTERNAL SECRET | Object storage secret key | Same as above |
| `SANOCEA_S3_BUCKET` | REQUIRED (if object storage is used) | Bucket/container name | `/health`'s object-storage check is skipped entirely if this is unset — see `production-deployment.md`'s health-verification section for what that means |
| `SANOCEA_TEMPORAL_TARGET` | OPTIONAL | Real Temporal server address (`host:port`) | **Deliberately left unset in this topology** — see Part I discussion in `production-deployment.md`. No business workflow currently depends on it; setting it only affects `/health`'s optional connectivity probe. |
| `SANOCEA_PG_REUSE_CONNECTION` | OPTIONAL | Reuses one Postgres connection across calls instead of opening one per operation | Existing `PostgresStore` behavior, unrelated to this step; leave unset unless a specific performance need is identified |
| `SANOCEA_USE_IN_MEMORY_STORE` | DEVELOPMENT ONLY | Bypasses Postgres/credential-provider entirely for unit-test harnesses | **Must never be set in production** — it silently discards durability and encryption. `_build_store()` treats its presence as authoritative regardless of any other variable. |
| `SANOCEA_SHOPIFY_LIVE_SHOP_DOMAIN`, `SANOCEA_SHOPIFY_LIVE_CLIENT_ID`, `SANOCEA_SHOPIFY_LIVE_CLIENT_SECRET`, `SANOCEA_SHOPIFY_LIVE_API_VERSION`, `SANOCEA_SHOPIFY_LIVE_WEBHOOK_DELIVERY_BASE_URL` | CHANNEL-SPECIFIC | Shopify Dev-Store certification harness only | Read only by `scripts/run_shopify_dev_store_certification.py`, which then POSTs them into a merchant's own config/credentials via the API — **the running application never reads these directly**. Do not set these on a production API host; they belong only in whatever environment runs the one-time certification script. |
| `SANOCEA_BIGCOMMERCE_STORE_HASH`, `SANOCEA_BIGCOMMERCE_ACCESS_TOKEN`, `SANOCEA_BIGCOMMERCE_WEBHOOK_VERIFICATION_SECRET`, `SANOCEA_BIGCOMMERCE_WEBHOOK_DELIVERY_BASE_URL` | CHANNEL-SPECIFIC | BigCommerce sandbox certification harness only | Same treatment as the Shopify Dev-Store variables above |

## What is explicitly NOT a deployment environment variable

Every merchant/channel credential Sanocea actually operates with in production — Shopify webhook
secrets, WooCommerce consumer key/secret, Flipkart partner client ID/secret + per-merchant refresh
token, Amazon LWA client ID/secret + per-merchant refresh token, Meesho client ID/security/supplier
identifier — is set via `store.set_credential_ref(merchant_id, ref, secret)` (through the running
application's own onboarding path, `POST /admin/merchants`), landing in `encrypted_credentials`
(P0.1), never in this host's environment file. **If you find yourself about to add a merchant's own API
key to `sanocea.env`, stop — that credential belongs in the encrypted store, reached through onboarding,
not deployment configuration.**

## Logging configuration, allowed origins/hosts, service ports

- **Logging:** no structured-logging framework is configured yet (a disclosed P1 gap — see
  `docs/architecture/core-roadmap-after-9q.md`). Default Python/uvicorn logging goes to stdout, captured
  by systemd/journald (`journalctl -u sanocea-api`) — no separate log-file configuration is required or
  provided by this step.
- **Allowed origins/hosts:** no CORS/allowed-host restriction is currently configured in
  `apps/api/app.py`. This is a real, disclosed gap for a public-facing deployment; mitigated for a first
  controlled pilot by the deployment topology itself (reverse-proxy/firewall exposure, not yet built —
  tracked as P0.6, explicitly out of scope for P0.2) rather than by application-level configuration.
- **Service port:** `8010` (matching the existing `infra/docker/sanocea.Dockerfile`'s convention, kept
  consistent across every deployment mechanism this repository has ever documented). Configurable in the
  systemd unit's `ExecStart` line if a different port is genuinely needed; not exposed as its own
  environment variable in this step, since nothing else in the repository reads a port from the
  environment.
- **Bind address:** `127.0.0.1` (loopback only) — **P0.3 finding, real Ubuntu host**: the target VPS's
  firewall was found inactive (bare iptables ACCEPT-all), so `--host 0.0.0.0` would expose the API
  directly to the public Internet with no protection at all. Public exposure is P0.6's job (reverse
  proxy/TLS/rate limiting); until that exists, every deployment must bind loopback-only.
