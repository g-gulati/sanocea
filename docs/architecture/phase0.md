# Sanocea Commerce OS Phase 0

Phase 0 proves the architectural spine:

- tenant-scoped canonical domain contract
- connector capability model
- guarded mutation idempotency
- append-only audit ledger
- external ID mapping
- merchant configuration
- deterministic policy decisions
- Temporal-shaped workflow skeleton
- Shopify and Chatwoot narrow vertical slices
- supplier ingestion and reconciliation primitives

Excluded by decision: Medusa, Akeneo, Pimcore, Activepieces, OPA, flagd,
LangGraph, Amazon, voice, billing, Kubernetes.

## Phase 0.5 additions

Phase 0.5 adds production-shaped implementations behind the same contracts:

- Postgres migrations and repository implementation
- environment-backed credential reference provider
- Temporal Python SDK workflow and worker
- S3-compatible object storage
- Docling extraction adapter
- deterministic product media transform boundary
- integration/E2E test stratification
- Docker Compose topology for local validation

## Phase 0.5 Core Infrastructure Validation

Status: PASS.

Validated against real local infrastructure:

- PostgreSQL
- migrations
- durable database idempotency
- concurrent duplicate suppression
- real Temporal service
- real Temporal worker/process boundary
- worker recovery/runtime interaction
- MinIO / S3-compatible object storage
- real Docling execution
- separate API process
- Shopify webhook HTTP ingestion
- Chatwoot webhook HTTP ingestion
- persistent canonical mapping
- external ID mapping
- audit persistence
- tenant-aware persistence
- out-of-order/idempotent event behaviour

Qualifications:

- Shopify Admin API live validation is pending external credentials.
- Chatwoot full-instance integration is a deferred component pilot.
- imgproxy runtime validation is a deferred component pilot.
- PostgreSQL RLS is deliberately rejected/deferred per ADR 0004.
- No production deployment or security certification is implied.

The Sanocea architectural spine has now been validated against real
persistent/durable local infrastructure and is ready for the first end-to-end
commercial capability slice.
