# SEO/GEO open-source review — 2026-10-01

Scope: five repositories reviewed at source level against `packages/seo-stack`, the bridge, and `/demo.html`
(per the OSS-first rule in `CLAUDE.md`). Decision codes: A reuse, B adapt pattern, C learn only, D n/a, E build own.

| Repository (licence) | Capability | SANOCEA status | Decision |
|---|---|---|---|
| claude-seo (MIT) | Retired Google rich results (FAQ, sitelinks box, HowTo) | **Wrong**: FAQ and sitelinks-box findings claimed CTR loss with invented ₹ figures and auto-injected placeholder FAQ copy. Verified against Google's changelog 2026-10-01 | B → `core/retiredRichResults.ts` |
| claude-seo, geo-seo-claude (MIT) | AI crawler taxonomy (search vs training vs user-triggered) | Partial: bots listed, purpose conflated; multi-`User-agent` groups mis-parsed; no wildcard inheritance | B → `core/aiCrawlerPolicy.ts` (RFC 9309) |
| claude-seo, ai-seo (MIT) | Crawlers read server-delivered HTML | Thin-content rule existed (on-demand only, undercounted words) | B → `core/publishedPageAudit.ts`, AI Content Auditor now runs on the existing daily job |
| RankMeFast (AGPL-3.0, ideas only) | Confirm a drop before alerting | Tier-1 raised P0 on one failed request | C → confirm-before-P0 in tier-1 |
| geo-seo-claude (MIT) | 0–100 citability score | n/a | **Rejected** (E not needed): weights/thresholds have no validated source; would be an invented metric |
| claude-seo seo-drift (MIT) | Page-element baseline/drift | Tier-1 diffs only sitemap count (in memory) | **Deferred**: needs a baseline table; own change |
| firecrawl-workflows (ISC) | seo-audit / competitive-intel / qa / dashboard-reporting | Prompt-level recipes needing a Firecrawl key; SANOCEA already has crawler, sitemap diff, reports | D |
| marketingskills (MIT) | seo-audit, ai-seo, schema, site-architecture, competitor-profiling | Prompt frameworks; nothing executable SANOCEA lacks | D / C |
| RankMeFast | Deterministic next-action ordering, "still detected after fixed" | SANOCEA has priority engine + apply→verify loop | ALREADY HAVE |
| all | Falsifiable recs / before-after evidence | `beforeEvidence/afterEvidence/verificationResult` exist | ALREADY HAVE |

## Needs an external provider (recorded, not faked)
Keyword volume, exact SERP ranks, AI-assistant citation rates, AEO/AI-Overview observation, backlinks/authority beyond
the Common Crawl graph. These stay `NOT AVAILABLE` with their dependency text.

## Licensing
No third-party code was copied. RankMeFast (AGPL-3.0) was read for product ideas only. MIT/ISC repos prompted
independent implementations; attribution is noted in file headers.

---

# Google / Bing / analytics / Postiz / publishing — audit of what already exists (2026-10-01)

## GOOGLE INTEGRATION STATUS
1. Credentials found: **YES**.
2. Type: **service account** (JWT assertion signed with `node:crypto`). An OAuth 2.0 web flow (auth URL, code exchange, refresh) is also implemented in the same class but not used for our own property.
3. Loading path: `packages/seo-stack/src/worker/seoMonitoringWorker.ts` reads `GSC_SERVICE_ACCOUNT_PATH` (file, mode 0600, outside the repo) or `GSC_SERVICE_ACCOUNT_KEY` (inline/base64); both set via `infra/systemd/sanocea-seo-worker.service` (`GSC_PROPERTY_URL` too). No secret values are recorded here.
4. Existing GSC client: **YES** — `search-intel/gscClient.ts`, auth in `search-intel/gscAuth.ts`.
5. Methods: `GscAuthManager.getAccessToken / verifyProperty (sites.get) / generateAuthUrl / exchangeCodeForTokens`; `GscClient.querySearchAnalytics` (searchAnalytics.query) and `captureSnapshot` (query, page, device, country, searchAppearance dimensions).
6. Property: `sc-domain:sanocea.com`. Live check today: token obtained, `permissionLevel = siteFullUser`, `sites.list` returns that one property, `sitemaps.list` returns `https://www.sanocea.com/sitemap.xml` (last downloaded 2026-09-29, 0 errors, 0 warnings).
7. Data retrieved today: clicks, impressions, CTR, position by query (0 rows: Google privacy threshold), page (1 row), device (2 rows), country, searchAppearance (0 rows returned by Google).
8. Worker/job: `SeoMonitoringWorker.runTier2` (snapshot) and scheduler job `gsc-position` (`runGscPositionTracking`), both in `worker/seoMonitoringWorker.ts`.
9. Cadence: tier-2 every 24 h; `gsc-position` every 24 h (persisted scheduler).
10. Persistence: SQLite `gsc_snapshots`, `gsc_queries`, `gsc_pages`, `gsc_position_observations` (`persistence/seoDb.ts`).
11. Tests: `gscAnalyticsEngine`, `gscPositionTracker`, `searchSignalsEngine`, `rankingIndexationIntelligence` — all within the 200 passing seo-stack tests.
12. Genuinely missing: (a) `urlInspection.index.inspect` call (indexation code accepts inspection data as input but nothing fetches it; the existing read-only scope is sufficient); (b) `sitemaps.list` fetch/persist (works live, not coded); (c) sitemap *submit* needs the write scope `webmasters`, not granted (read-only today, deliberately); (d) a persisted connection-state record (health already reports `gsc.live/authMethod/propertyUrl`). **OAuth is NOT a prerequisite for our own property.** It becomes relevant only for onboarding customer-owned properties.
Opportunity engine: already reads the persisted GSC snapshot (`pageRows`/`queryRows`); with today's volume (28 impressions) neither GSC rule fires — that is correct, not a wiring gap.

