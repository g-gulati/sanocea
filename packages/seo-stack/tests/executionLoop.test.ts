import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { OpportunityEngine } from '../src/opportunities/opportunityEngine.js';
import { ExecutionLoop } from '../src/opportunities/executionLoop.js';
import { ExecutorBridge, ExecutorResult, PythonExecutorBridge } from '../src/opportunities/executorBridge.js';

const T = 'a';
const L = 'https://a.test/x', X = 'https://a.test/x/';
const PLAN = { selected: 'FIX_SITEMAP_ENTRY', why: 'w', rejected: [], investigate_next: [], candidates: [{ action: 'FIX_SITEMAP_ENTRY', addresses: 'a', preconditions: [], verification: 'v', fallback: 'ROLLBACK',
  expected_outcome: [{ kind: 'sitemap_lists', subject: X, equals: X }, { kind: 'sitemap_lists', subject: L, absent: true }, { kind: 'redirects_to', subject: X, absent: true }] }] };
const EXPECTED = PLAN.candidates[0].expected_outcome;
const OK_FACTS = [{ id: 'f1', kind: 'sitemap_lists', subject: X, value: X, source: 's' }];
const BAD_FACTS = [{ id: 'f2', kind: 'sitemap_lists', subject: L, value: L, source: 's' }, ...OK_FACTS]; // the old entry is still listed => NOT_MET
const T0 = new Date('2026-10-02T10:00:00Z');
const at = (h: number) => new Date(T0.getTime() + h * 3600_000);

/** Seeds an opportunity through the REAL policy path (authorize), so execution tests only pass for policy-approved work. */
function seed(action = 'FIX_SITEMAP_ENTRY', mode: any = 'AUTONOMOUS_SEO', id = 'OPP-1') {
  const db = new SeoDatabase(':memory:');
  const eng = new OpportunityEngine(db);
  db.handle.prepare(`INSERT INTO seo_opportunities (opportunity_id, tenant_id, type, target, dedupe_key, status, confidence, source, reason, evidence_json, recommended_action, decision_json, objective, detected_at, last_seen_at, updated_at, diagnosis_json, action_plan_json)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`).run(id, T, 'SITEMAP_URL_REDIRECTS', L, `k|${id}`, 'AWAITING_APPROVAL', 'OBSERVED', '[OBSERVED: LIVE PAGE FETCH]', 'r', JSON.stringify({ listedUrl: L, finalUrl: X }), action,
    JSON.stringify({ action, requiresApproval: true, rationale: 'because', checks: ['c'] }), 'o', T0.toISOString(), T0.toISOString(), T0.toISOString(), null, JSON.stringify(PLAN));
  eng.setAutonomyMode(T, mode, 'human:owner');
  return { db, eng, authorize: () => eng.authorize(T, id, T0.toISOString()) };
}

type Script = Partial<Record<'dry' | 'execute' | 'observe' | 'rollback', ExecutorResult | ((c: any) => ExecutorResult)>>;
function bridge(script: Script) {
  const calls: any[] = [];
  const b: ExecutorBridge = { run: async c => {
    calls.push(c);
    const k: string = c.command === 'execute' && c.dry_run ? 'dry' : String(c.command);
    const r = (script as any)[k as string];
    return typeof r === 'function' ? r(c) : r ?? { status: 'ERROR', reason: `unscripted ${k}` };
  } };
  return { b, calls, count: (k: string) => calls.filter(c => (c.command === 'execute' ? (c.dry_run ? 'dry' : 'execute') : c.command) === k).length };
}
const PUBLISHED: ExecutorResult = { status: 'PUBLISHED', change_id: 'chg_1', receipt: { action: 'FIX_SITEMAP_ENTRY', previous_release: 'r1', new_release: 'r2', changed_files: [{ path: 'sitemap.xml' }] }, source_sync: { commit: 'abcdef123456' } };
const HAPPY: Script = { dry: { status: 'ELIGIBLE', change_id: 'chg_1' }, execute: PUBLISHED, observe: { status: 'OBSERVED', observable: true, facts: OK_FACTS, expected_outcome: EXPECTED } };
const notes = (eng: OpportunityEngine) => eng.history(T, 'OPP-1').map(e => e.note);

// ── bridge process boundary ──────────────────────────────────────────────────

