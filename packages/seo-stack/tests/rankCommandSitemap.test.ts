import test from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { CompetitorIntelligenceEngine } from '../src/search-intel/competitorWorker.js';
import { CompetitorConfig } from '../src/search-intel/rankCommandTypes.js';
import { fakeFetch, urlset, sitemapIndex } from './helpers/fakeHttp.js';

const COMP: CompetitorConfig = { competitorId: 'c1', name: 'Acme', domain: 'acme.test', sitemapUrl: 'https://acme.test/sitemap.xml', trackedRoutes: [] };
const mk = (db: SeoDatabase, routes: Parameters<typeof fakeFetch>[0], comps = [COMP], timeoutMs = 2000) =>
  new CompetitorIntelligenceEngine(comps, db, { fetchImpl: fakeFetch(routes), timeoutMs });

test('sitemap: first successful poll is a baseline with parsed URLs, no invented additions', async () => {
  const db = new SeoDatabase(':memory:');
  const [o] = await mk(db, { 'https://acme.test/sitemap.xml': { status: 200, body: urlset(['https://acme.test/a', 'https://acme.test/b']) } }).pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_OK');
  assert.equal(o.totalUrls, 2);
  assert.equal(o.httpStatus, 200);
  assert.equal(o.diffedAgainstPrevious, false);
  assert.deepEqual(o.newlyDiscoveredUrls, []);
  assert.deepEqual(o.removedUrls, []);
  assert.equal(o.provenance, '[OBSERVED: SITEMAP FETCH]');
  assert.deepEqual(db.getCompetitorSitemapSnapshot('t1', 'c1', COMP.sitemapUrl!)!.urls, ['https://acme.test/a', 'https://acme.test/b']);
});

test('sitemap: additions and removals are diffed against the last successful snapshot', async () => {
  const db = new SeoDatabase(':memory:');
  let body = urlset(['https://acme.test/a', 'https://acme.test/b']);
  const engine = mk(db, { 'https://acme.test/sitemap.xml': () => ({ status: 200, body }) });
  await engine.pollCompetitorSitemaps('t1');
  body = urlset(['https://acme.test/b', 'https://acme.test/c', 'https://acme.test/d']);
  const [o] = await engine.pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_OK');
  assert.equal(o.diffedAgainstPrevious, true);
  assert.deepEqual(o.newlyDiscoveredUrls, ['https://acme.test/c', 'https://acme.test/d']);
  assert.deepEqual(o.removedUrls, ['https://acme.test/a']);
  assert.equal(db.getCompetitorSitemapHistory('t1', 'c1').length, 2);
});

test('sitemap: sitemap index children are followed; gzip is decoded', async () => {
  const db = new SeoDatabase(':memory:');
  const engine = mk(db, {
    'https://acme.test/sitemap.xml': { status: 200, body: sitemapIndex(['https://acme.test/s1.xml', 'https://acme.test/s2.xml.gz']) },
    'https://acme.test/s1.xml': { status: 200, body: urlset(['https://acme.test/1']) },
    'https://acme.test/s2.xml.gz': { status: 200, body: gzipSync(Buffer.from(urlset(['https://acme.test/2']))) }
  });
  const [o] = await engine.pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_OK');
  assert.equal(o.totalUrls, 2);
});

test('sitemap: index child on a foreign host fails the poll (no SSRF via untrusted XML)', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch({ 'https://acme.test/sitemap.xml': { status: 200, body: sitemapIndex(['http://169.254.169.254/latest']) } });
  const [o] = await new CompetitorIntelligenceEngine([COMP], db, { fetchImpl: f }).pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_FAILED');
  assert.match(o.error!, /outside acme\.test/);
  assert.equal(f.calls.length, 1);
});

