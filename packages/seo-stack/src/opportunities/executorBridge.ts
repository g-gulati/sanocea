/**
 * Cross-process executor bridge: the Node worker hands an ALREADY-AUTHORISED change to the supported Python publisher
 * (packages/content_engine/seo/executor.py) and gets one JSON object back. No network, no shared database, no token: the
 * only channel is the child's stdin/stdout, and a child that fails, times out or prints anything but JSON becomes an ERROR
 * result, never an exception that could be mistaken for success.
 */
import { spawn } from 'node:child_process';

export type ExecutorStatus = 'ELIGIBLE' | 'PUBLISHED' | 'ALREADY_PUBLISHED' | 'BLOCKED' | 'UNSUPPORTED' | 'OBSERVED' | 'ROLLED_BACK' | 'ROLLBACK_UNAVAILABLE' | 'ERROR';
export interface ExecutorResult { status: ExecutorStatus; reason?: string; blocked_by?: string[]; change_id?: string; receipt?: Record<string, any>; facts?: any[]; observable?: boolean; unobservable?: string[]; [k: string]: any }
export interface ExecutorBridge { run(command: Record<string, unknown>): Promise<ExecutorResult> }

export interface PythonBridgeOptions { python: string; cwd: string; timeoutMs?: number; env?: NodeJS.ProcessEnv }

export class PythonExecutorBridge implements ExecutorBridge {
  constructor(private opts: PythonBridgeOptions) {}

  public run(command: Record<string, unknown>): Promise<ExecutorResult> {
    return new Promise(resolve => {
      const err = (reason: string): ExecutorResult => ({ status: 'ERROR', reason });
      let out = '', errOut = '', done = false;
      const finish = (r: ExecutorResult) => { if (!done) { done = true; clearTimeout(timer); resolve(r); } };
      const child = spawn(this.opts.python, ['-m', 'packages.content_engine.seo.executor'], {
        cwd: this.opts.cwd, env: { ...process.env, ...this.opts.env, PYTHONPATH: this.opts.cwd, PYTHONDONTWRITEBYTECODE: '1' }, stdio: ['pipe', 'pipe', 'pipe']
      });
      const timer = setTimeout(() => { child.kill('SIGKILL'); finish(err(`executor timed out after ${this.opts.timeoutMs ?? 180000}ms`)); }, this.opts.timeoutMs ?? 180000);
      child.stdout.on('data', d => { out += d; });
      child.stderr.on('data', d => { errOut += d; });
      child.on('error', e => finish(err(`could not start executor: ${e.message}`)));
      child.on('close', code => {
        const line = out.trim().split('\n').filter(Boolean).pop();
        if (!line) return finish(err(`executor produced no output (exit ${code}): ${errOut.slice(-200)}`));
        try {
          const r = JSON.parse(line);
          finish(r && typeof r.status === 'string' ? r : err('executor returned an unrecognised response'));
        } catch { finish(err(`executor output was not JSON (exit ${code})`)); }
      });
      child.stdin.on('error', () => { /* child exited early; 'close' reports it */ });
      child.stdin.end(JSON.stringify(command));
    });
  }
}

export function bridgeFromEnv(env: NodeJS.ProcessEnv = process.env): PythonExecutorBridge | null {
  const python = env.SEO_EXECUTOR_PYTHON, cwd = env.SEO_EXECUTOR_CWD;
  return python && cwd ? new PythonExecutorBridge({ python, cwd, timeoutMs: env.SEO_EXECUTOR_TIMEOUT_MS ? Number(env.SEO_EXECUTOR_TIMEOUT_MS) : undefined }) : null;
}
