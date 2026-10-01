import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { GscPropertyService, GscAuthLike } from '../src/search-intel/gscProperty.js';
import { OpportunityEngine } from '../src/opportunities/opportunityEngine.js';
import { SeoMonitoringWorker } from '../src/worker/seoMonitoringWorker.js';
import { fakeFetch } from './helpers/fakeHttp.js';

const SITE = 'sc-domain:a.test';
const SM = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(SITE)}/sitemaps`;
const INSPECT = 'https://searchconsole.googleapis.com/v1/urlInspection/index:inspect';
const auth = (over: Partial<GscAuthLike> = {}): GscAuthLike => ({
  getAccessToken: async () => 'tok', verifyProperty: async () => ({ verified: true, permissionLevel: 'siteFullUser', authMethod: 'SERVICE_ACCOUNT' }), ...over });
const json = (o: any) => ({ status: 200, body: JSON.stringify(o) });

test('connection state: NOT_CONNECTED without a live credential; CONNECTED with permission; TOKEN_EXPIRED on 401; ERROR on 403; last success is kept', async () => {
  const db = new SeoDatabase(':memory:');
  assert.equal((await new GscPropertyService(db, { live: false }).refreshConnection('t', SITE)).state, 'NOT_CONNECTED');
  const ok = new GscPropertyService(db, { live: true, auth: auth() });
  const c = await ok.refreshConnection('t', SITE, '2026-10-01T00:00:00Z');
  assert.equal(c.state, 'CONNECTED'); assert.equal(c.permissionLevel, 'siteFullUser');
  const exp = await new GscPropertyService(db, { live: true, auth: auth({ verifyProperty: async () => ({ verified: false, permissionLevel: 'siteUnverified', authMethod: 'OAUTH_2', errorMessage: 'Google API HTTP 401: Unauthorized' }) }) }).refreshConnection('t', SITE, '2026-10-02T00:00:00Z');
  assert.equal(exp.state, 'TOKEN_EXPIRED'); assert.equal(exp.lastSuccessAt, '2026-10-01T00:00:00Z', 'last success survives a later failure');
  const err = await new GscPropertyService(db, { live: true, auth: auth({ verifyProperty: async () => ({ verified: false, permissionLevel: 'siteUnverified', authMethod: 'SERVICE_ACCOUNT', errorMessage: 'User or Service Account does not have verified access to this GSC property' }) }) }).refreshConnection('t', SITE);
  assert.equal(err.state, 'ERROR');
  assert.equal(new GscPropertyService(db, { live: true, auth: auth() }).getConnection('other-tenant', SITE), undefined, 'tenant scoped');
});

test('sitemaps: stored exactly as returned, replaced on refresh, and failures store nothing', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch({ [SM]: () => json({ sitemap: [{ path: 'https://a.test/sitemap.xml', lastDownloaded: '2026-09-29T18:26:38.446Z', errors: '0', warnings: '2', isPending: false, type: 'sitemap' }] }) });
  const s = new GscPropertyService(db, { live: true, auth: auth(), fetchImpl: f });
  assert.deepEqual(await s.collectSitemaps('t', SITE), { status: 'OBSERVED', count: 1 });
  assert.equal(s.getSitemaps('t', SITE)[0].warnings, 2);
  assert.equal(f.calls[0].init && (f.calls[0].init.headers as any).Authorization, 'Bearer tok');
  const gone = new GscPropertyService(db, { live: true, auth: auth(), fetchImpl: fakeFetch({ [SM]: () => json({}) }) });
  assert.equal((await gone.collectSitemaps('t', SITE)).count, 0, 'no key = none submitted (a real observation)');
  assert.equal(s.getSitemaps('t', SITE).length, 0);
  const bad = new GscPropertyService(db, { live: true, auth: auth(), fetchImpl: fakeFetch({ [SM]: { status: 500 } }) });
  assert.equal((await bad.collectSitemaps('t', SITE)).status, 'NOT_AVAILABLE');
});

test('URL Inspection: stored as returned, capped, rate-limited per URL, stops on quota, no write call is ever made', async () => {
  const db = new SeoDatabase(':memory:');
  let n = 0;
  const f = fakeFetch({ [INSPECT]: () => { n++; return json({ inspectionResult: { indexStatusResult: { verdict: n === 1 ? 'PASS' : 'NEUTRAL', coverageState: n === 1 ? 'Submitted and indexed' : 'Discovered - currently not indexed', lastCrawlTime: '2026-09-30T00:00:00Z', googleCanonical: 'https://a.test/x', userCanonical: 'https://a.test/x' } } }); } });
  const s = new GscPropertyService(db, { live: true, auth: auth(), fetchImpl: f });
  const r = await s.inspectUrls('t', SITE, ['https://a.test/', 'https://a.test/b', 'https://a.test/c'], { max: 2, now: '2026-10-01T00:00:00Z' });
  assert.equal(r.inspected, 2); assert.equal(r.skipped, 1);
  assert.equal(s.latestInspection('t', SITE, 'https://a.test/b')!.coverageState, 'Discovered - currently not indexed');
  const again = await s.inspectUrls('t', SITE, ['https://a.test/'], { now: '2026-10-01T05:00:00Z' });
  assert.equal(again.skipped, 1, 'inspected within 20h: not repeated');
  assert.ok(f.calls.every(c => c.init?.method === 'POST' && c.url === INSPECT), 'only the read-only inspect endpoint');
  const quota = new GscPropertyService(new SeoDatabase(':memory:'), { live: true, auth: auth(), fetchImpl: fakeFetch({ [INSPECT]: { status: 429 } }) });
  const q = await quota.inspectUrls('t', SITE, ['https://a.test/1', 'https://a.test/2']);
  assert.equal(q.stoppedOnQuota, true); assert.equal(q.inspected, 0);
  assert.equal((await new GscPropertyService(db, { live: true, auth: auth({ getAccessToken: async () => null }) }).inspectUrls('t', SITE, ['https://a.test/z'])).failed[0].reason, 'No access token');
});

test('opportunity engine turns a non-PASS Google verdict and sitemap problems into observed opportunities; PASS yields none', async () => {
  const db = new SeoDatabase(':memory:');
  const svc = new GscPropertyService(db, { live: true, auth: auth(), fetchImpl: fakeFetch({
    [INSPECT]: () => json({ inspectionResult: { indexStatusResult: { verdict: 'NEUTRAL', coverageState: 'Crawled - currently not indexed' } } }),
    [SM]: () => json({ sitemap: [{ path: 'https://a.test/sitemap.xml', errors: '1', warnings: '0' }] }) }) });
  await svc.refreshConnection('t', SITE); await svc.collectSitemaps('t', SITE); await svc.inspectUrls('t', SITE, ['https://a.test/p']);
  const eng = new OpportunityEngine(db);
  eng.refresh('t');
  const types = eng.list('t').opportunities.map(o => o.type).sort();
  assert.deepEqual(types, ['GOOGLE_INDEX_STATUS_ISSUE', 'SITEMAP_REPORTED_ISSUES']);
  const idx = eng.list('t').opportunities.find(o => o.type === 'GOOGLE_INDEX_STATUS_ISSUE')!;
  assert.equal(idx.source, '[OBSERVED: GOOGLE SEARCH CONSOLE API]');
  assert.match(idx.reason, /has not determined the cause/);
  assert.equal(eng.refresh('t').created, 0, 'idempotent');
});

test('worker: the daily Google job records NOT_CONNECTED honestly when no credential exists, and exposes persisted state only', async () => {
  const w = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false,
    googleFetch: fakeFetch({}), rankCommand: { pageFetch: fakeFetch({}) } });
  const before = w.getGoogleSearchState();
  assert.equal(before.connection, null); assert.equal(before.provenance, '[NOT AVAILABLE]');
  assert.match(await w.runGoogleProperty(), /NOT_CONNECTED/);
  const after = w.getGoogleSearchState();
  assert.equal(after.connection!.state, 'NOT_CONNECTED');
  assert.match(after.writeCapabilities.sitemapSubmission, /NOT ENABLED/);
  w.stop();
});