test('sitemap: a child failure fails the whole poll and keeps the previous baseline', async () => {
  const db = new SeoDatabase(':memory:');
  let broken = false;
  const engine = mk(db, {
    'https://acme.test/sitemap.xml': { status: 200, body: sitemapIndex(['https://acme.test/s1.xml']) },
    'https://acme.test/s1.xml': () => (broken ? { status: 500 } : { status: 200, body: urlset(['https://acme.test/1']) })
  });
  await engine.pollCompetitorSitemaps('t1');
  broken = true;
  const [o] = await engine.pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_FAILED');
  assert.deepEqual(db.getCompetitorSitemapSnapshot('t1', 'c1', COMP.sitemapUrl!)!.urls, ['https://acme.test/1']);
});

for (const [label, body] of [
  ['not XML at all', '<html><body>Access denied</body></html>'],
  ['truncated document', '<urlset><url><loc>https://acme.test/a</loc></url>'],
  ['plain text', 'hello']
] as const) {
  test(`sitemap: malformed XML (${label}) is POLL_FAILED, never POLL_OK`, async () => {
    const db = new SeoDatabase(':memory:');
    const [o] = await mk(db, { 'https://acme.test/sitemap.xml': { status: 200, body } }).pollCompetitorSitemaps('t1');
    assert.equal(o.status, 'POLL_FAILED');
    assert.match(o.error!, /malformed/);
    assert.equal(o.provenance, '[NOT AVAILABLE]');
    assert.equal(db.getCompetitorSitemapSnapshot('t1', 'c1', COMP.sitemapUrl!), undefined, 'failed poll must not create a baseline');
  });
}

test('sitemap: HTTP error is POLL_FAILED with the status recorded', async () => {
  const db = new SeoDatabase(':memory:');
  const [o] = await mk(db, { 'https://acme.test/sitemap.xml': { status: 503 } }).pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_FAILED');
  assert.equal(o.httpStatus, 503);
});

test('sitemap: network error (DNS/connect) is POLL_FAILED', async () => {
  const db = new SeoDatabase(':memory:');
  const [o] = await mk(db, { 'https://acme.test/sitemap.xml': { throw: Object.assign(new TypeError('fetch failed'), { cause: { code: 'ENOTFOUND' } }) } }).pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_FAILED');
  assert.match(o.error!, /ENOTFOUND/);
});

test('sitemap: timeout is POLL_FAILED', async () => {
  const db = new SeoDatabase(':memory:');
  const [o] = await mk(db, { 'https://acme.test/sitemap.xml': { hang: true } }, [COMP], 50).pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_FAILED');
  assert.match(o.error!, /timeout/);
});

test('sitemap: empty sitemap is DEGRADED, keeps the baseline and reports no mass removal', async () => {
  const db = new SeoDatabase(':memory:');
  let body = urlset(['https://acme.test/a', 'https://acme.test/b']);
  const engine = mk(db, { 'https://acme.test/sitemap.xml': () => ({ status: 200, body }) });
  await engine.pollCompetitorSitemaps('t1');
  body = urlset([]);
  const [o] = await engine.pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'DEGRADED');
  assert.equal(o.totalUrls, 0);
  assert.deepEqual(o.removedUrls, []);
  assert.equal(db.getCompetitorSitemapSnapshot('t1', 'c1', COMP.sitemapUrl!)!.urls.length, 2);
});

test('sitemap: one failing competitor does not abort the others', async () => {
  const db = new SeoDatabase(':memory:');
  const c2: CompetitorConfig = { ...COMP, competitorId: 'c2', domain: 'beta.test', sitemapUrl: 'https://beta.test/sitemap.xml' };
  const obs = await mk(db, {
    'https://acme.test/sitemap.xml': { status: 500 },
    'https://beta.test/sitemap.xml': { status: 200, body: urlset(['https://beta.test/x']) }
  }, [COMP, c2]).pollCompetitorSitemaps('t1');
  assert.deepEqual(obs.map(o => o.status), ['POLL_FAILED', 'POLL_OK']);
});

