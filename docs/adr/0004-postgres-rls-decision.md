# ADR 0004: PostgreSQL RLS decision for Phase 0.5

Decision: reject PostgreSQL Row Level Security for Phase 0.5 and enforce tenant
isolation through repository methods plus structural schema constraints.

Reason:

- Sanocea Phase 0.5 has one application database role, not per-merchant database
  roles or request-scoped database sessions.
- Enabling RLS without a robust `SET LOCAL sanocea.merchant_id` discipline would
  create a false sense of isolation.
- The current risk is better controlled by mandatory `merchant_id` columns,
  tenant-scoped unique indexes, repository-level access checks, and adversarial
  tests that try cross-merchant reads/writes.

This decision should be revisited when the API authentication model introduces a
trusted request context that can set transaction-local tenant identity before
every query.

