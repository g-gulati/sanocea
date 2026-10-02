---
gsd_state_version: "1.0"
status: needs_decision
last_updated: "2026-10-02"
state_head: f80ea8a
note: Rewritten from git history on 2026-10-02. The old "Phase 7 ready to plan" state was stale.
---

# Project State

See `.planning/ROADMAP.md` for phases and `CLAUDE.md` for standing rules.

## Current position

- Last commit: `f80ea8a` (2026-10-01) — Bing never-crawled sentinel date shown as no date.
- Phases 1–6 and the 2026-09-30 → 10-01 work (zero-cost SEO stack, single `/demo.html` UI, autonomous
  SEO execution loop and lifecycle UI) are committed.
- Phase 7 as written (paid SERP provider) conflicts with the zero-cost-only SEO rule. It is not the
  next action until that is decided.
- Large uncommitted working tree (demo sessions, domain/approvals/notifications, website, CLAUDE.md).
  See ROADMAP "In progress".

## Not recorded here (verify live, don't trust this file)

- Test counts: the old figure (125) is from 2026-09-30 and has not been re-run.
- Deployment state: whether `sanocea-api` and `sanocea-seo-worker` run the latest commit.
- GSC telemetry numbers: read them from `GET /demo/seo/overview`; do not copy them into docs.

## Invariants

1. Truth provenance: observed, calculated and modeled values stay segregated and labelled.
2. No fabricated data: a value the worker does not supply renders NOT AVAILABLE with its reason.
3. Tenant isolation: autonomous mutations only on the `sanocea` tenant; prospect tenants stay quarantined.
4. One canonical UI: `/demo.html` (see `CLAUDE.md`).

## Next action

1. Decide Phase 7: drop, redefine on free sources, or ADR for a paid provider.
2. Review the uncommitted tree and commit or discard.
3. Demo session leasing Slice 2; fix the channel-id collision bug.
