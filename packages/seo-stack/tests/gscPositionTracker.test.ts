import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { GscClient } from '../src/search-intel/gscClient.js';
import { GscAuthManager } from '../src/search-intel/gscAuth.js';
import { GscPositionTracker } from '../src/search-intel/gscPositionTracker.js';

const SITE = 'sc-domain:example.test';
type R = { keys: string[]; impressions: number; position: number; clicks?: number };

/** Live-mode GscClient with the HTTP layer faked. `data` maps joined dimensions ("date", "page,date", "query,date") to raw GSC rows. */
function liveClient(data: Record<string, R[]> | Error) {
  const auth = new GscAuthManager({ authType: 'MOCK_FIXTURE' });
  (auth as any).getAccessToken = async () => 'tok';
  const client = new GscClient(auth);
  const calls: any[] = [];
  const orig = globalThis.fetch;
  return {
    client, calls,
    install() {
      globalThis.fetch = (async (_u: any, init: any) => {
        const body = JSON.parse(init.body);
        calls.push(body);
        if (data instanceof Error) throw data;
        const all = data[body.dimensions.join(',')] ?? [];
        const rows = all.slice(body.startRow, body.startRow + body.rowLimit)
          .map(r => ({ keys: r.keys, clicks: r.clicks ?? 0, impressions: r.impressions, ctr: 0, position: r.position }));
        return new Response(JSON.stringify({ rows }), { status: 200 });
      }) as any;
    },
    restore() { globalThis.fetch = orig; }
  };
}
const withLive = async (data: Record<string, R[]> | Error, fn: (h: ReturnType<typeof liveClient>) => Promise<void>) => {
  const h = liveClient(data); h.install();
  try { await fn(h); } finally { h.restore(); }
};

test('gsc tracker: fixture-mode client is refused — nothing stored', async () => {
  const db = new SeoDatabase(':memory:');
  const client = new GscClient(new GscAuthManager({ authType: 'MOCK_FIXTURE' }), { snapshotId: 's', siteUrl: SITE, dateRange: { startDate: 'a', endDate: 'b' },
    totalClicks: 1, totalImpressions: 1, averageCtr: 1, averagePosition: 1, queryRows: [{ query: 'q', date: '2026-01-01', position: 1, impressions: 1, clicks: 0, ctr: 0 }], pageRows: [], capturedAt: 'x' });
  const r = await new GscPositionTracker(db, client).collect('t1', SITE);
  assert.equal(r.status, 'NOT_AVAILABLE');
  assert.match(r.unavailable!.reason, /fixture/);
  assert.equal(db.getGscPositionObservations('t1', SITE).length, 0);
});

test('gsc tracker: API failure stores nothing and reports the reason', async () => {
  await withLive(new Error('GSC HTTP 403'), async h => {
    const db = new SeoDatabase(':memory:');
    const r = await new GscPositionTracker(db, h.client).collect('t1', SITE);
    assert.equal(r.status, 'NOT_AVAILABLE');
    assert.match(r.unavailable!.reason, /403/);
    assert.equal(db.getGscPositionObservations('t1', SITE).length, 0);
  });
});

test('gsc tracker: mirrors the real production shape — site+page rows exist, query rows are empty (anonymized) => QUERY level NOT AVAILABLE, never approximated', async () => {
  await withLive({
    'date': [{ keys: ['2026-09-13'], impressions: 3, position: 1.33 }, { keys: ['2026-09-14'], impressions: 8, position: 3.625 }, { keys: ['2026-09-18'], impressions: 0, position: 0 }],
    'page,date': [{ keys: ['https://example.test/', '2026-09-13'], impressions: 3, position: 1.33 }],
    'query,date': []
  }, async h => {
    const db = new SeoDatabase(':memory:');
    const t = new GscPositionTracker(db, h.client);
    const r = await t.collect('t1', SITE);
    assert.equal(r.status, 'OBSERVED');
    assert.equal(r.levels.SITE.rowsStored, 2, 'the zero-impression day is a gap, not an observation');
    assert.equal(r.levels.PAGE.rowsStored, 1);
    assert.equal(r.levels.QUERY.rowsStored, 0);
    assert.match(r.levels.QUERY.note!, /anonymized/);
    assert.equal(t.trajectories('t1', SITE, 'QUERY').length, 0);
    assert.equal(t.trajectories('t1', SITE, 'SITE')[0].key, SITE);
    assert.equal(t.trajectories('t1', SITE, 'SITE')[0].observationDays, 2);
    assert.deepEqual(h.calls.map(c => c.dimensions.join(',')), ['date', 'page,date', 'query,date']);
  });
});

test('gsc tracker: re-collect is idempotent (upsert)', async () => {
  await withLive({ 'query,date': [{ keys: ['alpha', '2026-09-01'], impressions: 10, position: 9.5 }] }, async h => {
    const db = new SeoDatabase(':memory:');
    const t = new GscPositionTracker(db, h.client);
    await t.collect('t1', SITE); await t.collect('t1', SITE);
    assert.equal(db.getGscPositionObservations('t1', SITE, 'QUERY').length, 1);
  });
});

