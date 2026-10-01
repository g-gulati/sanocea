import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { BingWebmasterCollector, parseAspNetDate, BING_POSITION_PROVENANCE } from '../src/search-intel/bingWebmaster.js';
import { fakeFetch } from './helpers/fakeHttp.js';

const SITE = 'https://www.example.test/';
const KEY = 'SECRETKEY123';
const u = (m: string) => `https://ssl.bing.com/webmaster/api.svc/json/${m}?apikey=${KEY}&siteUrl=${encodeURIComponent(SITE)}`;
const ok = (body: any) => ({ status: 200, body: JSON.stringify(body) });
const d = (ms: number) => `/Date(${ms})/`;

test('bing: parses ASP.NET dates incl. offsets; rejects junk', () => {
  assert.equal(parseAspNetDate('/Date(1699920000000)/'), '2023-11-14');
  assert.equal(parseAspNetDate('/Date(1699920000000-0700)/'), '2023-11-14');
  assert.equal(parseAspNetDate('2023-11-14'), null);
  assert.equal(parseAspNetDate(undefined), null);
});

test('bing: no API key => NOT AVAILABLE, no request made', async () => {
  const f = fakeFetch({});
  const r = await new BingWebmasterCollector(new SeoDatabase(':memory:'), { apiKey: '', fetchImpl: f }).collect('t1', SITE);
  assert.equal(r.status, 'NOT_AVAILABLE');
  assert.match(r.unavailable!.reason, /BING_WEBMASTER_API_KEY/);
  assert.equal(f.calls.length, 0);
});

test('bing: stores per-query positions and link counts; skips rows without impressions/position', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch({
    [u('GetQueryStats')]: ok({ d: [
      { Query: 'alpha', Date: d(1699920000000), AvgImpressionPosition: 4.5, AvgClickPosition: 3, Impressions: 20, Clicks: 2 },
      { Query: 'alpha', Date: d(1700006400000), AvgImpressionPosition: 3.5, Impressions: 10, Clicks: 1 },
      { Query: 'nopos', Date: d(1699920000000), AvgImpressionPosition: -1, Impressions: 5, Clicks: 0 },
      { Query: 'noimpr', Date: d(1699920000000), AvgImpressionPosition: 2, Impressions: 0, Clicks: 0 }] }),
    [u('GetLinkCounts')]: ok({ d: { Links: [{ Url: 'https://www.example.test/', Count: 7 }, { Url: 'https://www.example.test/x', Count: 2 }] } })
  });
  const c = new BingWebmasterCollector(db, { apiKey: KEY, fetchImpl: f });
  const r = await c.collect('t1', SITE);
  assert.equal(r.status, 'OBSERVED');
  assert.equal(r.positionRowsStored, 2);
  assert.equal(r.linkRowsStored, 2);
  const t = c.trajectories('t1', SITE);
  assert.equal(t.length, 1);
  assert.equal(t[0].key, 'alpha');
  assert.equal(t[0].movementSinceStart, 1);
  assert.equal(t[0].provenance, BING_POSITION_PROVENANCE);
  assert.equal(c.linkCounts('t1', SITE).rows[0].inboundLinks, 7);
  assert.equal(c.linkCounts('t1', SITE).scope, 'inbound links to pages of our own site only');
});

test('bing: tenant isolation', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch({ [u('GetQueryStats')]: ok({ d: [{ Query: 'a', Date: d(1699920000000), AvgImpressionPosition: 2, Impressions: 3, Clicks: 0 }] }), [u('GetLinkCounts')]: ok({ d: { Links: [] } }) });
  const c = new BingWebmasterCollector(db, { apiKey: KEY, fetchImpl: f });
  await c.collect('A', SITE);
  assert.equal(c.trajectories('A', SITE).length, 1);
  assert.equal(c.trajectories('B', SITE).length, 0);
});

for (const [label, routes] of [
  ['HTTP 401 on both', { [u('GetQueryStats')]: { status: 401 }, [u('GetLinkCounts')]: { status: 401 } }],
  ['network error', { [u('GetQueryStats')]: { throw: new TypeError('fetch failed') }, [u('GetLinkCounts')]: { throw: new TypeError('fetch failed') } }],
  ['unrecognised shapes', { [u('GetQueryStats')]: ok({ unexpected: true }), [u('GetLinkCounts')]: ok({ nope: 1 }) }],
  ['API error object', { [u('GetQueryStats')]: ok({ ErrorCode: 3, Message: `bad key ${KEY}` }), [u('GetLinkCounts')]: ok({ ErrorCode: 3, Message: 'bad key' }) }]
] as const) {
  test(`bing: ${label} fails closed, stores nothing and never leaks the API key`, async () => {
    const db = new SeoDatabase(':memory:');
    const r = await new BingWebmasterCollector(db, { apiKey: KEY, fetchImpl: fakeFetch(routes as any) }).collect('t1', SITE);
    assert.equal(r.status, 'NOT_AVAILABLE');
    assert.ok(!JSON.stringify(r).includes(KEY), 'API key must never appear in results');
    assert.equal(db.getBingPositionObservations('t1', SITE).length, 0);
  });
}

test('bing: one endpoint failing yields a partial result with the failure disclosed', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch({ [u('GetQueryStats')]: ok({ d: [{ Query: 'a', Date: d(1699920000000), AvgImpressionPosition: 2, Impressions: 3, Clicks: 0 }] }), [u('GetLinkCounts')]: { status: 500 } });
  const r = await new BingWebmasterCollector(db, { apiKey: KEY, fetchImpl: f }).collect('t1', SITE);
  assert.equal(r.status, 'OBSERVED');
  assert.ok(r.notes.some(n => /GetLinkCounts: HTTP 500/.test(n)));
});

