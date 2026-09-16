# Core roadmap after Step 9Q.6 — what's between here and a real, safely-operated first merchant

No external research was performed for this document — every finding below is from direct inspection of
the current repository. No implementation was performed as a result of this document either.

**The question this answers:** given everything already implemented through Step 9Q.6, what actually
prevents Sanocea from becoming a sellable production system for the channels whose contracts we already
possess (Shopify, WooCommerce, and — pending only credentials — Flipkart and Amazon India)?

**The short answer:** almost nothing in the *business logic*. Tenant isolation, approval workflows,
idempotency/recovery, consequential-mutation safety, reconciliation, audit/evidence, and RBAC are all
real, tested, and already proven extensively across this session's work. What's actually missing is a
short list of **operational/infrastructure** items — none of them large, several of them already
half-built and simply never wired into the production path.

## Classification key

- **P0** — required before first paying merchant.
- **P1** — required shortly after first merchant.
- **P2** — useful scale/quality improvement.
- **DEFER** — not justified yet.
- **EXTERNAL** — channel/credential dependency, not Sanocea engineering.

## The 35-area inspection

| # | Area | Current state (verified) | Classification |
|---|---|---|---|
| 1 | Merchant onboarding | Real, validated (`MerchantOnboardingService.onboard()`), reachable via `POST /admin/merchants`. Manpreet can onboard a merchant today through this route. | Sufficient — not a blocker |
| 2 | Credential/config onboarding | Same service sets config + credentials + channels + supplier mappings in one validated call. The onboarding FLOW is fine; the credential STORAGE backend is the real gap — see #7. | Sufficient (flow); see #7 (storage) |
| 3 | Tenant isolation | `TenantAccessError` enforced throughout every store/connector operation, proven repeatedly across every step this session. | Sufficient |
| 4 | RBAC/operator permissions | Real bearer-token API keys with `operator`/`service` roles; `require_operator` verifies the authenticated key's merchant_id matches the URL path merchant_id — a caller cannot access another merchant by changing the URL. | Sufficient for one/few-operator use |
| 5 | Approval workflows | Real, extensively tested (`Approval` model, refund/cancellation/PO approve/reject flows) across this entire session. | Sufficient |
| 6 | PolicyEngine — GAP-003 | See dedicated section below. | P1/P2 — not a merchant-safety blocker |
| 7 | Secrets management | **Real gap.** `EnvCredentialProvider` (`packages/domain_contract/postgres_store.py:173`) stores secrets in `os.environ` at write time — its own docstring calls it "Local Phase 0.5... Production should swap this provider for KMS/Vault." Secrets do not survive a process restart and are not encrypted at rest. | **P0** |
| 8 | Production deployment | No Dockerfile, no CI/CD, no deployment script found anywhere in the repository. | **P0** |
| 9 | Linux/VPS readiness | No Linux-specific code gap found; the one disclosed platform quirk (WooCommerce's own docstring: slow HTTP round-trips under Docker-on-Windows) is explicitly a *Windows dev-environment* artifact, expected to disappear on real Linux — this expectation has never been verified against a real target VPS. | **P0** (verification, not new code) |
| 10 | DB migrations/backups/recovery | One migration file (`0001_phase05.sql`), applied via `.migrate()` — fine for a single current schema version. **No backup script, no restore procedure, anywhere.** | **P0** (backups); P1 (migration versioning tooling) |
| 11 | Object storage durability | `S3ObjectStorage` exists and is already S3-protocol-compatible — durability is a matter of pointing it at a real durable bucket, not a code gap. | EXTERNAL (config choice) |
| 12 | Temporal/runtime durability | See dedicated finding below — **less severe than it first appears.** | P1 (tracked, not blocking) |
| 13 | Observability | Standard logging + the audit ledger (business-event observability) + `/health` (checks Postgres/Temporal/Storage connectivity). No structured metrics/APM. | P1 |
| 14 | Alerting | None. At single/few-merchant scale, periodic manual checks of the exception queue (#15) are a reasonable substitute. | P1 |
| 15 | Exception queues | Real, reachable: `GET /merchants/{merchant_id}/exceptions`. Manpreet can query this directly today. | Sufficient for manual operation |
| 16 | Operational dashboard | Does not exist (no frontend anywhere in the repo). The exceptions/approvals APIs are directly usable via any HTTP client in the meantime. | P1/P2 |
| 17 | Audit/evidence | Real, extensive, proven throughout every step this session. | Sufficient |
| 18 | Idempotency/recovery | Real, extensive (`IdempotencyService`, Step 9's full mutation-recovery framework). | Sufficient |
| 19 | Consequential mutation safety | Real, extensive (Step 9: CONFIRMED_SUCCEEDED/CONFIRMED_NOT_APPLIED/STILL_UNKNOWN discipline, proven for refund and cancellation, and reused by the Flipkart/Amazon connectors' retry logic). | Sufficient |
| 20 | Reconciliation | The logic exists and is real (`workers/reconciliation_worker.py`, plus every connector's own `reconcile()` method) — but **it has never been scheduled to actually run in production.** Its own docstring says exactly this: "meant to be invoked periodically (a systemd timer / cron...); wiring an actual Temporal workflow around it is tracked debt, not built here." | **P0** (scheduling only — the code is done) |
| 21 | Merchant reporting | No report/dashboard endpoints exist. Manpreet can query the API/DB directly for now. | DEFER |
| 22 | Support/Chatwoot integration | Real (`ChatwootConnector`, `SupportWorkflowService`), tested throughout. | Sufficient |
| 23 | WhatsApp/Meta integration | Explicitly out of scope throughout every prior step's mandate. | DEFER |
| 24 | Billing/subscription enforcement | Does not exist. Per this step's own explicit guidance, first merchants can be invoiced manually — building SaaS billing now would be commercial-convenience work mistaken for production safety. | DEFER |
| 25 | SKU-capacity enforcement | Does not exist; no evidence yet that it's needed at pilot scale. | DEFER |
| 26 | Usage metering | Does not exist. | DEFER |
| 27 | Merchant data export/deletion | Does not exist. Not legally blocking for a single, direct commercial relationship at pilot stage (typically covered by contract terms initially) — worth a cheap legal check, not an engineering task, before scaling past a handful of merchants. | DEFER |
| 28 | Retention | Undefined. Same reasoning as #27. | DEFER |
| 29 | Security hardening | No rate limiting on the API; TLS termination is a deployment-level concern, not yet exercised. At pilot scale with a small number of known, trusted merchants (not public signup), the realistic risk is lower than a public SaaS, but a bearer-token API with no rate limit exposed on the open internet is still a real gap. | **P0** (minimum: TLS-only exposure + basic auth rate-limiting) |
| 30 | Production connector certification | Shopify: certified (Dev Store PASS). WooCommerce: real-local proven. Flipkart/Amazon India: implemented, pending real credentials only. | EXTERNAL (credentials), otherwise done |
| 31 | Deployment/rollback | Same gap as #8 — no deployment procedure exists to roll back from yet. | **P0** (folds into #8) |
| 32 | Disaster recovery | Same as #10 — no backup exists to recover from yet. | **P0** (folds into #10) |
| 33 | Health checks | Real, already good (`/health` checks Postgres/Temporal/Storage connectivity). | Sufficient |
| 34 | Runbooks | None written. Given Manpreet's direct familiarity with the system, not blocking for a first controlled pilot, but cheap and worth writing once the P0 items land. | P1 |
| 35 | Support/operator intervention path | The exceptions + approvals APIs already constitute a real intervention path, usable via any HTTP client. A short written guide tying this together (#34) is the only remaining piece. | Sufficient (API); P1 (guide) |

## The Temporal/runtime durability finding, precisely

Direct inspection of `workers/workflow/engine.py` and `order_orchestrator.py` clarifies something
important: **the mutation logic that actually matters (inventory reservation, order state) runs
synchronously, inside the same call, against the durable Postgres-backed canonical entities — it does
not depend on the in-memory "fake" workflow engine surviving a restart.** `OrderOrchestrator._advance()`
calls `PostOrderOperationsService.reserve_inventory_for_order()` directly and immediately, every time,
regardless of whether the underlying `FakeTemporalEngine` call was a fresh workflow start or a signal to
an existing one. The `WorkflowExecution` bookkeeping ROW itself is durably persisted
(`self.store.put(execution)` — real Postgres, not memory). The only genuinely ephemeral piece is the
engine's own internal `_workflows: dict[str, OrderWorkflow]` — used for in-process signal dispatch within
a single process lifetime, explicitly documented (by the `OrderOrchestrator`'s own docstring) as
orchestration-progress bookkeeping, never business truth. **Conclusion: this is real, disclosed, tracked
debt (a genuine real-Temporal integration would add timer/long-running-workflow robustness this fake
engine doesn't have), but it does not put a first merchant's actual data at risk, and does not block
launch.** P1.

## PolicyEngine — GAP-003, special attention

**Exact unresolved deficiency:** `PolicyEngine.decide()` (`packages/policy_engine/engine.py`) is
confirmed dead code — re-verified directly this step: `.decide()` is called nowhere in `packages/`,
`apps/`, or any connector, including the three new marketplace connectors added since Step 8's original
finding. Four independent decision sites (`evaluate_cancellation`, `evaluate_return`, `_refund_decision`,
`ProcurementService.evaluate_po_authority`) each reimplement their own policy logic inline, and — as of
Step 8's audit — have already functionally diverged from `decide()` and from each other (e.g.
`_refund_decision` has strictly more invariants than `decide()`'s refund branch; `evaluate_po_authority`
is an entirely different multi-factor architecture).

**Which merchant operations it affects:** cancellation, return, refund, and procurement/PO-authority
decisions — every approval-gated consequential decision path in the system.

**Does it block first production merchant: No.** Each of the four sites is independently, extensively
tested and has already been hardened by real bug fixes found and closed during Steps 7A/7B (the
DENY-collapses-into-REQUIRE_APPROVAL bug class, found and fixed identically and independently in TWO
different sites — direct, concrete evidence of the maintainability cost of the duplication, but not a
currently-open correctness bug).

**Smallest correct repair (not performed, per this step's instruction):** either (a) fold each site's
already-correct, already-tested logic into `PolicyEngine.decide()` so it stops being dead code, then
switch each call site to delegate to it — a moderate, mechanical refactor, not a redesign; or (b) accept
the duplication as tracked debt and add a lint/test rule that fails if a fifth independent reimplementation
appears without at least checking `decide()` first.

**Tests required before any repair:** golden-master tests capturing each of the four sites' CURRENT
exact behavior (including their already-fixed DENY-handling) before any centralization, so a refactor
can be verified behavior-preserving rather than trusted by inspection; plus a new test proving the
DENY-collapse bug class cannot recur a third time regardless of which site adds policy logic next.

**Verdict: P1/P2, not P0.** Worth doing before a *third* recurrence of the DENY-bug class, not before a
first merchant.

## What Manpreet can safely operate manually at first (no UI needed)

Every one of these already has a real, tenant-safe, authenticated API endpoint or a direct, well-tested
service call — no polished UI is required for Manpreet to operate them through a controlled admin path:

- Merchant onboarding (config, credentials, channels, supplier mappings) — `POST /admin/merchants`.
- Approving/rejecting refunds, cancellations, purchase orders — existing approve/reject endpoints.
- Reviewing and resolving exceptions — `GET /merchants/{id}/exceptions`.
- Reconciliation and recovery sweeps — `workers/reconciliation_worker.py`'s `run_once()`, invokable
  directly by Manpreet (or, once P0.3 lands, running on its own schedule).
- Checking system health — `GET /health`.

## What does NOT need to exist before first merchant

A merchant-facing self-service UI, a merchant-facing reporting dashboard, SaaS billing/metering/plan
enforcement, WhatsApp integration, data export/deletion self-service, and formal runbooks are all
genuinely deferrable — none of them make a first, Manpreet-supervised pilot merchant unsafe to operate
without them, and building any of them now would be commercial-convenience or scale-readiness work
mistaken for production safety.

## Ordered P0 execution sequence

**P0.1 — Durable, encrypted secrets provider.** *Exists today:* `EnvCredentialProvider`, an explicitly-
labeled placeholder with a designed swap point (`credential_provider` constructor argument on
`PostgresStore`). *Gap:* secrets don't survive a restart and aren't encrypted at rest. *Smallest
production-grade fix:* implement a provider satisfying the exact same `resolve(locator) -> str`
interface, backed by an encrypted column in Postgres (application-level encryption with a single
master key from environment/KMS) — no new external dependency required. *Blocks first merchant:* yes —
losing credentials on every restart is not viable. *Dependencies:* none. *Verification:* a credential
set before a process restart is still resolvable after it, and the raw secret is never present in
plaintext in the database.

**P0.2 — Documented, repeatable deployment procedure.** *Exists today:* nothing — no Dockerfile, no CI,
no deploy script. *Smallest production-grade fix:* a documented, scripted deploy (systemd unit or
supervisor config + a venv + a deploy script) — does not require Docker/Kubernetes for a first pilot.
*Blocks first merchant:* yes — there is currently no repeatable way to get the application running
durably on a server. *Dependencies:* none. *Verification:* a fresh checkout can be deployed to a target
VPS and restarted cleanly by following the documented steps alone.

**P0.3 — Real Linux VPS smoke test.** *Exists today:* the application, developed and tested on Windows.
*Gap:* never run on the actual target OS. *Smallest production-grade fix:* deploy once (using P0.2) to a
real Linux VPS and run the existing test suite plus one real end-to-end workflow smoke test against it.
*Blocks first merchant:* yes — this is the cheapest possible risk-reduction step before real usage.
*Dependencies:* P0.2. *Verification:* full test suite green on the real target OS; the WooCommerce
Docker-on-Windows slowness disclosed in Step 0-era docs does not recur.

**P0.4 — Scheduled reconciliation.** *Exists today:* the reconciliation worker's logic is fully written
and tested (`workers/reconciliation_worker.py`). *Gap:* it has never been scheduled to actually run.
*Smallest production-grade fix:* a cron entry or systemd timer invoking `run_once()` per merchant on a
fixed interval (e.g. every 15-30 minutes). *Blocks first merchant:* yes — without this, the entire
Step-9 mutation-recovery safety net this session built exists in code but never actually executes in
production. *Dependencies:* P0.2 (needs a running deployment to schedule against). *Verification:* a
deliberately-injected `mutation_uncertain` refund/cancellation is autonomously resolved within one
scheduling interval without manual invocation.

**P0.5 — Database backups.** *Exists today:* nothing. *Smallest production-grade fix:* a scheduled
`pg_dump` (cron/systemd timer) writing to the already-available `S3ObjectStorage`, plus a documented,
once-tested restore procedure. *Blocks first merchant:* yes — losing the database means losing a real
merchant's entire operational history with no recovery path. *Dependencies:* P0.2 (deployment target),
object storage pointed at a real durable bucket (see area #11). *Verification:* a backup taken today can
be restored into a fresh Postgres instance and the application starts cleanly against it.

**P0.6 — Minimum security hardening.** *Exists today:* a real bearer-token auth system with no rate
limit; TLS termination not yet exercised. *Smallest production-grade fix:* deploy behind TLS-only
(reverse proxy, e.g. Caddy/nginx with a real certificate) and add a basic rate limit on the
authentication path. *Blocks first merchant:* yes — an unencrypted, unrate-limited bearer-token API on
the open internet is not an acceptable exposure for real merchant data or credentials. *Dependencies:*
P0.2. *Verification:* the API is unreachable over plain HTTP from outside the deployment host, and a
credential-guessing burst against the auth path is throttled rather than processed at full rate.

## What can truthfully be demonstrated to Medconic now

Using only what already exists, clearly labeled by what it actually is:

- **Real, certified:** the full canonical order/cancellation/refund/return/exception/reconciliation
  workflow, demonstrated end to end on the Shopify Dev Store certification (real external platform) and
  the WooCommerce real-local integration.
- **Real, implemented, credentials pending:** the same canonical workflow operating a real Flipkart or
  Amazon India seller account — contract-tested against Flipkart's/Amazon's own documented schemas, not
  yet exercised against a real live account.
- **Real capability, simulated external platform:** the same canonical workflow operating against the
  in-memory simulated Shopify/logistics/payments connectors, useful for showing the FULL breadth of
  exception handling, cancellation/refund recovery (Step 9's mutation-uncertainty discipline), and
  reconciliation behavior without needing live external systems — must always be labeled as simulated,
  never presented as live.
- **Not demonstrable, and must not be implied:** any Blinkit/Zepto/Instamart/quick-commerce vendor
  operation — none has a legitimately obtainable technical contract yet (Step 9Q.6). Nothing about
  Sanocea's own readiness should be inferred from this — it is an external access/documentation gap, not
  a Sanocea engineering gap, and should be presented to Medconic exactly that way if quick commerce comes
  up.

No Medconic-specific demo was built — this is a description of what already exists, not new work.

## Recommended next implementation step

**P0.1 — the durable, encrypted secrets provider.** It's the cheapest of the six P0 items (a single new
class matching an already-designed interface, no external infrastructure dependency), it's a genuine
correctness/safety issue right now (not merely a nice-to-have), and every other P0 item (deployment,
smoke test, scheduling, backups, hardening) either depends on a real deployment existing first or is
independent of it — starting with the credential-storage fix touches the least amount of surrounding
infrastructure while closing the most clearly unacceptable gap.
