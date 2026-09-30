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
