---
last_mapped_commit: ee202cf2d03a25f8a2a597e5a2348729f29a2eca
last_mapped_at: 2026-09-30
---
# Testing Patterns

**Analysis Date:** 2026-09-30

## Test Framework

**Runner:**
- Node.js Native Test Runner (`node:test`) for TypeScript/JavaScript in `@sanocea/seo-stack` and `website/`. Zero third-party testing dependencies, ultra-fast parallel test execution.
- Pytest for Python backend packages (`apps/api/`, `packages/*`).

**Assertion Library:**
- `node:assert/strict` for Node.js suites.
- Built-in `assert` and pytest assertions for Python suites.

**Run Commands:**

```bash

# Run all Node.js tests across SEO Stack and Website (125 tests total)

npm --prefix packages/seo-stack test    # 73 passing tests
npm --prefix website test               # 52 passing tests

# Combined single command

cd packages/seo-stack && npm test && cd ../../website && npm test

# Run Python backend tests

PYTHONPATH=. .venv/bin/pytest tests/unit -q
```

## Test File Organization

**Location:**
- `@sanocea/seo-stack`: Tests located in `packages/seo-stack/tests/`, compiled to `packages/seo-stack/dist/tests/` and run against compiled JavaScript.
- `website`: Tests located in `website/tests/`.
- Python backend: Tests located in `tests/unit/`, `tests/integration/`, `tests/e2e/`.

**Naming:**
- Node.js test files: `*.test.js` or `*.test.ts`.
- Python test files: `test_*.py`.

**Structure:**

```
packages/seo-stack/tests/
├── liveGscAudit.test.ts             # Live GSC API integration and credentials verification
├── searchSignalsEngine.test.ts      # Truth provenance, signal derivations, and benchmark tests
├── serpTracker.test.ts              # SERP trajectory math, SQLite WAL persistence, truth rules
├── technicalAuditor.test.ts         # Technical SEO checks (meta, canonicals, robots, schema)
├── ecommerceAuditor.test.ts         # Product schema, price, availability, SKU checks
├── geoAuditor.test.ts               # Generative Engine Optimization & AI bot directives
├── autonomousRemediator.test.ts     # Closed-loop technical remediations & verification receipts
└── parameterClassifier.test.ts     # URL parameter bloat and faceted navigation classifiers

website/tests/
├── store.test.js                    # Operational store deep isolation, state transitions, reset
├── narrativeHierarchy.test.js       # Viewport structure, scorecard rendering, live sentinels
├── tenantIsolation.test.js          # Multi-tenant isolation (Waaree, Carzex, Sanocea)
├── regression.test.js               # 18 critical regression assertions protecting truth integrity
├── whatsappFlow.test.js             # WhatsApp interactive console & menu parser tests
└── evidenceIntegrity.test.js        # GSC observed vs Modeled opportunity separation rules
```

## Test Structure

**Suite Organization (Node.js native test runner):**

```typescript
import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

describe('SearchSignalsEngine — Evidence Integrity', () => {
  test('SIG-GSC-CTR-01 marks CTR differential without navigational claims when query rows absent', () => {
    const rawGsc = {
      clicks: 11,
      impressions: 28,
      ctr: 0.3929,
      position: 2.43,
      queryRows: [] // Privacy withholding
    };

    const engine = new SearchSignalsEngine();
    const signals = engine.deriveSignals(rawGsc);
    const ctrSignal = signals.find(s => s.id === 'SIG-GSC-CTR-01');

    assert.equal(ctrSignal.provenance, 'CALCULATED');
    assert.match(ctrSignal.inference, /observed CTR is materially above/);
    assert.doesNotMatch(ctrSignal.inference, /confirms navigational|brand intent dominance/);
  });
});
```

## Mocking & Isolation

**Live Verification vs Offline Fixtures:**
- The test suite supports two explicit execution modes:
  1. **Deterministic Offline Fixtures:** Standard CI/unit tests run against fixed HTML/JSON snapshots (`dist/src/cli.js fixture`), requiring no network or external API access.
  2. **Live Service Account Verification:** Dedicated test (`packages/seo-stack/tests/liveGscAudit.test.ts`) verifies real live credentials at `/opt/sanocea/repo/config/credentials/google-search-console.json` against `sc-domain:sanocea.com`.

**What NOT to Mock in Critical Paths:**
- SQLite database interactions in persistence tests: use real in-memory or temporary file-based SQLite databases to verify actual WAL transactions, constraints, and schemas.
- Invariant state transformations in `store.js`: run real state mutations to verify deep-freeze isolation.

## Fixtures and Factories

**Test Data:**
- Synthetic HTML fixtures containing intentional SEO defects (missing canonical, malformed JSON-LD, missing alt tags, duplicate headings) are maintained in `packages/seo-stack/tests/fixtures/`.
- Pristine company state fixtures for all 5 demo companies are maintained in `website/src/data/tenantSeoRegistry.js`.

## Coverage & Guarantees

**Regression Suite Coverage (website/tests/regression.test.js):**
1. SANOCEA Dashboard contains no SEO case-study or audit component.
2. SEO view renders the SANOCEA case study when `companyId=sanocea`.
3. SANOCEA SEO monitoring data never appears for prospect tenants.
4. Switching Dashboard <-> SEO does not retain stale SEO state.
5. Switching tenants cannot leak SEO findings between tenants.
6. Semantic Channel Icon Mapping: Production Web !== Shopify and AI Crawlers !== Amazon.
7. Rendered SANOCEA Dashboard has 0 SEO remediation cards.
8. Channel count consistency: SANOCEA displays 3/3 channels, not 4/4.
9. GSC clicks are never mislabeled as orders on SANOCEA.
10. Prominent Before -> Current -> Delta Scorecard exists on SANOCEA Dashboard.
11. Prospect tenants retain commerce operations without autonomous monitoring.
12. Autonomous Activity Feed contains only verified real operations from authentic Sentinels.
13. Activity Feed Isolation: Prospect tenants NEVER expose autonomous operations feed.
14. Narrative Hierarchy & Viewport Structure: Primary live sentinel and scorecard render first.
15. GSC Telemetry vs Modeled Opportunity Layer Separation in DashboardView.
16. Zero Query Rows & Modeled Opportunity Provenance in Case Study View & Dataset.
17. SERP Rank Movement & Velocity Tracker (SQLite WAL Ledger) & Truth Rules.
18. Four Current Growth Constraints Identified From Available Evidence.

---

*Testing analysis: 2026-09-30*
