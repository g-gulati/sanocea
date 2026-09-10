# ADR 0003: Phase 0.5 infrastructure validation boundaries

Phase 0.5 keeps the Phase 0 contracts intact and adds real implementations
behind them:

- `PostgresStore` behind the domain repository contract
- Temporal Python SDK workflow/worker beside the deterministic harness
- S3-compatible object storage using boto3
- Docling extraction adapter
- deterministic image transform boundary for imgproxy/libvips profiles

The in-memory harness remains for unit tests.

Initial local validation blockers found in this workspace:

- Docker is not installed, so the Compose topology cannot be started here.
- PostgreSQL 17 is installed and running, but no password/DSN is available in
  the environment. Integration tests require `SANOCEA_PG_DSN`.
- No Shopify or Chatwoot credentials are present, so live external tests remain
  credential-gated.

Follow-up disposition:

- Local Postgres was self-provisioned with the installed PostgreSQL binaries.
- Temporal CLI was downloaded as a user-space binary and run locally.
- MinIO was downloaded as a user-space binary and run locally.
- Docker/WSL remain absent, but that no longer blocks Sanocea core
  infrastructure validation.

Remaining component-specific pilots:

- Shopify live SaaS validation requires external development-store credentials.
- Chatwoot full-instance validation is deferred until a container/Ruby runtime is
  available.
- imgproxy runtime validation is a deferred component pilot; the media contract
  remains processor-neutral.
