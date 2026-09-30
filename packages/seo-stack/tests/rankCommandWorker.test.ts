import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { SeoMonitoringWorker } from '../src/worker/seoMonitoringWorker.js';
import { AgentRosterManager, DEFAULT_AGENTS } from '../src/agents/agentRoster.js';
import { KeywordIntelligenceEngine, DataForSeoKeywordAdapter } from '../src/search-intel/keywordIntelligence.js';
import { AeoIntelligenceEngine, UnconfiguredAeoProvider } from '../src/search-intel/aeoIntelligence.js';
import { GeoCitationEngine, UnconfiguredGeoProvider } from '../src/search-intel/geoCitationEngine.js';
import { CompetitorIntelligenceEngine } from '../src/search-intel/competitorWorker.js';
import { fakeFetch, urlset } from './helpers/fakeHttp.js';

const COMP = [{ competitorId: 'c1', name: 'Acme', domain: 'acme.test', sitemapUrl: 'https://acme.test/sitemap.xml', trackedRoutes: [] }];

function roster(db: SeoDatabase, opts: { kwFetch?: typeof fetch; creds?: boolean; sitemapFetch?: typeof fetch } = {}) {
  const keywordEngine = new KeywordIntelligenceEngine(new DataForSeoKeywordAdapter({
    login: opts.creds ? 'l' : '', password: opts.creds ? 'p' : '', fetchImpl: opts.kwFetch ?? fakeFetch({}) }), db);
  const competitorEngine = new CompetitorIntelligenceEngine(COMP, db, { fetchImpl: opts.sitemapFetch ?? fakeFetch({}) });
  return new AgentRosterManager(db, { domain: 'sanocea.com', queries: ['q one'], keywordEngine, competitorEngine,
    aeoEngine: new AeoIntelligenceEngine(new UnconfiguredAeoProvider(), db), geoEngine: new GeoCitationEngine(new UnconfiguredGeoProvider(), db) });
}

test('roster: 10 agents registered and every one persists an execution record', async () => {
  const db = new SeoDatabase(':memory:');
  const r = roster(db);
  assert.equal(r.getAllAgents().length, 10);
  assert.equal(DEFAULT_AGENTS.length, 10);
  const runs = await r.executeAll('t1');
  assert.equal(runs.length, 10);
  assert.equal(db.getLatestAgentRoster('t1').length, 10);
  assert.equal(new Set(runs.map(x => x.role)).size, 10);
});

test('roster: with no credentials/providers/evidence NO agent claims a result — all report AWAITING_PROVIDER or ALERT with [NOT AVAILABLE]', async () => {
  const db = new SeoDatabase(':memory:');
  const runs = await roster(db).executeAll('t1');
  for (const run of runs) {
    assert.notEqual(run.status, 'COMPLETED', `${run.agentName} must not complete without evidence: ${run.outputSummary}`);
    assert.equal(run.provenance, '[NOT AVAILABLE]', run.agentName);
    assert.equal(run.nextScheduledAt, '', 'no schedule may be claimed without an executor');
  }
  const summary = roster(db).getRosterSummary('t1');
  assert.equal(summary.totalAgentsCount, 10);
  assert.equal(summary.activeAgentsCount, 0);
});

test('roster: canned strings are gone — no agent output contains a previously hardcoded claim', async () => {
  const db = new SeoDatabase(':memory:');
  const text = (await roster(db).executeAll('t1')).map(r => r.outputSummary).join('\n');
  for (const banned of ['0 indexability traps', '100% of approved drafts', 'Verified 618px', '0 broken internal links', '39.29%', 'Verified 4 growth constraints'])
    assert.ok(!text.includes(banned), `hardcoded claim resurfaced: ${banned}`);
});

