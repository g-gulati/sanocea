import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { OpportunityEngine } from '../src/opportunities/opportunityEngine.js';
import { AUTONOMOUS_ACTOR, POLICY_REF, classifyAction, evaluateAuthorization, modeAllows, CLASS_C_PROHIBITED } from '../src/opportunities/autonomyPolicy.js';

const GSC = (q: string) => ({ snapshotId: 'S', siteUrl: 'sc-domain:a.test', dateRange: { startDate: '2026-09-01', endDate: '2026-09-28' }, totalClicks: 0, totalImpressions: 80, averageCtr: 0, averagePosition: 12,
  queryRows: [{ query: q, clicks: 0, impressions: 80, ctr: 0, position: 12 }], pageRows: [{ page: 'https://a.test/', clicks: 2, impressions: 400, ctr: 0.005, position: 9 }], capturedAt: '2026-09-29T00:00:00Z' });
const PAGES = [{ url: 'https://a.test/', status: 200, staticWords: 400, bodyWords: 420, title: 'Acme', h1Text: 'Acme ops', h1Count: 1, jsonLdTypes: [], retiredSchemaTypes: [], finalUrl: 'https://a.test/', redirected: false }];

/** Seeds a tenant with a content opportunity (query with no matching page => CREATE_SEO_PAGE) and a title/meta one (UPDATE_TITLE_META). */
function setup(tenant = 'a') {
  const db = new SeoDatabase(':memory:');
  db.recordAgentTaskExecution({ taskId: `t-${tenant}`, tenantId: tenant, agentId: 'agent-ai-content-auditor', agentName: 'x', role: 'AI_CONTENT_AUDITOR', status: 'COMPLETED', currentTask: 'x', outputSummary: 'x', provenance: '[OBSERVED: LIVE PAGE FETCH]', executedAt: new Date().toISOString(), nextScheduledAt: '', details: { checkedAt: new Date().toISOString(), pages: PAGES } } as any);
  db.saveGscSnapshot(tenant, GSC('gst invoice format') as any);
  const eng = new OpportunityEngine(db); eng.refresh(tenant);
  const by = (t: string) => eng.list(tenant).opportunities.find(o => o.type === t)!;
  const toAwaiting = (id: string) => { for (const s of ['QUALIFIED', 'ACTIONABLE', 'AWAITING_APPROVAL'] as const) eng.transition(tenant, id, s, 'agent:content-workflow', 'prepared'); };
  return { db, eng, by, toAwaiting };
}

test('action classes: A / B / C / D exactly as decided; every prohibited and every unrecognised action (incl. the retired FIX_TECHNICAL_SEO) is Class C', () => {
  for (const a of ['UPDATE_TITLE_META', 'ADD_INTERNAL_LINK', 'UPDATE_SCHEMA', 'FIX_SITEMAP_ENTRY']) assert.equal(classifyAction(a), 'A', a);
  for (const a of ['CREATE_SEO_PAGE', 'CREATE_SUPPORTING_CONTENT', 'UPDATE_EXISTING_PAGE', 'CHANGE_CANONICAL', 'CHANGE_INDEXABILITY']) assert.equal(classifyAction(a), 'B', a);
  for (const a of ['DISTRIBUTE_EXISTING_CONTENT', 'PUBLISH_SOCIAL_DERIVATIVE', 'OTHER_EXTERNAL_CHANNEL_PUBLICATION']) assert.equal(classifyAction(a), 'D', a);
  for (const a of CLASS_C_PROHIBITED) assert.equal(classifyAction(a), 'C', a);
  for (const a of ['CHANGE_REDIRECT', 'CHANGE_SERVER_RENDERING', 'DELETE_PAGE', 'CHANGE_DNS', 'CHANGE_CREDENTIALS', 'FIX_TECHNICAL_SEO', 'WHATEVER_NEW_ACTION', '']) assert.equal(classifyAction(a), 'C', a);
});