function fakePython(body: string) {
  const f = join(mkdtempSync(join(tmpdir(), 'bridge-')), 'py.sh');
  writeFileSync(f, `#!/bin/bash\n${body}\n`); chmodSync(f, 0o755);
  return f;
}

test('bridge: sends the command as JSON on stdin and returns the one JSON object the child prints', async () => {
  const py = fakePython('read -r line; printf \'{"status":"OBSERVED","echo":%s}\\n\' "$line"');
  const r = await new PythonExecutorBridge({ python: py, cwd: tmpdir() }).run({ command: 'observe', tenant_id: 'a' });
  assert.equal(r.status, 'OBSERVED');
  assert.deepEqual(r.echo, { command: 'observe', tenant_id: 'a' });
});

test('bridge: a crash, garbage output, no output, a missing interpreter and a hang all become ERROR results (never success, never an exception)', async () => {
  const run = (python: string, timeoutMs?: number) => new PythonExecutorBridge({ python, cwd: tmpdir(), timeoutMs }).run({ command: 'execute' });
  assert.equal((await run(fakePython('exit 3'))).status, 'ERROR');
  assert.equal((await run(fakePython('echo "Traceback (most recent call last)"; exit 1'))).status, 'ERROR');
  assert.equal((await run(fakePython('echo \'{"no_status": 1}\''))).status, 'ERROR');
  const missing = await run('/nonexistent/python');
  assert.equal(missing.status, 'ERROR'); assert.match(missing.reason!, /could not start/);
  const hung = await run(fakePython('sleep 5'), 200);
  assert.equal(hung.status, 'ERROR'); assert.match(hung.reason!, /timed out/);
});

// ── authorisation: the loop executes only what the policy authorised ─────────

test('not authorised => never executed: awaiting approval, mode lowered after approval, Class C, and unsupported Class A all leave the publisher untouched', async () => {
  // (1) never authorised
  let s = seed(); const b1 = bridge(HAPPY);
  await new ExecutionLoop(s.eng, b1.b).run(T, T0);
  assert.equal(b1.calls.length, 0); assert.equal(s.eng.get(T, 'OPP-1')!.status, 'AWAITING_APPROVAL');
  // (2) authorised, then the owner lowers the mode
  s = seed(); s.authorize(); s.eng.setAutonomyMode(T, 'RECOMMEND_ONLY', 'human:owner');
  const b2 = bridge(HAPPY);
  await new ExecutionLoop(s.eng, b2.b).run(T, T0);
  assert.equal(b2.calls.length, 0); assert.equal(s.eng.get(T, 'OPP-1')!.status, 'APPROVED');
  assert.ok(notes(s.eng).some(n => /EXECUTION_NOT_PERMITTED: the tenant mode no longer permits it/.test(n)));
  // (3) Class C approved by a human is still never run by this loop
  s = seed('CHANGE_REDIRECT'); for (const st of ['QUALIFIED', 'ACTIONABLE'] as const) void st;
  s.eng.transition(T, 'OPP-1', 'APPROVED', 'human:owner', 'ok');
  const b3 = bridge(HAPPY);
  await new ExecutionLoop(s.eng, b3.b).run(T, T0);
  assert.equal(b3.calls.length, 0);
  // (4) a Class A action the publisher does not support is also never handed over
  s = seed('UPDATE_TITLE_META'); s.authorize();
  const b4 = bridge(HAPPY);
  await new ExecutionLoop(s.eng, b4.b).run(T, T0);
  assert.equal(b4.calls.length, 0);
});

test('requests carry ids only: approval, status and mode are never sent for the executor to trust', async () => {
  const s = seed(); s.authorize(); const b = bridge(HAPPY);
  await new ExecutionLoop(s.eng, b.b).run(T, T0);
  for (const c of b.calls) for (const k of ['approval', 'mode', 'status', 'opportunity']) assert.equal(k in c, false, `${c.command} must not send ${k}`);
  assert.equal(b.calls[0].opportunity_id, 'OPP-1');
});

// ── execution, denial, crash ─────────────────────────────────────────────────

