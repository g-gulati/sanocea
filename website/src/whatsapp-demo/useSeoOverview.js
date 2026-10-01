import {useSyncExternalStore} from 'react'
import {fetchSeoOverview} from './seoOverview.js'

// ONE shared SEO data contract for /demo.html. Every SEO surface (the SEO & Commerce Audit tab and the Dashboard's SEO
// sections) subscribes to this single store, so there is exactly one fetch and one 60 s poll no matter how many
// components are mounted, and two screens can never show different SEO numbers.
//
// status: 'loading' | 'ok' | 'error'. `overview` is the last successful bridge response, never a default
// or fixture. When a refresh fails the previous overview stays together with `error`, and every section prints the
// persisted-data time the worker gave it, so stale data is never shown as current.
const POLL_MS = 60_000

let state = {status: 'loading', overview: null, error: null, loadedAt: null}
const listeners = new Set()
let timer = null
let generation = 0

function set(next) {
  state = next
  listeners.forEach((l) => l())
}

// A first load that fails (for example a demo-session lease that errored) is retried a few times within seconds, so a
// visitor does not wait a full poll interval for data that is available. Bounded: it never retries forever.
const RETRY_MS = 4_000
const MAX_FAST_RETRIES = 3
let fastRetries = 0
let retryTimer = null

async function load() {
  const mine = generation
  try {
    const overview = await fetchSeoOverview()
    fastRetries = 0
    if (mine === generation) set({status: 'ok', overview, error: null, loadedAt: new Date().toISOString()})
  } catch (err) {
    if (mine !== generation) return
    set({...state, status: 'error', error: err && err.status === 503 ? 'SEO worker unavailable' : (err && err.message) || 'request failed'})
    if (!state.overview && fastRetries < MAX_FAST_RETRIES) {
      fastRetries += 1
      clearTimeout(retryTimer)
      retryTimer = setTimeout(() => { if (mine === generation) load() }, RETRY_MS)
    }
  }
}

export function subscribeSeoStore(listener) {
  listeners.add(listener)
  if (listeners.size === 1) {
    generation += 1
    fastRetries = 0
    load()
    timer = setInterval(load, POLL_MS)
  }
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) {
      clearInterval(timer)
      clearTimeout(retryTimer)
      timer = null
      generation += 1 // drop any in-flight response
    }
  }
}

const noopSubscribe = () => () => {}

// `enabled` lets a screen that only sometimes shows SEO data (the Dashboard, for non-Sanocea tenants) avoid
// subscribing, so it never triggers a fetch or leases a demo session it will not use.
export const getSeoSnapshot = () => state

export function useSeoOverview(enabled = true) {
  return useSyncExternalStore(enabled ? subscribeSeoStore : noopSubscribe, getSeoSnapshot, getSeoSnapshot)
}

// test hook: restore the pristine store
export function __resetSeoStoreForTests() {
  clearInterval(timer)
  clearTimeout(retryTimer)
  fastRetries = 0
  timer = null
  listeners.clear()
  generation += 1
  state = {status: 'loading', overview: null, error: null, loadedAt: null}
}

export const view = (overview, name) => (overview && overview.views && overview.views[name]) || {ok: false, updated_at: null, error: 'view missing from response'}
export const fmtTime = (iso) => (iso ? String(iso).replace('T', ' ').replace(/:\d\d(\.\d+)?Z$/, 'Z').replace(/\+00:00$/, 'Z') : 'no timestamp reported')

// Selectors: the only place a number is derived from the response, so every screen reads identical values. A missing
// view yields null (rendered as NOT AVAILABLE), never 0 or a placeholder.
export function gscNumbers(overview) {
  const v = view(overview, 'gsc_summary')
  if (!v.ok || !v.data || !v.data.snapshot) return null
  const s = v.data.snapshot
  return {
    clicks: s.totalClicks, impressions: s.totalImpressions, ctr: s.averageCtr, position: s.averagePosition,
    queryRows: s.queryRowCount, startDate: s.startDate, endDate: s.endDate, capturedAt: s.capturedAt,
    snapshotId: s.snapshotId, siteUrl: s.siteUrl, provenance: v.data.provenance,
  }
}

export function sentinelStatus(overview, now = Date.now()) {
  const v = view(overview, 'scheduler')
  if (!v.ok || !v.data) return {state: 'unavailable', reason: v.error || 'scheduler view not returned'}
  const tick = v.data.lastHeartbeat && v.data.lastHeartbeat.tickAt
  const fresh = Boolean(tick) && now - Date.parse(tick) < 5 * 60 * 1000
  return {state: v.data.loopRunning && fresh ? 'live' : 'stale', loopRunning: v.data.loopRunning, tickAt: tick || null, jobs: v.data.jobs || [], tickMs: v.data.tickMs}
}

export function latestHeartbeat(overview) {
  const v = view(overview, 'heartbeats')
  return v.ok && Array.isArray(v.data) && v.data.length ? v.data[0] : null
}