// ── Live-verified behaviour (sanocea.com, 2026-10-01): property detection, empty-but-valid answers, crawl/index evidence ──
const APEX = 'https://sanocea.com/';
const ua = (m: string, extra = '') => `https://ssl.bing.com/webmaster/api.svc/json/${m}?apikey=${KEY}&siteUrl=${encodeURIComponent(APEX)}${extra}`;
const emptyRoutes = (over: Record<string, any> = {}) => ({
  [ua('GetQueryStats')]: ok({ d: [] }), [ua('GetLinkCounts')]: ok({ d: { Links: [], TotalPages: 0 } }), [ua('GetPageStats')]: ok({ d: [] }),
  [ua('GetCrawlStats')]: ok({ d: [] }), [ua('GetCrawlIssues')]: ok({ d: [] }), [ua('GetFeeds')]: ok({ d: [] }),
  [ua('GetUrlInfo', `&url=${encodeURIComponent(APEX)}`)]: ok({ d: { Url: APEX, DiscoveryDate: d(1789455600000), LastCrawledDate: d(1789484109000), HttpStatus: 0 } }), ...over });

test('bing: resolveSite picks the verified property for the domain whatever the www spelling', async () => {
  const f = fakeFetch({ [`https://ssl.bing.com/webmaster/api.svc/json/GetUserSites?apikey=${KEY}`]: ok({ d: [{ Url: 'https://other.test/', IsVerified: true }, { Url: APEX, IsVerified: true }, { Url: 'https://www.sanocea.com/', IsVerified: false }] }) });
  const r = await new BingWebmasterCollector(new SeoDatabase(':memory:'), { apiKey: KEY, fetchImpl: f }).resolveSite('www.sanocea.com');
  assert.equal(r.siteUrl, APEX);
  const none = await new BingWebmasterCollector(new SeoDatabase(':memory:'), { apiKey: KEY, fetchImpl: fakeFetch({ [`https://ssl.bing.com/webmaster/api.svc/json/GetUserSites?apikey=${KEY}`]: ok({ d: [{ Url: APEX, IsVerified: false }] }) }) }).resolveSite('sanocea.com');
  assert.equal(none.siteUrl, null, 'an unverified property is never used');
});

test('bing: a verified property with no data yet is OBSERVED-empty (not a failure), and URL index info is stored', async () => {
  const db = new SeoDatabase(':memory:');
  const c = new BingWebmasterCollector(db, { apiKey: KEY, fetchImpl: fakeFetch(emptyRoutes()) });
  const r = await c.collect('t1', APEX);
  assert.equal(r.status, 'OBSERVED');
  assert.equal(r.positionRowsStored + r.linkRowsStored, 0);
  assert.equal(r.extra.URL_INFO, 1);
  assert.ok(r.notes.some(n => /no data for this property yet/.test(n)) === false, 'URL info was stored, so it is not wholly empty');
  const rep = c.crawlReport('t1', APEX);
  assert.equal(rep.urlInfo[0].LastCrawledDate, '2026-09-15');
  assert.equal(rep.aiPerformance.available, false);
  assert.match(rep.aiPerformance.reason, /no API/);
});

test('bing: crawl stats, issues and sitemaps are stored as returned; rows without a key are disclosed, not silently dropped', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch(emptyRoutes({
    [ua('GetCrawlStats')]: ok({ d: [{ Date: d(1699920000000), CrawledPages: 10, Code4xx: 2 }] }),
    [ua('GetCrawlIssues')]: ok({ d: [{ Url: 'https://sanocea.com/x', HttpCode: 404, Issues: 1 }, { Nope: 1 }] }),
    [ua('GetFeeds')]: ok({ d: [{ Url: 'https://sanocea.com/sitemap.xml', Status: 'Success' }] }) }));
  const c = new BingWebmasterCollector(db, { apiKey: KEY, fetchImpl: f });
  const r = await c.collect('t1', APEX);
  assert.deepEqual([r.extra.CRAWL_STATS, r.extra.CRAWL_ISSUE, r.extra.FEED], [1, 1, 1]);
  assert.ok(r.notes.some(n => /GetCrawlIssues: 1 of 2 rows had no usable key/.test(n)));
  const rep = c.crawlReport('t1', APEX);
  assert.equal(rep.crawlIssues[0].HttpCode, 404);
  assert.equal(rep.sitemaps[0].Status, 'Success');
  assert.equal(c.crawlReport('other', APEX).provenance, '[NOT AVAILABLE]', 'tenant isolation');
});

test('bing: a submitted-but-never-crawled sitemap (live shape, 2026-10-01) shows Pending with no fake crawl date', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch(emptyRoutes({ [ua('GetFeeds')]: ok({ d: [{ Url: 'https://www.sanocea.com/sitemap.xml', Status: 'Pending', Submitted: d(1790862260071), LastCrawled: d(-11644473600000), UrlCount: 0, FileSize: 0 }] }) }));
  const c = new BingWebmasterCollector(db, { apiKey: KEY, fetchImpl: f });
  await c.collect('t1', APEX);
  const sm = c.crawlReport('t1', APEX).sitemaps[0];
  assert.equal(sm.Status, 'Pending'); assert.equal(sm.LastCrawled, null); assert.equal(sm.Submitted, '2026-10-01');
});
