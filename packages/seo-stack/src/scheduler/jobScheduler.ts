/**
 * SANOCEA SEO Stack — Persisted job scheduler
 *
 * Replaces "nextScheduledAt = now + interval with nothing behind it". Everything that makes a schedule real is
 * persisted in SQLite (WAL):
 * - `scheduled_jobs.next_run_at`: survives restarts; overdue jobs run once on the next tick (no burst catch-up).
 * - Leases: a job is claimed with a conditional UPDATE, so two ticks/processes can never run it twice. A crashed run's
 *   lease expires and its RUNNING record is marked ABANDONED.
 * - Outcomes are three-valued: OK, UNAVAILABLE (a provider/credential is missing: not a failure, retried at normal
 *   cadence, reason stored) and FAILED (threw or timed out: exponential-backoff retries up to max_attempts, then the
 *   job waits its normal interval; consecutive_failures keeps counting until the next success).
 * - `job_runs` is the execution ledger; `scheduler_heartbeats` proves the loop itself is alive.
 */

import * as os from 'node:os';
import { randomUUID } from 'node:crypto';
import { SeoDatabase } from '../persistence/seoDb.js';

export type JobOutcome = { status: 'OK' | 'UNAVAILABLE'; summary?: string; output?: unknown };

export interface JobDefinition {
  name: string;
  intervalMs: number;
  maxAttempts?: number; // consecutive failures before falling back to the normal interval (default 3)
  timeoutMs?: number; // default 30 min
  run(ctx: { tenantId: string; now: Date }): Promise<JobOutcome>;
}

export interface SchedulerOptions {
  tenantId: string;
  owner?: string;
  tickMs?: number;
  retryBaseMs?: number;
  now?: () => Date;
}

export interface TickResult { due: number; ran: number; results: Array<{ job: string; status: 'OK' | 'UNAVAILABLE' | 'FAILED'; error?: string }> }

export class JobScheduler {
  private readonly tenantId: string;
  private readonly owner: string;
  private readonly tickMs: number;
  private readonly retryBaseMs: number;
  private readonly now: () => Date;
  private defs = new Map<string, JobDefinition>();
  private timer?: NodeJS.Timeout;
  private ticking = false;

  constructor(private db: SeoDatabase, opts: SchedulerOptions) {
    this.tenantId = opts.tenantId;
    this.owner = opts.owner ?? `${os.hostname()}:${process.pid}`;
    this.tickMs = opts.tickMs ?? 30000;
    this.retryBaseMs = opts.retryBaseMs ?? 60000;
    this.now = opts.now ?? (() => new Date());
  }

  /** Registers (idempotently) a job. An existing persisted next_run_at is kept, so restarts do not reset schedules. */
  public register(def: JobDefinition): void {
    this.defs.set(def.name, def);
    const nowIso = this.now().toISOString();
    this.db.raw.prepare(`
      INSERT INTO scheduled_jobs (tenant_id, job_name, interval_ms, next_run_at, max_attempts, registered_at)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(tenant_id, job_name) DO UPDATE SET interval_ms = excluded.interval_ms, max_attempts = excluded.max_attempts
    `).run(this.tenantId, def.name, def.intervalMs, nowIso, def.maxAttempts ?? 3, nowIso);
  }

  public start(): void {
    if (this.timer) return;
    void this.tick();
    this.timer = setInterval(() => void this.tick(), this.tickMs);
  }

