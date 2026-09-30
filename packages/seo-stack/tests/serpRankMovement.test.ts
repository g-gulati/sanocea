import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { SerpObservation } from '../src/search-intel/serpTypes.js';
import { buildLiveSerpRankMovement, VERIFIED_SERP_PROVIDERS, LIVE_SERP_DEPENDENCY, verifiedSerpTrajectories } from '../src/search-intel/serpRankMovement.js';
import { SeoMonitoringWorker } from '../src/worker/seoMonitoringWorker.js';
import { AgentRosterManager, DEFAULT_AGENTS } from '../src/agents/agentRoster.js';

const obs = (o: Partial<SerpObservation> & { query: string; timestamp: string }): SerpObservation => ({
  observationId: `${o.tenantId ?? 't1'}-${o.query}-${o.timestamp}-${o.device ?? 'DESKTOP'}`, tenantId: 't1', observedUrl: 'https://example.test/', targetDomain: 'example.test',
  rank: 10, serpType: 'ORGANIC', device: 'DESKTOP', geography: 'IN', language: 'en', provider: 'TEST_PROVIDER', ...o });

const VERIFIED = new Set(['TEST_PROVIDER']);

test('guard: no SERP provider is verified in this codebase (adding one must be a deliberate, reviewed change)', () => {
  assert.equal(VERIFIED_SERP_PROVIDERS.size, 0);
});

test('live SERP rank: with no verified provider the capability is NOT AVAILABLE with the exact dependency, and no rows', () => {
  const db = new SeoDatabase(':memory:');
  const r = buildLiveSerpRankMovement(db, 't1');
  assert.equal(r.capability, 'LIVE SERP RANK MOVEMENT');
  assert.equal(r.status, 'NOT_AVAILABLE');
  assert.equal(r.provenance, '[NOT AVAILABLE]');
  assert.deepEqual(r.rows, []);
  assert.equal(r.dependency, LIVE_SERP_DEPENDENCY);
  assert.match(r.dependency!, /verified provider adapter/);
  assert.match(r.reason!, /No verified SERP provider/);
});

test('live SERP rank: rows from unverified providers (e.g. a re-introduced seed script) are ignored and counted, never shown as ranks', () => {
  const db = new SeoDatabase(':memory:');
  for (const [i, provider] of ['DATA_FOR_SEO', 'SERP_API', 'MOCK_COMPLIANT_PROVIDER', 'anything'].entries())
    db.recordSerpObservation(obs({ query: 'q' + i, rank: 42, provider, timestamp: '2026-09-30T10:00:00.000Z' }));
  const r = buildLiveSerpRankMovement(db, 't1');
  assert.equal(r.status, 'NOT_AVAILABLE');
  assert.equal(r.rows.length, 0);
  assert.equal(r.ignoredRowCount, 4);
  assert.equal(verifiedSerpTrajectories(db, 't1').length, 0);
});

test('live SERP rank: with a verified provider, Start/Previous/Current/Daily/Net delta and timestamps come only from its real observations', () => {
  const db = new SeoDatabase(':memory:');
  db.recordSerpObservation(obs({ query: 'alpha', rank: 48, timestamp: '2026-09-01T10:00:00.000Z' }));
  db.recordSerpObservation(obs({ query: 'alpha', rank: 42, timestamp: '2026-09-02T10:00:00.000Z' }));
  db.recordSerpObservation(obs({ query: 'alpha', rank: 40, timestamp: '2026-09-03T10:00:00.000Z' }));
  const r = buildLiveSerpRankMovement(db, 't1', VERIFIED);
  assert.equal(r.status, 'OBSERVED');
  assert.equal(r.provenance, '[OBSERVED: SERP PROVIDER]');
  assert.equal(r.dependency, null);
  const row = r.rows[0];
  assert.equal(row.query, 'alpha');
  assert.equal(row.startRank, 48);
  assert.equal(row.previousRank, 42);
  assert.equal(row.currentRank, 40);
  assert.equal(row.dailyDelta, 2);
  assert.equal(row.netDelta, 8);
  assert.equal(row.firstObservedAt, '2026-09-01T10:00:00.000Z');
  assert.equal(row.lastCheckedAt, '2026-09-03T10:00:00.000Z');
  assert.equal(row.observationCount, 3);
  assert.equal(row.provider, 'TEST_PROVIDER');
  assert.match(row.methodology, /device DESKTOP · geography IN · language en/);
});

