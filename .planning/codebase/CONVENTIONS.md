---
last_mapped_commit: ee202cf2d03a25f8a2a597e5a2348729f29a2eca
last_mapped_at: 2026-09-30
---
# Coding Conventions

**Analysis Date:** 2026-09-30

## Truth Provenance Standards (Immutable Invariant)

Every metric, signal, report, and visual card produced in this codebase MUST belong to one of four epistemological categories:

1. **`[OBSERVED]` (Direct Observation):**
   - Telemetry directly received from an external authoritative API (e.g. Google Search Console API HTTP response, live HTTP status from crawler, Playwright DOM extraction).
   - Rules:
     - Never fabricate, backfill, or invent historical data points.
     - If an API returns zero rows due to privacy thresholds (e.g. GSC query withholding for queries with <10 impressions), the UI must explicitly state: "Query rows withheld by Google Search Console privacy threshold (0 queries returned)".
     - Never report modeled search volumes as observed clicks or impressions.

2. **`[CALCULATED]` (Deterministic Derivation):**
   - Direct arithmetic transformations of observed values with zero heuristic speculation.
   - Examples: `CTR = (Clicks / Impressions) * 100`, `Position Delta = Current Position - Previous Position`.
   - Rules:
     - Document exact calculation formula and input metrics.
     - When sample size is small (e.g., 28 impressions, 11 clicks), include sample-size disclaimers and do not present small-sample variance as statistical certainty.

3. **`[MODELED]` (Opportunity / Industry Projections):**
   - External market estimations, keyword difficulty models, and third-party benchmark opportunities.
   - Rules:
     - MUST be visually and architecturally segregated from Observed Telemetry.
     - In the UI, tables displaying keyword opportunities must be titled: `"SEO Opportunity Model — Not GSC Observed"` with explicit methodology notes explaining that these are industry search demand models, not live site impressions.

4. **`[REQUIRES_ACCESS]` (Prospect Gated):**
   - Data points for prospect tenants (Waaree Energies, Carzex, etc.) that cannot be observed without client Google Search Console or Analytics credentials.
   - Must be labeled with a quarantine badge and explanation.

## Naming Patterns

**Files:**
- TypeScript/JavaScript source files: `camelCase.ts` or `camelCase.js` (e.g. `gscClient.ts`, `searchSignalsEngine.ts`).
- React Components: `PascalCase.jsx` (e.g. `DashboardView.jsx`, `SeoView.jsx`).
- Python modules: `snake_case.py` (e.g. `domain_contract/models/order.py`).
- Test files: `*.test.ts`, `*.test.js`, or `test_*.py`.

**Functions:**
- Action-oriented verbs: `fetchSearchAnalytics()`, `remediateSchema()`, `calculateSerpTrajectory()`, `deriveSearchSignals()`.
- Boolean checks: `isMenuCommand()`, `isTechnicalRoute()`, `hasSufficientSample()`.

**Variables:**
- Descriptive `camelCase` in TS/JS, `snake_case` in Python.
- Constants in `UPPER_SNAKE_CASE` (e.g. `AWR_OCT_2024_BENCHMARK`, `DEFAULT_OBSERVATION_WINDOW`).

**Types & Interfaces:**
- TypeScript interfaces and types: `PascalCase` (e.g. `SearchSignal`, `AuditFinding`, `SerpTrajectoryRecord`).
- Pydantic models: `PascalCase` inheriting from `BaseModel`.

## Code Style

**Formatting & Language Rules:**
- TypeScript: Target `ESNext` with `NodeNext` module resolution. Explicit return types on exported functions.
- Python: Python 3.11+, strict typing with type annotations, Pydantic v2 schemas for all payload boundaries.
- No dangling promises in async code; always `await` or return promises.

**Linting:**
- Strict compiler options enabled in `packages/seo-stack/tsconfig.json` (`strict: true`, `noImplicitAny: true`).

## Import Organization

**TypeScript/JavaScript Order:**
1. Built-in Node.js modules (`node:fs`, `node:path`, `node:test`, `node:assert`).
2. External npm dependencies (`better-sqlite3`, `cheerio`, `playwright`, `react`).
3. Internal package/workspace imports (`./persistence/sqlitePersistence.js`, `../crawler/engine.js`).

**Python Order:**
1. Standard library (`os`, `sys`, `dataclasses`, `datetime`).
2. Third-party packages (`fastapi`, `pydantic`, `temporalio`).
3. Local application and package modules (`packages.domain_contract`, `packages.policy_engine`).

## Error Handling

**Patterns:**
- **Graceful API Degradation:** When an external API (like GSC) fails or returns 403/429, log structured error and fall back to the most recent cached SQLite snapshot with an explicit `DEGRADED` status indicator.
- **Fail-Safe Remediations:** Remediations must be idempotent and verifiable. An autonomous patch must verify that the target DOM element actually changed to the expected state before writing a success receipt to SQLite WAL.
- **Database Transactions:** SQLite writes must be executed inside explicit transactions (`db.transaction(...)`) to prevent partial or corrupted state in the event of worker restarts.

## Logging

**Framework:**
- Structured logging with JSON format or standard prefixes (`[SEO-WORKER]`, `[GSC-CLIENT]`, `[REMEDIATOR]`).
- All log events include ISO timestamps and tenant IDs.

## Tenant Isolation Invariance

- **Strict Boundary:** The `sanocea` tenant is the only autonomous tenant with real credential access and background worker execution.
- **Prospect Quarantine:** All demo and prospect tenants (Waaree Energies, Carzex, Premium Basket, Ajanta Soya, Golden Bird Jewels) operate in strict read-only or in-memory simulation mode. Their operational stores are deep-frozen and isolated; switching tenants must never leak findings, state, or credentials.

---

*Convention analysis: 2026-09-30*