test('roster: keyword + competitive agents produce real, evidence-backed results when providers respond', async () => {
  const db = new SeoDatabase(':memory:');
  const kwFetch = fakeFetch({ 'https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live': {
    status: 200, body: JSON.stringify({ status_code: 20000, tasks: [{ status_code: 20000, result: [{ keyword: 'q one', search_volume: 900, cpc: 3, competition_index: 40 }] }] }) } });
  const sitemapFetch = fakeFetch({ 'https://acme.test/sitemap.xml': { status: 200, body: urlset(['https://acme.test/a']) } });
  const r = roster(db, { creds: true, kwFetch, sitemapFetch });
  const kw = await r.executeAgent('agent-keyword-researcher', 't1');
  assert.equal(kw.status, 'COMPLETED');
  assert.equal(kw.provenance, '[OBSERVED: KEYWORD PROVIDER]');
  assert.match(kw.outputSummary, /900/);
  const ci = await r.executeAgent('agent-competitive-intel', 't1');
  assert.equal(ci.status, 'COMPLETED');
  assert.equal(ci.provenance, '[OBSERVED: SITEMAP FETCH]');
  assert.match(ci.outputSummary, /keyword gaps NOT AVAILABLE/);
});

test('roster: competitive agent raises ALERT when every sitemap poll fails', async () => {
  const db = new SeoDatabase(':memory:');
  const run = await roster(db, { sitemapFetch: fakeFetch({ 'https://acme.test/sitemap.xml': { status: 500 } }) }).executeAgent('agent-competitive-intel', 't1');
  assert.equal(run.status, 'ALERT');
  assert.equal((run.details as any).failed, 1);
});

test('roster: an agent that throws is recorded as ALERT, and the rest still run', async () => {
  const db = new SeoDatabase(':memory:');
  const r = new AgentRosterManager(db, {} as any, [
    { id: 'a1', name: 'Boom', role: 'SEO_STRATEGIST', run: async () => { throw new Error('kaboom'); } },
    { id: 'a2', name: 'Fine', role: 'KEYWORD_RESEARCHER', run: async () => ({ status: 'COMPLETED', currentTask: 't', outputSummary: 'ok', provenance: '[CALCULATED]' }) }
  ]);
  const runs = await r.executeAll('t1');
  assert.equal(runs[0].status, 'ALERT');
  assert.match(runs[0].outputSummary, /kaboom/);
  assert.equal(runs[1].status, 'COMPLETED');
});

test('roster: analytics agent reads the persisted GSC snapshot and the technical agent reads a real heartbeat; tenants are isolated', async () => {
  const db = new SeoDatabase(':memory:');
  db.saveGscSnapshot('tenant-A', { snapshotId: 's1', siteUrl: 'sc-domain:x', dateRange: { startDate: '2026-01-01', endDate: '2026-01-28' },
    totalClicks: 11, totalImpressions: 28, averageCtr: 0.3929, averagePosition: 2.43, queryRows: [], pageRows: [], capturedAt: '2026-01-29T00:00:00.000Z' });
  db.recordHeartbeat({ tenantId: 'tenant-A', domain: 'x', timestamp: '2026-01-29T00:00:00.000Z', tier: 'tier1', status: 'ok', changeCount: 3, durationMs: 12 });
  const r = roster(db);
  const a = await r.executeAgent('agent-analytics-manager', 'tenant-A');
  assert.equal(a.status, 'COMPLETED');
  assert.match(a.outputSummary, /11 clicks \/ 28 impressions, CTR 39\.29%, avg position 2\.43/);
  assert.equal((await r.executeAgent('agent-technical-seo', 'tenant-A')).details!.changeCount, 3);
  assert.equal((await r.executeAgent('agent-analytics-manager', 'tenant-B')).status, 'AWAITING_PROVIDER');
  assert.equal((await r.executeAgent('agent-technical-seo', 'tenant-B')).status, 'AWAITING_PROVIDER');
});

