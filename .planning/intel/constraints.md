# Ingested System Constraints

**Analysis Date:** 2026-09-30

## Epistemological & Evidence Integrity Constraints
1. **Zero Query Fabrication Invariant:** When Google Search Console withholds query rows due to privacy threshold (<10 impressions), SANOCEA must report 0 queries and explicitly inform operators rather than synthesizing or backfilling query terms.
2. **Modeled vs Observed Segregation:** Modeled keyword demand tables must never be visually or logically blended with observed Google Search Console telemetry.
3. **5-Phase Progress Latency:** Search engine indexation latency (Remediated -> Declared -> Discovered -> Evaluated -> Surfaced) must be respected; code remediations must not promise instantaneous SERP rank changes.

## Tenant Isolation Constraints
1. **Single Autonomous Flagship:** Autonomous background mutation is strictly restricted to the `sanocea` tenant.
2. **Prospect Quarantine:** Prospect tenants (Waaree Energies, Carzex, Premium Basket, Ajanta Soya, Golden Bird Jewels) are quarantined to interactive demonstration and detection-only modes.
3. **Database Tenant Isolation:** Enforced via mandatory `merchant_id` columns, tenant-scoped unique constraints, and repository-level access checks (per ADR 0004).