test('mode matrix: nothing / nothing / A / A+B / A+B+D, and no mode authorises C; distribution is no longer reachable from AUTONOMOUS_SEO', () => {
  const A = 'UPDATE_TITLE_META', B = 'CREATE_SEO_PAGE', D = 'DISTRIBUTE_EXISTING_CONTENT', C = 'CHANGE_REDIRECT';
  const expect: Record<string, [boolean, boolean, boolean]> = { AUTONOMY_DISABLED: [false, false, false], RECOMMEND_ONLY: [false, false, false], AUTONOMOUS_SEO: [true, false, false], AUTONOMOUS_CONTENT: [true, true, false], AUTONOMOUS_DISTRIBUTION: [true, true, true] };
  for (const [m, [a, b, d]] of Object.entries(expect)) {
    assert.equal(modeAllows(m as any, classifyAction(A), A).allowed, a, `${m}/A`);
    assert.equal(modeAllows(m as any, classifyAction(B), B).allowed, b, `${m}/B`);
    assert.equal(modeAllows(m as any, classifyAction(D), D).allowed, d, `${m}/D`);
    assert.equal(modeAllows(m as any, classifyAction(C), C).allowed, false, `${m}/C`);
  }
});

test('autonomous approval: recorded as AUTONOMOUS_AGENT under the policy, with evidence, gates and reason; never labelled human', () => {
  const { eng, by, toAwaiting } = setup();
  assert.equal(eng.getAutonomyMode('a'), 'RECOMMEND_ONLY', 'no configuration => recommend-only');
  eng.setAutonomyMode('a', 'AUTONOMOUS_CONTENT', 'human:owner');
  const o = by('QUERY_PAGE_MATCH_GAP'); toAwaiting(o.opportunityId);
  const r = eng.authorize('a', o.opportunityId, '2026-10-02T00:00:00Z');
  assert.equal(r.decision.allowed, true); assert.equal(r.decision.actionClass, 'B');
  assert.equal(r.opportunity.status, 'APPROVED');
  const ap = r.opportunity.approval!;
  assert.deepEqual({ t: ap.actorType, by: ap.by, pol: ap.policy, at: ap.at, act: ap.approvedAction }, { t: 'AUTONOMOUS_AGENT', by: AUTONOMOUS_ACTOR, pol: POLICY_REF, at: '2026-10-02T00:00:00Z', act: 'CREATE_SEO_PAGE' });
  assert.match(ap.reason, /All authorisation gates passed/);
  assert.equal(by('QUERY_PAGE_MATCH_GAP').approval!.by.startsWith('human:'), false);
  const row: any = (eng as any).db.handle.prepare(`SELECT * FROM seo_approvals`).get();
  assert.equal(row.approval_actor_type, 'AUTONOMOUS_AGENT'); assert.ok(JSON.parse(row.evidence_json).query); assert.ok(JSON.parse(row.gates_json).length >= 5); assert.equal(row.tenant_id, 'a'); assert.ok(row.target);
  assert.match(eng.history('a', o.opportunityId).at(-1)!.note, /AUTONOMOUS_AGENT approval under sanocea-autonomy-policy@1\.0\.0/);
});

test('policy denial: recommend-only, disabled, and Class B in SEO mode are denied, audited, and change nothing', () => {
  for (const mode of ['RECOMMEND_ONLY', 'AUTONOMY_DISABLED', 'AUTONOMOUS_SEO'] as const) {
    const { eng, by, toAwaiting } = setup(); eng.setAutonomyMode('a', mode, 'human:owner');
    const o = by('QUERY_PAGE_MATCH_GAP'); toAwaiting(o.opportunityId);
    const r = eng.authorize('a', o.opportunityId);
    assert.equal(r.decision.allowed, false, mode); assert.equal(r.opportunity.status, 'AWAITING_APPROVAL');
    assert.equal(eng.get('a', o.opportunityId)!.approval, null);
    assert.match(eng.history('a', o.opportunityId).at(-1)!.note, /^POLICY_DENIED/);
  }
});

