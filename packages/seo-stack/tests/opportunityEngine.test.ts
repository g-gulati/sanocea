import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { OpportunityEngine, detectOpportunities, queryOverlap } from '../src/opportunities/opportunityEngine.js';
import { PublishedPageObservation } from '../src/core/publishedPageAudit.js';

const page = (url: string, over: Partial<PublishedPageObservation> = {}): PublishedPageObservation =>
  ({ url, status: 200, staticWords: 400, bodyWords: 450, finalUrl: url, redirected: false, title: '', h1Text: '', h1Count: 1, jsonLdTypes: [], retiredSchemaTypes: [], ...over });

function seed(db: SeoDatabase, tenant: string, pages: PublishedPageObservation[], gsc?: any) {
  db.recordAgentTaskExecution({ taskId: `t-${tenant}-${Math.random()}`, tenantId: tenant, agentId: 'agent-ai-content-auditor', agentName: 'AI Content Auditor',
    role: 'AI_CONTENT_AUDITOR', status: 'COMPLETED', currentTask: 'x', outputSummary: 'x', provenance: '[OBSERVED: LIVE PAGE FETCH]',
    executedAt: new Date().toISOString(), nextScheduledAt: '', details: { checkedAt: '2026-10-01T00:00:00Z', pages } } as any);
  if (gsc) db.saveGscSnapshot(tenant, gsc);
}

