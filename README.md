# Sanocea Commerce OS Phase 0 / 0.5

This directory contains the Phase 0 foundation and Phase 0.5 real-infrastructure
validation boundary for Sanocea Commerce OS.

It proves:

- tenant-scoped canonical commerce entities
- connector capability contracts
- guarded connector mutation idempotency
- append-only audit events
- external ID mapping
- merchant configuration
- deterministic policy decisions
- Temporal-shaped workflow semantics
- Shopify order webhook narrow slice
- Chatwoot support conversation narrow slice
- supplier ingestion skeleton
- reconciliation divergence handling
- Postgres migration/repository implementation
- Temporal SDK workflow/worker implementation
- S3-compatible object storage implementation
- Docling extraction adapter
- deterministic image processing boundary

Excluded by architecture decision: Medusa, Akeneo, Pimcore, Activepieces, OPA,
flagd, LangGraph, Amazon, voice, billing, Kubernetes.

## Run

From the workspace root:

```bash
python -m pytest sanocea/tests -q
```

Phase 0.5 core infrastructure validation status:

```text
CORE INFRASTRUCTURE: PASS
```

Start local Phase 0.5 infrastructure without Docker:

```powershell
powershell -ExecutionPolicy Bypass -File sanocea/scripts/start_phase05_local.ps1
powershell -ExecutionPolicy Bypass -File sanocea/scripts/run_phase05_integration.ps1
```

Validated locally against PostgreSQL, migrations, durable idempotency, Temporal,
Temporal worker process restart, MinIO/S3-compatible storage, Docling, separate
API process, Shopify webhook HTTP ingestion, Chatwoot webhook HTTP ingestion,
canonical/external mapping, audit persistence, tenant-aware persistence, and
out-of-order/idempotent event behaviour.

Test counts from the validated run:

```text
Unit: 15 passed / 0 failed / 0 skipped
Integration: 6 passed / 0 failed / 0 skipped
E2E: 1 passed / 0 failed / 2 skipped
```

The skipped E2E cases are:

- Shopify live SaaS integration: external credential blocker
- Chatwoot full API instance: component pilot pending

The tests require real infrastructure configuration when not using the script
above:

- `SANOCEA_PG_DSN`
- `SANOCEA_RUN_TEMPORAL_TESTS=1`
- `SANOCEA_S3_ENDPOINT`
- `SANOCEA_S3_ACCESS_KEY`
- `SANOCEA_S3_SECRET_KEY`
- `SANOCEA_S3_BUCKET`
- optional live `SANOCEA_SHOPIFY_ADMIN_TOKEN`
- optional live `SANOCEA_CHATWOOT_API_TOKEN`

Optional API:

```bash
python -m uvicorn sanocea.apps.api.app:app --host 127.0.0.1 --port 8010
```

Docker topology, when Docker is available:

```bash
docker compose -f sanocea/infra/docker/docker-compose.phase05.yml up --build
```