test('Class C is refused even in the most permissive mode, and a technical fix is Class C', () => {
  const { eng } = setup(); eng.setAutonomyMode('a', 'AUTONOMOUS_DISTRIBUTION', 'human:owner');
  const d = evaluateAuthorization('AUTONOMOUS_DISTRIBUTION', { status: 'AWAITING_APPROVAL', type: 'X', source: 's', target: 't', recommendedAction: 'DELETE_PAGE', evidence: { a: 1 }, decision: { action: 'DELETE_PAGE', rationale: 'r', checks: ['c'] } });
  assert.equal(d.allowed, false); assert.equal(d.actionClass, 'C'); assert.match(d.reason, /Class C/);
});

test('technical opportunities carry the most specific supported action: server rendering = Class C, sitemap entry = Class A, unknown cause = INVESTIGATE (Class C)', () => {
  const db = new SeoDatabase(':memory:');
  db.recordAgentTaskExecution({ taskId: 'tt', tenantId: 'a', agentId: 'agent-ai-content-auditor', agentName: 'x', role: 'AI_CONTENT_AUDITOR', status: 'COMPLETED', currentTask: 'x', outputSummary: 'x', provenance: '[OBSERVED: LIVE PAGE FETCH]', executedAt: new Date().toISOString(), nextScheduledAt: '', details: { checkedAt: 'x', pages: [{ ...PAGES[0], url: 'https://a.test/s', staticWords: 0, bodyWords: 0, h1Count: 0, redirected: true, finalUrl: 'https://a.test/s/' }] } } as any);
  const eng = new OpportunityEngine(db); eng.refresh('a');
  const act = (t: string) => eng.list('a').opportunities.find(o => o.type === t)!.recommendedAction;
  assert.equal(act('SERVER_RENDERED_CONTENT_GAP'), 'CHANGE_SERVER_RENDERING');
  assert.equal(act('MISSING_STATIC_H1'), 'CHANGE_SERVER_RENDERING');
  assert.equal(act('SITEMAP_URL_REDIRECTS'), 'FIX_SITEMAP_ENTRY');
  assert.equal(classifyAction('FIX_SITEMAP_ENTRY'), 'A');
  assert.equal(classifyAction('CHANGE_REDIRECT'), 'C', 'the redirect itself is never changed autonomously');
  const sm = eng.list('a').opportunities.find(o => o.type === 'SITEMAP_URL_REDIRECTS')!;
  assert.ok(sm.decision.checks.some(c => /verify the destination/i.test(c)) && sm.decision.checks.some(c => /before\/after/i.test(c)), 'pre-execution verification is recorded in the decision');
  assert.match(sm.decision.rationale, /redirect itself is NOT changed/);
});

test('gates: no evidence, a decision that disagrees with the action, or an overlapping page each block authorisation', () => {
  const ok = { status: 'AWAITING_APPROVAL', type: 'QUERY_PAGE_MATCH_GAP', source: 's', target: 'q', recommendedAction: 'CREATE_SEO_PAGE', evidence: { query: 'q', bestMatchOverlap: 0 }, decision: { action: 'CREATE_SEO_PAGE', rationale: 'r', checks: ['c'] } };
  assert.equal(evaluateAuthorization('AUTONOMOUS_CONTENT', ok).allowed, true);
  assert.equal(evaluateAuthorization('AUTONOMOUS_CONTENT', { ...ok, evidence: {} }).allowed, false);
  assert.equal(evaluateAuthorization('AUTONOMOUS_CONTENT', { ...ok, decision: { ...ok.decision, action: 'UPDATE_EXISTING_PAGE' } }).allowed, false);
  assert.equal(evaluateAuthorization('AUTONOMOUS_CONTENT', { ...ok, decision: { ...ok.decision, rationale: '' } }).allowed, false);
  const ov = evaluateAuthorization('AUTONOMOUS_CONTENT', { ...ok, evidence: { query: 'q', bestMatchOverlap: 0.6 } });
  assert.equal(ov.allowed, false); assert.equal(ov.gates.find(g => g.gate === 'no_page_overlap')!.passed, false);
  assert.equal(evaluateAuthorization('AUTONOMOUS_CONTENT', { ...ok, status: 'DISCOVERED' }).allowed, false, 'only an opportunity awaiting authorisation can be authorised');
});