test('successful execution: dry run, publish, COMPLETED with the change linked, then immediate re-observation moves it to MEASURING', async () => {
  const s = seed(); s.authorize(); const b = bridge(HAPPY);
  const sum = await new ExecutionLoop(s.eng, b.b).run(T, T0);
  assert.deepEqual([b.count('dry'), b.count('execute'), b.count('observe')], [1, 1, 1]);
  assert.equal(b.calls.findIndex(c => c.command === 'observe') > b.calls.findIndex(c => c.command === 'execute' && !c.dry_run), true, 're-observation happens AFTER the publish');
  const o = s.eng.get(T, 'OPP-1')!;
  assert.equal(o.status, 'MEASURING'); assert.equal(o.resultingAction, 'change:chg_1');
  assert.equal(JSON.parse(o.resultingMeasurement!).status, 'MET');
  assert.equal(sum.executed, 1); assert.equal(sum.verified, 1);
  assert.ok(notes(s.eng).some(n => /EXECUTED FIX_SITEMAP_ENTRY: release r1 -> r2; sitemap.xml; source committed abcdef12/.test(n)));
});

test('denied execution: a blocked publisher leaves the opportunity APPROVED, nothing is published, and the reason is audited once', async () => {
  const s = seed(); s.authorize();
  const b = bridge({ dry: { status: 'BLOCKED', blocked_by: ['source_of_truth_matches_live'], reason: 'source differs' } });
  const loop = new ExecutionLoop(s.eng, b.b);
  await loop.run(T, T0); await loop.run(T, at(1));
  assert.equal(b.count('execute'), 0); assert.equal(s.eng.get(T, 'OPP-1')!.status, 'APPROVED');
  assert.equal(notes(s.eng).filter(n => n.startsWith('EXECUTION_BLOCKED (source_of_truth_matches_live)')).length, 1, 'a persisting condition is recorded once, not every cycle');
});

test('executor failure: an ERROR before publishing changes nothing; an ERROR after IN_PROGRESS is resumed next cycle without a second publication', async () => {
  let s = seed(); s.authorize();
  const down = bridge({ dry: { status: 'ERROR', reason: 'executor timed out' } });
  const sum = await new ExecutionLoop(s.eng, down.b).run(T, T0);
  assert.equal(sum.errors, 1); assert.equal(s.eng.get(T, 'OPP-1')!.status, 'APPROVED');

  s = seed(); s.authorize();
  let n = 0;
  const flaky = bridge({ dry: () => (n++ === 0 ? { status: 'ELIGIBLE', change_id: 'chg_1' } : { status: 'ALREADY_PUBLISHED', change_id: 'chg_1', receipt: PUBLISHED.receipt }), execute: { status: 'ERROR', reason: 'crashed mid-publish' }, observe: { status: 'OBSERVED', observable: true, facts: OK_FACTS, expected_outcome: EXPECTED } });
  const loop = new ExecutionLoop(s.eng, flaky.b);
  await loop.run(T, T0);
  assert.equal(s.eng.get(T, 'OPP-1')!.status, 'IN_PROGRESS', 'stays IN_PROGRESS, not falsely completed');
  await loop.run(T, at(0.25));
  assert.equal(s.eng.get(T, 'OPP-1')!.status, 'MEASURING');
  assert.equal(flaky.count('execute'), 1, 'the resume used the existing publication; the publisher was not asked to publish again');
});

// ── verification, rollback, scheduling ───────────────────────────────────────

test('verification: an unobservable live site defers (no verdict) and is abandoned for investigation after repeated failures, never rolled back', async () => {
  const s = seed(); s.authorize();
  const b = bridge({ ...HAPPY, observe: { status: 'OBSERVED', observable: false, unobservable: ['sitemap_lists (HTTP 503)'], facts: [] } });
  const loop = new ExecutionLoop(s.eng, b.b, { maxDeferrals: 3 });
  for (let i = 0; i < 5; i++) await loop.run(T, at(i * 0.25));
  const n = notes(s.eng);
  assert.equal(n.filter(x => x.startsWith('VERIFICATION_DEFERRED')).length, 2);
  assert.equal(n.filter(x => x.startsWith('VERIFICATION_ABANDONED')).length, 1);
  assert.equal(b.count('rollback'), 0); assert.equal(s.eng.get(T, 'OPP-1')!.status, 'COMPLETED');
  assert.equal(b.count('observe'), 3, 'after abandonment it stops observing');
});

