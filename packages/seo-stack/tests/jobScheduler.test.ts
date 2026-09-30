import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { JobScheduler, JobDefinition } from '../src/scheduler/jobScheduler.js';

function clock(start = '2026-01-01T00:00:00.000Z') {
  let t = Date.parse(start);
  return { now: () => new Date(t), advance: (ms: number) => { t += ms; }, iso: () => new Date(t).toISOString() };
}
const HOUR = 3600000;
const mk = (db: SeoDatabase, c: ReturnType<typeof clock>, tenantId = 't1', owner = 'o1') => new JobScheduler(db, { tenantId, owner, now: c.now, retryBaseMs: 60000, tickMs: 1000 });
const okJob = (name: string, counter: { n: number }, intervalMs = HOUR): JobDefinition => ({ name, intervalMs, run: async () => { counter.n++; return { status: 'OK', summary: 'done' }; } });

test('scheduler: a new job is due immediately, runs once, then waits its persisted interval', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const s = mk(db, c); const n = { n: 0 };
  s.register(okJob('j', n));
  assert.equal((await s.tick()).ran, 1);
  assert.equal(n.n, 1);
  assert.equal(s.getNextRunAt('j'), new Date(Date.parse(c.iso()) + HOUR).toISOString());
  assert.equal((await s.tick()).ran, 0, 'not due again yet');
  c.advance(HOUR - 1); assert.equal((await s.tick()).ran, 0);
  c.advance(1); assert.equal((await s.tick()).ran, 1);
  assert.equal(n.n, 2);
});

test('scheduler: next_run_at is persisted — a restart (new scheduler, same DB) does not reset or re-run early', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const n = { n: 0 };
  const s1 = mk(db, c); s1.register(okJob('j', n)); await s1.tick();
  c.advance(10 * 60000);
  const s2 = mk(db, c); s2.register(okJob('j', n));
  assert.equal((await s2.tick()).ran, 0);
  assert.equal(n.n, 1);
});

test('scheduler: overdue after downtime runs exactly once (no burst catch-up)', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const n = { n: 0 }; const s = mk(db, c);
  s.register(okJob('j', n)); await s.tick();
  c.advance(10 * HOUR);
  await s.tick(); await s.tick();
  assert.equal(n.n, 2);
});

test('scheduler: failure => exponential backoff retries, then normal interval after max attempts; success resets counter', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const s = mk(db, c);
  let fail = true; let calls = 0;
  s.register({ name: 'flaky', intervalMs: HOUR, maxAttempts: 3, run: async () => { calls++; if (fail) throw new Error('boom'); return { status: 'OK' }; } });
  await s.tick(); // failure 1 -> retry in 60s
  assert.equal(s.status().jobs[0].consecutiveFailures, 1);
  assert.equal(s.getNextRunAt('flaky'), new Date(Date.parse(c.iso()) + 60000).toISOString());
  c.advance(60000); await s.tick(); // failure 2 -> retry in 120s
  assert.equal(s.getNextRunAt('flaky'), new Date(Date.parse(c.iso()) + 120000).toISOString());
  c.advance(120000); await s.tick(); // failure 3 = max -> back to normal interval
  assert.equal(s.getNextRunAt('flaky'), new Date(Date.parse(c.iso()) + HOUR).toISOString());
  const j = s.status().jobs[0];
  assert.equal(j.lastStatus, 'FAILED'); assert.equal(j.lastError, 'boom'); assert.equal(j.consecutiveFailures, 3);
  fail = false; c.advance(HOUR); await s.tick();
  assert.equal(s.status().jobs[0].consecutiveFailures, 0);
  assert.equal(s.status().jobs[0].lastStatus, 'OK');
  assert.equal(calls, 4);
});

