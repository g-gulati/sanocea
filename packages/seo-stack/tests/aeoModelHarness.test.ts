import test from 'node:test';
import assert from 'node:assert/strict';
import { SeoDatabase } from '../src/persistence/seoDb.js';
import { ModelVisibilityHarness, detectMentions, buildPrompt, isPrivateHost, MODEL_SCOPE_NOTICE } from '../src/search-intel/aeoModelHarness.js';
import { fakeFetch } from './helpers/fakeHttp.js';

const URL_ = 'http://127.0.0.1:11434/v1/chat/completions';
const completion = (text: string, model = 'tiny-model') => ({ status: 200, body: JSON.stringify({ model, choices: [{ message: { role: 'assistant', content: text } }] }) });

test('mention detection is word-bounded, case-insensitive and extracts URLs', () => {
  const r = detectMentions('Try SANOCEA or see https://www.sanocea.com/x). Sanoceanic is unrelated.', ['Sanocea', 'sanocea.com']);
  assert.deepEqual(r.matched, ['Sanocea', 'sanocea.com']); // the domain inside the URL is a genuine domain mention; "Sanoceanic" is not a match
  assert.deepEqual(r.urls, ['https://www.sanocea.com/x']);
  assert.deepEqual(detectMentions('nothing here', ['Sanocea']).matched, []);
});

test('prompt is brand-neutral and host classification is right', () => {
  assert.ok(!/sanocea/i.test(buildPrompt('inventory drift')));
  assert.equal(isPrivateHost('127.0.0.1'), true);
  assert.equal(isPrivateHost('192.168.1.5'), true);
  assert.equal(isPrivateHost('api.openai.com'), false);
});

test('harness: no model configured => unavailable, no request', async () => {
  const f = fakeFetch({});
  const run = await new ModelVisibilityHarness(new SeoDatabase(':memory:'), { model: '', fetchImpl: f }).run('t1', ['q'], ['Sanocea']);
  assert.equal(run.observations.length, 0);
  assert.equal(run.mentionRatePercent, null);
  assert.match(run.unavailable[0].reason, /SEO_LLM_MODEL/);
  assert.equal(f.calls.length, 0);
});

test('harness: records model-specific observations with scope, full text and LOCAL provenance', async () => {
  const db = new SeoDatabase(':memory:');
  let n = 0;
  const f = fakeFetch({ [URL_]: () => completion(n++ === 0 ? 'I would look at Sanocea and Acme.' : 'Acme and Rival are options.') });
  const run = await new ModelVisibilityHarness(db, { model: 'tiny-model', samples: 2, fetchImpl: f }).run('t1', ['inventory drift'], ['Sanocea']);
  assert.equal(run.observations.length, 2);
  assert.equal(run.mentionRatePercent, 50);
  assert.equal(run.observations[0].provenance, '[OBSERVED: LOCAL MODEL RESPONSE]');
  assert.equal(run.observations[0].scope, 'MODEL_SPECIFIC');
  assert.equal(run.scopeNotice, MODEL_SCOPE_NOTICE);
  const sent = JSON.parse(f.calls[0].init!.body as string);
  assert.equal(sent.model, 'tiny-model');
  assert.equal(sent.stream, false);
  const stored = db.getLlmModelObservations('t1');
  assert.equal(stored.length, 2);
  assert.ok(stored.some(s => s.responseText.includes('Sanocea') && s.brandMentioned));
});

test('harness: remote endpoint is labelled MODEL API, not LOCAL', async () => {
  const f = fakeFetch({ 'https://models.example.test/v1/chat/completions': completion('Acme.') });
  const run = await new ModelVisibilityHarness(new SeoDatabase(':memory:'), { model: 'm', baseUrl: 'https://models.example.test/v1', samples: 1, fetchImpl: f }).run('t1', ['q'], ['Sanocea']);
  assert.equal(run.observations[0].provenance, '[OBSERVED: MODEL API RESPONSE]');
});

for (const [label, r] of [
  ['HTTP 500', { status: 500 }],
  ['connection refused (no runtime)', { throw: Object.assign(new TypeError('fetch failed'), { cause: { code: 'ECONNREFUSED' } }) }],
  ['empty completion', completion('   ')],
  ['malformed JSON shape', { status: 200, body: JSON.stringify({ nope: true }) }]
] as const) {
  test(`harness: ${label} fails closed — no observation stored`, async () => {
    const db = new SeoDatabase(':memory:');
    const run = await new ModelVisibilityHarness(db, { model: 'm', samples: 1, fetchImpl: fakeFetch({ [URL_]: r as any }) }).run('t1', ['q'], ['Sanocea']);
    assert.equal(run.observations.length, 0);
    assert.equal(run.unavailable.length, 1);
    assert.equal(run.mentionRatePercent, null);
    assert.equal(db.getLlmModelObservations('t1').length, 0);
  });
}

test('harness: summary groups per model (never blends) and isolates tenants', async () => {
  const db = new SeoDatabase(':memory:');
  for (const [model, text] of [['modelA', 'Sanocea!'], ['modelB', 'nothing']] as const)
    await new ModelVisibilityHarness(db, { model, samples: 1, fetchImpl: fakeFetch({ [URL_]: completion(text, model) }) }).run('A', ['q'], ['Sanocea']);
  const h = new ModelVisibilityHarness(db);
  const s = h.summary('A');
  assert.equal(s.models.length, 2);
  assert.equal(s.models.find(m => m.modelAtHost.startsWith('modelA'))!.mentionRatePercent, 100);
  assert.equal(s.models.find(m => m.modelAtHost.startsWith('modelB'))!.mentionRatePercent, 0);
  assert.equal(h.summary('B').provenance, '[NOT AVAILABLE]');
  assert.equal(s.scopeNotice, MODEL_SCOPE_NOTICE);
});
