// The ONE data path for every SEO section in /demo.html: GET /demo/seo/overview, a read-only bridge to the
// SEO worker's persisted state (packages/seo_bridge). It is authorized by the existing demo-session key, the same
// credential POST /demo/sessions already mints for this demo. No other login, no static snapshot, no provider call
// from the browser, and no credential is ever rendered.
//
// Session reuse: one sessionStorage record is kept for the tab, so the session is leased once and reused. Only when none
// exists, it has expired, or the server rejected it is a new one leased.
import {API_BASE, apiFetch} from './api.js'

const SESSION_KEY = 'sanocea_demo_session'
let inflightSession = null

function readStoredSession() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(SESSION_KEY) || 'null')
    if (!parsed || !parsed.apiKey || !parsed.merchantId || !parsed.expiresAt) return null
    if (new Date(parsed.expiresAt).getTime() <= Date.now() + 10_000) return null
    return parsed
  } catch {
    return null
  }
}

function storeSession(session) {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session))
  } catch {
    // storage blocked: the session still works for this page load
  }
}

function clearStoredSession() {
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {
    // nothing to clear
  }
}

async function ensureSession() {
  const stored = readStoredSession()
  if (stored) return stored
  if (!inflightSession) {
    inflightSession = apiFetch('/demo/sessions', {method: 'POST', body: {}})
      .then((raw) => {
        const session = {merchantId: raw.merchant_id, apiKey: raw.api_key, displayName: raw.display_name, expiresAt: raw.expires_at}
        storeSession(session)
        return session
      })
      .finally(() => {
        inflightSession = null
      })
  }
  return inflightSession
}

export async function fetchSeoOverview() {
  let session = await ensureSession()
  try {
    return await apiFetch('/demo/seo/overview', {apiKey: session.apiKey})
  } catch (err) {
    if (err.status !== 401 && err.status !== 403) throw err
    clearStoredSession() // expired or reaped session: lease one fresh and retry exactly once
    session = await ensureSession()
    return apiFetch('/demo/seo/overview', {apiKey: session.apiKey})
  }
}

export {API_BASE}
