---
last_mapped_commit: ee202cf2d03a25f8a2a597e5a2348729f29a2eca
last_mapped_at: 2026-09-30
---
# Codebase Concerns

**Analysis Date:** 2026-09-30

## Tech Debt & Architectural Gaps

**1. GSC Query Privacy Withholding vs Keyword Tracking:**
- Issue: Google Search Console API automatically withholds query strings and keyword-level data when query volume is below privacy thresholds (<10 impressions). Because SANOCEA is in early incubation (28 impressions, 11 clicks in the 28-day window), GSC returns 0 query rows.
- Files: `packages/seo-stack/src/worker/gscClient.ts`, `packages/seo-stack/src/signals/searchSignalsEngine.ts`, `website/src/components/DashboardView.jsx`
- Impact: Cannot attribute clicks or impressions to specific commercial keywords using GSC alone.
- Fix approach: Implement external SERP provider adapters (e.g. DataForSEO, SerpAPI) to query live Google SERP positions for target keywords independently of GSC query rows.

**2. Multi-Channel Commerce Data Drift & Reconciliation:**
- Issue: Inventory and pricing synchronization across multiple external platforms (Shopify, Amazon, Flipkart, Tally ERP) experiences network jitter and webhook delays.
- Files: `packages/channel_ops/`, `packages/policy_engine/`, `packages/exceptions/`
- Impact: Out-of-sync inventory can cause overselling or cancelled orders.
- Fix approach: Scheduled periodic background reconciliation loops running under Temporal workflows to detect and resolve drift against the canonical PostgresStore.

**3. External Authority & Backlink Data Gap:**
- Issue: The internal crawler audits internal linking, canonicals, and DOM structure, but cannot discover external referring domains or backlinks pointing to `sanocea.com` from other sites.
- Files: `packages/seo-stack/src/auditors/`
- Impact: Domain authority, external backlink strength, and competitive link-building comparisons cannot be calculated purely from on-page audits.
- Fix approach: Integrate a commercial backlink API (DataForSEO Backlinks API, OpenLinkProfiler, or Ahrefs/Semrush API) to pull authoritative external backlink metrics into SQLite.

## Operational & Performance Constraints

**1. Search Engine Crawl Budget vs Autonomous Velocity:**
- Issue: Even when autonomous technical remediations are applied immediately to HTML/JSON-LD, search engine bots do not index changes instantaneously.
- Details: Google deprecated the XML sitemap ping endpoint in 2023. While IndexNow provides instant notification to Bing and Yandex, Google relies solely on periodic sitemap polling and GSC Inspection API quotas (2,000 requests/day per property).
- Files: `packages/seo-stack/src/remediation/autonomousRemediator.ts`
- Impact: Expected ranking or traffic movement lags code remediation by days or weeks. The UI must explicitly present the 5-phase progression (Remediated -> Declared -> Discovered -> Evaluated -> Surfaced) so operators understand this latency.

**2. Single Autonomous Tenant Policy Boundary:**
- Issue: Autonomous remediation and real credential execution must strictly remain isolated to the `sanocea` tenant.
- Files: `website/src/data/store.js`, `website/src/data/tenantSeoRegistry.js`
- Impact: If an operator switches to a prospect tenant (e.g. Waaree Energies), background workers must never attempt to mutate external customer assets.
- Current mitigation: Hard architectural boundary in `store.js` and `autonomousRemediator.ts` blocking execution if tenant is not `sanocea`.

## Security Considerations

**1. Service Account Credential Protection:**
- Risk: Leaking Google Search Console service account JSON would compromise Google Search Console property control.
- Files: `/opt/sanocea/repo/config/credentials/google-search-console.json`
- Current mitigation: Excluded in `.gitignore`, filesystem permissions set to `0600`, worker reads path from `SANOCEA_GSC_CREDENTIALS_PATH`.
- Recommendations: Maintain automated pre-commit secret scanners and ensure docs never quote private key fields.

## Test Coverage & Maintenance

**1. Python Monorepo Import Path Discipline:**
- Issue: Python packages in `packages/*` use root-level imports (`from packages.content_engine...`). Running pytest without `PYTHONPATH=.` causes `ModuleNotFoundError: No module named 'packages'`.
- Files: `pyproject.toml`, `.pyroot`
- Fix approach: Update `pyproject.toml` `pythonpath` setting or run test commands with `PYTHONPATH=.`.

---

*Concerns audit: 2026-09-30*