test('gsc tracker: paginates until a short page', async () => {
  await withLive({ 'query,date': [
    { keys: ['a', '2026-09-01'], impressions: 3, position: 5 }, { keys: ['b', '2026-09-01'], impressions: 3, position: 6 }, { keys: ['c', '2026-09-01'], impressions: 3, position: 7 }] }, async h => {
    const db = new SeoDatabase(':memory:');
    const r = await new GscPositionTracker(db, h.client).collect('t1', SITE, { rowLimit: 2 });
    assert.equal(r.levels.QUERY.rowsStored, 3);
    assert.equal(h.calls.filter(c => c.dimensions.includes('query')).length, 2);
  });
});

test('gsc tracker: no rows at any level => NOT_AVAILABLE with reason', async () => {
  await withLive({}, async h => {
    const r = await new GscPositionTracker(new SeoDatabase(':memory:'), h.client).collect('t1', SITE);
    assert.equal(r.status, 'NOT_AVAILABLE');
    assert.equal(r.rowsStored, 0);
  });
});

test('trajectory: first observation is a baseline; nothing is invented', () => {
  const t = GscPositionTracker.computeTrajectory('t1', SITE, 'QUERY', 'q', [{ observedDate: '2026-09-01', position: 12.3, impressions: 40, clicks: 1, fetchedAt: 'f' }])!;
  assert.equal(t.observationDays, 1);
  assert.equal(t.previous, null);
  assert.equal(t.movementSinceStart, null);
  assert.equal(t.movementSincePrevious, null);
  assert.match(t.startFormatted, /first observation/);
  assert.equal(t.previousFormatted, 'N/A — no earlier observation');
  assert.equal(t.movementFormatted, 'N/A — first observation');
  assert.equal(t.provenance, '[OBSERVED: GSC AVERAGE POSITION]');
});

test('trajectory: start -> previous -> current, positive = improved; gaps are reported, not filled', () => {
  const t = GscPositionTracker.computeTrajectory('t1', SITE, 'PAGE', 'https://example.test/', [
    { observedDate: '2026-09-10', position: 6, impressions: 30, clicks: 2, fetchedAt: 'f2' },
    { observedDate: '2026-09-01', position: 12, impressions: 20, clicks: 0, fetchedAt: 'f1' },
    { observedDate: '2026-09-05', position: 9, impressions: 25, clicks: 1, fetchedAt: 'f3' }
  ])!;
  assert.equal(t.start.date, '2026-09-01');
  assert.equal(t.previous!.date, '2026-09-05');
  assert.equal(t.current.date, '2026-09-10');
  assert.equal(t.movementSinceStart, 6);
  assert.equal(t.movementSincePrevious, 3);
  assert.equal(t.gapDaysSincePrevious, 5);
  assert.equal(t.observationDays, 3);
  assert.match(t.movementFormatted, /▲ \+6/);
  assert.equal(t.lastFetchedAt, 'f3');
});

test('trajectory: decline is negative and low-impression endpoints are flagged', () => {
  const t = GscPositionTracker.computeTrajectory('t1', SITE, 'SITE', SITE, [
    { observedDate: '2026-09-01', position: 3, impressions: 2, clicks: 0, fetchedAt: 'f' },
    { observedDate: '2026-09-02', position: 8, impressions: 50, clicks: 0, fetchedAt: 'f' }])!;
  assert.equal(t.movementSinceStart, -5);
  assert.match(t.movementFormatted, /▼ -5/);
  assert.equal(t.lowSample, true);
});

test('trajectories: tenant, property and level isolation; ordered by current impressions', () => {
  const db = new SeoDatabase(':memory:');
  const mk = (tenantId: string, siteUrl: string, dimension: 'SITE' | 'PAGE' | 'QUERY', key: string, observedDate: string, impressions: number) =>
    ({ tenantId, siteUrl, dimension, key, observedDate, position: 5, impressions, clicks: 0, ctr: 0, fetchedAt: 'f' });
  db.upsertGscPositionObservations([mk('A', SITE, 'QUERY', 'small', '2026-09-01', 3), mk('A', SITE, 'QUERY', 'big', '2026-09-01', 300),
    mk('B', SITE, 'QUERY', 'other', '2026-09-01', 9), mk('A', 'sc-domain:else.test', 'QUERY', 'x', '2026-09-01', 9), mk('A', SITE, 'PAGE', 'p', '2026-09-01', 9)]);
  const t = new GscPositionTracker(db, {} as any);
  assert.deepEqual(t.trajectories('A', SITE, 'QUERY').map(x => x.key), ['big', 'small']);
  assert.equal(t.trajectories('B', SITE, 'QUERY').length, 1);
  assert.equal(t.trajectories('C', SITE, 'QUERY').length, 0);
  assert.equal(t.trajectories('A', SITE, 'PAGE').length, 1);
});

test('trajectory: exposes every observed point in date order so a chart can draw gaps honestly', () => {
  const t = GscPositionTracker.computeTrajectory('t1', SITE, 'SITE', SITE, [
    { observedDate: '2026-09-10', position: 6, impressions: 30, clicks: 2, fetchedAt: 'f' },
    { observedDate: '2026-09-01', position: 12, impressions: 20, clicks: 0, fetchedAt: 'f' }])!;
  assert.deepEqual(t.points.map(p => p.date), ['2026-09-01', '2026-09-10']);
  assert.equal(t.points.length, t.observationDays);
  assert.equal(t.points[0].impressions, 20);
});