test('live finding shape: a page with 0 server-delivered words becomes an observed, plain-English opportunity that does not overstate', () => {
  const c = detectOpportunities({ pages: [page('https://s.test/', { staticWords: 0, h1Count: 0 })], gscPages: [], gscQueries: [] });
  const gap = c.find(x => x.type === 'SERVER_RENDERED_CONTENT_GAP')!;
  assert.equal(gap.confidence, 'OBSERVED');
  assert.equal(gap.decision.action, 'FIX_TECHNICAL_SEO');
  assert.equal(gap.decision.requiresApproval, true);
  assert.match(gap.reason, /was not measured/);
  assert.doesNotMatch(gap.reason + gap.plainEnglish, /cannot read|can't read|invisible|penal/i);
  assert.ok(c.some(x => x.type === 'MISSING_STATIC_H1'));
  assert.equal(detectOpportunities({ pages: [page('https://s.test/')], gscPages: [], gscQueries: [] }).length, 0, 'healthy page: nothing invented');
});

test('no GSC rows => no search opportunities (never fabricated); with rows, thresholds are stated in evidence', () => {
  assert.equal(detectOpportunities({ pages: [page('https://s.test/')], gscPages: [], gscQueries: [] }).length, 0);
  const c = detectOpportunities({ pages: [page('https://s.test/')], gscPages: [{ page: 'https://s.test/', clicks: 1, impressions: 500, ctr: 0.002, position: 7 }], gscQueries: [] });
  assert.equal(c[0].type, 'HIGH_IMPRESSIONS_LOW_CTR');
  assert.equal(c[0].decision.action, 'IMPROVE_TITLE_META');
  assert.match(String(c[0].evidence.rule), /impressions >= 100/);
  assert.equal('expectedTraffic' in c[0].evidence, false);
});

test('decision: a query that shares words with an existing page updates it; a total miss proposes a new page only with a documented check', () => {
  const pages = [page('https://s.test/solutions/marketplace-reconciliation', { title: 'Marketplace reconciliation', h1Text: 'Marketplace reconciliation' })];
  assert.ok(queryOverlap('marketplace reconciliation software', pages[0]) >= 0.5, '2 of 3 words match');
  const partial = detectOpportunities({ pages, gscPages: [], gscQueries: [{ query: 'amazon marketplace payouts', clicks: 0, impressions: 80, ctr: 0, position: 12 }] });
  assert.equal(partial[0].decision.action, 'UPDATE_EXISTING_PAGE');
  const miss = detectOpportunities({ pages, gscPages: [], gscQueries: [{ query: 'gst invoice format', clicks: 0, impressions: 80, ctr: 0, position: 12 }] });
  assert.equal(miss[0].decision.action, 'CREATE_NEW_PAGE');
  assert.ok(miss[0].decision.checks.length > 0);
  assert.match(String(miss[0].evidence.limitation), /unaudited page/);
  const covered = detectOpportunities({ pages, gscPages: [], gscQueries: [{ query: 'marketplace reconciliation', clicks: 5, impressions: 80, ctr: 0.06, position: 3 }] });
  assert.equal(covered.length, 0);
});

test('engine: refresh is idempotent (deduplicated), tenant-scoped, and audit-logged', () => {
  const db = new SeoDatabase(':memory:');
  seed(db, 'a', [page('https://a.test/', { staticWords: 0 })]);
  seed(db, 'b', [page('https://b.test/', { staticWords: 3 })]);
  const eng = new OpportunityEngine(db);
  assert.deepEqual(eng.refresh('a').created, 1);
  const again = eng.refresh('a');
  assert.equal(again.created, 0); assert.equal(again.updated, 1);
  assert.equal(eng.list('a').count, 1);
  assert.equal(eng.list('b').count, 0, 'tenant b has not been refreshed and never sees a\'s rows');
  eng.refresh('b');
  assert.equal(eng.list('b').opportunities[0].target, 'https://b.test/');
  const id = eng.list('a').opportunities[0].opportunityId;
  assert.throws(() => eng.transition('b', id, 'QUALIFIED', 'agent:x', 'n'), /not found/, 'cross-tenant transition refused');
  assert.equal(eng.history('a', id).length, 1);
});

test('lifecycle: legal path works, illegal jumps are refused, agents cannot approve, rejection is final', () => {
  const db = new SeoDatabase(':memory:');
  seed(db, 'a', [page('https://a.test/', { staticWords: 0 })]);
  const eng = new OpportunityEngine(db);
  eng.refresh('a');
  const id = eng.list('a').opportunities[0].opportunityId;
  assert.throws(() => eng.transition('a', id, 'COMPLETED', 'human:ops', 'skip'), /illegal transition/);
  eng.transition('a', id, 'QUALIFIED', 'agent:q', 'ok');
  eng.transition('a', id, 'ACTIONABLE', 'agent:q', 'ok');
  eng.transition('a', id, 'AWAITING_APPROVAL', 'agent:q', 'ok');
  assert.throws(() => eng.transition('a', id, 'IN_PROGRESS', 'human:ops', 'skip approval'), /illegal transition/, 'work cannot start without APPROVED');
  assert.throws(() => eng.transition('a', id, 'APPROVED', 'agent:q', 'self-approve'), /only a human/);
  assert.throws(() => eng.transition('a', id, 'APPROVED', 'system', 'self-approve'), /only a human/);
  assert.equal(eng.get('a', id)!.approval, null, 'no approval recorded by the refused attempts');
  eng.transition('a', id, 'APPROVED', 'human:ops', 'approved');
  assert.deepEqual({ by: eng.get('a', id)!.approval!.by }, { by: 'human:ops' });
  eng.transition('a', id, 'IN_PROGRESS', 'agent:q', 'work started after human approval');
  eng.transition('a', id, 'COMPLETED', 'human:ops', 'deployed');
  assert.equal(eng.history('a', id).map(h => h.to).join('>'), 'DISCOVERED>QUALIFIED>ACTIONABLE>AWAITING_APPROVAL>APPROVED>IN_PROGRESS>COMPLETED');
  const r = eng.refresh('a');
  assert.equal(r.reopened, 1, 'observed again after completion => reopened with an event');
  assert.equal(eng.get('a', id)!.status, 'DISCOVERED');
  eng.transition('a', id, 'REJECTED', 'human:ops', 'not now');
  eng.refresh('a');
  assert.equal(eng.get('a', id)!.status, 'REJECTED', 'a detector never overrides a human rejection');
  assert.throws(() => eng.transition('a', id, 'QUALIFIED', 'human:ops', 'x'), /illegal/);
});

test('engine reads the persisted GSC snapshot (pages) and labels the result CALCULATED from an OBSERVED snapshot', () => {
  const db = new SeoDatabase(':memory:');
  const snap: any = { snapshotId: 'S1', siteUrl: 'sc-domain:a.test', dateRange: { startDate: '2026-09-01', endDate: '2026-09-28' }, totalClicks: 2, totalImpressions: 400, averageCtr: 0.005, averagePosition: 9,
    queryRows: [], pageRows: [{ page: 'https://a.test/', clicks: 2, impressions: 400, ctr: 0.005, position: 9 }], capturedAt: '2026-09-29T00:00:00Z' };
  seed(db, 'a', [page('https://a.test/')], snap);
  const eng = new OpportunityEngine(db);
  eng.refresh('a');
  const o = eng.list('a').opportunities[0];
  assert.equal(o.type, 'HIGH_IMPRESSIONS_LOW_CTR');
  assert.equal(o.confidence, 'CALCULATED');
  assert.equal(o.source, '[OBSERVED: PERSISTED GSC SNAPSHOT]');
  assert.equal(o.resultingAction, null);
  assert.equal(o.resultingMeasurement, null);
});

test('a sitemap-listed URL that redirects is an observed opportunity; a shell page is described as a shell, not as empty', () => {
  const c = detectOpportunities({ pages: [page('https://s.test/a', { redirected: true, finalUrl: 'https://s.test/a/', staticWords: 0, bodyWords: 14 })], gscPages: [], gscQueries: [] });
  const r = c.find(x => x.type === 'SITEMAP_URL_REDIRECTS')!;
  assert.equal(r.evidence.finalUrl, 'https://s.test/a/');
  const g = c.find(x => x.type === 'SERVER_RENDERED_CONTENT_GAP')!;
  assert.match(g.plainEnglish, /short shell \(14 words/);
  assert.match(g.reason, /14 words of body text in total/);
});

test('listing order is deterministic (first detected, address, type) and no priority/severity field exists on an opportunity', () => {
  const db = new SeoDatabase(':memory:');
  seed(db, 'a', [page('https://a.test/z', { staticWords: 0, h1Count: 0 }), page('https://a.test/b', { staticWords: 0 })]);
  const eng = new OpportunityEngine(db);
  eng.refresh('a', '2026-10-01T00:00:00Z');
  const order = eng.list('a').opportunities.map(o => `${o.target.replace('https://a.test', '')}:${o.type}`);
  assert.deepEqual(order, ['/b:SERVER_RENDERED_CONTENT_GAP', '/z:MISSING_STATIC_H1', '/z:SERVER_RENDERED_CONTENT_GAP']);
  const o: any = eng.list('a').opportunities[0];
  for (const k of ['priority', 'severity', 'score', 'rank', 'impact']) assert.equal(k in o, false, `${k} must not exist until a priority model is defined`);
});

import { contentEligibility } from '../src/opportunities/opportunityEngine.js';
import { controlAuthorized } from '../src/worker/controlAuth.js';

test('content eligibility: only search-wording/page-content opportunities with a content action; every technical type is refused whatever its action', () => {
  assert.equal(contentEligibility('QUERY_PAGE_MATCH_GAP', 'CREATE_NEW_PAGE').eligible, true);
  assert.equal(contentEligibility('QUERY_PAGE_MATCH_GAP', 'UPDATE_EXISTING_PAGE').eligible, true);
  assert.equal(contentEligibility('HIGH_IMPRESSIONS_LOW_CTR', 'IMPROVE_TITLE_META').eligible, true);
  for (const t of ['SERVER_RENDERED_CONTENT_GAP', 'MISSING_STATIC_H1', 'SITEMAP_URL_REDIRECTS', 'GOOGLE_INDEX_STATUS_ISSUE', 'SITEMAP_REPORTED_ISSUES'] as const)
    for (const a of ['CREATE_NEW_PAGE', 'UPDATE_EXISTING_PAGE', 'FIX_TECHNICAL_SEO'] as const) assert.equal(contentEligibility(t, a).eligible, false, `${t}/${a}`);
  assert.equal(contentEligibility('QUERY_PAGE_MATCH_GAP', 'FIX_TECHNICAL_SEO').eligible, false);
});

test('every opportunity the real crawler/Google detectors produce is content-ineligible; the listing exposes eligibility and approval', () => {
  const db = new SeoDatabase(':memory:');
  seed(db, 'a', [page('https://a.test/', { staticWords: 0, h1Count: 0, redirected: true, finalUrl: 'https://a.test/x' })]);
  const eng = new OpportunityEngine(db);
  eng.refresh('a');
  const all = eng.list('a').opportunities;
  assert.ok(all.length >= 3);
  assert.ok(all.every(o => o.contentEligible === false && o.approval === null));
});

test('linkResult: only for an approved opportunity, tenant scoped, never changes status, audit-logged', () => {
  const db = new SeoDatabase(':memory:');
  seed(db, 'a', [page('https://a.test/', { staticWords: 0 })]); seed(db, 'b', [page('https://b.test/', { staticWords: 0 })]);
  const eng = new OpportunityEngine(db); eng.refresh('a'); eng.refresh('b');
  const id = eng.list('a').opportunities[0].opportunityId;
  assert.throws(() => eng.linkResult('a', id, 'brief:x', 'agent:brief'), /approved/);
  for (const to of ['QUALIFIED', 'ACTIONABLE', 'AWAITING_APPROVAL'] as const) eng.transition('a', id, to, 'agent:q', 'n');
  eng.transition('a', id, 'APPROVED', 'human:ops', 'ok');
  assert.throws(() => eng.linkResult('b', id, 'brief:x', 'agent:brief'), /not found/);
  const o = eng.linkResult('a', id, 'brief:abc', 'agent:brief');
  assert.equal(o.resultingAction, 'brief:abc'); assert.equal(o.status, 'APPROVED');
  assert.equal(o.approval!.by, 'human:ops', 'a linked-result event by an agent must never replace the human approval');
  assert.match(eng.history('a', id).at(-1)!.note, /Linked result: brief:abc/);
});

test('worker control token: fails closed without configuration, rejects wrong/short tokens, accepts the exact token', () => {
  const T = 'a'.repeat(32);
  assert.equal(controlAuthorized(T, undefined), false);
  assert.equal(controlAuthorized(T, ''), false);
  assert.equal(controlAuthorized(undefined, T), false);
  assert.equal(controlAuthorized('b'.repeat(32), T), false);
  assert.equal(controlAuthorized('short', 'short'), false, 'a configured token under 16 chars is refused');
  assert.equal(controlAuthorized(T, T), true);
});