test('human actors: approval is recorded HUMAN; agents and autonomous labels cannot approve via transition; only a human can change a tenant mode', () => {
  const { eng, by, toAwaiting } = setup();
  const o = by('QUERY_PAGE_MATCH_GAP'); toAwaiting(o.opportunityId);
  for (const who of ['agent:x', AUTONOMOUS_ACTOR, 'autonomous:anything', 'system', 'human:']) assert.throws(() => eng.transition('a', o.opportunityId, 'APPROVED', who, 'x'), /only a human/, who);
  assert.throws(() => eng.setAutonomyMode('a', 'AUTONOMOUS_CONTENT', AUTONOMOUS_ACTOR), /only a human/);
  assert.throws(() => eng.setAutonomyMode('a', 'AUTONOMOUS_CONTENT', 'agent:x'), /only a human/);
  assert.throws(() => eng.setAutonomyMode('a', 'GOD_MODE', 'human:owner'), /unknown autonomy mode/);
  const h = eng.transition('a', o.opportunityId, 'APPROVED', 'human:asha', 'Reviewed and approved');
  assert.equal(h.approval!.actorType, 'HUMAN'); assert.equal(h.approval!.policy, 'human-manual');
});

test('human override: a human can halt autonomous work (REJECTED) and a detector/policy never reopens it', () => {
  const { eng, by, toAwaiting } = setup(); eng.setAutonomyMode('a', 'AUTONOMOUS_CONTENT', 'human:owner');
  const o = by('QUERY_PAGE_MATCH_GAP'); toAwaiting(o.opportunityId); eng.authorize('a', o.opportunityId);
  const r = eng.transition('a', o.opportunityId, 'REJECTED', 'human:asha', 'Stop: not wanted');
  assert.equal(r.status, 'REJECTED');
  assert.equal(r.approval!.actorType, 'AUTONOMOUS_AGENT', 'the original autonomous approval stays in the record');
  assert.equal(eng.authorize('a', o.opportunityId).decision.allowed, false, 'a rejected opportunity cannot be authorised again');
});

test('idempotency: authorising twice yields one approval record', () => {
  const { eng, by, toAwaiting } = setup(); eng.setAutonomyMode('a', 'AUTONOMOUS_CONTENT', 'human:owner');
  const o = by('QUERY_PAGE_MATCH_GAP'); toAwaiting(o.opportunityId);
  const a = eng.authorize('a', o.opportunityId); const b = eng.authorize('a', o.opportunityId);
  assert.equal(a.decision.allowed, true); assert.equal(b.decision.allowed, true); assert.match(b.decision.reason, /Already authorised/);
  assert.equal(((eng as any).db.handle.prepare(`SELECT COUNT(*) n FROM seo_approvals`).get() as any).n, 1);
});

test('tenant isolation: tenant B cannot be authorised by tenant A\'s mode, id or approval', () => {
  const a = setup('a'); const b = setup('b');
  a.eng.setAutonomyMode('a', 'AUTONOMOUS_CONTENT', 'human:owner');
  assert.equal(b.eng.getAutonomyMode('b'), 'RECOMMEND_ONLY');
  const ob = b.by('QUERY_PAGE_MATCH_GAP'); b.toAwaiting(ob.opportunityId);
  assert.equal(b.eng.authorize('b', ob.opportunityId).decision.allowed, false, 'b has no autonomy configured');
  const oa = a.by('QUERY_PAGE_MATCH_GAP'); a.toAwaiting(oa.opportunityId);
  assert.throws(() => a.eng.authorize('b', oa.opportunityId), /not found/, 'cross-tenant id refused');
  a.eng.authorize('a', oa.opportunityId);
  assert.equal(b.eng.list('b').opportunities.every(o => o.approval === null), true);
});