## Matrix
| Area | Status | Where |
|---|---|---|
| GSC credentials, auth, client, snapshots, schedule, persistence | ALREADY HAVE | above |
| GSC → opportunity engine | ALREADY HAVE (this session) | `opportunities/opportunityEngine.ts` |
| URL Inspection fetch, sitemaps.list persist | MISSING AND VALUABLE (no new credential) | extend `gscClient.ts` |
| Sitemap submit | EXTERNAL: write scope + owner approval | — |
| Bing connector | EXISTS, unverified live, no key; JSON/HTTP surface is **current** (see Bing finding) | `search-intel/bingWebmaster.ts` |
| Bing keyword / URL info / OAuth | MISSING | — |
| Bing AI Performance | NOT AVAILABLE via API (dashboard/CSV only at last reports) | — |
| Analytics (GA4) | NOT PRESENT (only the site gtag tag) | — |
| Postiz | ALREADY HAVE | `packages/content_engine/postiz/` (container on 127.0.0.1:4007) |
| Content engine | ALREADY HAVE | `packages/content_engine/` |
| Website publishing connector | NOT PRESENT | — |

## Secret hygiene finding
`gmail_credentials.json` and `gmail_outreach_token.pickle` sit untracked in the repo root and are **not git-ignored**. Add them to `.gitignore` (and move them outside the repo) before anyone runs `git add -A`.

## Decisions recorded (2026-10-01)
- **No priority labels.** The opportunity engine has no priority/severity field and none may be shown (HIGH/MEDIUM/INFO were editorial in the preview and are removed). Status (Needs review / Approved / In progress / Completed / Rejected / Monitoring) is a separate concept. Listing order is deterministic and is NOT a priority: first-detected time, then affected address, then type (`OpportunityEngine.list`). A future priority model must be explicit, testable, explainable, persisted in the engine and shown consistently in the UI (inputs such as evidence confidence, measurable business impact, scope, technical severity, reversibility, urgency, customer-defined importance).
- **Google gaps, step 1 (read-only, no new credential/scope):** `search-intel/gscProperty.ts` — persisted connection state (`search_connections`), sitemap list (`gsc_sitemaps`), URL Inspection (`gsc_url_inspections`), run inside the existing daily `gsc-position` job; worker `GET /google-search-state`; bridge view `gsc_property`. **Sitemap submission is NOT implemented** (write scope + explicit authorization, separate change).
- Planned order: Opportunity UI (preview, no priority labels) -> Opportunity-to-Content-Brief handoff via the Python content engine -> SEO QA (Draft -> QA -> Approval) -> generic website publisher -> Postiz derivatives -> measurement/learning.

