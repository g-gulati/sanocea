import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { DataForSeoKeywordAdapter, KeywordIntelligenceEngine } from '../src/search-intel/keywordIntelligence.js';
import { fakeFetch } from './helpers/fakeHttp.js';

const URL_ = 'https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live';
const ok = (result: any[]) => ({ status: 200, body: JSON.stringify({ status_code: 20000, tasks: [{ status_code: 20000, result }] }) });

test('keyword adapter: no credentials -> NOT AVAILABLE, no network call, no numbers', async () => {
  const f = fakeFetch({});
  const a = new DataForSeoKeywordAdapter({ login: '', password: '', fetchImpl: f });
  const obs = await a.fetchKeywordMetrics('t1', ['a b c']);
  assert.equal(f.calls.length, 0);
  assert.equal(obs[0].searchVolume, null);
  assert.equal(obs[0].provenance, '[NOT AVAILABLE]');
  assert.equal(obs[0].tenantId, 't1');
});

test('keyword adapter: parses provider response; competition comes from competition_index/100', async () => {
  const f = fakeFetch({ [URL_]: ok([{ keyword: 'Foo Bar', search_volume: 320, cpc: 1.5, competition: 'LOW', competition_index: 12 }]) });
  const a = new DataForSeoKeywordAdapter({ login: 'l', password: 'p', fetchImpl: f });
  const [o] = await a.fetchKeywordMetrics('t1', ['foo bar'], { geography: 'IN' });
  assert.equal(o.searchVolume, 320);
  assert.equal(o.cpc, 1.5);
  assert.equal(o.competition, 0.12);
  assert.equal(o.provenance, '[OBSERVED: KEYWORD PROVIDER]');
  assert.equal(o.provider, 'DATAFORSEO_LIVE');
  const sent = JSON.parse(f.calls[0].init!.body as string)[0];
  assert.equal(sent.location_name, 'India');
  assert.match(String((f.calls[0].init!.headers as any).Authorization), /^Basic /);
});

test('keyword adapter: keyword absent from provider result -> NOT AVAILABLE, never zero', async () => {
  const f = fakeFetch({ [URL_]: ok([{ keyword: 'other', search_volume: 5 }]) });
  const [o] = await new DataForSeoKeywordAdapter({ login: 'l', password: 'p', fetchImpl: f }).fetchKeywordMetrics('t1', ['missing']);
  assert.equal(o.searchVolume, null);
  assert.equal(o.provenance, '[NOT AVAILABLE]');
});

for (const [label, route] of [
  ['HTTP 401', { status: 401 }],
  ['HTTP 500', { status: 500 }],
  ['task-level error inside HTTP 200', { status: 200, body: JSON.stringify({ status_code: 20000, tasks: [{ status_code: 40501, status_message: 'Invalid Field' }] }) }],
  ['top-level API error', { status: 200, body: JSON.stringify({ status_code: 40100, status_message: 'auth' }) }],
  ['network failure', { throw: new TypeError('fetch failed') }]
] as const) {
  test(`keyword adapter: ${label} fails closed`, async () => {
    const f = fakeFetch({ [URL_]: route as any });
    const obs = await new DataForSeoKeywordAdapter({ login: 'l', password: 'p', fetchImpl: f }).fetchKeywordMetrics('t1', ['x', 'y']);
    assert.equal(obs.length, 2);
    for (const o of obs) {
      assert.equal(o.searchVolume, null);
      assert.equal(o.provenance, '[NOT AVAILABLE]');
      assert.ok(JSON.parse(o.rawJson!).error);
    }
  });
}

test('keyword adapter: timeout fails closed', async () => {
  const f = fakeFetch({ [URL_]: { hang: true } });
  const [o] = await new DataForSeoKeywordAdapter({ login: 'l', password: 'p', fetchImpl: f, timeoutMs: 40 }).fetchKeywordMetrics('t1', ['x']);
  assert.equal(o.provenance, '[NOT AVAILABLE]');
  assert.match(JSON.parse(o.rawJson!).error, /timeout/);
});

