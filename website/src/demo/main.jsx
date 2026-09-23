import React, {useCallback, useEffect, useMemo, useState} from 'react'
import {createRoot} from 'react-dom/client'
import './demo.css'

// The self-service demo browser calls the Sanocea Commerce OS API directly, cross-origin (this page is
// static, served from /var/www/sanocea while the API stays loopback-only behind the api.sanocea.com
// nginx reverse proxy - see infra/systemd/sanocea-api.service.example and
// /etc/nginx/sites-available/sanocea-api on the VPS). https://api.sanocea.com is the real production
// default; override with VITE_SANOCEA_API_BASE at build time for local dev against a different API host.
const API_BASE = (import.meta.env.VITE_SANOCEA_API_BASE || 'https://api.sanocea.com').replace(/\/$/, '')
const LOGO = 'https://www.sanocea.com/sanocea-wordmark.png'
const SESSION_KEY = 'sanocea_demo_session'

const TABS = [
  {id: 'overview', label: 'Overview'},
  {id: 'orders', label: 'Orders'},
  {id: 'inventory', label: 'Inventory'},
  {id: 'exceptions', label: 'Exceptions'},
  {id: 'approvals', label: 'Approvals'},
  {id: 'reconciliation', label: 'Reconciliation'},
  {id: 'channel-ops', label: 'Channel Operations'},
]

// ---- Session bootstrap -----------------------------------------------------------------------------

function loadStoredSession() {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed.apiKey || !parsed.merchantId || !parsed.expiresAt) return null
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
    // sessionStorage unavailable (private mode, blocked site data) - the session still works for this
    // page load, it just won't survive a refresh. Never block the demo over this.
  }
}

function clearStoredSession() {
  try {
    sessionStorage.removeItem(SESSION_KEY)
  } catch {}
}

async function createSession() {
  const res = await fetch(`${API_BASE}/demo/sessions`, {method: 'POST', headers: {Accept: 'application/json'}})
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail || detail
    } catch {}
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  const body = await res.json()
  return {
    sessionId: body.session_id,
    merchantId: body.merchant_id,
    displayName: body.display_name,
    apiKey: body.api_key,
    expiresAt: body.expires_at,
  }
}

// ---- Authenticated API client ----------------------------------------------------------------------

function useApi(session, onSessionInvalid) {
  return useCallback(
    async (path, {method = 'GET', body} = {}) => {
      const headers = {Accept: 'application/json', Authorization: `Bearer ${session.apiKey}`}
      if (body) headers['Content-Type'] = 'application/json'
      // cache: 'no-store' - the Command Center hit a real bug from the browser HTTP cache silently
      // serving a stale response for an identical GET (apps/command_center/app.js apiCall) - same fix.
      const res = await fetch(`${API_BASE}${path}`, {
        method,
        headers,
        cache: 'no-store',
        body: body ? JSON.stringify(body) : undefined,
      })
      if (res.status === 401 || res.status === 403) {
        onSessionInvalid()
        const err = new Error('Your demo session expired. Starting a new one...')
        err.status = res.status
        throw err
      }
      if (!res.ok) {
        let detail = res.statusText
        try {
          detail = (await res.json()).detail || detail
        } catch {}
        const err = new Error(detail)
        err.status = res.status
        throw err
      }
      if (res.status === 204) return null
      return res.json()
    },
    [session.apiKey, onSessionInvalid],
  )
}

// ---- Formatting helpers -----------------------------------------------------------------------------

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/

function formatCell(value) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string' && ISO_DATE_RE.test(value)) {
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
  }
  if (typeof value === 'object') {
    const s = JSON.stringify(value)
    return s.length > 70 ? s.slice(0, 67) + '…' : s
  }
  const s = String(value)
  return s.length > 90 ? s.slice(0, 87) + '…' : s
}

const PRIORITY_KEYS = [
  'order_number', 'sku', 'action', 'category', 'status', 'decision', 'payment_status',
  'fulfillment_status', 'financial_reconciliation_status', 'severity', 'channel', 'run_id',
  'batch_id', 'quantity', 'available', 'sellable', 'reserved', 'summary', 'message', 'reason',
  'discrepancy', 'total_amount', 'amount', 'currency', 'placed_at', 'decided_at', 'resolved_at',
  'requested_at', 'created_at', 'updated_at',
]
// Every CanonicalEntity carries these bookkeeping fields (packages/domain_contract/models.py) - real
// data, but internal plumbing a prospect evaluating the product doesn't need cluttering every table.
const HIDDEN_KEYS = new Set(['merchant_id', 'source_of_truth', 'sync', 'idempotency', 'external_refs'])

