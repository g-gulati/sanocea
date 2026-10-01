import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { OpportunityEngine } from '../src/opportunities/opportunityEngine.js';
import { collectRedirectFamilyFacts, diagnoseRedirectFamily, selectAction, verifyOutcome, Fact } from '../src/opportunities/diagnosis.js';
import { classifyAction } from '../src/opportunities/autonomyPolicy.js';

const L = 'https://a.test/s', D = 'https://a.test/s/';
const pg = (url: string, o: any = {}) => ({ url, status: 200, finalUrl: url, redirected: false, canonical: null, internalLinks: [], staticWords: 400, bodyWords: 420, title: '', h1Text: '', h1Count: 1, jsonLdTypes: [], retiredSchemaTypes: [], ...o });
const target = (canonical: string | null) => pg(L, { redirected: true, finalUrl: D, canonical });
/** root links to `link`; siblings use `sib` form; Google's chosen canonical is `google` (undefined = not inspected). */
function world(o: { canonical: string | null; link?: string; sibs?: string[]; google?: string | null }) {
  const pages = [pg('https://a.test/', { internalLinks: o.link ? [o.link] : [] }), target(o.canonical), ...(o.sibs ?? []).map(u => pg(u))];
  const insp = o.google === undefined ? [] : [{ url: D, googleCanonical: o.google }];
  const facts = collectRedirectFamilyFacts(pages[1] as any, pages as any, insp);
  const d = diagnoseRedirectFamily(facts);
  return { pages, insp, facts, d, plan: selectAction(d, facts) };
}
const ids = (fs: Fact[]) => new Set(fs.map(f => f.id));

test('1. today\'s real conflict (split signals, no Google canonical, no siblings) => INVESTIGATE with hypotheses citing fact ids; no change is selected', () => {
  const { facts, d, plan } = world({ canonical: L, link: D });
  assert.equal(d.sufficient, false); assert.equal(plan.selected, 'INVESTIGATE');
  assert.equal(d.hypotheses.length, 2); for (const h of d.hypotheses) assert.ok(['LIKELY', 'POSSIBLE'].includes(h.status), h.status);
  const known = ids(facts);
  for (const h of d.hypotheses) for (const f of [...h.supported_by, ...h.contradicted_by]) assert.ok(known.has(f), `unknown fact ${f}`);
  const hD = d.hypotheses[0], hL = d.hypotheses[1];
  assert.ok(hD.supported_by.some(f => f.startsWith('fact:redirects_to')) && hD.contradicted_by.some(f => f.startsWith('fact:sitemap_lists')) && hD.contradicted_by.some(f => f.startsWith('fact:destination_canonical')));
  assert.ok(hL.supported_by.some(f => f.startsWith('fact:destination_canonical')) && hL.contradicted_by.some(f => f.startsWith('fact:redirects_to')));
  assert.ok(d.missing_evidence.some(m => /Google-selected canonical/.test(m)) && d.missing_evidence.some(m => /sibling/.test(m)));
  assert.deepEqual(plan.rejected.map(r => r.action).sort(), ['CHANGE_CANONICAL', 'CHANGE_REDIRECT', 'FIX_SITEMAP_ENTRY']);
  assert.match(plan.rejected.find(r => r.action === 'FIX_SITEMAP_ENTRY')!.reason, /canonical/);
  assert.ok(plan.investigate_next.length >= 2);
  assert.doesNotMatch(JSON.stringify(d) + JSON.stringify(plan), /"(score|confidence)":\s*\d/);
});

test('2. slash convention established by Google + internal links + siblings, canonical says no-slash => CHANGE_CANONICAL first (sitemap fix deferred); not chosen by Google alone', () => {
  const alone = world({ canonical: L, google: D });                       // Google alone is NOT sufficient
  assert.equal(alone.d.sufficient, false); assert.equal(alone.plan.selected, 'INVESTIGATE');
  const w = world({ canonical: L, link: D, sibs: ['https://a.test/about/', 'https://a.test/pricing/'], google: D });
  assert.equal(w.d.hypotheses[0].status, 'ESTABLISHED'); assert.equal(w.d.hypotheses[1].status, 'RULED_OUT'); assert.equal(w.d.intended, D);
  assert.equal(w.plan.selected, 'CHANGE_CANONICAL');
  assert.deepEqual(w.plan.candidates.map(c => c.action), ['CHANGE_CANONICAL', 'FIX_SITEMAP_ENTRY'], 'the redirect agrees with the convention, so no redirect change is a candidate');
  assert.match(w.plan.rejected.find(r => r.action === 'FIX_SITEMAP_ENTRY')!.reason, /deferred/);
  assert.deepEqual(w.plan.candidates[0].expected_outcome, [{ kind: 'destination_canonical', subject: D, equals: D }]);
  assert.ok(w.d.hypotheses[0].supported_by.some(f => f.startsWith('fact:google_canonical')) && w.d.hypotheses[0].supported_by.some(f => f.startsWith('fact:sibling_form')));
});

