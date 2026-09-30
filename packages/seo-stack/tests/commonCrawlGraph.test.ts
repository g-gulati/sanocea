import test from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { CommonCrawlAuthorityCollector, ccDomainRanksUrl, reverseDomain, CC_GRAPH_PROVENANCE } from '../src/search-intel/commonCrawlGraph.js';
import { fakeFetch } from './helpers/fakeHttp.js';

const REL = 'cc-main-test';
const HEADER = '#harmonicc_pos\t#harmonicc_val\t#pr_pos\t#pr_val\t#host_rev\t#n_hosts';
const FILE = [HEADER, '1\t2.9E7\t3\t0.009\tcom.facebook\t3054', '467099\t1.4155235E7\t233560\t1.1E-7\tcom.acme\t4', '688141\t1.39E7\t138807\t1.8E-7\tcom.rival\t19', '900000\t1.0E7\t500000\t1.0E-8\tin.co.example\t2'].join('\n') + '\n';
const route = (body: string | Buffer = gzipSync(FILE), extra: Record<string, string> = {}) => ({ [ccDomainRanksUrl(REL)]: { status: 200, body, headers: { 'last-modified': 'Tue, 22 Sep 2026 19:22:16 GMT', ...extra } } });

test('reverseDomain handles www, scheme, paths and multi-part TLDs', () => {
  assert.equal(reverseDomain('https://www.Acme.com/x'), 'com.acme');
  assert.equal(reverseDomain('example.co.in'), 'in.co.example');
});

test('authority: finds tracked domains, records release/method provenance, and marks absent domains not-in-graph (never zero)', async () => {
  const db = new SeoDatabase(':memory:');
  const r = await new CommonCrawlAuthorityCollector(db, { fetchImpl: fakeFetch(route()), release: REL }).collect('t1', ['www.acme.com', 'rival.com', 'example.co.in', 'newsite.com']);
  assert.equal(r.status, 'OBSERVED');
  const by = Object.fromEntries(r.results.map(x => [x.domain, x]));
  assert.equal(by['acme.com'].inGraph, true);
  assert.equal(by['acme.com'].harmonicPos, 467099);
  assert.equal(by['acme.com'].pagerankVal, 1.1e-7);
  assert.equal(by['acme.com'].nHosts, 4);
  assert.equal(by['example.co.in'].harmonicPos, 900000);
  assert.equal(by['newsite.com'].inGraph, false);
  assert.equal(by['newsite.com'].harmonicPos, null);
  assert.equal(by['newsite.com'].harmonicVal, null);
  assert.equal(by['acme.com'].provenance, CC_GRAPH_PROVENANCE);
  assert.match(by['acme.com'].methodology, /not a backlink count/);
  assert.equal(by['acme.com'].releaseId, REL);
  assert.equal(db.getDomainAuthority('t1', REL)[0].sourceLastModified, 'Tue, 22 Sep 2026 19:22:16 GMT');
  // the served rows (what the Command Centre displays) must carry the release source and dates too
  assert.equal(by['acme.com'].sourceLastModified, 'Tue, 22 Sep 2026 19:22:16 GMT');
  assert.equal(by['acme.com'].sourceUrl, ccDomainRanksUrl(REL));
  assert.ok(by['acme.com'].fetchedAt);
});

test('authority: second collect for the same release is served from persistence (no re-download)', async () => {
  const db = new SeoDatabase(':memory:');
  const f = fakeFetch(route());
  const c = new CommonCrawlAuthorityCollector(db, { fetchImpl: f, release: REL });
  await c.collect('t1', ['acme.com']);
  const again = await c.collect('t1', ['acme.com']);
  assert.equal(again.fromCache, true);
  assert.equal(f.calls.length, 1);
});

test('authority: tenant isolation', async () => {
  const db = new SeoDatabase(':memory:');
  await new CommonCrawlAuthorityCollector(db, { fetchImpl: fakeFetch(route()), release: REL }).collect('A', ['acme.com']);
  assert.equal(db.getDomainAuthority('A').length, 1);
  assert.equal(db.getDomainAuthority('B').length, 0);
});

for (const [label, r] of [
  ['HTTP 404 (release does not exist)', { status: 404 }],
  ['HTTP 500', { status: 500 }],
  ['network failure', { throw: new TypeError('fetch failed') }],
  ['unexpected header', { status: 200, body: gzipSync('#a\t#b\nx\ty\n') }],
  ['empty file', { status: 200, body: gzipSync('') }],
  ['corrupt gzip', { status: 200, body: Buffer.from('not gzip at all') }]
] as const) {
  test(`authority: ${label} fails closed and stores nothing`, async () => {
    const db = new SeoDatabase(':memory:');
    const r2 = await new CommonCrawlAuthorityCollector(db, { fetchImpl: fakeFetch({ [ccDomainRanksUrl(REL)]: r as any }), release: REL }).collect('t1', ['acme.com']);
    assert.equal(r2.status, 'NOT_AVAILABLE');
    assert.ok(r2.unavailable!.reason.length > 0);
    assert.equal(db.getDomainAuthority('t1').length, 0);
  });
}