  public stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = undefined;
  }

  /** Runs every due job once. Safe to call concurrently; overlapping ticks in one process are skipped. */
  public async tick(): Promise<TickResult> {
    const result: TickResult = { due: 0, ran: 0, results: [] };
    if (this.ticking) return result;
    this.ticking = true;
    try {
      const now = this.now();
      const nowIso = now.toISOString();
      const due = this.db.raw.prepare(`
        SELECT job_name FROM scheduled_jobs WHERE tenant_id = ? AND enabled = 1 AND next_run_at <= ? AND (lease_expires_at IS NULL OR lease_expires_at < ?)
        ORDER BY next_run_at ASC
      `).all(this.tenantId, nowIso, nowIso) as Array<{ job_name: string }>;
      result.due = due.length;

      for (const { job_name } of due) {
        const def = this.defs.get(job_name);
        if (!def) continue;
        const r = await this.runOne(def);
        if (r) { result.ran++; result.results.push(r); }
      }
      this.db.raw.prepare(`INSERT INTO scheduler_heartbeats (owner, tick_at, due_jobs, ran_jobs) VALUES (?, ?, ?, ?)`).run(this.owner, nowIso, result.due, result.ran);
      this.db.raw.prepare(`DELETE FROM scheduler_heartbeats WHERE id <= (SELECT MAX(id) FROM scheduler_heartbeats) - 500`).run();
      return result;
    } finally {
      this.ticking = false;
    }
  }

  private async runOne(def: JobDefinition): Promise<{ job: string; status: 'OK' | 'UNAVAILABLE' | 'FAILED'; error?: string } | null> {
    const raw = this.db.raw;
    const startedAt = this.now();
    const timeoutMs = def.timeoutMs ?? 30 * 60 * 1000;
    const leaseUntil = new Date(startedAt.getTime() + timeoutMs + 60000).toISOString();

    // Claim: only one claimant can flip the lease.
    const claimed = raw.prepare(`
      UPDATE scheduled_jobs SET lease_owner = ?, lease_expires_at = ?
      WHERE tenant_id = ? AND job_name = ? AND (lease_expires_at IS NULL OR lease_expires_at < ?)
    `).run(this.owner, leaseUntil, this.tenantId, def.name, startedAt.toISOString()).changes;
    if (claimed !== 1) return null;

    raw.prepare(`UPDATE job_runs SET status = 'ABANDONED', finished_at = ? WHERE tenant_id = ? AND job_name = ? AND status = 'RUNNING'`).run(startedAt.toISOString(), this.tenantId, def.name);
    const job = raw.prepare(`SELECT consecutive_failures, max_attempts, interval_ms FROM scheduled_jobs WHERE tenant_id = ? AND job_name = ?`).get(this.tenantId, def.name) as any;
    const attempt = job.consecutive_failures + 1;
    const runId = `run-${randomUUID()}`;
    raw.prepare(`INSERT INTO job_runs (run_id, tenant_id, job_name, attempt, started_at, status) VALUES (?, ?, ?, ?, ?, 'RUNNING')`).run(runId, this.tenantId, def.name, attempt, startedAt.toISOString());

    let status: 'OK' | 'UNAVAILABLE' | 'FAILED' = 'OK';
    let error: string | undefined;
    let output: unknown;
    let timeoutHandle: NodeJS.Timeout | undefined;
    try {
      const out = await Promise.race([
        def.run({ tenantId: this.tenantId, now: startedAt }),
        // Deliberately ref'd: a hung job must still be timed out even if nothing else keeps the process alive.
        new Promise<never>((_, rej) => { timeoutHandle = setTimeout(() => rej(new Error(`job timed out after ${timeoutMs}ms`)), timeoutMs); })
      ]);
      status = out.status;
      error = out.status === 'UNAVAILABLE' ? out.summary : undefined;
      output = { summary: out.summary, ...(out.output !== undefined ? { output: out.output } : {}) };
    } catch (err: any) {
      status = 'FAILED';
      error = err?.message ?? String(err);
    } finally {
      if (timeoutHandle) clearTimeout(timeoutHandle);
    }

    const finished = this.now();
    const failures = status === 'FAILED' ? job.consecutive_failures + 1 : 0;
    let nextMs = job.interval_ms;
    if (status === 'FAILED' && failures < job.max_attempts) nextMs = Math.min(this.retryBaseMs * 2 ** (failures - 1), job.interval_ms);
    const nextRunAt = new Date(finished.getTime() + nextMs).toISOString();

    raw.transaction(() => {
      raw.prepare(`UPDATE job_runs SET status = ?, finished_at = ?, error = ?, duration_ms = ?, output_json = ? WHERE run_id = ?`)
        .run(status, finished.toISOString(), error ?? null, finished.getTime() - startedAt.getTime(), output === undefined ? null : JSON.stringify(output), runId);
      raw.prepare(`
        UPDATE scheduled_jobs SET last_run_at = ?, last_status = ?, last_error = ?, consecutive_failures = ?, next_run_at = ?, lease_owner = NULL, lease_expires_at = NULL
        WHERE tenant_id = ? AND job_name = ?
      `).run(finished.toISOString(), status, error ?? null, failures, nextRunAt, this.tenantId, def.name);
    })();
    return { job: def.name, status, ...(error ? { error } : {}) };
  }

  public getNextRunAt(jobName: string): string | null {
    const r = this.db.raw.prepare(`SELECT next_run_at FROM scheduled_jobs WHERE tenant_id = ? AND job_name = ?`).get(this.tenantId, jobName) as any;
    return r?.next_run_at ?? null;
  }

  /** Persisted-only status for health endpoints. */
  public status() {
    const raw = this.db.raw;
    const hb = raw.prepare(`SELECT owner, tick_at, due_jobs, ran_jobs FROM scheduler_heartbeats ORDER BY id DESC LIMIT 1`).get() as any;
    const nowMs = this.now().getTime();
    return {
      tenantId: this.tenantId,
      loopRunning: Boolean(this.timer),
      lastHeartbeat: hb ? { owner: hb.owner, tickAt: hb.tick_at, dueJobs: hb.due_jobs, ranJobs: hb.ran_jobs, ageMs: nowMs - Date.parse(hb.tick_at) } : null,
      tickMs: this.tickMs,
      jobs: (raw.prepare(`SELECT * FROM scheduled_jobs WHERE tenant_id = ? ORDER BY job_name`).all(this.tenantId) as any[]).map(j => ({
        name: j.job_name, intervalMs: j.interval_ms, nextRunAt: j.next_run_at, lastRunAt: j.last_run_at, lastStatus: j.last_status, lastError: j.last_error,
        consecutiveFailures: j.consecutive_failures, maxAttempts: j.max_attempts, enabled: Boolean(j.enabled), overdue: Date.parse(j.next_run_at) < nowMs
      })),
      recentRuns: (raw.prepare(`SELECT run_id, job_name, attempt, started_at, finished_at, status, error, duration_ms FROM job_runs WHERE tenant_id = ? ORDER BY started_at DESC LIMIT 20`).all(this.tenantId) as any[])
        .map(r => ({ runId: r.run_id, job: r.job_name, attempt: r.attempt, startedAt: r.started_at, finishedAt: r.finished_at, status: r.status, error: r.error, durationMs: r.duration_ms }))
    };
  }
}
