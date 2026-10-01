import test from 'node:test'
import assert from 'node:assert/strict'

// The shared SEO data contract: session reuse, exactly-once retry on an expired session, one shared fetch/poll for any
// number of subscribers, and selectors that never turn a missing view into a zero.

function installBrowser({sessions = [], overview = {views: {}}, failFirstOverview = null} = {}) {
  const storage = new Map()
  globalThis.sessionStorage = {getItem: (k) => (storage.has(k) ? storage.get(k) : null), setItem: (k, v) => storage.set(k, String(v)), removeItem: (k) => storage.delete(k)}
  const calls = []
  let leased = 0
  let overviewCalls = 0
  globalThis.fetch = async (url, opts = {}) => {
    const path = String(url).replace('https://api.sanocea.com', '')
    calls.push({path, method: opts.method || 'GET', auth: opts.headers && opts.headers.Authorization})
    if (path === '/demo/sessions') {
      const s = sessions[leased++] || {merchant_id: `m_${leased}`, api_key: `key_${leased}`, display_name: 'x', expires_at: new Date(Date.now() + 3_600_000).toISOString()}
      return {ok: true, status: 200, json: async () => s}
    }
    if (path === '/demo/seo/overview') {
      overviewCalls += 1
      if (failFirstOverview && overviewCalls === 1) return {ok: false, status: failFirstOverview, statusText: 'x', json: async () => ({detail: 'demo session required'})}
      return {ok: true, status: 200, json: async () => overview}
    }
    throw new Error(`unexpected request ${path}`)
  }
  return {storage, calls}
}

const fresh = async () => {
  const mod = await import(`../src/whatsapp-demo/seoOverview.js?${Math.random()}`)
  return mod
}

test('leases a demo session once, stores it, and sends it as the bearer token', async () => {
  const env = installBrowser()
  const {fetchSeoOverview} = await fresh()
  await fetchSeoOverview()
  await fetchSeoOverview()
  assert.equal(env.calls.filter((c) => c.path === '/demo/sessions').length, 1, 'second call must reuse the stored session')
  const overviewCalls = env.calls.filter((c) => c.path === '/demo/seo/overview')
  assert.equal(overviewCalls.length, 2)
  assert.ok(overviewCalls.every((c) => c.auth === 'Bearer key_1'))
  assert.equal(JSON.parse(env.storage.get('sanocea_demo_session')).apiKey, 'key_1')
})

test('reuses the session already stored for this tab, without leasing', async () => {
  const env = installBrowser()
  env.storage.set('sanocea_demo_session', JSON.stringify({apiKey: 'existing', merchantId: 'm', expiresAt: new Date(Date.now() + 3_600_000).toISOString()}))
  const {fetchSeoOverview} = await fresh()
  await fetchSeoOverview()
  assert.equal(env.calls.filter((c) => c.path === '/demo/sessions').length, 0)
  assert.equal(env.calls[0].auth, 'Bearer existing')
})

test('an expired stored session is not used; a rejected one is replaced and retried exactly once', async () => {
  const env = installBrowser({failFirstOverview: 403})
  env.storage.set('sanocea_demo_session', JSON.stringify({apiKey: 'stale', merchantId: 'm', expiresAt: new Date(Date.now() - 1000).toISOString()}))
  const {fetchSeoOverview} = await fresh()
  await fetchSeoOverview()
  const auths = env.calls.filter((c) => c.path === '/demo/seo/overview').map((c) => c.auth)
  assert.deepEqual(auths, ['Bearer key_1', 'Bearer key_2'], 'first attempt is rejected (403), then exactly one retry with a freshly leased session')
})

test('a persistent 403 surfaces as an error after one retry, never an endless loop', async () => {
  installBrowser({failFirstOverview: 403})
  const mod = await fresh()
  globalThis.fetch = async (url) => {
    const path = String(url).replace('https://api.sanocea.com', '')
    if (path === '/demo/sessions') return {ok: true, status: 200, json: async () => ({merchant_id: 'm', api_key: 'k', display_name: 'x', expires_at: new Date(Date.now() + 3_600_000).toISOString()})}
    return {ok: false, status: 403, statusText: 'Forbidden', json: async () => ({detail: 'demo session required'})}
  }
  await assert.rejects(() => mod.fetchSeoOverview(), (e) => e.status === 403)
})

