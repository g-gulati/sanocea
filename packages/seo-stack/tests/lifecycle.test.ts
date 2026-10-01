import test from 'node:test';
import assert from 'node:assert/strict';
import { buildLifecycle } from '../src/opportunities/lifecycle.js';

const base: any = { opportunityId: 'OPP-SECRET-1', tenantId: 'a', type: 'SITEMAP_URL_REDIRECTS', target: 'https://a.test/x', status: 'AWAITING_APPROVAL', plainEnglish: 'A web address listed in the sitemap sends visitors on to a different address.',
  reason: 'r', recommendedAction: 'FIX_SITEMAP_ENTRY', decision: { action: 'FIX_SITEMAP_ENTRY', rationale: 'because', checks: [] }, detectedAt: '2026-10-01T00:00:00Z', updatedAt: '2026-10-01T00:00:00Z', approval: null, diagnosis: null, actionPlan: null, resultingAction: null };
const diag: any = { finding: 'f', hypotheses: [{ status: 'ESTABLISHED' }, { status: 'RULED_OUT' }], conclusion: 'The intended address is https://a.test/x/.', sufficient: true, missing_evidence: [], intended: 'https://a.test/x/' };
const plan: any = { selected: 'FIX_SITEMAP_ENTRY', why: 'Selected the sitemap fix.', candidates: [], rejected: [], investigate_next: [] };
const appr: any = { by: 'autonomous:sanocea-autonomy-policy@1.0.0', at: '2026-10-02T00:00:00Z', actorType: 'AUTONOMOUS_AGENT', policy: 'sanocea-autonomy-policy@1.0.0', reason: 'ok', actionClass: 'A', approvedAction: 'FIX_SITEMAP_ENTRY' };
const ev = (note: string, at = '2026-10-02T01:00:00Z') => ({ at, actor: 'agent:executor', from: 'APPROVED', to: 'APPROVED', note });
const states = (l: any) => l.stages.map((s: any) => s.state);

test('six stages in the customer order, always', () => {
  assert.deepEqual(buildLifecycle(base, [], 'AUTONOMOUS_SEO').stages.map(s => s.label), ['Found', 'Concluded', 'Selected', 'Policy decision', 'Executed', 'Verified']);
});

test('fully autonomous success: every stage done, in business language only', () => {
  const o = { ...base, status: 'MEASURING', diagnosis: diag, actionPlan: plan, approval: appr };
  const l = buildLifecycle(o, [ev('EXECUTED FIX_SITEMAP_ENTRY: release r1 -> r2; sitemap.xml; source committed abc'), ev('VERIFICATION MET: ok', '2026-10-02T01:01:00Z'), ev('VERIFICATION MET: ok', '2026-10-03T01:02:00Z')], 'AUTONOMOUS_SEO');
  assert.deepEqual(states(l), ['done', 'done', 'done', 'done', 'done', 'done']);
  assert.equal(l.summary, 'Complete.');
  assert.match(l.stages[3].headline, /Permitted automatically/);
  assert.match(l.stages[3].detail!, /low-risk technical fix.*Autonomous SEO mode/);
  assert.match(l.stages[5].headline, /twice/);
});

test('customer text never exposes ids, actors, policy versions, release names or file paths', () => {
  const o = { ...base, status: 'MEASURING', diagnosis: diag, actionPlan: plan, approval: appr };
  const l = buildLifecycle(o, [ev('EXECUTED FIX_SITEMAP_ENTRY: release 2026-10-02T00-00-00Z-chg_abc -> 2026-10-02T00-00-05Z-chg_abc; sitemap.xml; source committed abcdef12'), ev('VERIFICATION MET: ok')], 'AUTONOMOUS_SEO');
  const text = JSON.stringify(l.stages);
  for (const bad of ['OPP-', 'autonomous:', 'sanocea-autonomy-policy', 'chg_', 'sitemap.xml', 'release 2026', 'AUTONOMOUS_SEO', 'AUTONOMOUS_AGENT', 'agent:']) assert.equal(text.includes(bad), false, `leaked ${bad}`);
});

test('class C in an autonomous mode: policy stage is blocked with a plain reason, nothing executed', () => {
  const o = { ...base, recommendedAction: 'CHANGE_REDIRECT', decision: { ...base.decision, action: 'CHANGE_REDIRECT' }, actionPlan: { ...plan, selected: 'CHANGE_REDIRECT' }, diagnosis: diag };
  const l = buildLifecycle(o, [ev('POLICY_DENIED: Class C action (CHANGE_REDIRECT) requires explicit human authorisation in every mode.')], 'AUTONOMOUS_SEO');
  assert.equal(l.stages[3].state, 'blocked'); assert.match(l.stages[3].headline, /always needs a person/);
  assert.equal(l.stages[4].state, 'waiting'); assert.match(l.summary, /Policy decision/);
  assert.equal(JSON.stringify(l).includes('Class C'), false);
});

test('decision needed: concluded is blocked, no action chosen, policy not applicable, and the one question is surfaced', () => {
  const dn = { question: 'Which address?', why: 'split', options: [{ address: 'https://a.test/x/', signals: ['s'], consequence: 'c' }] };
  const o = { ...base, recommendedAction: 'INVESTIGATE', decision: { ...base.decision, action: 'INVESTIGATE' }, diagnosis: { ...diag, sufficient: false, decision_needed: dn }, actionPlan: { ...plan, selected: 'INVESTIGATE', investigate_next: ['Ask the site owner: Which address?'] } };
  const l = buildLifecycle(o, [], 'AUTONOMOUS_SEO');
  assert.deepEqual(states(l), ['done', 'blocked', 'waiting', 'not_applicable', 'waiting', 'waiting']);
  assert.deepEqual(l.decisionNeeded, dn); assert.equal(l.summary, 'Waiting for one decision from the owner.');
});

test('a mode lowered after approval and an executor hold are shown honestly; verification failure with rollback is explained', () => {
  const held = buildLifecycle({ ...base, status: 'APPROVED', diagnosis: diag, actionPlan: plan, approval: appr }, [ev('EXECUTION_BLOCKED (source_of_truth_matches_live): the source file differs from the live sitemap')], 'AUTONOMOUS_SEO');
  assert.equal(held.stages[4].state, 'blocked'); assert.match(held.stages[4].headline, /held back/);
  const rb = buildLifecycle({ ...base, status: 'COMPLETED', diagnosis: diag, actionPlan: plan, approval: appr }, [ev('EXECUTED FIX_SITEMAP_ENTRY: release a -> b; sitemap.xml; source synced'), ev('ROLLED_BACK: restored release a; repository source restored.')], 'AUTONOMOUS_SEO');
  assert.equal(rb.stages[5].state, 'blocked'); assert.match(rb.stages[5].headline, /did not work, so it was undone/);
});

test('non-diagnosed observations say they were observed directly, not concluded by inference', () => {
  const l = buildLifecycle({ ...base, type: 'MISSING_STATIC_H1', recommendedAction: 'CHANGE_SERVER_RENDERING', decision: { ...base.decision, action: 'CHANGE_SERVER_RENDERING' } }, [], 'AUTONOMOUS_SEO');
  assert.match(l.stages[1].headline, /Observed directly/);
});
