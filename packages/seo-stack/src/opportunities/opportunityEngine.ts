/**
 * SANOCEA SEO Stack — Opportunity engine (evidence -> opportunity -> decision)
 *
 * Turns observations SANOCEA already persists into structured, deduplicated, tenant-scoped Opportunities with a
 * lifecycle and an audit trail. It reads existing evidence only (the AI Content Auditor's published-page
 * observations, the latest persisted GSC snapshot); it never calls a provider and never changes a customer site.
 *
 * Truth rules
 * - An opportunity states what was observed and what it recommends. It never states a consequence it did not measure
 *   ("Google cannot read this" is NOT claimed; only "the server-delivered HTML has N words").
 * - No expected traffic, volume or ranking is ever attached. `objective` names what would be measured, not a forecast.
 * - Thresholds are explicit constants copied into each opportunity's evidence, so a number is never unexplained.
 * - Dedupe key = tenant + type + target. Re-detection updates evidence; it does not create a second row.
 * - A COMPLETED/LEARNED/REJECTED opportunity that is observed again is reopened with an audit event
 *   (idea: RankMeFast's "still detected after being marked fixed"; independent implementation, AGPL code not used),
 *   except REJECTED, which stays rejected: a human decision is not overridden by a detector.
 */

import { randomUUID } from 'node:crypto';
import { buildLifecycle, Lifecycle } from './lifecycle.js';
import { Expectation, ActionPlan, Diagnosis, Fact, collectRedirectFamilyFacts, Ga4LandingObs, diagnoseRedirectFamily, selectAction, verifyOutcome, Verification } from './diagnosis.js';
import { AUTONOMOUS_ACTOR, modeAllows, AuthorizationDecision, AutonomyMode, DEFAULT_MODE, POLICY_REF, classifyAction, evaluateAuthorization, isAutonomyMode } from './autonomyPolicy.js';
import { SeoDatabase } from '../persistence/seoDb.js';
import { GscPropertyService, InspectionRecord, SitemapRecord } from '../search-intel/gscProperty.js';
import { PublishedPageObservation, THIN_STATIC_WORD_THRESHOLD } from '../core/publishedPageAudit.js';

export const OPPORTUNITY_STATUSES = [
  'DISCOVERED', 'QUALIFIED', 'RESEARCHING', 'ACTIONABLE', 'AWAITING_APPROVAL', 'APPROVED',
  'IN_PROGRESS', 'COMPLETED', 'MEASURING', 'LEARNED', 'REJECTED'
] as const;
export type OpportunityStatus = typeof OPPORTUNITY_STATUSES[number];

export type OpportunityType =
  | 'SERVER_RENDERED_CONTENT_GAP' | 'MISSING_STATIC_H1'
  | 'SITEMAP_URL_REDIRECTS' | 'GOOGLE_INDEX_STATUS_ISSUE' | 'SITEMAP_REPORTED_ISSUES' | 'HIGH_IMPRESSIONS_LOW_CTR' | 'QUERY_PAGE_MATCH_GAP';

export type DecisionAction =
  | 'UPDATE_EXISTING_PAGE' | 'CREATE_SEO_PAGE' | 'CREATE_SUPPORTING_CONTENT' | 'UPDATE_TITLE_META'
  | 'ADD_INTERNAL_LINK' | 'UPDATE_SCHEMA' | 'FIX_SITEMAP_ENTRY' | 'CHANGE_CANONICAL' | 'CHANGE_INDEXABILITY' | 'CHANGE_REDIRECT' | 'CHANGE_SERVER_RENDERING'
  | 'DISTRIBUTE_EXISTING_CONTENT' | 'PUBLISH_SOCIAL_DERIVATIVE' | 'OTHER_EXTERNAL_CHANNEL_PUBLICATION' | 'INVESTIGATE' | 'NO_ACTION';

/** Allowed lifecycle moves. REJECTED is terminal; COMPLETED may be reopened only by re-detection (see engine). */
const TRANSITIONS: Record<OpportunityStatus, OpportunityStatus[]> = {
  DISCOVERED: ['QUALIFIED', 'REJECTED'],
  QUALIFIED: ['RESEARCHING', 'ACTIONABLE', 'REJECTED'],
  RESEARCHING: ['ACTIONABLE', 'REJECTED'],
  ACTIONABLE: ['AWAITING_APPROVAL', 'REJECTED'],
  AWAITING_APPROVAL: ['APPROVED', 'REJECTED'],
  APPROVED: ['IN_PROGRESS', 'REJECTED'],
  IN_PROGRESS: ['COMPLETED', 'REJECTED'],
  COMPLETED: ['MEASURING'],
  MEASURING: ['LEARNED'],
  LEARNED: [],
  REJECTED: []
};

/**
 * Content workflow eligibility (documented rule). An opportunity may enter the content-brief workflow only when BOTH:
 *  - its recommended action is a content action, and
 *  - its type is one whose subject is page content or search wording, never a delivery/indexing/sitemap observation.
 * Technical opportunities (redirects, missing static H1, server-rendered content, Google index status, sitemap issues)
 * are never eligible, whatever action they carry.
 */
