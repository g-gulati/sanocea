# Ingested Architectural Decisions

**Analysis Date:** 2026-09-30

## ADR 0001: Python Importable Package Layout
- **Status:** LOCKED
- **Decision:** Python packages use underscores (e.g. `domain_contract`, `policy_engine`, `connector_sdk`) because Python cannot import module names with hyphens.
- **Source:** `docs/adr/0001-python-package-layout.md`

## ADR 0002: Storage Boundary for Phase 0
- **Status:** LOCKED
- **Decision:** Production Sanocea uses PostgreSQL for canonical state, configuration, idempotency, external ID mapping, and audit indexes. Phase 0 implements a tenant-aware repository interface with an in-memory test backend so acceptance proofs are deterministic without requiring local Postgres credentials.
- **Source:** `docs/adr/0002-phase0-storage.md`

## ADR 0003: Phase 0.5 Infrastructure Validation Boundaries
- **Status:** LOCKED
- **Decision:** Implement real backends behind domain contracts: `PostgresStore` behind repository contract, Temporal Python SDK worker, S3/MinIO via boto3, Docling extraction adapter, and deterministic image transform boundaries. In-memory harness preserved for unit tests.
- **Source:** `docs/adr/0003-phase05-infra-validation-boundaries.md`

## ADR 0004: PostgreSQL RLS Decision for Phase 0.5
- **Status:** LOCKED
- **Decision:** Reject PostgreSQL Row Level Security (RLS) for Phase 0.5 because there is a single application database role without per-merchant database sessions. Enforce tenant isolation via mandatory `merchant_id` columns, tenant-scoped unique indexes, repository-level access checks, and adversarial isolation test suites.
- **Source:** `docs/adr/0004-postgres-rls-decision.md`
