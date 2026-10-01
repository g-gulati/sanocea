import test from 'node:test'
import assert from 'node:assert/strict'
import {describeOpportunity, opportunitiesFrom, statusLabel, STATUS_LABELS, STATUS_GUIDE} from '../src/whatsapp-demo/seoOpportunities.js'

// Shapes copied from the real worker output (GET /opportunities on the worker) for the Solutions page.
const solutionsUrl = 'https://www.sanocea.com/solutions/marketplace-reconciliation'
const OPPS = [
  {type: 'GOOGLE_INDEX_STATUS_ISSUE', target: solutionsUrl, status: 'DISCOVERED', source: '[OBSERVED: GOOGLE SEARCH CONSOLE API]', lastSeenAt: '2026-10-01T09:09:23.000Z',
    plainEnglish: "Google's own report for this page says: Discovered - currently not indexed.",
    evidence: {url: solutionsUrl, verdict: 'NEUTRAL', coverageState: 'Discovered - currently not indexed', indexingState: 'INDEXING_STATE_UNSPECIFIED', pageFetchState: 'PAGE_FETCH_STATE_UNSPECIFIED', lastCrawlTime: null, inspectedAt: '2026-10-01T09:09:23.038Z'}},
  {type: 'SERVER_RENDERED_CONTENT_GAP', target: solutionsUrl, status: 'DISCOVERED', source: '[OBSERVED: LIVE PAGE FETCH]', lastSeenAt: '2026-10-01T08:53:00.000Z',
    evidence: {url: solutionsUrl, staticWords: 0, bodyWords: 0, threshold: 100, method: 'HTTP GET, no JavaScript', observedAt: '2026-10-01T08:51:30.327Z'}},
  {type: 'MISSING_STATIC_H1', target: solutionsUrl, status: 'DISCOVERED', source: '[OBSERVED: LIVE PAGE FETCH]', lastSeenAt: '2026-10-01T08:53:00.000Z',
    evidence: {url: solutionsUrl, h1Count: 0, method: 'HTTP GET, no JavaScript', observedAt: '2026-10-01T08:51:30.327Z'}},
  {type: 'SITEMAP_URL_REDIRECTS', target: solutionsUrl, status: 'DISCOVERED', source: '[OBSERVED: LIVE PAGE FETCH]', lastSeenAt: '2026-10-01T08:53:00.000Z',
    evidence: {listedUrl: solutionsUrl, finalUrl: `${solutionsUrl}/`, method: 'HTTP GET following redirects', observedAt: '2026-10-01T08:51:30.327Z'}},
]
const overview = {views: {opportunities: {ok: true, updated_at: '2026-10-01T09:09:23.000Z', data: {count: OPPS.length, opportunities: OPPS}}}}

test('the real opportunities are mapped one-to-one, in the worker order, with no id and no priority field', () => {
  const r = opportunitiesFrom(overview)
  assert.equal(r.ok, true)
  assert.equal(r.items.length, 4)
  assert.deepEqual(r.items.map((i) => i.key.split('|')[0]), OPPS.map((o) => o.type))
  for (const i of r.items) {
    for (const k of ['priority', 'severity', 'score', 'rank', 'impact', 'opportunityId', 'id']) assert.equal(k in i, false, k)
    assert.equal(i.status, 'Needs review')
  }
})

test('Google evidence is quoted as Google reported it and states no cause', () => {
  const g = describeOpportunity(OPPS[0])
  assert.equal(g.title, 'Google has found the marketplace reconciliation page but has not added it to search yet')
  assert.match(g.evidence, /"Discovered - currently not indexed"/)
  assert.match(g.evidence, /Google reports no crawl yet\./)
  assert.match(g.evidence, /Google does not say why\./)
  assert.match(g.why, /has not determined a cause/)
  assert.match(g.action, /not linking them to this one/)
  assert.deepEqual(g.tech.find(([k]) => k === 'Coverage'), ['Coverage', 'Discovered - currently not indexed'])
})