test('3. canonical and redirect are right (destination is intended); only the sitemap entry is stale => FIX_SITEMAP_ENTRY, derived from the evidence', () => {
  const w = world({ canonical: D, link: D, sibs: ['https://a.test/about/', 'https://a.test/pricing/'], google: D });
  assert.equal(w.d.intended, D); assert.equal(w.plan.selected, 'FIX_SITEMAP_ENTRY'); assert.deepEqual(w.plan.candidates.map(c => c.action), ['FIX_SITEMAP_ENTRY']);
  assert.ok(w.plan.candidates[0].preconditions.some(p => /canonical equals/.test(p)));
  // the same evidence with the no-slash convention selects a REDIRECT change instead: the action follows the evidence, not the finding type
  const rev = world({ canonical: L, link: L, sibs: ['https://a.test/about', 'https://a.test/pricing'], google: L });
  assert.equal(rev.d.intended, L); assert.equal(rev.plan.selected, 'CHANGE_REDIRECT'); assert.equal(classifyAction('CHANGE_REDIRECT'), 'C');
});

test('4. verification: MET -> LEARN; contradicted -> ROLLBACK (or INVESTIGATE without rollback); missing facts -> INVESTIGATE; outcome is recorded on the opportunity', () => {
  const { plan } = world({ canonical: D, link: D, sibs: ['https://a.test/about/', 'https://a.test/pricing/'], google: D });
  const f = (kind: string, subject: string, value: string | null): Fact => ({ id: `x:${kind}`, kind, subject, value, source: 's' });
  assert.deepEqual([verifyOutcome(plan, [f('sitemap_lists', D, D)], true).status, verifyOutcome(plan, [f('sitemap_lists', D, D)], true).next], ['MET', 'LEARN']);
  const bad = verifyOutcome(plan, [f('sitemap_lists', D, D), f('sitemap_lists', L, L)], true);
  assert.deepEqual([bad.status, bad.next], ['NOT_MET', 'ROLLBACK']);
  assert.equal(verifyOutcome(plan, [f('sitemap_lists', D, D), f('sitemap_lists', L, L)], false).next, 'INVESTIGATE');
  assert.deepEqual([verifyOutcome(plan, [], true).status, verifyOutcome(plan, [], true).next], ['INCONCLUSIVE', 'INVESTIGATE'], 'missing evidence is never read as success');
  assert.equal(verifyOutcome(plan, [f('sitemap_lists', D, D), f('redirects_to', D, 'https://a.test/other')], true).status, 'NOT_MET');
});

function seeded(w: ReturnType<typeof world>) {
  const db = new SeoDatabase(':memory:');
  db.recordAgentTaskExecution({ taskId: 't', tenantId: 'a', agentId: 'agent-ai-content-auditor', agentName: 'x', role: 'AI_CONTENT_AUDITOR', status: 'COMPLETED', currentTask: 'x', outputSummary: 'x', provenance: '[OBSERVED: LIVE PAGE FETCH]', executedAt: new Date().toISOString(), nextScheduledAt: '', details: { checkedAt: 'c', pages: w.pages } } as any);
  db.handle.prepare(`INSERT INTO search_connections (tenant_id, provider, property, state, auth_method, last_checked_at) VALUES ('a','GOOGLE_SEARCH_CONSOLE','sc-domain:a.test','CONNECTED','SERVICE_ACCOUNT','x')`).run();
  for (const i of w.insp) db.handle.prepare(`INSERT INTO gsc_url_inspections (tenant_id, site_url, url, inspected_at, verdict, google_canonical) VALUES ('a','sc-domain:a.test',?,?,?,?)`).run(i.url, 'x', 'NEUTRAL', i.googleCanonical);
  return db;
}
const redirectOpp = (eng: OpportunityEngine) => eng.list('a').opportunities.find(o => o.type === 'SITEMAP_URL_REDIRECTS')!;
const prep = (eng: OpportunityEngine, id: string) => { for (const s of ['QUALIFIED', 'ACTIONABLE', 'AWAITING_APPROVAL'] as const) eng.transition('a', id, s, 'agent:x', 'p'); };

