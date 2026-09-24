import React, {useCallback, useEffect, useState} from 'react'
import {apiFetch} from './api.js'
import './walkthrough.css'

const LOGO = 'https://www.sanocea.com/sanocea-wordmark.png'

function humanize(s) {
  if (!s) return ''
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function severityIcon(sev) {
  if (sev === 'critical') return '🔴'
  if (sev === 'warning') return '🟠'
  return '🟡'
}

// Merges real exceptions + real approvals into one clickable list of "findings" - an exception whose
// object_id/id is referenced by an approval's workflow_id is ONE finding (detection + prepared action
// together); anything left over stands on its own. No synthetic data - every finding here is a real row
// this tenant's sandbox actually seeded (packages/prospect_demo/scenarios.py).
function buildFindings(exceptions, approvals) {
  const usedApprovalIds = new Set()
  const findings = exceptions.map((exc) => {
    const approval = approvals.find((a) => a.workflow_id === exc.id)
    if (approval) usedApprovalIds.add(approval.id)
    return {
      key: exc.id,
      icon: severityIcon(exc.severity),
      title: humanize(exc.category),
      summary: exc.message,
      exception: exc,
      approval,
    }
  })
  approvals.filter((a) => !usedApprovalIds.has(a.id)).forEach((a) => {
    findings.push({
      key: a.id,
      icon: '🟡',
      title: humanize(a.action),
      summary: a.summary || humanize(a.action),
      exception: null,
      approval: a,
    })
  })
  return findings
}

function EvidenceGrid({finding}) {
  const evidence = finding.approval?.evidence || {}
  const rows = Object.entries(evidence).filter(([, v]) => v !== null && v !== undefined && v !== '')
  const extra = []
  if (finding.exception?.object_id) extra.push(['object_id', finding.exception.object_id])
  if (finding.exception?.remediation_options?.length) extra.push(['options', finding.exception.remediation_options.join(', ')])
  const all = [...rows, ...extra].slice(0, 6)
  if (all.length === 0) return null
  return (
    <div className="wt-evidence-grid">
      {all.map(([k, v]) => (
        <div key={k} className="wt-evidence-item">
          <div className="wt-evidence-label">{k.replace(/_/g, ' ')}</div>
          <div className="wt-evidence-value">{String(v)}</div>
        </div>
      ))}
    </div>
  )
}

export default function Walkthrough({onGoToChat}) {
  const [phase, setPhase] = useState('loading') // loading | browsing | detail | resolved | payoff
  const [session, setSession] = useState(null) // {merchantId, apiKey, displayName}
  const [findings, setFindings] = useState([])
  const [selected, setSelected] = useState(null)
  const [resolving, setResolving] = useState(false)
  const [auditRecord, setAuditRecord] = useState(null)
  const [error, setError] = useState(null)

  const loadFindings = useCallback(async (merchantId, apiKey) => {
    const [exceptions, approvals] = await Promise.all([
      apiFetch(`/merchants/${merchantId}/exceptions`, {apiKey}),
      apiFetch(`/merchants/${merchantId}/approvals`, {apiKey}),
    ])
    setFindings(buildFindings(exceptions, approvals))
  }, [])

  useEffect(() => {
    let cancelled = false
    async function boot() {
      try {
        const s = await apiFetch('/demo/sessions', {method: 'POST', body: {}})
        if (cancelled) return
        setSession({merchantId: s.merchant_id, apiKey: s.api_key, displayName: s.display_name, expiresAt: s.expires_at})
        await loadFindings(s.merchant_id, s.api_key)
        if (cancelled) return
        setPhase('browsing')
      } catch (err) {
        if (cancelled) return
        setError(err.status === 503 ? 'Every demo environment is in use right now - please try again shortly.' : err.message)
      }
    }
    boot()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selectFinding = (f) => {
    setSelected(f)
    setPhase('detail')
  }

  const backToBrowsing = () => {
    setSelected(null)
    setPhase('browsing')
  }

  const resolveSelected = async () => {
    if (!selected?.approval) return
    setResolving(true)
    try {
      await apiFetch(`/merchants/${session.merchantId}/approvals/${selected.approval.id}/resolve`, {
        method: 'POST', apiKey: session.apiKey, body: {decision: 'approved'},
      })
      const audit = await apiFetch(`/merchants/${session.merchantId}/audit`, {apiKey: session.apiKey})
      const record = audit.find((a) => a.object_id === selected.approval.id && a.action === 'approval_resolved')
      setAuditRecord(record || null)
      setFindings((fs) => fs.map((f) => (f.key === selected.key ? {...f, resolvedNow: true} : f)))
      setPhase('resolved')
    } catch (err) {
      setError(err.message)
    } finally {
      setResolving(false)
    }
  }

  if (phase === 'loading') {
    return (
      <div className="wt-shell">
        <div className="wt-main">
          <div className="wt-loading">{error || 'Connecting to a live sandboxed operation…'}</div>
        </div>
      </div>
    )
  }

  if (phase === 'payoff') {
    return <PayoffPhase session={session} findings={findings} onGoToChat={onGoToChat} onBack={() => setPhase('browsing')} />
  }

  return (
    <div className="wt-shell">
      <div className="wt-header">
        <img src={LOGO} alt="Sanocea" />
        <span className="wt-header-tag">{session?.displayName}</span>
      </div>
      <div className="wt-main">
        {phase === 'browsing' && (
          <>
            <h1 className="wt-h1">Today's operation</h1>
            <p className="wt-sub">
              Real findings from a live, sandboxed Sanocea tenant. Click one to see the evidence and what
              Sanocea has already prepared.
            </p>
            {findings.length === 0 ? (
              <p className="wt-sub">This tenant is clean right now - nothing needs attention.</p>
            ) : (
              <div className="wt-findings">
                {findings.map((f) => (
                  <button key={f.key} className={`wt-card${f.resolvedNow ? ' resolved' : ''}`} onClick={() => selectFinding(f)}>
                    <span>{f.icon}</span>
                    <span>
                      <span className="wt-card-title">{f.title}</span>
                      <span className="wt-card-text">{f.summary}</span>
                    </span>
                    {f.resolvedNow ? <span className="wt-card-status">✓ resolved</span> : <span className="wt-card-arrow">›</span>}
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {(phase === 'detail' || phase === 'resolved') && selected && (
          <>
            <button className="wt-back" onClick={backToBrowsing}>← Back to today's operation</button>

            {phase === 'resolved' && auditRecord && (
              <div className="wt-audit-card">
                <h2>✓ Action executed — audit record created</h2>
                <div className="wt-audit-row"><span>Record</span><span>{auditRecord.id}</span></div>
                <div className="wt-audit-row"><span>Result</span><span>{auditRecord.result}</span></div>
                <div className="wt-audit-row"><span>Actor</span><span>{auditRecord.actor}</span></div>
                <div className="wt-audit-row"><span>Time</span><span>{new Date(auditRecord.timestamp).toLocaleTimeString()}</span></div>
              </div>
            )}

            <div className="wt-detail-card">
              <h2>{selected.icon} {selected.title}</h2>
              <p>{selected.exception?.message || selected.approval?.summary}</p>
              <EvidenceGrid finding={selected} />
            </div>

            {selected.approval && phase === 'detail' && (
              <div className="wt-prepared">
                <div className="wt-prepared-label">Sanocea has prepared</div>
                <p>{selected.approval.recommendation || 'A decision is ready for your sign-off.'}</p>
              </div>
            )}

            {phase === 'detail' && selected.approval && selected.approval.status === 'pending' && (
              <div className="wt-btn-row">
                <button className="wt-btn" disabled={resolving} onClick={resolveSelected}>
                  {resolving ? 'Executing…' : 'Approve & execute'}
                </button>
                <button className="wt-btn wt-btn-secondary" onClick={backToBrowsing}>Not now</button>
              </div>
            )}
            {phase === 'detail' && !selected.approval && (
              <p className="wt-sub">Sanocea has flagged this and is tracking it - no action is pending yet.</p>
            )}
            {phase === 'resolved' && (
              <button className="wt-btn" onClick={backToBrowsing}>Continue exploring →</button>
            )}
          </>
        )}
      </div>

      {(phase === 'browsing' || phase === 'detail') && (
        <div className="wt-payoff-bar">
          <span>You don't need to sit in this dashboard.</span>
          <button className="wt-payoff-link" onClick={() => setPhase('payoff')}>See it in WhatsApp →</button>
        </div>
      )}
    </div>
  )
}

function PayoffPhase({session, findings, onGoToChat, onBack}) {
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  // Real findings from the SAME tenant the visitor was just looking at - not a generic placeholder that
  // might not even apply to this business (e.g. showing "Blinkit" for a tenant with no quick-commerce
  // channel at all would be exactly the kind of overclaim this demo is built to avoid).
  const openCount = findings.filter((f) => !f.resolvedNow).length
  const topLines = findings.filter((f) => !f.resolvedNow).slice(0, 3).map((f) => `${f.icon} ${f.title} — ${f.summary}`.slice(0, 90))

  const submit = async (e) => {
    e.preventDefault()
    if (!phone.trim()) {
      setError('Enter a WhatsApp number to continue.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const attached = await apiFetch(`/merchants/${session.merchantId}/demo/attach-whatsapp`, {
        method: 'POST', apiKey: session.apiKey, body: {whatsapp_number: phone.trim()},
      })
      onGoToChat({...session, expiresAt: attached.expires_at || session.expiresAt})
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="wt-shell">
      <div className="wt-header">
        <img src={LOGO} alt="Sanocea" />
        <span className="wt-header-tag">{session?.displayName}</span>
      </div>
      <div className="wt-main wt-payoff-stage">
        <h1 className="wt-h1">Sanocea brings this to you in WhatsApp.</h1>
        <p className="wt-sub">Instead of checking a dashboard, the same operational intelligence arrives as a conversation.</p>
        <div className="wt-wa-preview">
          <div className="wt-wa-bubble">
            Good morning. I found {openCount} thing{openCount === 1 ? '' : 's'} that need{openCount === 1 ? 's' : ''} your attention.
          </div>
          {topLines.length > 0 && <div className="wt-wa-bubble">{topLines.join('\n')}</div>}
        </div>
        <p className="wt-sub">Ask questions. Review the evidence. Approve actions. Resolve exceptions - all from here.</p>
        <form onSubmit={submit} className="wt-phone-row">
          <input
            className="wt-phone-input"
            type="tel"
            placeholder="+91 98765 43210"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={busy}
            autoFocus
          />
          <button className="wt-btn" type="submit" disabled={busy}>{busy ? '…' : 'Start →'}</button>
        </form>
        {error && <p className="wt-error">{error}</p>}
        <button className="wt-back" style={{marginTop: 20}} onClick={onBack}>← Back to today's operation</button>
      </div>
    </div>
  )
}