## Opportunity -> approval -> brief -> draft (backend slice, 2026-10-01)
- **Reuse:** the existing content engine's `ClaimsGate`, `DeduplicationEngine.compute_similarity`, `QACheckItem/QAResult`, tenant ids and JSON-record convention. New code lives in `packages/content_engine/seo/` (models, source, brief, qa, draft, workflow, store). The existing engine is a *social* engine (template copy from a curated topic reservoir, no LLM, no web-page/brief model); nothing there was duplicated.
- **Lifecycle:** `APPROVED` is now a persisted state: `AWAITING_APPROVAL -> APPROVED -> IN_PROGRESS`. Only an actor labelled `human:` can enter APPROVED; work can no longer start without it. The audit trail records who approved; `linkResult` records the brief/draft reference without touching status.
- **Eligibility rule (TS and Python, parity-tested):** content workflow only for types `QUERY_PAGE_MATCH_GAP` / `HIGH_IMPRESSIONS_LOW_CTR` with a content action (`CREATE_NEW_PAGE`, `CREATE_SUPPORTING_CONTENT`, `UPDATE_EXISTING_PAGE`, `IMPROVE_TITLE_META`). Every technical type is refused whatever its action.
- **Control plane:** worker `POST /opportunities/transition` and `/opportunities/link-result` require `SEO_WORKER_CONTROL_TOKEN` (fail closed). The token authorises the *process*; "who is the human" is still a caller-supplied label. **An operator-authenticated approval endpoint is a prerequisite before approvals are exposed in any UI** (demo-session keys are public and must never approve).
- **Drafts:** deterministic facts-only writer (no LLM configured); a draft is `DRAFT_READY` only if QA passes: evidence grounding (verbatim, cited approved facts), claims gate, no unsourced numbers, duplication, cannibalization, audience, internal links, title, meta, heading structure. No score of any kind. Stops at DRAFT.
- **Storage:** `SANOCEA_SEO_CONTENT_DIR` (default `/opt/sanocea/shared/seo_content`), per-tenant JSON, atomic writes; deliberately not under `website/`.

## Autonomy policy (requirement change: Claude/SANOCEA is the web operator) — NOT deployed
Replaces "only a human can approve" with a policy-governed authorisation event. Human approval and human override remain.
- **Tenant modes** (`tenant_autonomy`): AUTONOMY_DISABLED, RECOMMEND_ONLY (default when unconfigured), AUTONOMOUS_SEO (Class A), AUTONOMOUS_CONTENT (A+B), AUTONOMOUS_DISTRIBUTION (adds distribution). Only a human can change a mode. Class C is refused in every mode.
- **Classes** (`autonomyPolicy.ts`, mirrored and parity-tested in `seo/policy.py`): A = title/meta, internal links, schema, distribution; B = new page, supporting content, existing-page update; C = deletion, DNS, domain ownership, credentials, access/security, payment, destructive DB, infrastructure, out-of-scope, `FIX_TECHNICAL_SEO` (changes site delivery), and anything unknown (fail closed).
- **Decision point 1 — authorisation** (worker `authorize`): gates = awaiting authorisation, evidence-backed, valid decision, no page overlap, tenant mode permits the class. Allowed => persisted `seo_approvals` row: `approval_actor_type` (HUMAN | AUTONOMOUS_AGENT, DB-constrained), actor, policy `sanocea-autonomy-policy@1.0.0`, reason, approved_at, approved_action, class, target, evidence/decision/gate snapshots; opportunity AWAITING_APPROVAL -> APPROVED. Denied => audited `POLICY_DENIED`, status unchanged. Idempotent. No label can produce an approval: `transition(..., APPROVED)` accepts only `human:` actors (recorded HUMAN); autonomous approval exists only through `authorize()`.
- **Decision point 2 — publish eligibility** (`evaluate_publish_eligibility`, evaluate-only): evidence, decision, standing approval with consistent actor type, overlap, grounding, ClaimsGate, SEO QA, duplicate (near-duplicate draft AND no existing publication), tenant mode, publish-target authorisation, rollback information, audit event written before anything could publish. Class A keeps the safety gates; Class C is never eligible. Any failed gate => BLOCKED with reasons; decision persisted.
- **Rollback info** (`build_rollback`): change id, content hash, kind; a new page reverses by unpublishing, an update requires the previous version reference or the gate fails. **Audit trail**: append-only per tenant (`audit.jsonl`, idempotent event ids). **Publication ledger**: write-once per target (for the future publisher).
- **Human override**: `human_override` (human actor only) rejects work; the original autonomous approval stays on record; eligibility then blocks.
- **Not built (by instruction):** the website publisher. Eligibility is evaluated and recorded; nothing is published. **Not changed:** ClaimsGate, grounding, the writer's refusal to invent. **UI:** not changed; "Handled automatically / Queued / Published / Monitoring" wording and removing any approve action need a preview first.
