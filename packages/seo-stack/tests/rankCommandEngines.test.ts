import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { AeoIntelligenceEngine, AeoSerpProvider, UnconfiguredAeoProvider } from '../src/search-intel/aeoIntelligence.js';
import { GeoCitationEngine, GeoCitationProvider, UnconfiguredGeoProvider } from '../src/search-intel/geoCitationEngine.js';
import { AeoObservation, GeoCitationObservation } from '../src/search-intel/rankCommandTypes.js';

const aeoObs = (over: Partial<AeoObservation>): AeoObservation => ({
  observationId: 'a-' + Math.random(), tenantId: 'WRONG', query: 'q', targetDomain: 'sanocea.com',
  hasFeaturedSnippet: false, featuredSnippetOwner: null, isFeaturedSnippetOwned: false, featuredSnippetText: null,
  hasPeopleAlsoAsk: false, paaQuestions: [], hasAiOverview: false, aiOverviewCitations: [], isAiOverviewOwned: false,
  provider: 'TEST_SERP', provenance: '[OBSERVED: SERP PROVIDER]', timestamp: '2026-01-01T00:00:00.000Z', ...over });

const geoObs = (query: string, engine: any, over: Partial<GeoCitationObservation> = {}): GeoCitationObservation => ({
  observationId: 'g-' + Math.random(), tenantId: 'WRONG', query, engine, isCited: false, citedUrl: null, snippetText: null,
  citationRank: null, targetDomain: 'sanocea.com', provider: 'TEST_GEO', provenance: '[OBSERVED: AI CITATION ENGINE]',
  timestamp: '2026-01-01T00:00:00.000Z', ...over });

test('AEO: default/unconfigured provider fails closed — nothing persisted, rates null (not 0)', async () => {
  const db = new SeoDatabase(':memory:');
  const s = await new AeoIntelligenceEngine(new UnconfiguredAeoProvider(), db).trackQueries('t1', ['a', 'b'], 'sanocea.com');
  assert.equal(s.observations.length, 0);
  assert.equal(s.unavailable.length, 2);
  assert.equal(s.featuredSnippetCaptureRate, null);
  assert.equal(s.aiOverviewOwnershipRate, null);
  assert.equal(s.provenance, '[NOT AVAILABLE]');
  assert.equal(db.getLatestAeoObservations('t1').length, 0);
});

test('AEO: provider exceptions become unavailable, not crashes or zeros', async () => {
  const p: AeoSerpProvider = { name: 'BOOM', fetchSerpFeatures: async () => { throw new Error('HTTP 502'); } };
  const s = await new AeoIntelligenceEngine(p, new SeoDatabase(':memory:')).trackQueries('t1', ['a'], 'sanocea.com');
  assert.equal(s.unavailable[0].reason, 'HTTP 502');
  assert.equal(s.observations.length, 0);
});

test('AEO: rates are computed only over observed queries; mixed availability is reported', async () => {
  const db = new SeoDatabase(':memory:');
  const p: AeoSerpProvider = { name: 'MIX', fetchSerpFeatures: async (_t, q) =>
    q === 'bad' ? { available: false, provider: 'MIX', reason: 'no data', timestamp: 'x' }
      : aeoObs({ query: q, hasFeaturedSnippet: true, featuredSnippetOwner: 'sanocea.com', isFeaturedSnippetOwned: true, hasAiOverview: true, aiOverviewCitations: ['other.com'], isAiOverviewOwned: false }) };
  const s = await new AeoIntelligenceEngine(p, db).trackQueries('t1', ['ok', 'bad'], 'sanocea.com');
  assert.equal(s.observations.length, 1);
  assert.equal(s.totalQueriesTracked, 2);
  assert.equal(s.featuredSnippetCaptureRate, 100);
  assert.equal(s.aiOverviewOwnershipRate, 0, 'AI Overview observed and not owned is a real 0, unlike an unobserved query');
  assert.equal(s.observations[0].tenantId, 't1');
});

test('AEO: tenant isolation on persistence and on persisted-only summary', async () => {
  const db = new SeoDatabase(':memory:');
  const p: AeoSerpProvider = { name: 'T', fetchSerpFeatures: async (_t, q) => aeoObs({ query: q, hasPeopleAlsoAsk: true, paaQuestions: ['x?'] }) };
  const engine = new AeoIntelligenceEngine(p, db);
  await engine.trackQueries('tenant-A', ['q'], 'sanocea.com');
  assert.equal(engine.latestSummary('tenant-A', ['q']).observations.length, 1);
  assert.equal(engine.latestSummary('tenant-B', ['q']).observations.length, 0);
  assert.equal(engine.latestSummary('tenant-B', ['q']).provenance, '[NOT AVAILABLE]');
});

test('GEO: unconfigured provider fails closed — no "not cited" rows are fabricated', async () => {
  const db = new SeoDatabase(':memory:');
  const s = await new GeoCitationEngine(new UnconfiguredGeoProvider(), db).pollCitations('t1', ['a', 'b'], 'sanocea.com');
  assert.equal(s.observations.length, 0);
  assert.equal(s.unavailable.length, 6);
  assert.equal(s.citationRatePercent, null);
  assert.equal(s.lastPolledAt, null);
  assert.equal(s.provenance, '[NOT AVAILABLE]');
  assert.equal(db.getGeoCitationsForTenant('t1').length, 0);
});

test('GEO: records cited URL, query, provider, timestamp and observation id; distinguishes cited from checked-not-cited', async () => {
  const db = new SeoDatabase(':memory:');
  const p: GeoCitationProvider = { name: 'TEST_GEO', checkQueryCitations: async (_t, q, _d, engine) =>
    engine === 'PERPLEXITY' ? geoObs(q, engine, { isCited: true, citedUrl: 'https://www.sanocea.com/x', citationRank: 2 }) : geoObs(q, engine) };
  const s = await new GeoCitationEngine(p, db).pollCitations('t1', ['q'], 'sanocea.com', ['PERPLEXITY', 'CHATGPT_SEARCH']);
  assert.equal(s.observations.length, 2);
  assert.equal(s.totalCitationsObserved, 1);
  assert.equal(s.citationRatePercent, 50);
  const cited = db.getGeoCitationsForTenant('t1').find(o => o.isCited)!;
  assert.equal(cited.citedUrl, 'https://www.sanocea.com/x');
  assert.equal(cited.query, 'q');
  assert.equal(cited.provider, 'TEST_GEO');
  assert.ok(cited.observationId && cited.timestamp);
  assert.equal(cited.tenantId, 't1');
});

test('GEO: tenant isolation and persisted-only summary reports missing pairs as unavailable', async () => {
  const db = new SeoDatabase(':memory:');
  const p: GeoCitationProvider = { name: 'T', checkQueryCitations: async (_t, q, _d, e) => geoObs(q, e, { isCited: true, citedUrl: 'https://sanocea.com/' }) };
  const engine = new GeoCitationEngine(p, db);
  await engine.pollCitations('tenant-A', ['q'], 'sanocea.com', ['PERPLEXITY']);
  const a = engine.latestSummary('tenant-A', ['q'], ['PERPLEXITY', 'CHATGPT_SEARCH']);
  assert.equal(a.observations.length, 1);
  assert.equal(a.unavailable.length, 1, 'the un-polled engine is reported as unavailable, not as not-cited');
  assert.equal(engine.latestSummary('tenant-B', ['q'], ['PERPLEXITY']).observations.length, 0);
});