test('rollback path: a contradicting re-observation rolls the change back once and the change is never verified or rolled back again', async () => {
  const s = seed(); s.authorize();
  const b = bridge({ ...HAPPY, observe: { status: 'OBSERVED', observable: true, facts: BAD_FACTS, expected_outcome: EXPECTED }, rollback: { status: 'ROLLED_BACK', restored_release: 'r1', source_restored: true } });
  const loop = new ExecutionLoop(s.eng, b.b);
  const sum = await loop.run(T, T0);
  assert.equal(sum.rolledBack, 1);
  assert.deepEqual(b.calls.find(c => c.command === 'rollback'), { command: 'rollback', tenant_id: T, opportunity_id: 'OPP-1', change_id: 'chg_1' });
  assert.equal(JSON.parse(s.eng.get(T, 'OPP-1')!.resultingMeasurement!).status, 'NOT_MET');
  assert.ok(notes(s.eng).some(n => /^ROLLED_BACK: restored release r1; repository source restored/.test(n)));
  await loop.run(T, at(30)); await loop.run(T, at(60));
  assert.equal(b.count('rollback'), 1); assert.equal(b.count('observe'), 1); assert.equal(b.count('execute'), 1, 'a rolled-back change is not re-executed by the loop');
});

test('rollback unavailable (a later release exists): recorded for investigation, no repeated attempts', async () => {
  const s = seed(); s.authorize();
  const b = bridge({ ...HAPPY, observe: { status: 'OBSERVED', observable: true, facts: BAD_FACTS, expected_outcome: EXPECTED }, rollback: { status: 'ROLLBACK_UNAVAILABLE', code: 'ROLLBACK_CONFLICT', reason: 'a later release exists' } });
  const loop = new ExecutionLoop(s.eng, b.b);
  await loop.run(T, T0); await loop.run(T, at(30));
  assert.ok(notes(s.eng).some(n => /^ROLLBACK_UNAVAILABLE \(ROLLBACK_CONFLICT\)/.test(n)));
  assert.equal(b.count('rollback'), 1);
});

test('24-hour scheduling: verified now (MEASURING), not re-observed before 24h, settled re-check at 24h moves it to LEARNED, then it is left alone', async () => {
  const s = seed(); s.authorize(); const b = bridge(HAPPY);
  const loop = new ExecutionLoop(s.eng, b.b);
  await loop.run(T, T0);
  assert.equal(s.eng.get(T, 'OPP-1')!.status, 'MEASURING');
  await loop.run(T, at(1)); await loop.run(T, at(23.9));
  assert.equal(b.count('observe'), 1, 'no second observation before the settle window');
  await loop.run(T, at(24.1));
  assert.equal(b.count('observe'), 2);
  assert.equal(s.eng.get(T, 'OPP-1')!.status, 'LEARNED');
  await loop.run(T, at(80));
  assert.equal(b.count('observe'), 2); assert.equal(b.count('execute'), 1);
  assert.equal(notes(s.eng).filter(n => n.startsWith('VERIFICATION MET')).length, 2);
});

test('idempotency: re-running the loop on a completed opportunity never executes again; an unconfigured bridge does nothing', async () => {
  const s = seed(); s.authorize(); const b = bridge(HAPPY);
  const loop = new ExecutionLoop(s.eng, b.b);
  for (let i = 0; i < 4; i++) await loop.run(T, at(i * 0.25));
  assert.equal(b.count('execute'), 1); assert.equal(b.count('dry'), 1);
  const none = await new ExecutionLoop(seed().eng, null).run(T, T0);
  assert.deepEqual(none, { executed: 0, blocked: 0, verified: 0, rolledBack: 0, deferred: 0, errors: 0 });
});

test('tenant isolation: the loop for one tenant never touches another tenant\'s opportunities', async () => {
  const s = seed(); s.authorize(); const b = bridge(HAPPY);
  await new ExecutionLoop(s.eng, b.b).run('other', T0);
  assert.equal(b.calls.length, 0); assert.equal(s.eng.get(T, 'OPP-1')!.status, 'APPROVED');
});

// ── several changes over one opportunity's life ──────────────────────────────