test('5. the policy stays the boundary: diagnosis persists and is re-diagnosed on new evidence; no selected action bypasses the policy; investigation is never authorised', () => {
  const real = world({ canonical: L, link: D });
  const db = seeded(real); const eng = new OpportunityEngine(db); eng.refresh('a');
  let o = redirectOpp(eng);
  assert.equal(o.recommendedAction, 'INVESTIGATE'); assert.equal(o.diagnosis!.sufficient, false); assert.ok(o.actionPlan!.investigate_next.length);
  assert.ok(Array.isArray((o.evidence as any).facts) && (o.evidence as any).facts.every((f: Fact) => f.id.startsWith('fact:')), 'facts are persisted with the opportunity');
  eng.setAutonomyMode('a', 'AUTONOMOUS_DISTRIBUTION', 'human:owner'); prep(eng, o.opportunityId);
  const d0 = eng.authorize('a', o.opportunityId).decision;
  assert.equal(d0.allowed, false); assert.equal(d0.actionClass, 'C', 'INVESTIGATE can never execute, even in the most permissive mode');
  // the same finding after the evidence is gathered: re-diagnosed on the same row
  const better = world({ canonical: L, link: D, sibs: ['https://a.test/about/', 'https://a.test/pricing/'], google: D });
  db.recordAgentTaskExecution({ taskId: 't2', tenantId: 'a', agentId: 'agent-ai-content-auditor', agentName: 'x', role: 'AI_CONTENT_AUDITOR', status: 'COMPLETED', currentTask: 'x', outputSummary: 'x', provenance: '[OBSERVED: LIVE PAGE FETCH]', executedAt: new Date().toISOString(), nextScheduledAt: '', details: { checkedAt: 'c', pages: better.pages } } as any);
  db.handle.prepare(`INSERT INTO gsc_url_inspections (tenant_id, site_url, url, inspected_at, verdict, google_canonical) VALUES ('a','sc-domain:a.test',?,?,?,?)`).run(D, 'y', 'NEUTRAL', D);
  eng.refresh('a'); o = redirectOpp(eng);
  assert.equal(o.recommendedAction, 'CHANGE_CANONICAL'); assert.equal(o.diagnosis!.intended, D);
  assert.equal(eng.list('a').opportunities.filter(x => x.type === 'SITEMAP_URL_REDIRECTS').length, 1, 'one opportunity, re-diagnosed (not duplicated)');
});

test('5b. selected actions meet the policy: CHANGE_CANONICAL (B) is denied in AUTONOMOUS_SEO, FIX_SITEMAP_ENTRY (A) is authorised, CHANGE_REDIRECT (C) never', () => {
  const run = (w: ReturnType<typeof world>, mode: any) => {
    const db = seeded(w); const eng = new OpportunityEngine(db); eng.refresh('a'); eng.setAutonomyMode('a', mode, 'human:owner');
    const o = redirectOpp(eng); prep(eng, o.opportunityId);
    return { sel: o.recommendedAction, d: eng.authorize('a', o.opportunityId).decision, eng, o };
  };
  const sibs = ['https://a.test/about/', 'https://a.test/pricing/'], nsibs = ['https://a.test/about', 'https://a.test/pricing'];
  const b = run(world({ canonical: L, link: D, sibs, google: D }), 'AUTONOMOUS_SEO');
  assert.deepEqual([b.sel, b.d.actionClass, b.d.allowed], ['CHANGE_CANONICAL', 'B', false]);
  assert.equal(run(world({ canonical: L, link: D, sibs, google: D }), 'AUTONOMOUS_CONTENT').d.allowed, true, 'Class B is allowed once the tenant mode permits it');
  const a = run(world({ canonical: D, link: D, sibs, google: D }), 'AUTONOMOUS_SEO');
  assert.deepEqual([a.sel, a.d.actionClass, a.d.allowed], ['FIX_SITEMAP_ENTRY', 'A', true]);
  assert.equal(a.eng.get('a', a.o.opportunityId)!.approval!.actorType, 'AUTONOMOUS_AGENT');
  const c = run(world({ canonical: L, link: L, sibs: nsibs, google: L }), 'AUTONOMOUS_DISTRIBUTION');
  assert.deepEqual([c.sel, c.d.actionClass, c.d.allowed], ['CHANGE_REDIRECT', 'C', false]);
});

test('6. LEARN: a verification outcome is recorded on the opportunity and audited, never changing its status', () => {
  const w = world({ canonical: D, link: D, sibs: ['https://a.test/about/', 'https://a.test/pricing/'], google: D });
  const eng = new OpportunityEngine(seeded(w)); eng.refresh('a');
  const o = redirectOpp(eng);
  const v = eng.verify('a', o.opportunityId, [{ id: 'f', kind: 'sitemap_lists', subject: L, value: L, source: 's' }, { id: 'g', kind: 'sitemap_lists', subject: D, value: D, source: 's' }], true);
  assert.equal(v.status, 'NOT_MET'); assert.equal(v.next, 'ROLLBACK');
  const after = eng.get('a', o.opportunityId)!;
  assert.equal(JSON.parse(after.resultingMeasurement!).status, 'NOT_MET'); assert.equal(after.status, o.status);
  assert.match(eng.history('a', o.opportunityId).at(-1)!.note, /VERIFICATION NOT_MET/);
  assert.throws(() => eng.verify('a', 'nope', [], true), /not found|no action plan/);
});
