import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { Ga4Collector, GA4_PROVENANCE } from '../src/search-intel/ga4.js';
import { collectRedirectFamilyFacts, diagnoseRedirectFamily } from '../src/opportunities/diagnosis.js';

const auth = { getServiceAccountTokenForScope: async () => 'tok' } as any;
const json = (b: any, status = 200) => new Response(JSON.stringify(b), { status });
const report = (rows: string[][]) => ({ dimensionHeaders: [{}, {}, {}], metricHeaders: [{}], rowCount: rows.length,
  rows: rows.map(r => ({ dimensionValues: r.slice(0, 3).map(value => ({ value })), metricValues: r.slice(3).map(value => ({ value })) })) });
const stub = (over: Record<string, (body: any) => Response> = {}) => (async (url: any, init: any) => {
  const u = String(url), body = init?.body ? JSON.parse(init.body) : undefined;
  for (const [k, fn] of Object.entries(over)) if (u.includes(k)) return fn(body);
  if (u.endsWith(':runReport') && body.dimensions[0].name === 'date') return json(report([
    ['20260914', 'Email', '/', '86', '85', '67', '1021', '0'], ['20260914', 'Organic Search', '/pricing', '3', '3', '2', '40', '0'], ['bad', 'x', '/', '1', '1', '1', '1', '0']]));
  if (u.endsWith(':runReport')) return json({ dimensionHeaders: [{}], rows: [{ dimensionValues: [{ value: 'page_view' }], metricValues: [{ value: '496' }, { value: '0' }] }] });
  if (u.endsWith('/keyEvents')) return json({ keyEvents: [{ eventName: 'purchase' }] });
  return json({}, 404);
}) as typeof fetch;

test('ga4: no property id or no credential => NOT AVAILABLE, nothing stored, no request', async () => {
  let calls = 0; const f = (async () => { calls++; return json({}); }) as any;
  const db = new SeoDatabase(':memory:');
  assert.match((await new Ga4Collector(db, { auth, propertyId: '', fetchImpl: f }).collect('t')).unavailable!.reason, /GA4_PROPERTY_ID/);
  assert.match((await new Ga4Collector(db, { propertyId: '1', fetchImpl: f }).collect('t')).unavailable!.reason, /service account/);
  assert.equal(calls, 0);
});

test('ga4: stores real rows only, drops malformed ones, and reports configured-but-unobserved key events honestly', async () => {
  const db = new SeoDatabase(':memory:');
  const c = new Ga4Collector(db, { auth, propertyId: 'properties/553968706', fetchImpl: stub() });
  const r = await c.collect('t');
  assert.equal(r.status, 'OBSERVED');
  assert.equal(r.landingRowsStored, 2);
  const rep: any = c.report('t');
  assert.equal(rep.provenance, GA4_PROVENANCE);
  assert.equal(rep.byChannel[0].channel, 'Email');
  assert.deepEqual(rep.organicSearchLandingPages.map((p: any) => p.landingPage), ['/pricing']);
  assert.deepEqual(rep.conversionSignal.keyEventsConfigured, ['purchase']);
  assert.match(rep.conversionSignal.statement, /none was observed/);
});

test('ga4: API failure stores nothing; unrecognised shape fails closed', async () => {
  const db = new SeoDatabase(':memory:');
  const r = await new Ga4Collector(db, { auth, propertyId: '1', fetchImpl: (async () => json({ error: { status: 'PERMISSION_DENIED' } }, 403)) as any }).collect('t');
  assert.equal(r.status, 'NOT_AVAILABLE');
  assert.match(r.unavailable!.reason, /403 PERMISSION_DENIED/);
  assert.equal(db.getGa4LandingObservations('t', '1').length, 0);
  const r2 = await new Ga4Collector(db, { auth, propertyId: '1', fetchImpl: (async () => json({ nope: 1 })) as any }).collect('t');
  assert.equal(r2.status, 'NOT_AVAILABLE');
});

test('ga4: facts are provenance-labelled, support but never establish an intended address', () => {
  const L = 'https://x.test/a', D = 'https://x.test/a/';
  const page = { url: L, status: 200, finalUrl: D, redirected: true, canonical: null };
  const without = diagnoseRedirectFamily(collectRedirectFamilyFacts(page, [page], []));
  const facts = collectRedirectFamilyFacts(page, [page], [], undefined, [{ landingPage: '/a/', sessions: 40, engagedSessions: 20, organicSessions: 5, windowStart: '2026-09-14', windowEnd: '2026-09-30' }]);
  const ga = facts.filter(f => f.kind === 'ga4_landing_sessions');
  assert.equal(ga.length, 2);
  assert.ok(ga.every(f => f.source === '[OBSERVED: GOOGLE ANALYTICS 4 DATA API]'));
  assert.match(ga.find(f => f.subject === L)!.value!, /^0 sessions/);
  const withGa = diagnoseRedirectFamily(facts);
  assert.equal(withGa.sufficient, without.sufficient);
  assert.ok(withGa.hypotheses[0].supported_by.includes(ga.find(f => f.subject === D)!.id));
});