export const CONTENT_ACTIONS: ReadonlySet<DecisionAction> = new Set<DecisionAction>(['CREATE_SEO_PAGE', 'CREATE_SUPPORTING_CONTENT', 'UPDATE_EXISTING_PAGE', 'UPDATE_TITLE_META']);
export const CONTENT_OPPORTUNITY_TYPES: ReadonlySet<OpportunityType> = new Set<OpportunityType>(['HIGH_IMPRESSIONS_LOW_CTR', 'QUERY_PAGE_MATCH_GAP']);
export function contentEligibility(type: OpportunityType, action: DecisionAction): { eligible: boolean; reason: string } {
  if (!CONTENT_OPPORTUNITY_TYPES.has(type)) return { eligible: false, reason: 'Technical opportunity: handled as a technical fix, never as content.' };
  if (!CONTENT_ACTIONS.has(action)) return { eligible: false, reason: `Recommended action ${action} is not a content action.` };
  return { eligible: true, reason: 'Search-wording or page-content opportunity with a content action.' };
}

export interface Decision {
  action: DecisionAction;
  rationale: string;
  /** What was checked before choosing; "create" is never chosen without a documented overlap check. */
  checks: string[];
  requiresApproval: true;
}

export interface Opportunity {
  opportunityId: string;
  tenantId: string;
  type: OpportunityType;
  target: string;
  status: OpportunityStatus;
  confidence: 'OBSERVED' | 'CALCULATED' | 'INFERRED';
  source: string; // provenance label of the evidence
  reason: string; // plain English, observation only
  plainEnglish: string;
  evidence: Record<string, unknown>;
  recommendedAction: DecisionAction;
  decision: Decision;
  objective: string;
  detectedAt: string;
  lastSeenAt: string;
  updatedAt: string;
  resultingAction: string | null;
  resultingMeasurement: string | null;
  contentEligible: boolean;
  contentEligibilityReason: string;
  /** Who approved it, from the audit trail (null until a human approves). */
  approval: ApprovalRecord | null;
  diagnosis: Diagnosis | null;
  actionPlan: ActionPlan | null;
  /** Customer-facing Found -> Concluded -> Selected -> Policy -> Executed -> Verified view, derived from the fields above and the audit trail. */
  lifecycle?: Lifecycle;
}

/** Persisted authorisation record. actorType distinguishes HUMAN from AUTONOMOUS_AGENT and is never inferred from free text. */
export interface ApprovalRecord { by: string; at: string; actorType: 'HUMAN' | 'AUTONOMOUS_AGENT'; policy: string; reason: string; actionClass: string; approvedAction: string }

export interface Candidate {
  type: OpportunityType; target: string; confidence: Opportunity['confidence']; source: string;
  reason: string; plainEnglish: string; evidence: Record<string, unknown>; objective: string;
  decision: Decision;
  diagnosis?: Diagnosis; actionPlan?: ActionPlan;
}

// ── Thresholds (copied into evidence so no number is unexplained) ────────────
export const HIGH_IMPRESSIONS_MIN = 100;
export const LOW_CTR_MAX = 0.02;
export const QUERY_MIN_IMPRESSIONS = 50;
export const QUERY_MATCH_MIN_OVERLAP = 0.5;

const STOP = new Set(['the', 'a', 'an', 'and', 'or', 'of', 'for', 'to', 'in', 'on', 'with', 'how', 'what', 'is', 'are', 'best', 'near', 'me']);
export function tokens(text: string): Set<string> {
  return new Set(text.toLowerCase().split(/[^a-z0-9]+/).filter(t => t && !STOP.has(t)).map(t => t.replace(/s$/, '')));
}
/** Share of the query's tokens found in the page's own words (URL slug, title, h1). */
export function queryOverlap(query: string, page: Pick<PublishedPageObservation, 'url' | 'title' | 'h1Text'>): number {
  const q = tokens(query);
  if (q.size === 0) return 0;
  const p = tokens(`${new URL(page.url).pathname} ${page.title} ${page.h1Text}`);
  let hit = 0;
  for (const t of q) if (p.has(t)) hit++;
  return hit / q.size;
}

export interface DetectionInput {
  pages: PublishedPageObservation[];
  pagesObservedAt?: string;
  pagesSource?: string;
  gscPages: Array<{ page: string; clicks: number; impressions: number; ctr: number; position: number }>;
  gscQueries: Array<{ query: string; clicks: number; impressions: number; ctr: number; position: number }>;
  gscCapturedAt?: string;
  inspections?: InspectionRecord[];
  sitemaps?: SitemapRecord[];
  ga4Landings?: Ga4LandingObs[];
  /** stripped-slash page address -> address the owner stated is public */
  ownerIntents?: Record<string, string>;
}

const CRAWL_SOURCE = '[OBSERVED: LIVE PAGE FETCH]';
const GSC_SOURCE = '[OBSERVED: PERSISTED GSC SNAPSHOT]';