test('scheduler: UNAVAILABLE is not a failure — reason stored, normal cadence, no retry storm', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const s = mk(db, c);
  s.register({ name: 'bing', intervalMs: HOUR, run: async () => ({ status: 'UNAVAILABLE', summary: 'BING_WEBMASTER_API_KEY is not configured' }) });
  await s.tick();
  const j = s.status().jobs[0];
  assert.equal(j.lastStatus, 'UNAVAILABLE'); assert.match(j.lastError!, /BING_WEBMASTER_API_KEY/); assert.equal(j.consecutiveFailures, 0);
  assert.equal(s.getNextRunAt('bing'), new Date(Date.parse(c.iso()) + HOUR).toISOString());
});

test('scheduler: a hung job times out as FAILED without blocking the loop', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const s = mk(db, c);
  s.register({ name: 'hang', intervalMs: HOUR, timeoutMs: 30, run: () => new Promise(() => {}) });
  const r = await s.tick();
  assert.equal(r.results[0].status, 'FAILED');
  assert.match(r.results[0].error!, /timed out/);
});

test('scheduler: leases prevent double execution across two schedulers on one DB', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const n = { n: 0 };
  let release!: () => void; const gate = new Promise<void>(r => (release = r));
  const def: JobDefinition = { name: 'slow', intervalMs: HOUR, run: async () => { n.n++; await gate; return { status: 'OK' }; } };
  const a = mk(db, c, 't1', 'A'); const b = mk(db, c, 't1', 'B'); a.register(def); b.register(def);
  const pa = a.tick(); await new Promise(r => setImmediate(r));
  const rb = await b.tick();
  assert.equal(rb.ran, 0, 'B must not run a job A holds a lease on');
  release(); await pa;
  assert.equal(n.n, 1);
});

test('scheduler: an expired lease from a crashed run is reclaimed and the stale RUNNING record is marked ABANDONED', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const n = { n: 0 };
  const s = mk(db, c); s.register({ ...okJob('j', n), timeoutMs: 1000 });
  db.raw.prepare(`UPDATE scheduled_jobs SET lease_owner='dead', lease_expires_at=? WHERE job_name='j'`).run(new Date(Date.parse(c.iso()) + 1000).toISOString());
  db.raw.prepare(`INSERT INTO job_runs (run_id, tenant_id, job_name, attempt, started_at, status) VALUES ('stale','t1','j',1,?, 'RUNNING')`).run(c.iso());
  assert.equal((await s.tick()).ran, 0, 'lease still valid');
  c.advance(5000);
  assert.equal((await s.tick()).ran, 1);
  assert.equal((db.raw.prepare(`SELECT status FROM job_runs WHERE run_id='stale'`).get() as any).status, 'ABANDONED');
});

test('scheduler: heartbeats are recorded each tick; status is persisted-only; tenants are isolated', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const n = { n: 0 };
  const a = mk(db, c, 'A'); const b = mk(db, c, 'B'); a.register(okJob('j', n)); b.register(okJob('j', n));
  await a.tick();
  assert.equal(a.status().lastHeartbeat!.ranJobs, 1);
  assert.equal(a.status().jobs[0].lastStatus, 'OK');
  assert.equal(b.status().jobs[0].lastStatus, null, 'tenant B job untouched by tenant A tick');
  assert.equal(b.status().recentRuns.length, 0);
  assert.equal(a.status().recentRuns.length, 1);
});

test('scheduler: start() runs the loop and stop() ends it', async () => {
  const db = new SeoDatabase(':memory:'); const n = { n: 0 };
  const s = new JobScheduler(db, { tenantId: 't1', tickMs: 20 }); s.register(okJob('j', n, 30));
  s.start();
  await new Promise(r => setTimeout(r, 120));
  s.stop();
  assert.ok(n.n >= 2, `expected repeated executions, got ${n.n}`);
  const after = n.n; await new Promise(r => setTimeout(r, 80));
  assert.equal(n.n, after);
});

test('scheduler: status exposes each run\'s summary so operators see what a job actually did', async () => {
  const db = new SeoDatabase(':memory:'); const c = clock(); const s = mk(db, c);
  s.register({ name: 'j', intervalMs: HOUR, run: async () => ({ status: 'OK', summary: 'stored 20 rows' }) });
  await s.tick();
  assert.equal(s.status().recentRuns[0].summary, 'stored 20 rows');
});
