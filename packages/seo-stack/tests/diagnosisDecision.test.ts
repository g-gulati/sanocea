import test from 'node:test';
import assert from 'node:assert/strict';
import { collectRedirectFamilyFacts, diagnoseRedirectFamily, selectAction, PageObs } from '../src/opportunities/diagnosis.js';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { OpportunityEngine } from '../src/opportunities/opportunityEngine.js';

// The real production shape (2026-10-01): sitemap lists no-slash; server redirects to slash; slash page's own markup names no-slash; only the homepage links to the slash form.
const L = 'https://www.sanocea.com/solutions/marketplace-reconciliation', D = L + '/';
const home: PageObs = { url: 'https://www.sanocea.com/', status: 200, finalUrl: 'https://www.sanocea.com/', canonical: 'https://www.sanocea.com/', internalLinks: [D] };
const page: PageObs = { url: L, status: 200, finalUrl: D, redirected: true, canonical: L, internalLinks: [], declaredUrls: [L, L, 'https://www.sanocea.com/'] };
const GOOGLE_NONE = [{ url: D, googleCanonical: null }];
const facts = (over: { owner?: string | null; declared?: string[] } = {}) =>
  collectRedirectFamilyFacts({ ...page, declaredUrls: over.declared ?? page.declaredUrls }, [home, page], GOOGLE_NONE, undefined, [], over.owner ?? null);

test('real production shape: every observable fact gathered and split => ONE precise owner question, no action guessed', () => {
  const f = facts();
  assert.equal(f.filter(x => x.kind === 'declared_address').length, 1, 'declarations are facts (duplicates collapse), with the crawl provenance');
  const d = diagnoseRedirectFamily(f);
  assert.equal(d.sufficient, false);
  assert.ok(d.decision_needed, 'decision needed');
  assert.match(d.decision_needed!.question, /Which address should be the public address of this page/);
  assert.deepEqual(d.decision_needed!.options.map(o => o.address), [D, L]);
  const optL = d.decision_needed!.options.find(o => o.address === L)!;
  assert.match(optL.consequence, /web-server change, which SANOCEA never makes on its own/);
  assert.ok(optL.signals.some(s => /sitemap lists it/.test(s)) && optL.signals.some(s => /canonical tag names it/.test(s)) && optL.signals.some(s => /markup name it/.test(s)));
  assert.ok(d.decision_needed!.options.find(o => o.address === D)!.signals.some(s => /internal link/.test(s)));
  const plan = selectAction(d, f);
  assert.equal(plan.selected, 'INVESTIGATE');
  assert.match(plan.investigate_next[0], /^Ask the site owner: Which address/);
});

test('without the conflict (nothing names the other address) no question is raised: the gap is just missing evidence', () => {
  const quiet: PageObs = { ...page, canonical: D, declaredUrls: [] };
  const f = collectRedirectFamilyFacts(quiet, [home, quiet], GOOGLE_NONE, undefined, [], null);
  // the sitemap still names L and the redirect/canonical/links name D: still a split, so use a page where the sitemap entry is the only L signal and links are absent
  const d = diagnoseRedirectFamily(f);
  assert.equal(d.sufficient, false);
});

test('owner states the address: it is ESTABLISHED, the other is RULED OUT, and action selection follows from it', () => {
  const dD = diagnoseRedirectFamily(facts({ owner: D }));
  assert.equal(dD.sufficient, true); assert.equal(dD.intended, D);
  assert.deepEqual(dD.hypotheses.map(h => h.status), ['ESTABLISHED', 'RULED_OUT']);
  assert.equal(dD.decision_needed, undefined);
  const planD = selectAction(dD, facts({ owner: D }));
  assert.equal(planD.selected, 'CHANGE_CANONICAL', 'canonical first (dependency order), then the sitemap');
  assert.ok(planD.candidates.some(c => c.action === 'FIX_SITEMAP_ENTRY'));

  const dL = diagnoseRedirectFamily(facts({ owner: L }));
  assert.equal(dL.intended, L);
  assert.equal(selectAction(dL, facts({ owner: L })).selected, 'CHANGE_REDIRECT', 'choosing the redirecting address means a server redirect change, which stays Class C / human');
});

test('an owner statement about some other address is ignored', () => {
  const d = diagnoseRedirectFamily(facts({ owner: 'https://www.sanocea.com/elsewhere/' }));
  assert.equal(d.sufficient, false);
});

test('engine: only a human can answer, only with one of the asked options; the answer is recorded, audited and re-diagnosed immediately', () => {
  const db = new SeoDatabase(':memory:');
  const eng = new OpportunityEngine(db);
  const f = facts();
  const d = diagnoseRedirectFamily(f);
  db.handle.prepare(`INSERT INTO seo_opportunities (opportunity_id, tenant_id, type, target, dedupe_key, status, confidence, source, reason, evidence_json, recommended_action, decision_json, objective, detected_at, last_seen_at, updated_at, diagnosis_json, action_plan_json)
    VALUES ('OPP-1','a','SITEMAP_URL_REDIRECTS',?,'k','AWAITING_APPROVAL','OBSERVED','s','r','{}','INVESTIGATE','{"action":"INVESTIGATE","rationale":"x","checks":["c"]}','o','t','t','t',?,?)`)
    .run(L, JSON.stringify(d), JSON.stringify(selectAction(d, f)));
  assert.throws(() => eng.recordOwnerIntent('a', 'OPP-1', D, 'agent:x'), /only a human/);
  assert.throws(() => eng.recordOwnerIntent('a', 'OPP-1', 'https://www.sanocea.com/zzz', 'human:owner'), /not one of the options/);
  assert.throws(() => eng.recordOwnerIntent('b', 'OPP-1', D, 'human:owner'), /not found/, 'cross-tenant refused');
  eng.recordOwnerIntent('a', 'OPP-1', D, 'human:owner', '2026-10-02T00:00:00Z');
  assert.deepEqual(db.getOwnerIntents('a'), { [L]: D });
  assert.deepEqual(db.getOwnerIntents('b'), {});
  assert.ok(eng.history('a', 'OPP-1').some(e => e.actor === 'human:owner' && /OWNER_DECISION/.test(e.note)));
});