test('observation asks for the change by id and judges it against the outcome RECORDED at publication, not the opportunity\'s current plan', async () => {
  const s = seed(); s.authorize();
  const b = bridge({ ...HAPPY, observe: c => ({ status: 'OBSERVED', observable: true, facts: OK_FACTS, expected_outcome: EXPECTED, echo: c }) });
  await new ExecutionLoop(s.eng, b.b).run(T, T0);
  const obs = b.calls.find(c => c.command === 'observe');
  assert.equal(obs.change_id, 'chg_1'); assert.equal('expected_outcome' in obs, false, 'the caller does not supply the expectation');
  // the plan moves on to the NEXT step (as happens once the first change is in): the first change must still be judged by its own recorded outcome
  s.db.handle.prepare(`UPDATE seo_opportunities SET action_plan_json = ? WHERE opportunity_id = 'OPP-1'`).run(JSON.stringify({ ...PLAN, candidates: [{ ...PLAN.candidates[0], expected_outcome: [{ kind: 'something_else', subject: 'x', equals: 'y' }] }] }));
  const b2 = bridge({ observe: { status: 'OBSERVED', observable: true, facts: OK_FACTS, expected_outcome: EXPECTED } });
  await new ExecutionLoop(s.eng, b2.b).run(T, at(25));
  assert.equal(s.eng.get(T, 'OPP-1')!.status, 'LEARNED', 'verified against the recorded outcome (MET), unaffected by the moved-on plan');
});

test('a reopened opportunity starts a clean cycle: the old approval and result links no longer stand, and the second change is executed and verified on its own', async () => {
  const s = seed(); s.authorize();
  const b = bridge(HAPPY);
  const loop = new ExecutionLoop(s.eng, b.b);
  await loop.run(T, T0); await loop.run(T, at(24.5));
  assert.equal(s.eng.get(T, 'OPP-1')!.status, 'LEARNED');
  // observed again after being marked done (what refresh() records), plan now describes the next action
  s.db.handle.prepare(`UPDATE seo_opportunities SET status = 'DISCOVERED', resulting_action = NULL, resulting_measurement = NULL WHERE opportunity_id = 'OPP-1'`).run();
  s.db.handle.prepare(`INSERT INTO seo_opportunity_events (opportunity_id, tenant_id, at, actor, from_status, to_status, note) VALUES ('OPP-1', ?, ?, 'agent:opportunity-engine', 'LEARNED', 'DISCOVERED', 'Observed again after being marked done; reopened')`).run(T, at(26).toISOString());
  assert.equal(s.eng.get(T, 'OPP-1')!.approval, null, 'the previous cycle\'s approval does not carry over');
  for (const st of ['QUALIFIED', 'ACTIONABLE', 'AWAITING_APPROVAL'] as const) s.eng.transition(T, 'OPP-1', st, 'agent:autonomy-pass', 'prepared', at(26.1).toISOString());
  assert.equal(s.eng.authorize(T, 'OPP-1', at(26.2).toISOString()).decision.allowed, true, 'authorised afresh under the policy');
  const b2 = bridge({ dry: { status: 'ELIGIBLE', change_id: 'chg_2' }, execute: { ...PUBLISHED, change_id: 'chg_2' }, observe: { status: 'OBSERVED', observable: true, facts: OK_FACTS, expected_outcome: EXPECTED } });
  await new ExecutionLoop(s.eng, b2.b).run(T, at(26.3));
  const o = s.eng.get(T, 'OPP-1')!;
  assert.equal(o.status, 'MEASURING'); assert.equal(o.resultingAction, 'change:chg_2');
  assert.equal(b2.count('execute'), 1);
  assert.equal(b2.count('observe'), 1, 'the first cycle\'s two verifications are not counted toward the second change');
  assert.equal(buildLifecycleStates(s.eng).at(-1), 'current', 'lifecycle shows the latest change: verified once, second check pending');
});

import { buildLifecycle } from '../src/opportunities/lifecycle.js';
function buildLifecycleStates(eng: OpportunityEngine) {
  const o = eng.get(T, 'OPP-1')!;
  return buildLifecycle(o, eng.history(T, 'OPP-1'), eng.getAutonomyMode(T)).stages.map(x => x.state);
}

test('a human-approved Class B change (CHANGE_CANONICAL) is executed; the same change approved autonomously in SEO mode is not', async () => {
  const h = seed('CHANGE_CANONICAL'); h.eng.transition(T, 'OPP-1', 'APPROVED', 'human:owner', 'owner decision');
  const bh = bridge(HAPPY);
  await new ExecutionLoop(h.eng, bh.b).run(T, T0);
  assert.equal(bh.count('execute'), 1, 'a person is the authority for a Class B change');
  const a = seed('CHANGE_CANONICAL'); assert.equal(a.authorize().decision.allowed, false, 'SEO mode does not authorise Class B on its own');
  const ba = bridge(HAPPY);
  await new ExecutionLoop(a.eng, ba.b).run(T, T0);
  assert.equal(ba.calls.length, 0);
});