test('the shared store fetches once for many subscribers, polls on one timer, and stops when the last one leaves', async (t) => {
  const OV = {views: {gsc_summary: {ok: true, data: {snapshot: {totalClicks: 11}}}}}
  const env = installBrowser({overview: OV})
  t.mock.timers.enable({apis: ['setInterval']})
  const store = await import(`../src/whatsapp-demo/useSeoOverview.js?${Math.random()}`)
  store.__resetSeoStoreForTests()
  assert.equal(env.calls.length, 0, 'nothing is fetched until a component subscribes')
  const seen = []
  const unsubA = store.subscribeSeoStore(() => seen.push('a'))
  const unsubB = store.subscribeSeoStore(() => seen.push('b'))
  await new Promise((r) => setImmediate(r))
  await new Promise((r) => setImmediate(r))
  const bridgeCalls = () => env.calls.filter((c) => c.path === '/demo/seo/overview').length
  assert.equal(bridgeCalls(), 1, 'two subscribers share ONE fetch')
  assert.equal(store.getSeoSnapshot().status, 'ok')
  assert.equal(store.getSeoSnapshot().overview, OV, 'the response is stored unmodified')
  assert.ok(seen.includes('a') && seen.includes('b'), 'every subscriber is notified')
  t.mock.timers.tick(60_000)
  await new Promise((r) => setImmediate(r))
  await new Promise((r) => setImmediate(r))
  assert.equal(bridgeCalls(), 2, 'one poll per interval regardless of subscriber count')
  unsubA()
  t.mock.timers.tick(60_000)
  await new Promise((r) => setImmediate(r))
  assert.equal(bridgeCalls(), 3, 'still polling while one subscriber remains')
  unsubB()
  t.mock.timers.tick(180_000)
  await new Promise((r) => setImmediate(r))
  assert.equal(bridgeCalls(), 3, 'polling stops when the last subscriber leaves')
})

test('a failed refresh keeps the last good overview and reports the error; it never blanks to defaults', async (t) => {
  installBrowser({overview: {views: {x: 1}}})
  t.mock.timers.enable({apis: ['setInterval']})
  const store = await import(`../src/whatsapp-demo/useSeoOverview.js?${Math.random()}`)
  store.__resetSeoStoreForTests()
  const unsub = store.subscribeSeoStore(() => {})
  await new Promise((r) => setImmediate(r))
  await new Promise((r) => setImmediate(r))
  const good = store.getSeoSnapshot().overview
  assert.ok(good)
  globalThis.fetch = async () => ({ok: false, status: 503, statusText: 'x', json: async () => ({detail: 'SEO worker unavailable'})})
  t.mock.timers.tick(60_000)
  await new Promise((r) => setImmediate(r))
  await new Promise((r) => setImmediate(r))
  const snap = store.getSeoSnapshot()
  assert.equal(snap.status, 'error')
  assert.equal(snap.error, 'SEO worker unavailable')
  assert.equal(snap.overview, good, 'the last good response is kept, together with the error')
  unsub()
})

test('a failed first load is retried within seconds (bounded) instead of waiting a full poll interval', async (t) => {
  const OV = {views: {x: 1}}
  const env = installBrowser({overview: OV, failFirstOverview: 500})
  // a failing lease is the realistic cause: make the very first overview request fail with a 500, then succeed
  t.mock.timers.enable({apis: ['setInterval', 'setTimeout']})
  const store = await import(`../src/whatsapp-demo/useSeoOverview.js?${Math.random()}`)
  store.__resetSeoStoreForTests()
  const unsub = store.subscribeSeoStore(() => {})
  await new Promise((r) => setImmediate(r)); await new Promise((r) => setImmediate(r))
  assert.equal(store.getSeoSnapshot().status, 'error', 'first attempt failed')
  assert.equal(store.getSeoSnapshot().overview, null, 'no data is invented while failed')
  t.mock.timers.tick(4_000)   // far less than the 60 s poll interval
  await new Promise((r) => setImmediate(r)); await new Promise((r) => setImmediate(r))
  assert.equal(store.getSeoSnapshot().status, 'ok', 'recovered on the short retry')
  assert.equal(store.getSeoSnapshot().overview, OV)
  unsub()
  void env
})