test('sitemap: tenant isolation — baselines and observations never cross tenants', async () => {
  const db = new SeoDatabase(':memory:');
  let body = urlset(['https://acme.test/a']);
  const engine = mk(db, { 'https://acme.test/sitemap.xml': () => ({ status: 200, body }) });
  await engine.pollCompetitorSitemaps('tenant-A');
  body = urlset(['https://acme.test/a', 'https://acme.test/new']);
  const [b] = await engine.pollCompetitorSitemaps('tenant-B');
  assert.equal(b.diffedAgainstPrevious, false, 'tenant B must not diff against tenant A baseline');
  assert.deepEqual(b.newlyDiscoveredUrls, []);
  assert.equal(b.tenantId, 'tenant-B');
  assert.equal(db.getLatestCompetitorSitemapObservations('tenant-A').length, 1);
  assert.equal(db.getLatestCompetitorSitemapObservations('tenant-A')[0].totalUrls, 1);
  assert.equal(db.getCompetitorSitemapSnapshot('tenant-A', 'c1', COMP.sitemapUrl!)!.urls.length, 1);
});

test('competitor gaps: with no rank provider, gaps are NOT AVAILABLE and nothing is persisted or invented', async () => {
  const db = new SeoDatabase(':memory:');
  const engine = mk(db, { 'https://acme.test/sitemap.xml': { status: 200, body: urlset(['https://acme.test/a']) } });
  const report = await engine.generateReport('t1', ['some query']);
  assert.equal(report.keywordGapsStatus, 'NOT_AVAILABLE');
  assert.deepEqual(report.keywordGaps, []);
  assert.equal(db.getCompetitorKeywordGaps('t1').length, 0);
  assert.equal(report.backlinkStatus.status, 'NOT AVAILABLE');
  assert.ok(!('domainAuthority' in (report as any)));
});

test('competitor gaps: provider ranks are recorded with provenance; own rank is never defaulted', async () => {
  const db = new SeoDatabase(':memory:');
  const engine = new CompetitorIntelligenceEngine([COMP], db, {
    fetchImpl: fakeFetch({ 'https://acme.test/sitemap.xml': { status: 200, body: urlset(['https://acme.test/a']) } }),
    rankProvider: { name: 'TEST', fetchCompetitorRank: async () => ({ rank: 7, provider: 'TEST', observedAt: '2026-01-01T00:00:00.000Z' }) }
  });
  const { gaps } = await engine.compareKeywordCoverage('t1', ['untracked query']);
  assert.equal(gaps[0].competitorRank, 7);
  assert.equal(gaps[0].sanoceaRank, null, 'no persisted own rank -> null, not a default');
  assert.equal(gaps[0].gapStatus, 'GAP_OPPORTUNITY');
  assert.equal(db.getCompetitorKeywordGaps('t2').length, 0);
});

test('sitemap: real-world Yoast shape (xml-stylesheet PI before root, generator comment after) parses; a truncated one still fails', async () => {
  const yoast = (body: string) => `<?xml version="1.0" encoding="UTF-8"?><?xml-stylesheet type="text/xsl" href="//acme.test/main-sitemap.xsl"?>\n${body}\n<!-- XML Sitemap generated by Yoast SEO -->`;
  const db = new SeoDatabase(':memory:');
  const engine = mk(db, {
    'https://acme.test/sitemap.xml': { status: 200, body: yoast('<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://acme.test/page-sitemap.xml</loc><lastmod>2026-09-19T05:26:37+00:00</lastmod></sitemap></sitemapindex>') },
    'https://acme.test/page-sitemap.xml': { status: 200, body: yoast('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://acme.test/a</loc></url></urlset>') }
  });
  const [o] = await engine.pollCompetitorSitemaps('t1');
  assert.equal(o.status, 'POLL_OK');
  assert.equal(o.totalUrls, 1);
  const bad = await mk(new SeoDatabase(':memory:'), { 'https://acme.test/sitemap.xml': { status: 200, body: '<urlset><url><loc>https://acme.test/a</loc></url><!-- cut off' } }).pollCompetitorSitemaps('t1');
  assert.equal(bad[0].status, 'POLL_FAILED');
});