test('live SERP rank: first observation shows N/A for previous and deltas; >100 stays null; never invented', () => {
  const db = new SeoDatabase(':memory:');
  db.recordSerpObservation(obs({ query: 'first', rank: 17, timestamp: '2026-09-30T10:00:00.000Z' }));
  db.recordSerpObservation(obs({ query: 'deep', rank: null, timestamp: '2026-09-30T10:00:00.000Z' }));
  const rows = buildLiveSerpRankMovement(db, 't1', VERIFIED).rows;
  const first = rows.find(r => r.query === 'first')!;
  assert.equal(first.previousRank, null);
  assert.equal(first.previousRankFormatted, 'N/A — no observation');
  assert.equal(first.dailyDelta, null);
  assert.match(first.startRankFormatted, /first observation/);
  const deep = rows.find(r => r.query === 'deep')!;
  assert.equal(deep.currentRank, null);
  assert.equal(deep.startRank, null);
});

test('live SERP rank: separate rows per device/geography; tenants are isolated', () => {
  const db = new SeoDatabase(':memory:');
  db.recordSerpObservation(obs({ query: 'q', rank: 5, device: 'DESKTOP', timestamp: '2026-09-01T00:00:00.000Z' }));
  db.recordSerpObservation(obs({ query: 'q', rank: 9, device: 'MOBILE', timestamp: '2026-09-01T00:00:00.000Z' }));
  db.recordSerpObservation(obs({ tenantId: 'other', query: 'secret', rank: 1, timestamp: '2026-09-01T00:00:00.000Z' }));
  const a = buildLiveSerpRankMovement(db, 't1', VERIFIED);
  assert.equal(a.rows.length, 2);
  assert.ok(a.rows.every(r => r.query === 'q'));
  assert.equal(buildLiveSerpRankMovement(db, 'other', VERIFIED).rows[0].query, 'secret');
  assert.equal(buildLiveSerpRankMovement(db, 'nobody', VERIFIED).status, 'NOT_AVAILABLE');
});

test('live SERP rank: GSC average positions can never populate it (separate series, separate table)', () => {
  const db = new SeoDatabase(':memory:');
  db.upsertGscPositionObservations([{ tenantId: 't1', siteUrl: 'sc-domain:example.test', dimension: 'QUERY', key: 'alpha', observedDate: '2026-09-01', position: 3.2, impressions: 50, clicks: 4, ctr: 0.08, fetchedAt: 'f' }]);
  const r = buildLiveSerpRankMovement(db, 't1', VERIFIED);
  assert.equal(r.status, 'NOT_AVAILABLE');
  assert.deepEqual(r.rows, []);
});

test('worker: /serp-trajectories reader and the live capability both ignore unverified rows (production wiring)', () => {
  const worker = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false });
  const db: SeoDatabase = (worker as any).db;
  db.recordSerpObservation(obs({ tenantId: 'sanocea', query: 'seeded', rank: 42, provider: 'DATA_FOR_SEO', timestamp: '2026-09-30T10:00:00.000Z' }));
  assert.deepEqual(worker.getSerpTrajectories(), []);
  const live = worker.getLiveSerpRankMovement();
  assert.equal(live.status, 'NOT_AVAILABLE');
  assert.equal(live.ignoredRowCount, 1);
  worker.stop();
});

test('strategist agent does not count unverified SERP rows as evidence', async () => {
  const db = new SeoDatabase(':memory:');
  db.recordSerpObservation(obs({ query: 'seeded', rank: 42, provider: 'DATA_FOR_SEO', timestamp: '2026-09-30T10:00:00.000Z' }));
  const roster = new AgentRosterManager(db, { domain: 'example.test', queries: [], keywordEngine: {} as any, aeoEngine: {} as any, geoEngine: {} as any, competitorEngine: {} as any });
  const run = await roster.executeAgent('agent-seo-strategist', 't1');
  assert.equal(run.status, 'AWAITING_PROVIDER', 'unverified rows must not count as evidence');
  assert.equal(DEFAULT_AGENTS.length, 10);
});