export function detectOpportunities(input: DetectionInput): Candidate[] {
  const out: Candidate[] = [];
  const checkedAt = input.pagesObservedAt ?? null;
  const crawlSource = input.pagesSource ?? CRAWL_SOURCE;

  for (const p of input.pages) {
    if (p.status !== 200) continue;
    if (p.staticWords < THIN_STATIC_WORD_THRESHOLD) {
      out.push({
        type: 'SERVER_RENDERED_CONTENT_GAP', target: p.url, confidence: 'OBSERVED', source: crawlSource,
        reason: `The HTML this server sends contains ${p.staticWords} readable words outside navigation, header and footer (${p.bodyWords ?? 'unknown'} words of body text in total). Whether Google renders this page's JavaScript was not measured.`,
        plainEnglish: p.bodyWords > 0
          ? `Requested without running JavaScript, this page sends only a short shell (${p.bodyWords} words in total, such as a heading and links). Anything else the page shows is added by JavaScript after it loads.`
          : 'Requested without running JavaScript, this page sends no text at all. Anything the page shows is added by JavaScript after it loads.',
        evidence: { url: p.url, staticWords: p.staticWords, bodyWords: p.bodyWords ?? null, threshold: THIN_STATIC_WORD_THRESHOLD, method: 'HTTP GET, no JavaScript', observedAt: checkedAt, h1InStaticHtml: p.h1Count },
        objective: 'Re-fetch without JavaScript after the change and compare readable words; then watch indexing and impressions for this URL in Search Console, if connected.',
        decision: { action: 'CHANGE_SERVER_RENDERING', requiresApproval: true,
          rationale: 'The text exists only after JavaScript runs. The fix is how the page is delivered (server-side or static rendering), not new content.',
          checks: ['Observed readable words in server-delivered HTML', 'Existing page: yes (URL fetched with HTTP 200)'] }
      });
    }
    if (p.h1Count === 0) {
      out.push({
        type: 'MISSING_STATIC_H1', target: p.url, confidence: 'OBSERVED', source: crawlSource,
        reason: 'The HTML this server sends has no <h1>. An <h1> may be added after JavaScript runs; that was not measured.',
        plainEnglish: 'The main heading of this page is not in the HTML the server sends.',
        evidence: { url: p.url, h1Count: p.h1Count, method: 'HTTP GET, no JavaScript', observedAt: checkedAt },
        objective: 'Re-fetch without JavaScript and confirm one <h1> is present.',
        decision: { action: 'CHANGE_SERVER_RENDERING', requiresApproval: true,
          rationale: 'A heading is a page-delivery matter; no new page is needed.', checks: ['Observed <h1> count in server-delivered HTML'] }
      });
    }
  }

  // Redirecting sitemap URL: the detector supplies FACTS only. The action is derived downstream (diagnose -> selectAction).
  for (const p of input.pages) {
    if (!(p.redirected && p.finalUrl && p.finalUrl !== p.url)) continue;
    const facts = collectRedirectFamilyFacts(p as any, input.pages as any, (input.inspections ?? []).map(i => ({ url: i.url, googleCanonical: i.googleCanonical })), crawlSource, input.ga4Landings, input.ownerIntents?.[p.url.replace(/#.*$/, '').replace(/\/+$/, '')] ?? null);
    out.push({
      type: 'SITEMAP_URL_REDIRECTS', target: p.url, confidence: 'OBSERVED', source: crawlSource,
      reason: `${p.url} (listed in the sitemap) redirects to ${p.finalUrl}.`,
      plainEnglish: 'A web address listed in the sitemap sends visitors on to a different address.',
      evidence: { listedUrl: p.url, finalUrl: p.finalUrl, destinationCanonical: p.canonical ?? null, method: 'HTTP GET following redirects, canonical read from the delivered HTML', observedAt: checkedAt, facts },
      objective: 'The signals about this page (sitemap, redirect, canonical, links, Google) agree on one address.',
      decision: { action: 'INVESTIGATE', requiresApproval: true, rationale: 'pending diagnosis', checks: [] }
    });
  }

  const GSC_API = '[OBSERVED: GOOGLE SEARCH CONSOLE API]';
  for (const i of input.inspections ?? []) {
    if (!i.verdict || i.verdict === 'PASS') continue;
    out.push({
      type: 'GOOGLE_INDEX_STATUS_ISSUE', target: i.url, confidence: 'OBSERVED', source: GSC_API,
      reason: `Google's URL Inspection reports "${i.coverageState ?? 'no coverage state'}" (verdict ${i.verdict}) for this URL. SANOCEA has not determined the cause.`,
      plainEnglish: `Google's own report for this page says: ${i.coverageState ?? 'no status given'}.`,
      evidence: { url: i.url, verdict: i.verdict, coverageState: i.coverageState, indexingState: i.indexingState, robotsTxtState: i.robotsTxtState, pageFetchState: i.pageFetchState, lastCrawlTime: i.lastCrawlTime, googleCanonical: i.googleCanonical, userCanonical: i.userCanonical, inspectedAt: i.inspectedAt },
      objective: 'Inspect the URL again after any change and confirm Google reports a passing verdict.',
      decision: { action: 'INVESTIGATE', requiresApproval: true,
        rationale: 'Google states the current index status; the cause is not known from this data alone, so the first step is to review the reported state, the canonical and robots results with the web team.',
        checks: ['Google URL Inspection result stored as returned', 'No inference made from the status text'] }
    });
  }
  for (const m of input.sitemaps ?? []) {
    if (!((m.errors ?? 0) > 0 || (m.warnings ?? 0) > 0)) continue;
    out.push({
      type: 'SITEMAP_REPORTED_ISSUES', target: m.path, confidence: 'OBSERVED', source: GSC_API,
      reason: `Google reports ${m.errors ?? 0} error(s) and ${m.warnings ?? 0} warning(s) for this sitemap.`,
      plainEnglish: `Google reports problems with your sitemap (${m.errors ?? 0} errors, ${m.warnings ?? 0} warnings).`,
      evidence: { sitemap: m.path, errors: m.errors, warnings: m.warnings, lastDownloaded: m.lastDownloaded, fetchedAt: m.fetchedAt },
      objective: 'Re-read the sitemap report in Search Console and confirm the counts fall to zero.',
      decision: { action: 'INVESTIGATE', requiresApproval: true, rationale: 'The sitemap itself needs correcting; Google\'s report lists the affected entries.', checks: ['Counts taken directly from the Search Console sitemaps API'] }
    });
  }

  const pageIndexNote = `${input.pages.length} page(s) in the latest published-page audit`;
  for (const g of input.gscPages) {
    if (g.impressions >= HIGH_IMPRESSIONS_MIN && g.ctr < LOW_CTR_MAX) {
      out.push({
        type: 'HIGH_IMPRESSIONS_LOW_CTR', target: g.page, confidence: 'CALCULATED', source: GSC_SOURCE,
        reason: `Search Console reports ${g.impressions} impressions and ${g.clicks} clicks (CTR ${(g.ctr * 100).toFixed(2)}%) for this page. The CTR is calculated from those two observed numbers; SANOCEA applies no external benchmark.`,
        plainEnglish: `This page is shown often in Google but rarely clicked (${g.clicks} clicks from ${g.impressions} views).`,
        evidence: { page: g.page, impressions: g.impressions, clicks: g.clicks, ctr: g.ctr, averagePosition: g.position, rule: `impressions >= ${HIGH_IMPRESSIONS_MIN} and ctr < ${LOW_CTR_MAX}`, capturedAt: input.gscCapturedAt ?? null },
        objective: 'After a title/description change, compare this page\'s CTR in Search Console over a comparable window; causation is not established by a before/after comparison.',
        decision: { action: 'UPDATE_TITLE_META', requiresApproval: true,
          rationale: 'The page already earns impressions, so the title and description shown for it are the first thing to review. Google may choose to display different text.',
          checks: ['Existing URL with observed impressions'] }
      });
    }
  }

  for (const q of input.gscQueries) {
    if (q.impressions < QUERY_MIN_IMPRESSIONS || input.pages.length === 0) continue;
    const scored = input.pages.map(p => ({ p, o: queryOverlap(q.query, p) })).sort((a, b) => b.o - a.o);
    const best = scored[0];
    const matched = best.o >= QUERY_MATCH_MIN_OVERLAP;
    if (matched) continue; // a suitable page exists; title/meta rule above covers visibility problems
    out.push({
      type: 'QUERY_PAGE_MATCH_GAP', target: q.query, confidence: 'CALCULATED', source: GSC_SOURCE,
      reason: `Search Console reports ${q.impressions} impressions for "${q.query}". No audited page shares at least ${QUERY_MATCH_MIN_OVERLAP * 100}% of the query's words in its URL, title or heading (best match ${(best.o * 100).toFixed(0)}% on ${best.p.url}); ${pageIndexNote}.`,
      plainEnglish: `People are shown your site for "${q.query}", but none of the pages checked is clearly about it.`,
      evidence: { query: q.query, impressions: q.impressions, clicks: q.clicks, bestMatchUrl: best.p.url, bestMatchOverlap: best.o, minOverlap: QUERY_MATCH_MIN_OVERLAP, pagesCompared: input.pages.length, capturedAt: input.gscCapturedAt ?? null, limitation: 'Only pages in the latest bounded audit were compared; an unaudited page may already cover this query.' },
      objective: 'Confirm whether a page covers this query, then measure that page\'s impressions and clicks for it in Search Console.',
      decision: {
        action: best.o > 0 ? 'UPDATE_EXISTING_PAGE' : 'CREATE_SEO_PAGE', requiresApproval: true,
        rationale: best.o > 0
          ? `A page shares some of the query's words (${best.p.url}); extending it is preferred over creating a competing page.`
          : 'No audited page shares any of the query\'s words. A new page is proposed only after a human confirms no unaudited page covers it.',
        checks: [`Compared against ${input.pages.length} audited page(s) by URL, title and heading words`, 'Cannibalisation risk checked only against audited pages']
      }
    });
  }
  return out.map(applyDiagnosis);
}

/** Diagnosis and action selection, downstream of the detectors. Only the redirect/canonical/sitemap family is diagnosed so far. */
function applyDiagnosis(c: Candidate): Candidate {
  const facts = (c.evidence as any).facts as Fact[] | undefined;
  if (c.type !== 'SITEMAP_URL_REDIRECTS' || !facts) return c;
  const diagnosis = diagnoseRedirectFamily(facts), actionPlan = selectAction(diagnosis, facts);
  const sel = actionPlan.candidates.find(x => x.action === actionPlan.selected)!;
  return { ...c, diagnosis, actionPlan, reason: `${diagnosis.finding} ${diagnosis.conclusion}`, plainEnglish: diagnosis.sufficient ? `SANOCEA worked out that ${diagnosis.intended} is the intended address and chose: ${actionPlan.selected}.` : 'SANOCEA is gathering more evidence to work out which address of this page is the intended one. Nothing is being changed.',
    decision: { action: actionPlan.selected as any, requiresApproval: true, rationale: actionPlan.why, checks: [...sel.preconditions, sel.verification, ...actionPlan.investigate_next] } };
}

export class OpportunityEngine {
  constructor(private db: SeoDatabase) {}

  private rowToOpp(r: any): Opportunity {
    const c: Candidate | any = {};
    const evidence = JSON.parse(r.evidence_json);
    const decision = JSON.parse(r.decision_json);
    return {
      opportunityId: r.opportunity_id, tenantId: r.tenant_id, type: r.type, target: r.target, status: r.status,
      confidence: r.confidence, source: r.source, reason: r.reason, plainEnglish: evidence.__plain ?? r.reason,
      evidence: Object.fromEntries(Object.entries(evidence).filter(([k]) => k !== '__plain')),
      recommendedAction: r.recommended_action, decision, objective: r.objective,
      detectedAt: r.detected_at, lastSeenAt: r.last_seen_at, updatedAt: r.updated_at,
      resultingAction: r.resulting_action, resultingMeasurement: r.resulting_measurement,
      contentEligible: contentEligibility(r.type, r.recommended_action).eligible,
      contentEligibilityReason: contentEligibility(r.type, r.recommended_action).reason,
      approval: this.approvalOf(r.tenant_id, r.opportunity_id),
      diagnosis: r.diagnosis_json ? JSON.parse(r.diagnosis_json) : null,
      actionPlan: r.action_plan_json ? JSON.parse(r.action_plan_json) : null
    } as Opportunity & typeof c;
  }

  private approvalOf(tenantId: string, id: string): ApprovalRecord | null {
    const e = this.db.handle.prepare(`SELECT * FROM seo_approvals WHERE tenant_id = ? AND opportunity_id = ? ORDER BY rowid DESC LIMIT 1`).get(tenantId, id) as any;
    // An approval belongs to one cycle: once the opportunity has been reopened (observed again after being marked done) the earlier approval no longer stands.
    const reopen = this.db.handle.prepare(`SELECT at FROM seo_opportunity_events WHERE tenant_id = ? AND opportunity_id = ? AND note LIKE 'Observed again after being marked done; reopened%' ORDER BY id DESC LIMIT 1`).get(tenantId, id) as any;
    if (e && reopen && String(e.approved_at) < String(reopen.at)) return null;
    return e ? { by: e.actor, at: e.approved_at, actorType: e.approval_actor_type, policy: e.approval_policy, reason: e.approval_reason, actionClass: e.action_class, approvedAction: e.approved_action } : null;
  }

  // ── autonomy: tenant mode and policy-governed authorisation ────────────────
  public getAutonomyMode(tenantId: string): AutonomyMode {
    const r = this.db.handle.prepare(`SELECT mode FROM tenant_autonomy WHERE tenant_id = ?`).get(tenantId) as any;
    return r && isAutonomyMode(r.mode) ? r.mode : DEFAULT_MODE;
  }

  /** Changing what SANOCEA may do on its own is an access/security decision: human only. */
  public setAutonomyMode(tenantId: string, mode: string, actor: string, now = new Date().toISOString()): AutonomyMode {
    if (!actor.startsWith('human:') || actor.length <= 6) throw new Error('only a human actor can change a tenant autonomy mode');
    if (!isAutonomyMode(mode)) throw new Error(`unknown autonomy mode ${mode}`);
    this.db.handle.prepare(`INSERT INTO tenant_autonomy (tenant_id, mode, updated_at, updated_by) VALUES (?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET mode=excluded.mode, updated_at=excluded.updated_at, updated_by=excluded.updated_by`).run(tenantId, mode, now, actor);
    return mode;
  }

  /**
   * INTERNAL autonomous path (no external token, in-process, audited as the autonomous policy actor): for every open
   * opportunity, classify its selected action, apply the tenant mode, and authorise what the policy permits. Denials are audited
   * once. INVESTIGATE and anything the mode does not permit are never queued for approval or executed. Class-agnostic: the
   * mode matrix alone decides which classes pass; nothing here assumes a maximum class.
   */
  public autonomyPass(tenantId: string, now = new Date().toISOString()): { authorized: number; denied: number; unchanged: number } {
    const mode = this.getAutonomyMode(tenantId);
    let authorized = 0, denied = 0, unchanged = 0;
    for (const o of this.list(tenantId).opportunities) {
      if (!['DISCOVERED', 'QUALIFIED', 'ACTIONABLE', 'AWAITING_APPROVAL'].includes(o.status) || o.approval) { unchanged++; continue; }
      const action = o.recommendedAction, m = modeAllows(mode, classifyAction(action), action);
      if (!m.allowed) {
        const note = `POLICY_DENIED: ${m.reason}`;
        const seen = this.db.handle.prepare(`SELECT 1 FROM seo_opportunity_events WHERE tenant_id = ? AND opportunity_id = ? AND note = ? LIMIT 1`).get(tenantId, o.opportunityId, note);
        if (!seen) this.event(tenantId, o.opportunityId, o.status, o.status, AUTONOMOUS_ACTOR, note, now);
        denied++; continue;
      }
      for (const st of ['QUALIFIED', 'ACTIONABLE', 'AWAITING_APPROVAL'] as const) {
        const cur = this.get(tenantId, o.opportunityId)!.status;
        if (['DISCOVERED', 'QUALIFIED', 'ACTIONABLE'].includes(cur) && TRANSITIONS[cur as OpportunityStatus].includes(st)) this.transition(tenantId, o.opportunityId, st, 'agent:autonomy-pass', 'prepared for policy authorisation', now);
      }
      if (this.authorize(tenantId, o.opportunityId, now).decision.allowed) authorized++; else denied++;
    }
    return { authorized, denied, unchanged };
  }

  private insertApproval(tenantId: string, r: any, type: 'HUMAN' | 'AUTONOMOUS_AGENT', actor: string, policy: string, reason: string, gates: unknown, now: string): void {
    this.db.handle.prepare(`INSERT INTO seo_approvals (approval_id, tenant_id, opportunity_id, approval_actor_type, actor, approval_policy, approval_reason, approved_at, approved_action, action_class, target, evidence_json, decision_json, gates_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
      .run(`APR-${randomUUID()}`, tenantId, r.opportunity_id, type, actor, policy, reason, now, r.recommended_action, classifyAction(r.recommended_action), r.target, r.evidence_json, r.decision_json, JSON.stringify(gates));
  }

  /**
   * Policy-governed authorisation. Evaluates the tenant's mode and every authorisation gate; if all pass, records an
   * AUTONOMOUS_AGENT approval and moves AWAITING_APPROVAL -> APPROVED. If not, status is unchanged and the denial is audited.
   * Idempotent: an opportunity that already holds an approval returns it without a second record.
   */
  public authorize(tenantId: string, opportunityId: string, now = new Date().toISOString()): { decision: AuthorizationDecision; opportunity: Opportunity } {
    const r = this.db.handle.prepare(`SELECT * FROM seo_opportunities WHERE tenant_id = ? AND opportunity_id = ?`).get(tenantId, opportunityId) as any;
    if (!r) throw new Error('opportunity not found for this tenant');
    const existing = this.approvalOf(tenantId, opportunityId);
    const mode = this.getAutonomyMode(tenantId);
    const base = this.rowToOpp(r);
    if (existing && ['APPROVED', 'IN_PROGRESS', 'COMPLETED', 'MEASURING', 'LEARNED'].includes(r.status)) {
      return { decision: { allowed: true, actionClass: classifyAction(r.recommended_action), action: r.recommended_action, mode, policy: existing.policy, gates: [], reason: `Already authorised (${existing.actorType}) at ${existing.at}.` }, opportunity: base };
    }
    const decision = evaluateAuthorization(mode, { status: r.status, type: r.type, source: r.source, target: r.target, recommendedAction: r.recommended_action, evidence: JSON.parse(r.evidence_json), decision: JSON.parse(r.decision_json) });
    if (!decision.allowed) {
      this.event(tenantId, opportunityId, r.status, r.status, AUTONOMOUS_ACTOR, `POLICY_DENIED: ${decision.reason}`, now);
      return { decision, opportunity: base };
    }
    const tx = this.db.handle.transaction(() => {
      this.insertApproval(tenantId, r, 'AUTONOMOUS_AGENT', AUTONOMOUS_ACTOR, POLICY_REF, decision.reason, decision.gates, now);
      this.db.handle.prepare(`UPDATE seo_opportunities SET status = 'APPROVED', updated_at = ? WHERE tenant_id = ? AND opportunity_id = ?`).run(now, tenantId, opportunityId);
      this.event(tenantId, opportunityId, r.status, 'APPROVED', AUTONOMOUS_ACTOR, `AUTONOMOUS_AGENT approval under ${POLICY_REF}: ${decision.reason}`, now);
    });
    tx();
    return { decision, opportunity: this.get(tenantId, opportunityId)! };
  }

  /** LEARN: stores the verification outcome on the opportunity (resulting_measurement) and audits it. Never changes status. */
  public recordVerification(tenantId: string, opportunityId: string, v: Verification, now = new Date().toISOString()): void {
    const r = this.db.handle.prepare(`SELECT status FROM seo_opportunities WHERE tenant_id = ? AND opportunity_id = ?`).get(tenantId, opportunityId) as any;
    if (!r) throw new Error('opportunity not found for this tenant');
    this.db.handle.prepare(`UPDATE seo_opportunities SET resulting_measurement = ?, updated_at = ? WHERE tenant_id = ? AND opportunity_id = ?`).run(JSON.stringify(v), now, tenantId, opportunityId);
    this.event(tenantId, opportunityId, r.status, r.status, 'agent:verification', `VERIFICATION ${v.status}: ${v.reason} Next: ${v.next}`, now);
  }

  /** Verify against an expected outcome recorded at publication time (not the opportunity's current plan), then record the outcome. */
  public verifyExpected(tenantId: string, opportunityId: string, expected: Expectation[], observed: Fact[], rollbackAvailable: boolean, now = new Date().toISOString()): Verification {
    if (!this.get(tenantId, opportunityId)) throw new Error('opportunity not found for this tenant');
    const plan: ActionPlan = { selected: 'RECORDED_CHANGE', why: 'recorded at publication', rejected: [], investigate_next: [],
      candidates: [{ action: 'RECORDED_CHANGE', addresses: 'the published change', preconditions: [], expected_outcome: expected, verification: 'Re-observe the live site against the recorded outcome.', fallback: 'ROLLBACK' }] };
    const v = verifyOutcome(plan, observed, rollbackAvailable);
    this.recordVerification(tenantId, opportunityId, v, now);
    return v;
  }

  /** Verify an opportunity's selected action against freshly re-observed facts, then record the outcome. */
  public verify(tenantId: string, opportunityId: string, observed: Fact[], rollbackAvailable: boolean, now = new Date().toISOString()): Verification {
    const o = this.get(tenantId, opportunityId);
    if (!o?.actionPlan) throw new Error('no action plan to verify');
    const v = verifyOutcome(o.actionPlan, observed, rollbackAvailable);
    this.recordVerification(tenantId, opportunityId, v, now);
    return v;
  }

  /** Records the artefact (brief/draft reference) an approved opportunity produced. Never changes status. */
  public linkResult(tenantId: string, opportunityId: string, ref: string, actor: string, now = new Date().toISOString()): Opportunity {
    const r = this.db.handle.prepare(`SELECT status FROM seo_opportunities WHERE tenant_id = ? AND opportunity_id = ?`).get(tenantId, opportunityId) as any;
    if (!r) throw new Error('opportunity not found for this tenant');
    if (!['APPROVED', 'IN_PROGRESS', 'COMPLETED', 'MEASURING', 'LEARNED'].includes(r.status)) throw new Error('a result can only be linked to an approved opportunity');
    this.db.handle.prepare(`UPDATE seo_opportunities SET resulting_action = ?, updated_at = ? WHERE tenant_id = ? AND opportunity_id = ?`).run(ref, now, tenantId, opportunityId);
    this.event(tenantId, opportunityId, r.status, r.status, actor, `Linked result: ${ref}`, now);
    return this.get(tenantId, opportunityId)!;
  }

  private event(tenantId: string, id: string, from: string | null, to: string, actor: string, note: string, at: string): void {
    this.db.handle.prepare(`INSERT INTO seo_opportunity_events (opportunity_id, tenant_id, at, actor, from_status, to_status, note) VALUES (?,?,?,?,?,?,?)`)
      .run(id, tenantId, at, actor, from, to, note);
  }

  /** Pure-input refresh: reads persisted evidence, upserts opportunities. Idempotent. */
  public refresh(tenantId: string, now = new Date().toISOString()): { created: number; updated: number; reopened: number; candidates: number } {
    const roster = this.db.getLatestAgentRoster(tenantId);
    const auditor = roster.find(a => a.agentId === 'agent-ai-content-auditor');
    const pages: PublishedPageObservation[] = auditor?.status === 'COMPLETED' && Array.isArray((auditor.details as any)?.pages) ? (auditor.details as any).pages : [];
    const snaps = [...this.db.getGscSnapshotsForTenant(tenantId)].sort((a, b) => a.capturedAt.localeCompare(b.capturedAt));
    const snap = snaps[snaps.length - 1];
    const props = this.db.handle.prepare(`SELECT property FROM search_connections WHERE tenant_id = ? AND provider = 'GOOGLE_SEARCH_CONSOLE'`).all(tenantId) as Array<{ property: string }>;
    const gsvc = new GscPropertyService(this.db, { live: false });
    const inspections = props.flatMap(p => gsvc.latestInspections(tenantId, p.property));
    const sitemaps = props.flatMap(p => gsvc.getSitemaps(tenantId, p.property));
    const candidates = detectOpportunities({
      inspections, sitemaps, ga4Landings: this.db.getGa4LandingTotals(tenantId), ownerIntents: this.db.getOwnerIntents(tenantId),
      pages, pagesObservedAt: (auditor?.details as any)?.checkedAt, pagesSource: auditor?.provenance,
      gscPages: snap?.pageRows?.map((r: any) => ({ page: r.page ?? r.keys?.[0] ?? '', clicks: r.clicks, impressions: r.impressions, ctr: r.ctr, position: r.position })).filter(r => r.page) ?? [],
      gscQueries: snap?.queryRows?.map((r: any) => ({ query: r.query ?? r.keys?.[0] ?? '', clicks: r.clicks, impressions: r.impressions, ctr: r.ctr, position: r.position })).filter(r => r.query) ?? [],
      gscCapturedAt: snap?.capturedAt
    });

    let created = 0, updated = 0, reopened = 0;
    const tx = this.db.handle.transaction(() => {
      for (const c of candidates) {
        const key = `${c.type}|${c.target}`;
        const existing = this.db.handle.prepare(`SELECT * FROM seo_opportunities WHERE tenant_id = ? AND dedupe_key = ?`).get(tenantId, key) as any;
        const ev = JSON.stringify({ ...c.evidence, __plain: c.plainEnglish });
        if (!existing) {
          const id = `OPP-${randomUUID()}`;
          this.db.handle.prepare(`INSERT INTO seo_opportunities (opportunity_id, tenant_id, type, target, dedupe_key, status, confidence, source, reason, evidence_json, recommended_action, decision_json, objective, detected_at, last_seen_at, updated_at, diagnosis_json, action_plan_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
            .run(id, tenantId, c.type, c.target, key, 'DISCOVERED', c.confidence, c.source, c.reason, ev, c.decision.action, JSON.stringify(c.decision), c.objective, now, now, now, c.diagnosis ? JSON.stringify(c.diagnosis) : null, c.actionPlan ? JSON.stringify(c.actionPlan) : null);
          this.event(tenantId, id, null, 'DISCOVERED', 'agent:opportunity-engine', 'First detected from persisted evidence', now);
          created++;
          continue;
        }
        let status = existing.status as OpportunityStatus;
        if (status === 'COMPLETED' || status === 'LEARNED') {
          this.event(tenantId, existing.opportunity_id, status, 'DISCOVERED', 'agent:opportunity-engine', 'Observed again after being marked done; reopened', now);
          status = 'DISCOVERED'; reopened++;
          this.db.handle.prepare(`UPDATE seo_opportunities SET resulting_action = NULL, resulting_measurement = NULL WHERE tenant_id = ? AND opportunity_id = ?`).run(tenantId, existing.opportunity_id); // a new cycle starts clean; the audit trail keeps the old one
        }
        this.db.handle.prepare(`UPDATE seo_opportunities SET status = ?, reason = ?, evidence_json = ?, recommended_action = ?, decision_json = ?, objective = ?, source = ?, confidence = ?, last_seen_at = ?, updated_at = ?, diagnosis_json = ?, action_plan_json = ? WHERE tenant_id = ? AND opportunity_id = ?`)
          .run(status, c.reason, ev, c.decision.action, JSON.stringify(c.decision), c.objective, c.source, c.confidence, now, now, c.diagnosis ? JSON.stringify(c.diagnosis) : null, c.actionPlan ? JSON.stringify(c.actionPlan) : null, tenantId, existing.opportunity_id);
        updated++;
      }
    });
    tx();
    return { created, updated, reopened, candidates: candidates.length };
  }

  public transition(tenantId: string, opportunityId: string, to: OpportunityStatus, actor: string, note: string, now = new Date().toISOString()): Opportunity {
    if (!actor) throw new Error('actor is required for a status change');
    const r = this.db.handle.prepare(`SELECT * FROM seo_opportunities WHERE tenant_id = ? AND opportunity_id = ?`).get(tenantId, opportunityId) as any;
    if (!r) throw new Error('opportunity not found for this tenant');
    if (!TRANSITIONS[r.status as OpportunityStatus].includes(to)) throw new Error(`illegal transition ${r.status} -> ${to}`);
    // Approval is a human act: an agent can never move an opportunity into APPROVED, and work (IN_PROGRESS) can only
    // start from APPROVED, so no path reaches work without a human approval recorded in the audit trail.
    // APPROVED is reached only by a human (recorded HUMAN) or by authorize() (recorded AUTONOMOUS_AGENT under a policy).
    // Nothing else, and no label, can produce an approval.
    if (to === 'APPROVED' && !(actor.startsWith('human:') && actor.length > 6)) throw new Error('only a human actor can approve work directly; autonomous approval goes through authorize() under the policy');
    this.db.handle.prepare(`UPDATE seo_opportunities SET status = ?, updated_at = ? WHERE tenant_id = ? AND opportunity_id = ?`).run(to, now, tenantId, opportunityId);
    if (to === 'APPROVED') this.insertApproval(tenantId, r, 'HUMAN', actor, 'human-manual', note || 'Approved by a human', [], now);
    this.event(tenantId, opportunityId, r.status, to, actor, note, now);
    return this.get(tenantId, opportunityId)!;
  }

  /**
   * The owner's answer to a DECISION_NEEDED question. A human act (human: actor), recorded durably and audited; the diagnosis is
   * re-run at once so the answer takes effect through the same diagnose -> select -> policy path as any other fact.
   */
  public recordOwnerIntent(tenantId: string, opportunityId: string, address: string, actor: string, now = new Date().toISOString()): Opportunity {
    if (!actor.startsWith('human:') || actor.length <= 6) throw new Error('only a human can state the intended address');
    const o = this.get(tenantId, opportunityId);
    if (!o) throw new Error('opportunity not found for this tenant');
    const options = o.diagnosis?.decision_needed?.options.map(x => x.address) ?? [];
    if (!options.includes(address)) throw new Error('that address is not one of the options SANOCEA asked about');
    this.db.setOwnerIntent(tenantId, o.target.replace(/#.*$/, '').replace(/\/+$/, ''), address, actor, now);
    this.event(tenantId, opportunityId, o.status, o.status, actor, `OWNER_DECISION: the public address of this page is ${address}`, now);
    this.refresh(tenantId, now);
    return this.get(tenantId, opportunityId)!;
  }

  /** Records an audit event on an opportunity without changing its status (execution/verification observations). */
  public annotate(tenantId: string, opportunityId: string, actor: string, note: string, now = new Date().toISOString()): void {
    const r = this.db.handle.prepare(`SELECT status FROM seo_opportunities WHERE tenant_id = ? AND opportunity_id = ?`).get(tenantId, opportunityId) as any;
    if (!r) throw new Error('opportunity not found for this tenant');
    this.event(tenantId, opportunityId, r.status, r.status, actor, note, now);
  }

  public get(tenantId: string, opportunityId: string): Opportunity | undefined {
    const r = this.db.handle.prepare(`SELECT * FROM seo_opportunities WHERE tenant_id = ? AND opportunity_id = ?`).get(tenantId, opportunityId);
    return r ? this.rowToOpp(r) : undefined;
  }

  /**
   * Ordering rule (deterministic, NOT a priority): first-detected time ascending, then affected address, then type.
   * It says nothing about importance and must never be shown as one. A priority model is a separate, explicit piece of work.
   */
  public list(tenantId: string): { tenantId: string; provenance: string; count: number; opportunities: Opportunity[] } {
    const rows = this.db.handle.prepare(`SELECT * FROM seo_opportunities WHERE tenant_id = ? ORDER BY detected_at ASC, target ASC, type ASC, opportunity_id ASC`).all(tenantId);
    const mode = this.getAutonomyMode(tenantId);
    return { tenantId, provenance: '[CALCULATED]', count: rows.length, opportunities: rows.map(r => { const o = this.rowToOpp(r); return { ...o, lifecycle: buildLifecycle(o, this.history(tenantId, o.opportunityId), mode) }; }) };
  }

  public history(tenantId: string, opportunityId: string): Array<{ at: string; actor: string; from: string | null; to: string; note: string }> {
    return (this.db.handle.prepare(`SELECT * FROM seo_opportunity_events WHERE tenant_id = ? AND opportunity_id = ? ORDER BY id`).all(tenantId, opportunityId) as any[])
      .map(e => ({ at: e.at, actor: e.actor, from: e.from_status, to: e.to_status, note: e.note }));
  }
}