test('worker: production defaults fail closed and GET readers never call providers', async () => {
  const dbPath = ':memory:';
  const kwFetch = fakeFetch({});
  const sitemapFetch = fakeFetch({ 'https://acme.test/sitemap.xml': { status: 200, body: urlset(['https://acme.test/a']) } });
  const worker = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath, enableTier1: false, enableTier2: false, enableTier3: false,
    rankCommand: { keywordProvider: new DataForSeoKeywordAdapter({ login: '', password: '', fetchImpl: kwFetch }), competitors: COMP,
      competitorOptions: { fetchImpl: sitemapFetch }, trackedQueries: ['q one'] } });

  const before = sitemapFetch.calls.length;
  const kw0 = await worker.getKeywordReport(); await worker.getAeoReport(); await worker.getGeoReport(); await worker.getCompetitorReport(); await worker.getAgentRoster();
  assert.equal(sitemapFetch.calls.length, before, 'GET readers must not poll competitors');
  assert.equal(kwFetch.calls.length, 0);
  assert.equal(kw0.provenance, '[NOT AVAILABLE]');

  const res = await worker.runRankCommandIntelligence();
  assert.equal(sitemapFetch.calls.length, 1, 'one sync = exactly one sitemap fetch');
  assert.equal(res.keywords.observedKeywordsCount, 0);
  assert.equal(res.aeo.observations.length, 0);
  assert.equal(res.geo.observations.length, 0);
  assert.equal(res.competitors.sitemapObservations[0].status, 'POLL_OK');
  assert.equal(res.competitors.keywordGapsStatus, 'NOT_AVAILABLE');
  assert.equal(res.agents.roster.length, 10);

  const h = worker.getHealth().rankCommand!;
  assert.equal(h.keywordObservationsCount, 0);
  assert.equal(h.aeoObservationsCount, 0);
  assert.equal(h.geoCitationsCount, 0);
  assert.equal(h.registeredAgentsCount, 10);
  assert.equal(h.activeAgentsCount, 1, 'only competitive intel completed (real sitemap poll); the strategist runs first in the cycle and saw no evidence yet');
  worker.stop();
});

// ── Scheduler integration ────────────────────────────────────────────────────

import { gzipSync } from 'node:zlib';
import { ccDomainRanksUrl } from '../src/search-intel/commonCrawlGraph.js';

test('worker+scheduler: one tick executes every scheduled job with honest outcomes (no creds/model/live GSC => UNAVAILABLE, real sitemap+authority => OK)', async () => {
  const sitemapFetch = fakeFetch({ 'https://acme.test/sitemap.xml': { status: 200, body: urlset(['https://acme.test/a']) } });
  const REL = 'cc-main-test';
  const authorityFetch = fakeFetch({ [ccDomainRanksUrl(REL)]: { status: 200, body: gzipSync('#harmonicc_pos\t#harmonicc_val\t#pr_pos\t#pr_val\t#host_rev\t#n_hosts\n5\t1.0\t6\t0.1\ttest.acme\t3\n'), headers: { 'last-modified': 'x' } } });
  const worker = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false,
    rankCommand: { keywordProvider: new DataForSeoKeywordAdapter({ login: '', password: '', fetchImpl: fakeFetch({}) }), competitors: COMP, competitorOptions: { fetchImpl: sitemapFetch },
      trackedQueries: ['q one'], bingApiKey: '', authorityFetch, authorityRelease: REL, modelHarness: { model: '' } },
    scheduler: { retryBaseMs: 1 } });
  const t = await worker.scheduler.tick();
  assert.equal(t.due, 5);
  assert.equal(t.ran, 5);
  const by = Object.fromEntries(t.results.map(r => [r.job, r]));
  assert.equal(by['rankcommand-agents'].status, 'OK');
  assert.equal(by['gsc-position'].status, 'UNAVAILABLE', 'no service account => not live');
  assert.equal(by['bing-webmaster'].status, 'UNAVAILABLE');
  assert.equal(by['model-visibility'].status, 'UNAVAILABLE');
  assert.equal(by['authority-graph'].status, 'OK');
  assert.equal(sitemapFetch.calls.length, 1, 'the agents job polled the competitor sitemap exactly once');

  const st = worker.getSchedulerStatus();
  assert.equal(st.lastHeartbeat!.ranJobs, 5);
  assert.ok(st.jobs.every(j => Date.parse(j.nextRunAt) > Date.now()), 'every job has a persisted future next_run_at');
  assert.equal(worker.getAuthority().rows.length, 2);
  assert.equal(worker.getAuthority().rows.find(r => r.domain === 'sanocea.com')!.inGraph, false);
  assert.equal(worker.getBingReport().configured, false);
  assert.equal(worker.getHealth().scheduler!.jobs.length, 5);

  // Roster now carries the REAL persisted next-run time, not a fabricated one.
  const roster = await worker.getAgentRoster();
  const nextAgents = st.jobs.find(j => j.name === 'rankcommand-agents')!.nextRunAt;
  assert.ok(roster.roster.length === 10 && roster.roster.every(r => r.nextScheduledAt === nextAgents));
  worker.stop();
});