function inferColumns(rows, maxCols = 7) {
  const present = new Set()
  for (const row of rows.slice(0, 25)) {
    for (const [k, v] of Object.entries(row)) {
      if (HIDDEN_KEYS.has(k)) continue
      if (Array.isArray(v) && v.length === 0) continue
      present.add(k)
    }
  }
  const ordered = [
    ...PRIORITY_KEYS.filter((k) => present.has(k)),
    ...[...present].filter((k) => !PRIORITY_KEYS.includes(k) && k !== 'id'),
  ]
  const cols = ordered.slice(0, maxCols)
  if (cols.length === 0 && present.has('id')) cols.push('id')
  return cols
}

// ---- Generic table ----------------------------------------------------------------------------------

function DataTable({rows, loading, error, emptyLabel, renderActions}) {
  if (loading) return <div className="demo-loading">Loading…</div>
  if (error) return <div className="demo-error">{error}</div>
  if (!rows || rows.length === 0) return <div className="demo-empty">{emptyLabel || 'Nothing here right now.'}</div>

  const columns = inferColumns(rows)
  return (
    <div className="demo-table-wrap">
      <table className="demo-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c.replace(/_/g, ' ')}</th>
            ))}
            {renderActions && <th></th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={row.id || i}>
              {columns.map((c) => (
                <td key={c}>{formatCell(row[c])}</td>
              ))}
              {renderActions && <td className="demo-row-actions">{renderActions(row)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---- Screens ------------------------------------------------------------------------------------

function useListQuery(api, path, deps) {
  const [state, setState] = useState({rows: null, loading: true, error: null})
  const reload = useCallback(() => {
    setState((s) => ({...s, loading: true, error: null}))
    api(path)
      .then((rows) => setState({rows, loading: false, error: null}))
      .catch((err) => setState({rows: null, loading: false, error: err.message}))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(reload, [reload])
  return {...state, reload}
}

function OverviewScreen({api, merchantId}) {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    api(`/merchants/${merchantId}/operator/summary`).then(setSummary).catch((e) => setError(e.message))
  }, [api, merchantId])

  if (error) return <div className="demo-error">{error}</div>
  if (!summary) return <div className="demo-loading">Loading…</div>

  const tiles = [
    {label: 'Open exceptions', value: summary.open_exceptions, attention: summary.open_exceptions > 0},
    {label: 'Open approvals', value: summary.open_approvals, attention: summary.open_approvals > 0},
    {label: 'Uncertain commands', value: summary.uncertain_connector_commands, attention: summary.uncertain_connector_commands > 0},
    {label: 'Failed commands', value: summary.failed_connector_commands, attention: summary.failed_connector_commands > 0},
    {label: 'Refunds w/ discrepancy', value: summary.refunds_with_financial_discrepancy, attention: summary.refunds_with_financial_discrepancy > 0},
  ]

  return (
    <div>
      <p className="demo-screen-sub">
        This is what an operator sees the moment they open Sanocea for this tenant - everything below is
        real, live query state, not a mock.
      </p>
      <div className="demo-stats">
        {tiles.map((t) => (
          <div key={t.label} className={`demo-stat${t.attention ? ' attention' : ''}`}>
            <div className="demo-stat-value">{t.value}</div>
            <div className="demo-stat-label">{t.label}</div>
          </div>
        ))}
      </div>
      {summary.open_exceptions_by_category && Object.keys(summary.open_exceptions_by_category).length > 0 && (
        <>
          <p className="demo-screen-sub" style={{marginTop: 4}}>Open exceptions by category</p>
          <div className="demo-table-wrap">
            <table className="demo-table">
              <tbody>
                {Object.entries(summary.open_exceptions_by_category).map(([cat, count]) => (
                  <tr key={cat}>
                    <td>{cat.replace(/_/g, ' ')}</td>
                    <td>{count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

function ListScreen({api, merchantId, path, title, subtitle, emptyLabel}) {
  const {rows, loading, error} = useListQuery(api, `/merchants/${merchantId}${path}`, [api, merchantId, path])
  return (
    <div>
      {subtitle && <p className="demo-screen-sub">{subtitle}</p>}
      <DataTable rows={rows} loading={loading} error={error} emptyLabel={emptyLabel} />
    </div>
  )
}

function ApprovalsScreen({api, merchantId, notify}) {
  const {rows, loading, error, reload} = useListQuery(api, `/merchants/${merchantId}/approvals`, [api, merchantId])
  const [busyId, setBusyId] = useState(null)

  const decide = async (approval, decision) => {
    setBusyId(approval.id)
    try {
      await api(`/merchants/${merchantId}/approvals/${approval.id}/resolve`, {method: 'POST', body: {decision}})
      notify(`Approval ${decision}.`)
      reload()
    } catch (e) {
      notify(e.message, true)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <p className="demo-screen-sub">
        Every open approval Sanocea's policy engine is waiting on for this tenant. Approve or deny one -
        it runs through the exact same policy/approval boundary production traffic does.
      </p>
      <DataTable
        rows={rows}
        loading={loading}
        error={error}
        emptyLabel="No approvals pending right now."
        renderActions={(row) => (
          <>
            <button className="demo-btn demo-btn-approve" disabled={busyId === row.id} onClick={() => decide(row, 'approved')}>
              Approve
            </button>
            <button className="demo-btn demo-btn-deny" disabled={busyId === row.id} onClick={() => decide(row, 'denied')}>
              Deny
            </button>
          </>
        )}
      />
    </div>
  )
}

// ---- App shell ------------------------------------------------------------------------------------

function useCountdown(expiresAt) {
  const [label, setLabel] = useState('')
  useEffect(() => {
    const tick = () => {
      const ms = new Date(expiresAt).getTime() - Date.now()
      if (ms <= 0) {
        setLabel('refreshing…')
        return
      }
      const mins = Math.max(1, Math.round(ms / 60000))
      setLabel(`resets in ~${mins}m`)
    }
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [expiresAt])
  return label
}

function Toast({toast}) {
  if (!toast) return null
  return <div className={`demo-toast${toast.error ? ' error' : ''}`}>{toast.message}</div>
}

function DemoApp({session, onSessionInvalid}) {
  const [tab, setTab] = useState('overview')
  const [toast, setToast] = useState(null)
  const api = useApi(session, onSessionInvalid)
  const countdown = useCountdown(session.expiresAt)

  const notify = useCallback((message, error = false) => {
    setToast({message, error})
    const id = setTimeout(() => setToast(null), 4000)
    return () => clearTimeout(id)
  }, [])

  const screen = useMemo(() => {
    const props = {api, merchantId: session.merchantId}
    switch (tab) {
      case 'overview':
        return <OverviewScreen {...props} />
      case 'orders':
        return <ListScreen {...props} path="/orders" emptyLabel="No orders yet in this demo tenant." />
      case 'inventory':
        return <ListScreen {...props} path="/inventory" emptyLabel="No inventory records." />
      case 'exceptions':
        return (
          <ListScreen
            {...props}
            path="/exceptions"
            subtitle="Operational exceptions Sanocea's engines flagged automatically for this tenant."
            emptyLabel="No open exceptions - this tenant is clean right now."
          />
        )
      case 'approvals':
        return <ApprovalsScreen {...props} notify={notify} />
      case 'reconciliation':
        return (
          <ListScreen
            {...props}
            path="/finance/reconciliations"
            subtitle="Settlement vs. order-level reconciliation results."
            emptyLabel="No reconciliation runs yet."
          />
        )
      case 'channel-ops':
        return (
          <ListScreen
            {...props}
            path="/channel-operations"
            subtitle="Marketplace/storefront sync and publication activity across every connected demo channel."
            emptyLabel="No channel operations recorded yet."
          />
        )
      default:
        return null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, api, session.merchantId, notify])

  return (
    <div className="demo-shell">
      <div className="demo-header">
        <div className="demo-header-brand">
          <img src={LOGO} alt="Sanocea" />
          <span>Commerce OS — Live Demo</span>
        </div>
        <div className="demo-header-tenant">{session.displayName}</div>
        <div className="demo-header-right">
          <span>{countdown}</span>
        </div>
      </div>
      <div className="demo-disclosure">
        You're exploring an isolated, real Sanocea Commerce OS tenant — not a mockup. Actions here are
        real but sandboxed to this session, and this tenant resets automatically for the next visitor.
      </div>
      <div className="demo-tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`demo-tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="demo-main">
        <h2 className="demo-screen-title">{TABS.find((t) => t.id === tab)?.label}</h2>
        {screen}
      </div>
      <Toast toast={toast} />
    </div>
  )
}

function BootstrapGate() {
  const [session, setSession] = useState(() => loadStoredSession())
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (session) return
    let cancelled = false
    setError(null)
    createSession()
      .then((s) => {
        if (cancelled) return
        storeSession(s)
        setSession(s)
      })
      .catch((e) => {
        if (cancelled) return
        if (e.status === 503) setError("Every demo environment is in use right now. Please try again in a couple of minutes.")
        else if (e.status === 429) setError('Too many people are starting demos at once — please wait a few seconds and try again.')
        else setError(e.message || 'Could not start a demo session.')
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, attempt])

  const onSessionInvalid = useCallback(() => {
    clearStoredSession()
    setSession(null)
  }, [])

  if (session) return <DemoApp session={session} onSessionInvalid={onSessionInvalid} />

  return (
    <div className="demo-shell">
      <div className="demo-center">
        <div className="demo-card">
          <img src={LOGO} alt="Sanocea" style={{height: 26, marginBottom: 12}} />
          {error ? (
            <>
              <h1>Hold on a moment</h1>
              <p>{error}</p>
              <button className="demo-btn" onClick={() => setAttempt((a) => a + 1)}>
                Try again
              </button>
            </>
          ) : (
            <>
              <div className="demo-spinner" />
              <h1>Spinning up your demo…</h1>
              <p>Resetting a live Sanocea Commerce OS tenant just for this session.</p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BootstrapGate />
  </React.StrictMode>,
)
