# SANOCEA.com technical-SEO intervention (September 2026): HISTORICAL evidence

**Status: HISTORICAL · STATIC. This is not live telemetry and is not validated by the SEO worker.**

These figures used to appear in the live `/demo.html` SEO views as "SEO health scorecards". They were removed on
2026-10-01 (decision: neither had a sufficiently authoritative live source to be shown as an operational KPI, and the two
told different, unreconciled stories). They are preserved here as engineering case-study material only.

Do not re-add them to the live SEO command view. The live view shows only what the SEO worker persists
(`GET /demo/seo/overview`). If a health KPI is wanted later, it must be computed from a persisted source.

## 1. Dashboard scorecard: "SEO Health: Baseline → Intervention → Current → Delta"

| Field | Value shown |
|---|---|
| Baseline SEO health | 15.0% |
| Current SEO health | 20.1% |
| Delta | +5.1 pts (+34.0% relative) |
| Findings | 7 detected, 2 fixed, 5 in observation window (14-28 days) |
| Latest verification receipt | `VRCP-ACT-SANOCEA-AUTO-001` (492px title <= 561px boundary) |

## 2. SEO tab scorecard: "Measured Impact"

Headline pill: **Technical Compliance 15% → 100% (+85 pts)**

| Parameter | Baseline | After intervention | Delta |
|---|---|---|---|
| Google desktop SERP title width | 624px (truncated in SERP) | 492px (conformant <= 561px) | -132px (-21.1%) |
| Semantic SSR H1 heading | 0 `<h1>` tags | 1 semantic topic heading | +1 (+100%) |
| Meta description budget | 219 characters (truncated on mobile) | 148 characters (<= 160) | -71 chars (-32.4%) |
| Transport security headers | Missing HSTS | HSTS & CSP active | n/a |
| AI discovery context (`/llms.txt`) | 404 Not Found | 200 OK (clean AI markdown) | +100% crawl readiness |

## Known problems with presenting these as live KPIs

* The two scorecards disagree: "15.0% → 20.1%" versus "15% → 100%". No definition of "SEO health" or "technical
  compliance" was ever recorded that reconciles them.
* Neither figure is produced by the SEO worker or any persisted job. The worker reports `remediationCount: 0`.
* The per-parameter before/after values are one-time measurements; nothing re-measures them.

The detailed before/after diffs, the lifecycle narrative and the causality-governance notes remain in the SEO tab
(tabs 2, 4 and 5), each labelled historical.