test('worker+scheduler: a failing provider job is retried with backoff, not silently swallowed', async () => {
  const worker = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false,
    rankCommand: { competitors: COMP, competitorOptions: { fetchImpl: fakeFetch({}) }, bingApiKey: 'K', bingFetch: fakeFetch({}), authorityRelease: 'cc-x', authorityFetch: fakeFetch({}) },
    scheduler: { retryBaseMs: 60000 } });
  const t = await worker.scheduler.tick();
  const by = Object.fromEntries(t.results.map(r => [r.job, r]));
  assert.equal(by['bing-webmaster'].status, 'FAILED', 'key configured but API failing is a failure, unlike a missing key');
  assert.equal(by['authority-graph'].status, 'FAILED');
  const st = worker.getSchedulerStatus();
  assert.equal(st.jobs.find(j => j.name === 'bing-webmaster')!.consecutiveFailures, 1);
  assert.ok(Date.parse(st.jobs.find(j => j.name === 'bing-webmaster')!.nextRunAt) - Date.now() < 70000, 'retry is scheduled soon, not a day away');
  worker.stop();
});

test('worker: GSC summary is persisted-only and states whether the worker is live (fixtures must not read as live-verified)', () => {
  const worker = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false });
  assert.equal(worker.getGscSummary().snapshot, null);
  assert.equal(worker.getGscSummary().provenance, '[NOT AVAILABLE]');
  (worker as any).db.saveGscSnapshot('sanocea', { snapshotId: 's1', siteUrl: 'sc-domain:sanocea.com', dateRange: { startDate: '2026-09-02', endDate: '2026-09-30' },
    totalClicks: 11, totalImpressions: 28, averageCtr: 0.392857, averagePosition: 2.428571, queryRows: [], pageRows: [], capturedAt: '2026-09-30T08:15:17.165Z' });
  const g = worker.getGscSummary();
  assert.equal(g.live, false, 'no service account in this test => not live');
  assert.equal(g.snapshot!.totalImpressions, 28);
  assert.equal(g.snapshot!.totalClicks, 11);
  worker.stop();
});

test('worker: without live GSC and without a supplied snapshot, tier 2 fabricates and persists NOTHING (no hardcoded baseline can reach the tables)', async () => {
  const worker = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false });
  const db: SeoDatabase = (worker as any).db;
  const r = await worker.runTier2();
  assert.equal(r.status, 'unavailable');
  assert.match(r.reason!, /not connected in live mode/);
  assert.equal(r.snapshotId, '');
  assert.equal(db.getGscSnapshotsForTenant('sanocea').length, 0, 'no snapshot may be persisted');
  assert.equal(worker.getGscSummary().snapshot, null);
  assert.equal(worker.getGscSummary().provenance, '[NOT AVAILABLE]');
  // the old fabricated baseline's signature values must not exist anywhere
  const raw = (db as any).raw as import('better-sqlite3').Database;
  assert.equal((raw.prepare(`SELECT COUNT(*) AS n FROM gsc_queries`).get() as any).n, 0);
  worker.stop();
});

test('agent: with no real GSC snapshot the analytics agent reports AWAITING_PROVIDER (fixture data is never presented as observed)', async () => {
  const worker = new SeoMonitoringWorker({ tenantId: 'sanocea', domain: 'www.sanocea.com', dbPath: ':memory:', enableTier1: false, enableTier2: false, enableTier3: false });
  await worker.runTier2();
  const run = await (worker as any).agentRoster.executeAgent('agent-analytics-manager', 'sanocea');
  assert.equal(run.status, 'AWAITING_PROVIDER');
  assert.equal(run.provenance, '[NOT AVAILABLE]');
  worker.stop();
});