test('no wording anywhere claims a cause or a Google inability, and the crawler findings stay separate', () => {
  const banned = [/can't read/i, /cannot read/i, /can not read/i, /preventing indexing/i, /prevents? (google|indexing)/i, /caused (the|an?) /i, /because of the (redirect|javascript)/i, /due to (the )?(redirect|javascript)/i, /penal/i, /lost (traffic|revenue)/i, /₹|\$\d|%\s*(more|increase)/i]
  const r = opportunitiesFrom(overview)
  for (const i of r.items) {
    const text = [i.title, i.sub, i.what, i.evidence, i.why, i.action, ...i.tech.flat()].join(' | ')
    for (const b of banned) assert.doesNotMatch(text, b, `${i.key}: ${b}`)
  }
  assert.equal(new Set(r.items.map((i) => i.key)).size, 4, 'four separate rows; nothing merged into a single diagnosis')
  const ssr = r.items[1]
  assert.match(ssr.why, /We have not measured what Google does with this page/)
  assert.match(r.items[2].why, /we have not measured that/)
})

test('addresses are shown as paths only, and internal fields never reach the output', () => {
  const r = opportunitiesFrom(overview)
  const all = JSON.stringify(r.items.map(({key, ...shown}) => shown)) // `key` is React's list key, never rendered
  assert.doesNotMatch(all, /https?:\/\//, 'full URLs are shortened to paths')
  assert.doesNotMatch(all, /\/opt\/|\/etc\/|\/tmp\/|\.sqlite|dbPath|OPP-/)
  assert.equal(r.items[3].sub, '/solutions/marketplace-reconciliation → /solutions/marketplace-reconciliation/ (redirect)')
})

test('status words are the six lifecycle statuses only; every backend state maps into them', () => {
  assert.deepEqual(STATUS_GUIDE.map(([k]) => k), STATUS_LABELS)
  for (const s of ['DISCOVERED', 'QUALIFIED', 'RESEARCHING', 'ACTIONABLE', 'AWAITING_APPROVAL', 'APPROVED', 'IN_PROGRESS', 'COMPLETED', 'MEASURING', 'LEARNED', 'REJECTED', 'UNKNOWN_FUTURE_STATE']) assert.ok(STATUS_LABELS.includes(statusLabel(s)), s)
  assert.equal(statusLabel('APPROVED'), 'Approved')
  assert.equal(statusLabel('MEASURING'), 'Monitoring')
  assert.equal(statusLabel('REJECTED'), 'Rejected')
})

test('a missing or failed opportunities view yields nothing (never a default or fixture)', () => {
  assert.deepEqual(opportunitiesFrom(null), {ok: false, items: []})
  assert.deepEqual(opportunitiesFrom({views: {}}), {ok: false, items: []})
  assert.deepEqual(opportunitiesFrom({views: {opportunities: {ok: false, error: 'x'}}}), {ok: false, items: []})
  assert.equal(opportunitiesFrom({views: {opportunities: {ok: true, data: {opportunities: []}}}}).items.length, 0)
})

// ── Section 5 lifecycle (worker shapes copied from GET /opportunities, 2026-10-01) ──
import {lifecycleOf, pillOf, STEP_GUIDE} from '../src/whatsapp-demo/seoOpportunities.js'
const stage = (key, label, state, headline, detail, at) => ({key, label, state, headline, detail, at})
const LC_DECISION = {
  summary: 'Waiting for one decision from the owner.',
  decisionNeeded: {question: `Which address should be the public address of this page: ${solutionsUrl}/ or ${solutionsUrl}?`, why: 'The evidence is split and cannot be resolved by observing more.',
    options: [{address: `${solutionsUrl}/`, signals: ['the web server redirects visitors to it', '1 internal link(s) use it'], consequence: 'SANOCEA would correct the sitemap. The web server already serves this address, so no server change is needed.'},
      {address: solutionsUrl, signals: ['the sitemap lists it'], consequence: `${solutionsUrl} is not served today, so using it needs a web-server change, which SANOCEA never makes on its own.`}]},
  stages: [stage('found', 'Found', 'done', `The sitemap lists ${solutionsUrl}, which redirects to ${solutionsUrl}/.`, undefined, '2026-10-01T10:33:24.536Z'),
    stage('concluded', 'Concluded', 'blocked', 'The evidence is split; the owner needs to choose'), stage('selected', 'Selected', 'waiting', 'No action chosen yet'),
    stage('policy', 'Policy decision', 'not_applicable', 'Nothing to authorise yet'), stage('executed', 'Executed', 'waiting', 'Nothing has been changed'), stage('verified', 'Verified', 'waiting', 'Nothing to verify yet')],
}
const withLc = (o, lifecycle, status = 'AWAITING_APPROVAL') => ({...o, status, lifecycle})

test('lifecycle: six steps in order, full addresses shortened to paths, nothing but strings and known states reach the page', () => {
  const lc = lifecycleOf(withLc(OPPS[3], LC_DECISION))
  assert.deepEqual(lc.stages.map((s) => s.label), ['Found', 'Concluded', 'Selected', 'Policy decision', 'Executed', 'Verified'])
  assert.match(lc.stages[0].headline, /^The sitemap lists \/solutions\/marketplace-reconciliation, which redirects to \/solutions\/marketplace-reconciliation\/\.$/)
  assert.equal(JSON.stringify(lc).includes('https://'), false)
  assert.deepEqual(STEP_GUIDE.map(([k]) => k), lc.stages.map((s) => s.label))
})

test('lifecycle: a step the worker did not supply or with an unknown state is dropped, never invented; no lifecycle means no panel', () => {
  const odd = lifecycleOf(withLc(OPPS[3], {summary: 's', stages: [stage('found', 'Found', 'done', 'x'), {key: 'zz', label: 'Weird', state: 'exploded', headline: 'y'}, {label: 5}]}))
  assert.deepEqual(odd.stages.map((s) => s.label), ['Found'])
  assert.equal(lifecycleOf(OPPS[3]), null); assert.equal(lifecycleOf(null), null); assert.equal(lifecycleOf({lifecycle: {stages: []}}), null)
})

test('decision card: the one question with both options, the server-change consequence flagged, addresses as paths', () => {
  const d = lifecycleOf(withLc(OPPS[3], LC_DECISION)).decision
  assert.match(d.question, /Which address should be the public address of this page: \/solutions\/marketplace-reconciliation\/ or \/solutions\/marketplace-reconciliation\?/)
  assert.deepEqual(d.options.map((o) => [o.address, o.needsServerChange]), [['/solutions/marketplace-reconciliation/', false], ['/solutions/marketplace-reconciliation', true]])
})

test('pill: what the customer needs to know first', () => {
  const pill = (lifecycle, st) => pillOf({}, st, lifecycleOf({lifecycle}))
  assert.deepEqual(pill(LC_DECISION, 'Needs review'), {label: 'Needs your decision', tone: 'warn'})
  const base = LC_DECISION.stages.map((s) => ({...s})); const mk = (over) => ({summary: 's', stages: base.map((s) => ({...s, ...(over[s.key] ? {state: over[s.key]} : {})}))})
  assert.equal(pill(mk({policy: 'blocked'}), 'Needs review').label, 'Needs a person')
  assert.equal(pill(mk({policy: 'not_applicable'}), 'Needs review').label, 'Investigating')
  assert.equal(pill(mk({policy: 'done', executed: 'done', verified: 'current'}), 'Monitoring').label, 'Monitoring')
  assert.equal(pill(mk({policy: 'done', executed: 'done', verified: 'done'}), 'Completed').label, 'Completed')
  assert.deepEqual(pillOf({}, 'Needs review', null), {label: 'Needs review', tone: 'neutral'}, 'no lifecycle: the backend status words, as before')
})

test('the item carries the lifecycle and pill; no id, actor, policy or file path appears anywhere in it', () => {
  const it = describeOpportunity(withLc(OPPS[3], LC_DECISION))
  assert.equal(it.pill.label, 'Needs your decision')
  const text = JSON.stringify(it.lifecycle)
  for (const bad of ['OPP-', 'autonomous:', 'agent:', 'sanocea-autonomy-policy', '/opt/', 'chg_']) assert.equal(text.includes(bad), false, bad)
})