test('fast retries are bounded: a permanently failing bridge is not hammered', async (t) => {
  installBrowser()
  globalThis.fetch = async (url) => {
    const path = String(url).replace('https://api.sanocea.com', '')
    if (path === '/demo/sessions') return {ok: true, status: 200, json: async () => ({merchant_id: 'm', api_key: 'k', display_name: 'x', expires_at: new Date(Date.now() + 3_600_000).toISOString()})}
    globalThis.__calls = (globalThis.__calls || 0) + 1
    return {ok: false, status: 500, statusText: 'x', json: async () => ({detail: 'boom'})}
  }
  globalThis.__calls = 0
  t.mock.timers.enable({apis: ['setInterval', 'setTimeout']})
  const store = await import(`../src/whatsapp-demo/useSeoOverview.js?${Math.random()}`)
  store.__resetSeoStoreForTests()
  const unsub = store.subscribeSeoStore(() => {})
  for (let i = 0; i < 12; i++) { await new Promise((r) => setImmediate(r)); t.mock.timers.tick(4_000) }
  await new Promise((r) => setImmediate(r))
  assert.ok(globalThis.__calls <= 1 + 3, `1 initial + at most 3 fast retries within the first minute, got ${globalThis.__calls}`)
  unsub()
})

test('selectors never turn a missing or failed view into a zero or a default', async () => {
  const {gscNumbers, sentinelStatus, latestHeartbeat, view} = await import('../src/whatsapp-demo/useSeoOverview.js')
  assert.equal(gscNumbers(null), null)
  assert.equal(gscNumbers({views: {gsc_summary: {ok: false, error: 'HTTP 500'}}}), null)
  assert.equal(sentinelStatus({views: {}}).state, 'unavailable')
  assert.equal(latestHeartbeat({views: {heartbeats: {ok: false}}}), null)
  assert.equal(view({views: {}}, 'x').ok, false)
  const live = sentinelStatus({views: {scheduler: {ok: true, data: {loopRunning: true, tickMs: 30000, jobs: [], lastHeartbeat: {tickAt: new Date().toISOString()}}}}})
  assert.equal(live.state, 'live')
  const stale = sentinelStatus({views: {scheduler: {ok: true, data: {loopRunning: true, tickMs: 30000, jobs: [], lastHeartbeat: {tickAt: new Date(Date.now() - 3_600_000).toISOString()}}}}})
  assert.equal(stale.state, 'stale', 'a loop that has not ticked for an hour must not be reported live')
  const g = gscNumbers({views: {gsc_summary: {ok: true, data: {provenance: '[OBSERVED: PERSISTED GSC SNAPSHOT]', snapshot: {totalClicks: 11, totalImpressions: 28, averageCtr: 0.39285714285714285, averagePosition: 2.4285714285714284, queryRowCount: 0, startDate: '2026-09-02', endDate: '2026-09-30', capturedAt: 'c', snapshotId: 's', siteUrl: 'u'}}}}})
  assert.deepEqual([g.clicks, g.impressions, (g.ctr * 100).toFixed(2), g.position.toFixed(2)], [11, 28, '39.29', '2.43'])
})

test('provenance chips keep the worker label verbatim and never remap [INFERRED] or [ESTIMATED]', async () => {
  const fs = await import('node:fs')
  const src = fs.readFileSync('src/whatsapp-demo/components/SeoShared.jsx', 'utf8')
  const chip = src.slice(src.indexOf('export function Chip'), src.indexOf('// A value the worker could not supply'))
  assert.ok(chip.includes('{label}</span>'), 'the chip prints the label it was given')
  assert.ok(!/label\s*=\s*|label\.(replace|toLowerCase|toUpperCase|slice)/.test(chip.replace(/String\(label \|\| ''\)\.toUpperCase\(\)/g, '')), 'the displayed label is never rewritten')
  const family = src.slice(src.indexOf('function family'), src.indexOf('export function Chip'))
  assert.ok(family.includes("return 'inferred'") && !family.includes("'[INFERRED]'"), 'unknown worker labels (INFERRED, ESTIMATED, ...) fall through to a neutral style, not a remapped label')
})
