# ADR 0002: Storage boundary for Phase 0

Production Sanocea should use Postgres for canonical state, configuration,
idempotency, external ID mapping, and audit indexes.

Phase 0 implements a tenant-aware repository interface with an in-memory test
backend. This keeps the acceptance proof deterministic without requiring a local
Postgres service or credentials. Connector, policy, workflow, and API code depend
on the repository boundary rather than the in-memory implementation.