test('keyword engine: persists only OBSERVED rows, so a failed poll keeps the last real observation', async () => {
  const db = new SeoDatabase(':memory:');
  let route: any = ok([{ keyword: 'q one', search_volume: 100, cpc: 2, competition_index: 50 }]);
  const f = fakeFetch({ [URL_]: () => route });
  const engine = new KeywordIntelligenceEngine(new DataForSeoKeywordAdapter({ login: 'l', password: 'p', fetchImpl: f }), db);

  const r1 = await engine.evaluateKeywords('t1', ['q one']);
  assert.equal(r1.provenance, '[OBSERVED: KEYWORD PROVIDER]');
  assert.equal(r1.totalObservedVolume, 100);

  route = { status: 500 };
  const r2 = await engine.evaluateKeywords('t1', ['q one']);
  assert.equal(r2.provenance, '[NOT AVAILABLE]');
  assert.equal(r2.totalObservedVolume, null);

  const persisted = db.getLatestKeywordObservations('t1');
  assert.equal(persisted.length, 1);
  assert.equal(persisted[0].searchVolume, 100);
});

test('keyword engine: tenant isolation — provider-stamped tenant is overridden by the execution context', async () => {
  const db = new SeoDatabase(':memory:');
  const provider = { name: 'T', fetchKeywordMetrics: async (_t: string, qs: string[]) => qs.map(q => ({
    observationId: 'o-' + q, tenantId: 'WRONG', query: q, searchVolume: 10, cpc: 1, competition: 0.1, intent: 'UNKNOWN' as const,
    cluster: 'c', geography: 'IN', language: 'en', provider: 'T', provenance: '[OBSERVED: KEYWORD PROVIDER]' as const, timestamp: new Date().toISOString() })) };
  await new KeywordIntelligenceEngine(provider, db).evaluateKeywords('tenant-A', ['q']);
  assert.equal(db.getLatestKeywordObservations('tenant-A').length, 1);
  assert.equal(db.getLatestKeywordObservations('WRONG').length, 0);
  assert.equal(db.getLatestKeywordObservations('tenant-B').length, 0);
});

test('keyword intent is a documented heuristic: classifier rules, not provider data', () => {
  const c = KeywordIntelligenceEngine.classifyIntent;
  assert.equal(c('ecommerce operations automation'), 'COMMERCIAL');
  assert.equal(c('ecommerce inventory drift automation'), 'COMMERCIAL'); // no transactional keyword; 'automation' => commercial
  assert.equal(c('marketplace multi-channel reconciliation'), 'TRANSACTIONAL');
  assert.equal(c('shopify to amazon inventory sync india'), 'TRANSACTIONAL');
  assert.equal(c('sanocea autonomous commerce'), 'NAVIGATIONAL');
  assert.equal(c('what is inventory drift'), 'INFORMATIONAL');
  assert.equal(c('apparel catalogue'), 'UNKNOWN', 'substring "app" inside another word must not be navigational');
});

test('keyword default is zero-cost and inert: paid provider is never selected implicitly', async () => {
  const { createKeywordProviderFromEnv, UnconfiguredKeywordProvider } = await import('../src/search-intel/keywordIntelligence.js');
  // Credentials present but no explicit opt-in -> still the inert provider (no paid call can happen).
  const p = createKeywordProviderFromEnv({ DATAFORSEO_LOGIN: 'l', DATAFORSEO_PASSWORD: 'p' } as any);
  assert.ok(p instanceof UnconfiguredKeywordProvider);
  const [o] = await p.fetchKeywordMetrics('t1', ['anything']);
  assert.equal(o.searchVolume, null);
  assert.equal(o.provenance, '[NOT AVAILABLE]');
  assert.equal(createKeywordProviderFromEnv({ SEO_KEYWORD_PROVIDER: 'dataforseo' } as any).name, 'DATAFORSEO_LIVE');
});
